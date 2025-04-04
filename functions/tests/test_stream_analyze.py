import sys
import json
import logging
import traceback
from firebase_admin import firestore
import firebase_admin
import os
from dotenv import load_dotenv
import django
import datetime

os.environ["FUNCTIONS_EMULATOR"] = "True"

# Add the parent directory to the Python path
functions_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(functions_dir)

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'factchecker.settings')

# Initialize Django
django.setup()

# Now import the helper function - without the 'functions.' prefix
from helpers.stream_analyze import stream_analyze_helper

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for more verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('stream_analyze.log')
    ]
)
logger = logging.getLogger(__name__)

# Set emulator flag, this tells our code that we're running it locally, regardless of
# whether we're using it or not


# Initialize Firebase app if not already initialized
try:
    firebase_admin.get_app()
    logger.info("Firebase app already initialized")
except ValueError:
    # turn on emulator if needed
    if os.getenv('FUNCTIONS_EMULATOR'):
        logger.info("Using Firestore emulator")
        os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed
    logger.info("Initializing Firebase app")
    firebase_admin.initialize_app()

def local_stream_analyze(request_json):
    """
    Local version of the stream_analyze function that mimics the Cloud Function.
    
    Args:
        request_json (dict): The request data as a dictionary
        
    Returns:
        generator: A generator that yields analysis results as they come in
    """
    logger.info("Starting local_stream_analyze")
    logger.debug(f"Request data: {json.dumps(request_json, indent=2)}")
    
    # Initialize db
    db = firestore.client()
    logger.debug("Firestore client initialized")
    
    # Validate request data
    if not request_json:
        logger.error("No JSON data provided")
        yield json.dumps({"error": "No JSON data provided", "type": "error"}) + "\n"
        return
    
    # Get the required parameters
    dataset_ids = request_json.get('dataset_ids', [])
    query = request_json.get('query', '')
    
    # Optional file path parameter
    file_path = request_json.get('file_path', None)
    
    # Validate required parameters
    if not dataset_ids:
        logger.error("No dataset IDs provided")
        yield json.dumps({"error": "Dataset IDs required", "type": "error"}) + "\n"
        return
    
    if not query:
        logger.error("No query provided")
        yield json.dumps({"error": "Query is required", "type": "error"}) + "\n"
        return
    
    logger.info(f"Streaming analysis parameters: dataset_ids={dataset_ids}, query='{query}'")
    
    # Initialize a variable to store the final result
    final_result = None
    
    # Process the streaming analysis
    try:
        logger.info("Starting stream_analyze_helper")
        for chunk in stream_analyze_helper(
            dataset_ids=dataset_ids,
            query=query,
            file_path=file_path
        ):
            # Skip empty chunks
            if not chunk:
                logger.debug("Received empty chunk, skipping")
                continue
                
            # Try to parse the chunk as JSON
            try:
                chunk_data = json.loads(chunk.strip())
                logger.debug(f"Received chunk type: {chunk_data.get('type')}")
                
                if chunk_data.get('type') == 'complete':
                    logger.info("Received complete message")
                    final_result = chunk_data.get('data', {})
                    logger.debug(f"Final result data: {json.dumps(final_result, indent=2)}")
            except json.JSONDecodeError:
                # If it's not JSON, it might be a raw string message
                logger.warning(f"Received non-JSON chunk: {chunk[:100]}...")
                continue
            except Exception as e:
                logger.error(f"Error processing chunk: {str(e)}")
                logger.error(traceback.format_exc())
                continue
            
            # Yield the chunk
            yield chunk
            
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                logger.info("Storing results in Firestore")
                # Create a document with the analysis results
                analysis_ref = db.collection('analyses').document()
                
                # Add the analysis data with web search results
                analysis_ref.set({
                    'dataset_ids': dataset_ids,
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'results': final_result,
                    'has_web_search_results': 'web_search_results' in final_result
                })
                
                logger.info(f"Stored analysis results in Firestore with ID: {analysis_ref.id}")
            except Exception as e:
                logger.error(f"Error storing analysis results in Firestore: {e}")
                logger.error(traceback.format_exc())
                
    except Exception as e:
        error_message = f"Error processing streaming analysis: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        yield json.dumps({
            "type": "error",
            "data": {"message": error_message}
        }) + "\n"

def run_local_analysis(parallel=False):
    """
    Example of how to use the local_stream_analyze function
    
    Args:
        parallel: Boolean flag to control whether to run web searches in parallel (default: True)
    """
    logger.info("Starting run_local_analysis")
    
    # Example request data
    request_data = {
        "dataset_ids": ['0d6a490f-84b4-4bea-9c8f-b61b69447bf2', '0c6e9a3c-e265-464a-8eaf-38873f9d496a', 'cf44a5d2-bd13-4f7f-90bd-5a72fdd61e5b'],#, '3c8dc58d-5e8d-4f1e-b049-bd70f8f93cb9', '069446d9-10b3-4e25-8e63-ef8c977c4489', 'a74bb449-a747-4fe3-bb89-22a2c5d832e0', 'a3d65a40-4e51-42b4-95f2-84554e92beb8', 'bde2905d-98e0-40b5-8b29-bc9785f7ea7d', 'd7bff3c7-b71f-4644-8676-8e6b1f3e180f', '440e012f-1b5a-45fe-85c0-b8c5e7542ca0', '577dfef0-bd57-4d86-9271-3fce56fa50a4', 'be5a3038-769f-4c59-bbf1-14feca3578e1', 'aa00ecc1-667d-4407-a42c-880497c425e8', '4705e015-b09e-414d-a17d-2709be6d80b3', '3c4c5afd-0f25-40b1-b20d-efc9760e38b4'],  # Replace with actual dataset ID
        "query": "Orange Grove emissions factors",
        "parallel": parallel  # Add the parallel flag to the request data
    }
    
    logger.info(f"Running analysis with dataset_id: {request_data['dataset_ids']}")
    logger.info(f"Query: {request_data['query']}")
    logger.info(f"Parallel mode: {parallel}")
    
    # Tracking variables
    message_count = 0
    status_messages = []
    extracted_data = None
    formatted_data = None
    findings = None
    web_search_results = None
    web_search_summary = None
    analysis_results = []
    complete_data = None
    
    logger.info("Starting to process streaming response...")
    
    try:
        # Process each chunk from the generator
        for chunk in local_stream_analyze(request_data):
            try:
                # Skip empty chunks
                if not chunk:
                    logger.debug("Received empty chunk, skipping")
                    continue
                    
                # Parse the chunk as JSON
                data = json.loads(chunk.strip())
                message_count += 1
                
                # Process based on type
                msg_type = data.get('type')
                logger.debug(f"Processing message type: {msg_type}")
                
                if msg_type == 'status':
                    status_messages.append(data.get('message', ''))
                    logger.info(f"Status: {data.get('message', '')}")
                    
                elif msg_type == 'error':
                    logger.error(f"Error: {data.get('message', '')}")
                    if 'details' in data:
                        logger.error(f"Details: {data.get('details', '')}")
                    
                elif msg_type == 'web_search_results':
                    web_search_results = data.get('data')
                    logger.info(f"Received web search results with {len(web_search_results.get('results', []))} items")
                    logger.debug(f"Web search results: {json.dumps(web_search_results, indent=2)}")
                    
                elif msg_type == 'web_search_summary':
                    web_search_summary = data.get('data')
                    logger.info(f"Web search summary: {web_search_summary.get('summary', 'No summary available')}")
                    
                elif msg_type == 'analysis_result':
                    dataset_info = data.get('data', {}).get('dataset_info', {})
                    logger.info(f"Dataset: {dataset_info.get('title')}")
                    logger.info(f"Rows: {dataset_info.get('rows')}, Columns: {dataset_info.get('columns')}")
                    analysis_results.append(data.get('data'))
                    logger.debug(f"Analysis result: {json.dumps(data.get('data'), indent=2)}")
                    
                elif msg_type == 'analysis':
                    analysis = data.get('data', 'No analysis available')
                    logger.info(f"Analysis: {analysis}")
                    
                elif msg_type == 'formatted_data':
                    formatted_data = data.get('data')
                    logger.info("Received formatted data")
                    # Save formatted data to a JSON file
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_dir = "test_runs"
                        os.makedirs(output_dir, exist_ok=True)
                        
                        # Create a filename based on the query
                        query_slug = '_'.join(request_data.get('query', 'query').lower().split()[:4])
                        filename = f"{output_dir}/formatted_data_{query_slug}_{timestamp}.json"
                        
                        # Save the data to the file
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(formatted_data, f, indent=2, ensure_ascii=False)
                        logger.info(f"Saved formatted data to {filename}")
                    except Exception as e:
                        logger.error(f"Error saving formatted data: {e}")
                        logger.error(traceback.format_exc())
                    
                elif msg_type == 'findings':
                    findings = data.get('data')
                    logger.info("Received findings summary")
                    # Save findings to a JSON file
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_dir = "test_runs"
                        os.makedirs(output_dir, exist_ok=True)
                        
                        # Create a filename based on the query
                        query_slug = '_'.join(request_data.get('query', 'query').lower().split()[:4])
                        filename = f"{output_dir}/findings_{query_slug}_{timestamp}.json"
                        
                        # Save the data to the file
                        with open(filename, 'w', encoding='utf-8') as f:
                            json.dump(findings, f, indent=2, ensure_ascii=False)
                        logger.info(f"Saved findings to {filename}")
                    except Exception as e:
                        logger.error(f"Error saving findings: {e}")
                        logger.error(traceback.format_exc())
                    
                elif msg_type == 'complete':
                    complete_data = data.get('data')
                    logger.info(f"Analysis complete in {data.get('message', '')}")
                    logger.debug(f"Complete data: {json.dumps(complete_data, indent=2)}")
                    break  # Exit the loop when we receive the complete message
                    
                else:
                    logger.warning(f"Unknown message type: {msg_type}")
                    logger.debug(f"Full message: {json.dumps(data, indent=2)}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing message: {chunk[:100]}...")
                logger.error(f"Error details: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                logger.error(f"Message content: {chunk[:100]}...")
                logger.error(traceback.format_exc())
        
        # Print summary
        logger.info(f"\nReceived {message_count} messages in total")
        logger.info("\nAnalysis Summary:")
        logger.info(f"- Status messages: {len(status_messages)}")
        logger.info(f"- Has web search results: {web_search_results is not None}")
        logger.info(f"- Has web search summary: {web_search_summary is not None}")
        logger.info(f"- Analysis results count: {len(analysis_results)}")
        logger.info(f"- Has formatted data: {formatted_data is not None}")
        logger.info(f"- Has findings: {findings is not None}")
        logger.info(f"- Complete data received: {complete_data is not None}")
        
    except KeyboardInterrupt:
        logger.info("\nAnalysis interrupted by user")
    except Exception as e:
        logger.error(f"\nError during analysis: {str(e)}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Run the local analysis function when script is executed directly
    # You can choose to run in parallel or sequential mode
    run_local_analysis(parallel=False)  # Set to False for sequential processing 