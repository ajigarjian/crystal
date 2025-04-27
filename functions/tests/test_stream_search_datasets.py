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
import time # Added for potential timing/sorting if needed

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
    level=logging.INFO, # Changed to INFO for less noise during normal runs
    format='%(levelname)s:%(name)s:%(message)s', # Simplified format
    # handlers=[ # Commented out file handler for cleaner console output in example
    #     logging.StreamHandler(),
    #     # logging.FileHandler('stream_analyze.log')
    # ]
)
# Reduce verbosity from imported libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("azure").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

# Initialize Firebase app if not already initialized
# try: # Commented out Firebase for this example run
#     firebase_admin.get_app()
# except ValueError:
#     # turn on emulator if needed
#     if os.getenv('FUNCTIONS_EMULATOR'):
#         os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed
#     firebase_admin.initialize_app()

def local_stream_search_datasets(request_json):
    """
    Local version of the stream_search_datasets function that mimics the Cloud Function.

    Args:
        request_json (dict): The request data as a dictionary

    Returns:
        generator: A generator that yields dataset results as they come in
    """
    # Initialize db
    # db = firestore.client() # Commented out Firebase

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
    # census_max_results = int(request_json.get('census_max_results', 5)) # Census search likely not used here
    relevance_threshold = float(request_json.get('relevance_threshold', 0.4))

    logger.info(f"Streaming search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")

    # Initialize a variable to store the final result data for context
    final_result_data = None

    # Process the streaming search
    try:
        for chunk in stream_search_datasets_helper(
            query=query,
            similarity_threshold=similarity_threshold,
            search_method=search_method,
            max_results=max_results,
            #census_max_results=census_max_results,
            relevance_threshold=relevance_threshold,
            mode="search_and_download" # Ensures download/preview phase runs
        ):
            # If this is a JSON object and it's the 'complete' type, store its data
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result_data = chunk_data.get('data', {}) # Store the data part
            except json.JSONDecodeError:
                pass # Ignore non-JSON strings if necessary

            # Yield the chunk
            yield chunk + "\n"  # Add newline to ensure proper parsing on client side

        # If we have a final result data, store it in Firestore for later retrieval
        # if final_result_data: # Commented out Firebase storage
            # Prettyprint the final result data for review
            # pp = pprint.PrettyPrinter(indent=4)
            # pp.pprint(final_result_data)
            # try:
            #     # Create a document with the search results
            #     search_ref = db.collection('searches').document()

            #     # Add the search data
            #     search_ref.set({
            #         'query': query,
            #         'timestamp': firestore.SERVER_TIMESTAMP,
            #         'results': final_result_data # Store the data part
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
            "message": error_message # Changed 'data' to 'message' for consistency
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
        "max_results": 25,
        # "census_max_results": 5, # Likely not used
        "relevance_threshold": 0.35 # Use the threshold from your example run
    }

    print(f"\n🔍 Running search with query: '{request_data['query']}'")
    print("=" * 80)

    # Track progress and store dataset updates
    total_datasets_discovered = 0 # Renamed for clarity
    relevant_datasets_count = 0 # Renamed for clarity
    dataset_info_map = {} # Store basic dataset info (title) by ID
    dataset_relevance_updates = {} # Store relevance updates by ID
    dataset_preview_statuses = {} # Store preview statuses by ID
    final_summary_data = None # To store the data part of the 'complete' message

    start_time = time.time()

    # Process each chunk from the generator
    for chunk in local_stream_search_datasets(request_data):
        # Print the raw chunk received from the helper
        print(chunk.strip()) # Print the raw stream output

        try:
            # Parse the chunk as JSON
            data = json.loads(chunk.strip())
            event_type = data.get("type")
            dataset_data = data.get("data", {})

            if event_type == "dataset":
                # A newly discovered dataset result
                dataset_id = dataset_data.get("id")
                if dataset_id not in dataset_info_map:
                    total_datasets_discovered += 1
                    dataset_info_map[dataset_id] = {
                         "title": dataset_data.get('title', 'N/A'),
                         # Store other initial info if needed
                    }
                # No need to print here, it's already printed by the raw chunk print

            elif event_type == "dataset_update":
                # Update about dataset relevance
                update_data = data.get("data", {})
                dataset_id = update_data.get("id")
                relevance_info = update_data.get("relevance", {})

                # Store the update
                dataset_relevance_updates[dataset_id] = {
                    "relevance": relevance_info,
                    "message": data.get("message", ""),
                    "timestamp": data.get("timestamp", 0)
                }
                # Update relevant datasets count
                if relevance_info.get('is_relevant', False):
                     # Ensure we only count each relevant dataset once
                     if dataset_id not in [k for k, v in dataset_relevance_updates.items() if v['relevance'].get('is_relevant')]:
                         relevant_datasets_count +=1

            elif event_type == "dataset_download":
                 # Update about dataset download/preview status
                 download_data = data.get("data", {})
                 dataset_id = download_data.get("id")
                 dataset_preview_statuses[dataset_id] = download_data
                 # No need to print detailed preview here, summarize at the end

            elif event_type == "complete":
                # Final results data stored
                final_summary_data = data.get("data", {})
                # Final summary will be printed after the loop

            # elif event_type == "error": # Already printed by raw chunk print
            #     error = data.get("data", {})
            #     print(f"\n❌ Error: {error.get('message', 'Unknown error')}")

        except json.JSONDecodeError:
            # If chunk is not JSON, it might be a plain log message or status
            # It's already printed by the raw chunk print, so just pass
            pass
        except Exception as e:
            print(f"\n⚠️ Error processing chunk: {chunk.strip()} - {e}")


    end_time = time.time()
    total_execution_time = end_time - start_time

    # --- Final Summary Section ---
    print("\n" + "=" * 80)
    print("✨ Search Complete!")

    if final_summary_data:
        print(f"Total datasets found: {final_summary_data.get('total_found_unique', total_datasets_discovered)}") # Use final summary count if available
        print(f"Relevant datasets assessed: {final_summary_data.get('total_relevant', relevant_datasets_count)}") # Use final summary count if available
        print(f"Execution time: {final_summary_data.get('execution_time', total_execution_time):.2f} seconds")

        # Print summary of relevant datasets from the final summary data
        if final_summary_data.get('datasets'):
            print("\n📋 Relevance Summary:")
            # Count actual relevant datasets from the final list
            final_relevant_count = len([ds for ds in final_summary_data['datasets'] if ds.get('relevance', {}).get('is_relevant')])
            print(f"(Final Relevant Count: {final_relevant_count})")

            for dataset in final_summary_data['datasets']:
                 relevance_info = dataset.get('relevance', {})
                 if relevance_info.get('is_relevant'):
                     title = dataset.get('title', 'N/A')
                     score = relevance_info.get('relevance_score', 0)
                     reasoning = relevance_info.get('reasoning', 'N/A')
                     print(f"\n• ✓ Relevant: {title} (Score: {score:.2f})")
                     print(f"  Reasoning: {reasoning}")
        else:
             print("\nNo relevant datasets found in the final summary.")

    else:
        # Fallback if 'complete' message wasn't parsed or available
        print(f"Total datasets discovered: {total_datasets_discovered}")
        # Note: relevant_datasets_count might be inaccurate without the 'complete' message confirming assessments
        print(f"Relevant datasets assessed (estimated): {relevant_datasets_count}")
        print(f"Execution time: {total_execution_time:.2f} seconds")


    # --- Preview Summary Section ---
    print("\n" + "=" * 80)
    print("📋 Preview/Download Summary:")
    if dataset_preview_statuses:
        successful_previews = 0
        download_errors = 0
        load_errors = 0
        attempted_previews = len(dataset_preview_statuses)

        print(f"(Attempted: {attempted_previews})")

        for dataset_id, status in dataset_preview_statuses.items():
            title = dataset_info_map.get(dataset_id, {}).get('title', f"ID: {dataset_id}") # Get title from stored info
            if status.get('loaded'):
                print(f"  ✓ Previewed: {title} ({status.get('rows', 'N/A')}x{status.get('cols', 'N/A')})")
                successful_previews += 1
            elif not status.get('downloaded'):
                 print(f"  ✗ Download Failed: {title} - Error: {status.get('error', 'Unknown download error')}")
                 download_errors += 1
            else: # Downloaded but not loaded
                 print(f"  ✗ Load/Preview Failed: {title} - Error: {status.get('error', 'Unknown loading error')}")
                 load_errors += 1

        print(f"\nPreview Success Rate: {successful_previews}/{attempted_previews}")
        print(f"Download Errors: {download_errors}")
        print(f"Load/Preview Errors: {load_errors}")
    else:
        print("No datasets were attempted for download/preview (or status tracking failed).")

    print("=" * 80)


if __name__ == "__main__":
    # Run the local search function when script is executed directly
    run_local_search()