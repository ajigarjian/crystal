import sys
import json
import logging
import traceback
from firebase_admin import firestore
import firebase_admin
import os
from dotenv import load_dotenv
import django

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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set emulator flag, this tells our code that we're running it locally, regardless of
# whether we're using it or not
os.environ["FUNCTIONS_EMULATOR"] = "True"

# Initialize Firebase app if not already initialized
try:
    firebase_admin.get_app()
except ValueError:
    # turn on emulator if needed
    if os.getenv('FUNCTIONS_EMULATOR'):
        os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed
    firebase_admin.initialize_app()

def local_stream_analyze(request_json):
    """
    Local version of the stream_analyze function that mimics the Cloud Function.
    
    Args:
        request_json (dict): The request data as a dictionary
        
    Returns:
        generator: A generator that yields analysis results as they come in
    """
    # Initialize db
    db = firestore.client()
    
    # Validate request data
    if not request_json:
        yield json.dumps({"error": "No JSON data provided", "type": "error"}) + "\n"
        return
    
    # Get the required parameters
    dataset_id = request_json.get('dataset_id', '')
    query = request_json.get('query', '')
    
    # Optional file path parameter
    file_path = request_json.get('file_path', None)
    
    # Validate required parameters
    if not dataset_id:
        yield json.dumps({"error": "Dataset ID is required", "type": "error"}) + "\n"
        return
    
    if not query:
        yield json.dumps({"error": "Query is required", "type": "error"}) + "\n"
        return
    
    logger.info(f"Streaming analysis parameters: dataset_id={dataset_id}, query='{query}'")
    
    # Initialize a variable to store the final result
    final_result = None
    
    # Hardcode this
    dataset_ids = []
    dataset_ids.append(dataset_id)

    # Process the streaming analysis
    try:
        for chunk in stream_analyze_helper(
            dataset_ids=dataset_ids,
            query=query,
            file_path=file_path
        ):
            # If this is a JSON object and it's the 'complete' type, store it as the final result
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
            except:
                pass
            
            # Yield the chunk
            yield chunk  # Already has newline from helper function
            # Print the chunk
            print(chunk)
            
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Create a document with the analysis results
                analysis_ref = db.collection('analyses').document()
                
                # Add the analysis data
                analysis_ref.set({
                    'dataset_id': dataset_id,
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'results': final_result
                })
                
                logger.info(f"Stored analysis results in Firestore with ID: {analysis_ref.id}")
            except Exception as e:
                logger.error(f"Error storing analysis results in Firestore: {e}")
                
    except Exception as e:
        error_message = f"Error processing streaming analysis: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        yield json.dumps({
            "type": "error",
            "data": {"message": error_message}
        }) + "\n"

def run_local_analysis():
    """
    Example of how to use the local_stream_analyze function
    """
    # Example request data
    request_data = {
        "dataset_id": "f5899dc6-c712-43ac-a368-f7f4feda20aa",  # Replace with an actual dataset ID you want to test
        "query": "soybean emissions factors",
        "file_path": None  # Set to a specific path if needed, otherwise will use default locations
    }
    
    print(f"Running analysis with dataset_id: {request_data['dataset_id']}")
    print(f"Query: {request_data['query']}")
    
    # Process each chunk from the generator
    for chunk in local_stream_analyze(request_data):
        try:
            # Parse the chunk as JSON
            data = json.loads(chunk.strip())
            event_type = data.get("type")
            
            if event_type == "status":
                # Status update
                print(f"Status: {data.get('message', '')}")
                
            elif event_type == "analysis_result":
                # Dataset info
                dataset_info = data.get("data", {}).get("dataset_info", {})
                print(f"Dataset: {dataset_info.get('title')}")
                print(f"Rows: {dataset_info.get('rows')}, Columns: {dataset_info.get('columns')}")
                
            elif event_type == "analysis":
                # Analysis content
                analysis = data.get("data", "No analysis available")
                print("\nAnalysis:")
                print(analysis)
                
            elif event_type == "complete":
                # Final results
                result = data.get("data", {})
                print("\nAnalysis complete!")
                print(f"Execution time: {result.get('execution_time', 0)} seconds")
                
            elif event_type == "error":
                # Error occurred
                print(f"Error: {data.get('message', 'Unknown error')}")
                if data.get('details'):
                    print(f"Details: {data.get('details')}")
                
        except json.JSONDecodeError:
            print(f"Could not parse chunk: {chunk}")

if __name__ == "__main__":
    # Run the local analysis function when script is executed directly
    run_local_analysis() 