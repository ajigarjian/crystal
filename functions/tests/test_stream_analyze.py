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
import pprint # For pretty printing if needed
import re

# --- (Keep the existing setup code: imports, path, django setup, etc.) ---
os.environ["FUNCTIONS_EMULATOR"] = "True"

# Add the parent directory to the Python path
# Adjust this path if your structure is different
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
# Assuming 'functions' is the parent directory containing 'helpers' and this script
# If 'helpers' is directly under 'functions', this should work.
# If your test script is outside 'functions', adjust accordingly.
sys.path.append(parent_dir)
# print(f"Appended to sys.path: {parent_dir}") # Uncomment for path debugging

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'factchecker.settings') # Make sure 'factchecker' is the name of your Django project

# Initialize Django
try:
    django.setup()
    print("Django setup successful.")
except Exception as e:
    print(f"Error during Django setup: {e}")
    sys.exit(1)

# Now import the helper function - assuming it's in functions/helpers/stream_analyze.py
try:
    from helpers.stream_analyze import stream_analyze_helper
    print("Successfully imported stream_analyze_helper.")
except ModuleNotFoundError:
    print("Error: Could not import stream_analyze_helper. Check sys.path and file location.")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Error importing stream_analyze_helper: {e}")
    sys.exit(1)

# Load environment variables
load_dotenv()

# Configure logging
log_file = 'stream_analyze_test.log'
logging.basicConfig(
    level=logging.INFO, # Set to DEBUG for more verbosity if needed
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to console
        logging.FileHandler(log_file, mode='w') # Overwrite log file each run
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging configured. Log file: {log_file}")


# --- (Keep Firebase initialization code) ---
# Initialize Firebase app if not already initialized
try:
    if not firebase_admin._apps:
         # turn on emulator if needed
        if os.getenv('FUNCTIONS_EMULATOR'):
            logger.info("Using Firestore emulator")
            # Ensure these match your emulator settings
            os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
        logger.info("Initializing Firebase app")
        # Add credentials if needed for non-emulator connection
        # cred = firebase_admin.credentials.Certificate("path/to/your/serviceAccountKey.json")
        # firebase_admin.initialize_app(cred)
        firebase_admin.initialize_app() # Initialize without explicit creds for emulator or default ADC
    else:
        logger.info("Firebase app already initialized.")
except ValueError as e:
     logger.error(f"Firebase initialization error: {e}. Check credentials or emulator setup.")
     # Decide if you want to exit or continue without Firestore
     # sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected error during Firebase initialization: {e}")
    # sys.exit(1)


# --- (Keep local_stream_analyze function as is) ---
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

    # Initialize db client only if Firebase initialized successfully
    db = None
    try:
        if firebase_admin._apps:
            db = firestore.client()
            logger.debug("Firestore client initialized")
        else:
            logger.warning("Firestore client not initialized because Firebase app is not available.")
    except Exception as e:
        logger.error(f"Failed to create Firestore client: {e}")


    # Validate request data
    if not request_json:
        logger.error("No JSON data provided")
        yield json.dumps({"error": "No JSON data provided", "type": "error"}) + "\n"
        return

    # Get the required parameters
    dataset_ids = request_json.get('dataset_ids', [])
    query = request_json.get('query', '')
    parallel = request_json.get('parallel', True) # Get parallel flag

    # Optional file path parameter (less relevant now, but keep for compatibility)
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

    logger.info(f"Streaming analysis parameters: dataset_ids={dataset_ids}, query='{query}', parallel={parallel}")

    # Initialize a variable to store the final result for Firestore saving
    final_result_for_storage = None

    # Process the streaming analysis
    try:
        logger.info("Starting stream_analyze_helper")
        for chunk in stream_analyze_helper(
            dataset_ids=dataset_ids,
            query=query,
            file_path=file_path,
            parallel=parallel # Pass the parallel flag
        ):
            # Skip empty chunks or whitespace chunks
            if not chunk or chunk.isspace():
                logger.debug("Received empty or whitespace chunk, skipping")
                continue

            # Store the 'complete' message data for later saving
            try:
                # Peek at the chunk type without fully parsing if possible,
                # but parsing is generally needed.
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    logger.info("Received complete message type, storing data for Firestore.")
                    # Store the 'data' part of the 'complete' message
                    final_result_for_storage = chunk_data.get('data', {})
            except json.JSONDecodeError:
                 # This chunk might be a status message or something else not JSON formatted
                 # in the way we expect for the 'complete' check. It will be yielded anyway.
                 pass
            except Exception as e:
                logger.error(f"Error checking chunk type for 'complete' status: {str(e)}")
                # Log the problematic chunk for debugging
                logger.error(f"Problematic chunk: {chunk[:200]}...") # Log first 200 chars

            # Yield the chunk regardless of its type (unless empty)
            yield chunk

        # After the generator finishes, if we have a final result and db client, store it
        if final_result_for_storage and db:
            try:
                logger.info("Storing final results in Firestore")
                # Create a document with the analysis results
                # Use a timestamp in the doc ID for uniqueness or a generated ID
                doc_id = f"analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
                analysis_ref = db.collection('analyses').document(doc_id) # Changed to collection 'analyses'

                # Prepare data for Firestore
                firestore_data = {
                    'dataset_ids': dataset_ids,
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP, # Use server timestamp
                    'results': final_result_for_storage, # Store the 'data' from the 'complete' message
                    'has_web_search_results': 'web_search_results' in final_result_for_storage and final_result_for_storage['web_search_results'] is not None
                }

                # Remove potentially large/problematic fields before saving if needed
                # Example: Pruning large raw results if they cause issues
                # if 'web_search_results' in firestore_data['results']:
                #     if 'results' in firestore_data['results']['web_search_results']:
                #         # Keep only metadata or a summary
                #         pass # Modify as needed

                analysis_ref.set(firestore_data)
                logger.info(f"Stored analysis results in Firestore with ID: {analysis_ref.id}")

            except Exception as e:
                logger.error(f"Error storing analysis results in Firestore: {e}")
                # Log details about the data that failed if possible
                try:
                    logger.error(f"Data attempted to save: {json.dumps(firestore_data, indent=2, default=str)}")
                except Exception as dump_error:
                    logger.error(f"Could not serialize data for logging: {dump_error}")
                logger.error(traceback.format_exc())
        elif not db:
             logger.warning("Skipping Firestore storage as DB client is not available.")

    except Exception as e:
        error_message = f"Error processing streaming analysis in local_stream_analyze: {str(e)}"
        logger.error(error_message)
        logger.error(traceback.format_exc())
        # Yield a final error message
        yield json.dumps({
            "type": "error",
            "message": error_message, # Use message field standard
            "details": traceback.format_exc() # Add details
        }) + "\n"


def run_local_analysis(parallel_mode):
    """
    Example of how to use the local_stream_analyze function.

    Args:
        parallel_mode: Boolean flag to control parallel execution in stream_analyze_helper.
    """
    logger.info(f"--- Starting new analysis run (Parallel={parallel_mode}) ---")

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
        "parallel": parallel_mode  # Add the parallel flag to the request data
    }

    logger.info(f"Running analysis with {len(request_data['dataset_ids'])} dataset IDs.")
    logger.info(f"Query: {request_data['query']}")
    logger.info(f"Parallel mode: {parallel_mode}")

    # Tracking variables
    all_messages = [] # List to store all received message data dicts
    message_count = 0
    notable_messages = [] # List to store notable messages for saving
    notable_types = {
        'extracted_data',
        'web_search_results',
        'web_search_summary',
        'analysis_result',
        # 'analysis', # Often verbose, skip for notable unless debugging analysis text
        'formatted_data',
        'findings',
        'complete',
        'error'
    }
    status_messages = []
    error_messages = []
    # Store the *last* received message of each key type for final summary
    findings_data = None
    complete_data = None
    web_search_summary_data = None

    logger.info(">>> Starting to process streaming response...")

    try:
        # Process each chunk from the generator
        for chunk in local_stream_analyze(request_data):
            message_count += 1
            try:
                # Skip empty/whitespace chunks (already done in local_stream_analyze, but belt-and-suspenders)
                if not chunk or chunk.isspace():
                    logger.debug(f"Skipping empty/whitespace chunk #{message_count}")
                    continue

                # Parse the chunk as JSON
                # Use strip() to remove leading/trailing whitespace, including the newline
                data = json.loads(chunk.strip())
                all_messages.append(data) # Store parsed data

                # Process based on type
                msg_type = data.get('type')
                logger.debug(f"Processing message #{message_count}, type: {msg_type}")

                # Add to notable messages if the type matches
                if msg_type in notable_types:
                    notable_messages.append(data)

                # --- Handle specific message types ---
                if msg_type == 'status':
                    msg = data.get('message', '')
                    status_messages.append(msg)
                    logger.info(f"Status: {msg}")

                elif msg_type == 'dataset_status':
                    ds_id = data.get('dataset_id', 'N/A')
                    ds_status = data.get('status', 'N/A')
                    ds_prog = data.get('progress')
                    ds_msg = data.get('message', '')
                    prog_str = f", Progress: {ds_prog}" if ds_prog is not None else ""
                    logger.info(f"Dataset Status: ID={ds_id}, Status={ds_status}{prog_str}, Msg='{ds_msg}'")

                elif msg_type == 'error':
                    err_msg = data.get('message', 'Unknown error')
                    err_details = data.get('details', '')
                    logger.error(f"Received Error: {err_msg}")
                    if err_details:
                        logger.error(f"Error Details: {err_details[:500]}...") # Log first 500 chars of details
                    error_messages.append(data)

                elif msg_type == 'findings':
                    findings_data = data.get('data') # Store the data part
                    logger.info(">>> Received Findings Summary <<<")
                    # **Immediate Print for Verification**
                    if findings_data:
                         print("--- Findings Content ---")
                         print("Key Data Points:")
                         key_points = findings_data.get('key_data_points', [])
                         if key_points:
                              for point in key_points:
                                   print(f"  {point}")
                         else:
                              print("  (No key data points found in message)")
                         print("\nSummary Text:")
                         summary_txt = findings_data.get('summary', '(No summary text found in message)')
                         print(summary_txt)
                         print("--- End Findings Content ---")
                    else:
                         print("(Findings message received, but 'data' field was empty or missing)")
                    # Log structure for debugging
                    logger.debug(f"Findings data structure: {pprint.pformat(findings_data)}")

                elif msg_type == 'web_search_summary':
                     web_search_summary_data = data.get('data')
                     logger.info("Received Web Search Summary.")
                     logger.debug(f"Web Search Summary content: {pprint.pformat(web_search_summary_data)}")

                elif msg_type == 'complete':
                    complete_data = data.get('data') # Store data part
                    logger.info(f"--- Analysis Complete --- Message: {data.get('message', '')}")
                    logger.debug(f"Complete data received: {pprint.pformat(complete_data)}")
                    # Optional: break here if you don't need to process anything after 'complete'
                    # break

                # Add elif blocks for other types ('extracted_data', 'analysis_result', etc.)
                # if you need specific logging or actions for them during the stream.
                elif msg_type == 'extracted_data':
                    ex_data = data.get('data')
                    ds_title = ex_data.get('dataset_title', 'Unknown') if ex_data else 'Unknown'
                    logger.info(f"Received extracted data for dataset: {ds_title}")
                    # logger.debug(f"Extracted data content: {pprint.pformat(ex_data)}") # Can be very verbose

                elif msg_type == 'formatted_data':
                     logger.info("Received formatted data.")
                     # logger.debug(f"Formatted data content: {pprint.pformat(data.get('data'))}") # Can be verbose

                elif msg_type == 'analysis_result':
                     logger.info("Received analysis result.")
                     # logger.debug(f"Analysis result content: {pprint.pformat(data.get('data'))}") # Can be verbose

                elif msg_type == 'web_search_results':
                     logger.info("Received raw web search results.")
                     # logger.debug(f"Web search results content: {pprint.pformat(data.get('data'))}") # Can be verbose

                else:
                    # This catches types like 'dataset_analysis_result_internal', 'formatted_data_internal'
                    # which are handled internally by stream_analyze_helper but still yielded.
                    # Also catches any genuinely unknown types.
                    logger.warning(f"Received unhandled message type: {msg_type}")
                    logger.debug(f"Full unhandled message:\n{json.dumps(data, indent=2)}")

            except json.JSONDecodeError as e:
                logger.error(f"*** FATAL: Error parsing JSON message #{message_count} ***")
                logger.error(f"JSONDecodeError details: {str(e)}")
                # **Log the raw chunk that failed**
                logger.error(f"Raw chunk content that failed parsing:\n>>>\n{chunk}\n<<<")
                # Continue processing next chunks if possible, or decide to break/raise
                error_messages.append({"type": "parse_error", "message": str(e), "raw_chunk": chunk})


            except Exception as e:
                logger.error(f"*** FATAL: Error processing message #{message_count} (type: {data.get('type', 'N/A')}) ***")
                logger.error(f"Error details: {str(e)}")
                logger.error(traceback.format_exc())
                # Log the message that caused the error
                try:
                    logger.error(f"Message content causing error:\n{json.dumps(data, indent=2)}")
                except:
                    logger.error(f"Could not dump message content. Raw chunk: {chunk}")
                error_messages.append({"type": "processing_error", "message": str(e), "traceback": traceback.format_exc(), "message_data": data if 'data' in locals() else chunk})
                # Continue processing next chunks if possible

        logger.info(">>> Stream processing finished.")

        # --- Save Consolidated Notable Messages ---
        if notable_messages:
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = "test_runs"
                os.makedirs(output_dir, exist_ok=True)
                # Sanitize query for filename
                query_slug = re.sub(r'\W+', '_', request_data.get('query', 'query').lower())[:50] # Limit length
                parallel_suffix = "parallel" if parallel_mode else "sequential"
                filename = f"{output_dir}/consolidated_run_{query_slug}_{parallel_suffix}_{timestamp}.json"

                # Use NumpyEncoder if needed, otherwise default json dump
                # Make sure NumpyEncoder is defined or imported if you use it here
                # from helpers.stream_analyze import NumpyEncoder # Assuming it's there
                with open(filename, 'w', encoding='utf-8') as f:
                    # json.dump(notable_messages, f, indent=2, ensure_ascii=False, cls=NumpyEncoder) # If using NumpyEncoder
                    json.dump(notable_messages, f, indent=2, ensure_ascii=False, default=str) # Use default=str as fallback

                logger.info(f"Saved {len(notable_messages)} notable messages to {filename}")
            except Exception as e:
                logger.error(f"Error saving consolidated messages: {e}")
                logger.error(traceback.format_exc())

        # --- Final Summary Printout ---
        logger.info(f"\n--- Run Summary ---")
        logger.info(f"Total messages received: {message_count}")
        logger.info(f"Status messages count: {len(status_messages)}")
        logger.info(f"Error messages count: {len(error_messages)}")
        logger.info(f"Notable messages saved: {len(notable_messages)}")
        logger.info(f"Parallel mode used: {parallel_mode}")

        if error_messages:
            logger.warning("*** Errors occurred during the run. Check logs and saved file. ***")
            # Optionally print summary of errors
            for i, err in enumerate(error_messages[:3]): # Print first 3 errors
                 logger.warning(f"  Error {i+1}: Type='{err.get('type')}', Msg='{err.get('message', '')[:100]}...'")
            if len(error_messages) > 3:
                 logger.warning(f"  ... and {len(error_messages) - 3} more errors.")

        # **Detailed Findings Summary Printout**
        if findings_data:
            logger.info("\n--- Final Findings Summary ---")
            # Print key points
            key_points = findings_data.get('key_data_points', ['(No key data points found in final data)'])
            logger.info("Key Data Points:")
            if isinstance(key_points, list):
                for point in key_points:
                    logger.info(f"  {point}") # Assuming points are pre-formatted strings
            else:
                 logger.info(f"  (Expected list, got {type(key_points)}): {key_points}")

            # Print summary text
            summary_text = findings_data.get('summary', '(No summary text found in final data)')
            logger.info("\nSummary Text:")
            logger.info(summary_text if summary_text else "(Summary text is empty)")

             # Print Sources
            sources = findings_data.get('sources', [])
            logger.info("\nSources:")
            if sources:
                 for src in sources:
                      cit = src.get('citation_id', 'N/A')
                      title = src.get('title', 'N/A')
                      org = src.get('organization', 'N/A')
                      logger.info(f"  - [{cit}] {title} ({org})")
            else:
                 logger.info("  (No sources listed in final data)")

            logger.info("--- End Final Findings Summary ---")
        else:
            # This case handles when the 'findings' message type was *never* received.
            logger.warning("\n--- No Findings Summary Message Was Received During Run ---")
            # Check if perhaps the process errored out before findings could be generated.

        if web_search_summary_data:
             logger.info("\n--- Final Web Search Summary ---")
             logger.info(pprint.pformat(web_search_summary_data))
             logger.info("--- End Web Search Summary ---")
        else:
             logger.info("\n--- No Web Search Summary Received ---")


        if complete_data:
            logger.info("\n--- Final 'Complete' Message Data ---")
            # Print selected fields from complete_data for brevity
            exec_time = complete_data.get('execution_time', 'N/A')
            web_results_info = complete_data.get('web_search_results', {})
            web_results_count = len(web_results_info.get('search_results', {}).get('results', [])) if web_results_info else 0
            web_error = web_results_info.get('error') if web_results_info else None

            logger.info(f"Execution Time: {exec_time:.2f} seconds" if isinstance(exec_time, (int, float)) else f"Execution Time: {exec_time}")
            logger.info(f"Web Search Results Count in final data: {web_results_count}")
            if web_error:
                logger.warning(f"Web Search Error reported in final data: {web_error}")
            logger.info("--- End 'Complete' Message Data ---")
        else:
            logger.warning("\n--- No 'Complete' Message Was Received During Run ---")


    except KeyboardInterrupt:
        logger.info("\n--- Analysis Interrupted by User (KeyboardInterrupt) ---")
    except Exception as e:
        logger.error(f"\n--- An Unhandled Error Occurred in run_local_analysis ---")
        logger.error(f"Error details: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
         logger.info(f"--- Analysis run finished ---")


if __name__ == "__main__":
    # Run the local analysis function when script is executed directly
    # Choose parallel or sequential mode
    run_local_analysis(parallel_mode=True) # Or set to False for sequential
    # run_local_analysis(parallel_mode=False)