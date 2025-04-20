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

def run_local_analysis(parallel):
    """
    Example of how to use the local_stream_analyze function
    
    Args:
        parallel: Boolean flag to control whether to run web searches in parallel (default: True)
    """
    logger.info("Starting run_local_analysis")
    
    # Example request data
    request_data = {
        "dataset_ids": [
            "2746fc68-190d-407f-bb86-44c5f42bb6d1",
            "19bb999c-6208-4692-970a-131326d67be3",
            "5f961a68-66f9-4e8d-b3ed-b41cc8e1f9be",
            "7dea0c2b-b84e-48b2-95ad-0867fb14cd89",
            "41cc4071-57bd-452e-af0d-03174f7ade5c",
            "d5fa9b77-6b88-49e3-ba96-445254073d6f",
            "960213c2-effc-4da7-8ccd-375327f6d1e6",
            "e3f73ef6-ca46-4784-9161-c128109163b1",
            "28e0f154-e68b-406a-8871-f9ad62df11b2",
            "01f25998-f9c6-4508-a890-ef53ed596419",
            "044f8ebb-0c54-4f8d-866c-2eb7071817dc",
            "be5795c2-0737-4cad-915a-9a2783d78788",
            "6df5dd5a-f5e5-422a-a069-6d801f3a7208",
            "62915ff9-ca87-4f85-b9e6-6c1793fc4054",
            "bb97ac7a-5cee-4fe5-b0f8-598e46f5d735",
            "5a002f72-8ddb-4bd4-86e2-cdd991b9ad2d",
            "e61357f3-7d69-4067-8b1d-721beafc57ec",
            "9f691d06-ca23-43f7-acc6-90ec2db19dc9",
            "85e95821-1460-4de3-8665-0ade178bb16e",
            "fd699649-d276-43c8-829a-cb4a892cf776"
        ],
        "query": "Tell me about underground storage tanks",
        "parallel": parallel  # Add the parallel flag to the request data
    }
    
    logger.info(f"Running analysis with dataset_id: {request_data['dataset_ids']}")
    logger.info(f"Query: {request_data['query']}")
    logger.info(f"Parallel mode: {parallel}")
    
    # Tracking variables
    all_messages = [] # List to store all received messages
    message_count = 0
    notable_messages = [] # List to store only notable messages for saving
    notable_types = {
        'extracted_data', 
        'web_search_results', 
        'web_search_summary', 
        'analysis_result', 
        'analysis', # Add analysis text if desired
        'formatted_data', 
        'findings', 
        'complete', 
        'error'
    }
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
                all_messages.append(data) # Add the raw message data to the list
                
                # Process based on type
                msg_type = data.get('type')
                logger.debug(f"Processing message type: {msg_type}")
                
                # Add to notable messages if the type matches
                if msg_type in notable_types:
                    notable_messages.append(data)
                
                if msg_type == 'status':
                    status_messages.append(data.get('message', ''))
                    logger.info(f"Status: {data.get('message', '')}")
                    
                elif msg_type == 'error':
                    logger.error(f"Error: {data.get('message', '')}")
                    if 'details' in data:
                        logger.error(f"Details: {data.get('details', '')}")
                    
                elif msg_type == 'extracted_data':
                    extracted_data = data.get('data')
                    logger.info(f"Received extracted data for dataset: {extracted_data.get('dataset_title', 'Unknown')}")
                    # Removed individual file saving
                    
                elif msg_type == 'web_search_results':
                    web_search_results = data.get('data')
                    logger.info(f"Received web search results with {len(web_search_results.get('results', []))} items")
                    # Removed individual file saving
                    
                elif msg_type == 'web_search_summary':
                    web_search_summary = data.get('data')
                    summary_text = web_search_summary.get('summary', 'No summary available')
                    logger.info(f"Web search summary: {summary_text[:100]}...")
                    # Removed individual file saving
                    
                elif msg_type == 'analysis_result':
                    dataset_info = data.get('data', {}).get('dataset_info', {})
                    logger.info(f"Dataset: {dataset_info.get('title')}")
                    logger.info(f"Rows: {dataset_info.get('rows')}, Columns: {dataset_info.get('columns')}")
                    analysis_results.append(data.get('data'))
                    logger.debug(f"Analysis result:\n{json.dumps(data.get('data'), indent=2)}")
                    
                elif msg_type == 'analysis':
                    analysis = data.get('data', 'No analysis available')
                    logger.info(f"Analysis: {analysis}")
                    
                elif msg_type == 'formatted_data':
                    formatted_data = data.get('data')
                    logger.info("Received formatted data")
                    # Removed individual file saving
                    
                elif msg_type == 'findings':
                    findings = data.get('data')
                    logger.info("Received findings summary")
                    # Removed individual file saving
                    
                elif msg_type == 'dataset_status':
                    dataset_id = data.get('dataset_id')
                    status = data.get('status')
                    progress = data.get('progress')
                    message = data.get('message', '')
                    logger.info(f"Dataset Status: ID={dataset_id}, Status={status}, Progress={progress}, Message='{message}'")
                    logger.debug(f"Full dataset_status message:\n{json.dumps(data, indent=2)}")
                    
                elif msg_type == 'complete':
                    complete_data = data.get('data')
                    logger.info(f"Analysis complete in {data.get('message', '')}")
                    logger.debug(f"Complete data:\n{json.dumps(complete_data, indent=2)}")
                    break  # Exit the loop when we receive the complete message
                    
                else:
                    logger.warning(f"Unknown message type: {msg_type}")
                    logger.debug(f"Full unknown message:\n{json.dumps(data, indent=2)}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing non-JSON message chunk: {chunk[:150]}...")
                logger.error(f"JSONDecodeError details: {str(e)}")
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                logger.error(f"Message content: {chunk[:100]}...")
                logger.error(traceback.format_exc())
        
        # Save all collected messages to a single file
        if notable_messages:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = "test_runs"
                os.makedirs(output_dir, exist_ok=True)
                query_slug = '_'.join(request_data.get('query', 'query').lower().split()[:4])
                filename = f"{output_dir}/consolidated_run_{query_slug}_{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(notable_messages, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved {len(notable_messages)} notable messages to {filename}")
            except Exception as e:
                logger.error(f"Error saving consolidated messages: {e}")
        
        # Print summary
        logger.info(f"\nReceived {message_count} messages in total")
        logger.info("\nAnalysis Summary:")
        logger.info(f"- Status messages: {len(status_messages)}")
        logger.info(f"- Web search results received: {web_search_results is not None}")
        logger.info(f"- Web search summary received: {web_search_summary is not None}")
        logger.info(f"- Analysis results count: {len(analysis_results)}")
        logger.info(f"- Extracted data received: {extracted_data is not None}")
        logger.info(f"- Formatted data received: {formatted_data is not None}")
        logger.info(f"- Findings received: {findings is not None}")
        logger.info(f"- Complete data received: {complete_data is not None}")
        logger.info(f"- Notable messages saved to consolidated file.")
        
    except KeyboardInterrupt:
        logger.info("\nAnalysis interrupted by user")
    except Exception as e:
        logger.error(f"\nError during analysis: {str(e)}")
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Run the local analysis function when script is executed directly
    # You can choose to run in parallel or sequential mode
    run_local_analysis(parallel=True)  # Set to False for sequential processing 