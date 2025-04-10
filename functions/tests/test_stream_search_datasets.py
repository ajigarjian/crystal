import sys
import json
import logging
import traceback
import os
from dotenv import load_dotenv
import django
from firebase_admin import firestore
import firebase_admin
import pprint

load_dotenv()

os.environ["FUNCTIONS_EMULATOR"] = "True"

# Add the parent directory to the Python path
functions_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(functions_dir)

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'factchecker.settings')

# Initialize Django
django.setup()

# Import the helper function after Django is initialized
from helpers.stream_search_datasets import stream_search_datasets_helper

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

# Initialize Firebase app if not already initialized
try:
    firebase_admin.get_app()
except ValueError:
    # turn on emulator if needed
    if os.getenv('FUNCTIONS_EMULATOR'):
        os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed
    firebase_admin.initialize_app()

def local_stream_search_datasets(request_json):
    """
    Local version of the stream_search_datasets function that mimics the Cloud Function.
    
    Args:
        request_json (dict): The request data as a dictionary
        
    Returns:
        generator: A generator that yields dataset results as they come in
    """
    # Initialize db
    db = firestore.client()
    
    # Set environment variable for local database connection
    if os.getenv('FUNCTIONS_EMULATOR'):
        # Set PostgreSQL connection for local development
        os.environ["DB_HOST"] = os.getenv("DB_HOST", "localhost")
        os.environ["DB_PORT"] = os.getenv("DB_PORT", "1234")
        os.environ["DB_USER"] = os.getenv("DB_USER", "postgres")
        os.environ["DB_PASSWORD"] = os.getenv("DB_PASSWORD", "")
        os.environ["DB_NAME"] = os.getenv("DB_NAME", "crystal")
        # Unset Cloud SQL connection if it exists
        if "INSTANCE_CONNECTION_NAME" in os.environ:
            del os.environ["INSTANCE_CONNECTION_NAME"]
    
    # Validate request data
    if not request_json:
        yield json.dumps({"error": "No JSON data provided", "type": "error"}) + "\n"
        return
    
    # Get the query parameter
    query = request_json.get('query', '')
    
    if not query:
        yield json.dumps({"error": "Query is required", "type": "error"}) + "\n"
        return
    
    # Get optional parameters with defaults
    similarity_threshold = float(request_json.get('similarity_threshold', 0.3))
    search_method = request_json.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request_json.get('max_results', 15))
    census_max_results = int(request_json.get('census_max_results', 5))
    relevance_threshold = float(request_json.get('relevance_threshold', 0.4))
    
    logger.info(f"Streaming search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Initialize a variable to store the final result
    final_result = None
    
    # Process the streaming search
    try:
        for chunk in stream_search_datasets_helper(
            query=query,
            similarity_threshold=similarity_threshold,
            search_method=search_method,
            max_results=max_results,
            census_max_results=census_max_results,
            relevance_threshold=relevance_threshold
        ):
            # If this is a JSON object and it's the 'complete' type, store it as the final result
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
            except:
                pass
            
            # Yield the chunk
            yield chunk + "\n"  # Add newline to ensure proper parsing on client side
            # Print the chunk
            print(chunk)
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            # Prettyprin  the final result
            pp = pprint.PrettyPrinter(indent=4)
            pp.pprint(final_result)
            # try:
            #     # Create a document with the search results
            #     search_ref = db.collection('searches').document()
                
            #     # Add the search data
            #     search_ref.set({
            #         'query': query,
            #         'timestamp': firestore.SERVER_TIMESTAMP,
            #         'results': final_result
            #     })
                
            #     logger.info(f"Stored search results in Firestore with ID: {search_ref.id}")
            # except Exception as e:
            #     logger.error(f"Error storing results in Firestore: {e}")
                
    except Exception as e:
        error_message = f"Error processing streaming search: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        yield json.dumps({
            "type": "error",
            "data": {"message": error_message}
        }) + "\n"

def run_local_search():
    """
    Example of how to use the local_stream_search_datasets function
    """
    # Example request data
    request_data = {
        "query": "Philly crime stats",
        "similarity_threshold": 0.3,
        "search_method": None,  # None for hybrid search
        "max_results": 3,
        "census_max_results": 5,
        "relevance_threshold": 0.35
    }
    
    print(f"\n🔍 Running search with query: '{request_data['query']}'")
    print("=" * 80)
    
    # Track progress and store dataset updates
    total_datasets = 0
    relevant_datasets = 0
    dataset_updates = {}  # Store dataset updates by ID
    
    # Process each chunk from the generator
    for chunk in local_stream_search_datasets(request_data):
        try:
            # Parse the chunk as JSON
            data = json.loads(chunk.strip())
            event_type = data.get("type")
            
            if event_type == "dataset":
                # A new dataset result
                dataset = data.get("data", {})
                total_datasets += 1
                
                # Print dataset details
                print(f"\n📊 Dataset {total_datasets}:")
                print(f"Title: {dataset.get('title', 'N/A')}")
                print(f"Description: {dataset.get('description', 'N/A')}")
                print(f"Source: {dataset.get('source', 'N/A')}")
                print("-" * 40)
                
            elif event_type == "dataset_update":
                # Update about dataset relevance
                update_data = data.get("data", {})
                dataset_id = update_data.get("id")
                relevance_info = update_data.get("relevance", {})
                
                # Store the update
                dataset_updates[dataset_id] = {
                    "relevance": relevance_info,
                    "message": data.get("message", ""),
                    "timestamp": data.get("timestamp", 0)
                }
                
                # Print relevance update
                print(f"\n📈 Relevance Update:")
                print(f"Message: {data.get('message', '')}")
                print(f"Score: {relevance_info.get('relevance_score', 0):.2f}")
                print(f"Reasoning: {relevance_info.get('reasoning', 'N/A')}")
                print("-" * 40)
                
                # Update relevant datasets count
                if relevance_info.get('is_relevant', False):
                    relevant_datasets += 1
                
            elif event_type == "progress":
                # Progress update
                progress = data.get("data", {})
                print(f"\n🔄 {progress.get('message', '')}")
                
            elif event_type == "complete":
                # Final results
                result = data.get("data", {})
                print("\n" + "=" * 80)
                print("✨ Search Complete!")
                print(f"Total datasets found: {total_datasets}")
                print(f"Relevant datasets: {relevant_datasets}")
                print(f"Execution time: {result.get('execution_time', 0):.2f} seconds")
                
                # Print summary of relevant datasets
                if dataset_updates:
                    print("\n📋 Relevance Summary:")
                    for dataset_id, update in dataset_updates.items():
                        if update["relevance"].get("is_relevant", False):
                            print(f"\n• {update['message']}")
                            print(f"  Reasoning: {update['relevance'].get('reasoning', 'N/A')}")
                
                print("=" * 80)
                
            elif event_type == "error":
                # Error occurred
                error = data.get("data", {})
                print(f"\n❌ Error: {error.get('message', 'Unknown error')}")
                
        except json.JSONDecodeError:
            print(f"\n⚠️ Could not parse chunk: {chunk}")

if __name__ == "__main__":
    # Run the local search function when script is executed directly
    run_local_search()
