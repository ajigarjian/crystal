# stream_search_datasets.py

from firebase_functions import https_fn, options
# Remove firebase_admin import if not initialized/used directly here
# from firebase_admin import initialize_app, firestore
import requests
from datetime import datetime
# import firebase_admin # Remove if unused
import os
import logging
import time
import json
import traceback
import numpy as np
import concurrent.futures
from threading import Lock
import pandas as pd
import queue # Potentially useful for managing results from futures

# Factchecker imports
# Assume process_census_query is not needed since census is disabled
# from factchecker.search.census_search import process_query as process_census_query
from factchecker.search.search_utils import parallel_search # single_search might not be needed
from factchecker.search import search_datasets # Keyword search
from factchecker.search.pinecone_search import vector_search_datasets_pinecone as vector_search_datasets
# from factchecker.search.census_search import vector_search as census_vector_search # Disabled
from factchecker.processing.analysis.dataset_result_analyzer import assess_datafile_relevance_predownload, get_best_resource
from factchecker.download.download_gov_data import download_resource
from factchecker.processing.analysis.dataset_loader import load_datafile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        # --- Priority 1: Handle specific NumPy types ---
        if isinstance(obj, np.integer):
            # Convert numpy int types to standard Python int
            return int(obj)
        if isinstance(obj, np.floating):
            # Convert numpy float types to standard Python float or None for NaN/Inf
            if np.isnan(obj):
                return None
            if np.isinf(obj):
                # Represent infinity as None (null in JSON) for broader compatibility
                # Or use float('inf')/-float('inf') if receiver can handle it
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            # Recursively apply default to handle potential NaNs/Infs/nested types in arrays
            return [self.default(item) for item in obj.tolist()] # Use tolist() then recurse
        if isinstance(obj, np.bool_):
             # Convert numpy bool types to standard Python bool
             return bool(obj)

        # --- Priority 2: Handle specific Pandas types ---
        if isinstance(obj, pd.Timestamp):
            # Convert Timestamp to ISO 8601 string format
            return obj.isoformat()
        if isinstance(obj, pd.Series):
            # Convert Series to dict, let subsequent calls handle values
            # Handle potential non-standard types in Series values during conversion if needed
            try:
                # Attempt direct conversion, assuming mostly standard types
                return obj.to_dict()
            except Exception as e:
                logger.warning(f"Could not directly convert Series to dict for JSON ({e}), trying element-wise conversion.")
                # Fallback: convert element by element if direct fails
                return {k: self.default(v) for k, v in obj.items()}
        if isinstance(obj, pd.DataFrame):
             # Convert DataFrame to list of records (dicts), let subsequent calls handle values
             try:
                # Use records orientation, common for JSON APIs
                return obj.to_dict(orient='records')
             except Exception as e:
                 logger.warning(f"Could not directly convert DataFrame to list of records for JSON ({e}), trying row-by-row conversion.")
                 # Fallback: iterate rows and convert each row-dict
                 records = []
                 for index, row in obj.iterrows():
                     try:
                         records.append(row.to_dict()) # Convert each row Series
                     except Exception as row_e:
                          logger.warning(f"Failed to convert row {index} in DataFrame: {row_e}")
                          records.append({}) # Add empty dict on failure
                 return records

        # --- Priority 3: Handle standard Python types that might cause issues (rare) ---
        # Optional: Explicitly handle standard int/float if super() still fails sometimes
        # Generally, super().default(obj) should handle these correctly.
        # if isinstance(obj, float): # Example, usually unnecessary
        #    if np.isnan(obj): return None
        #    if np.isinf(obj): return None
        #    return float(obj)
        # if isinstance(obj, int): # Example, usually unnecessary
        #    return int(obj)

        # --- Let the base class handle standard serializable types ---
        try:
            return super(NumpyEncoder, self).default(obj)
        except TypeError:
            # --- Last Resort Fallback ---
            # For types not handled above and not serializable by default JSON encoder
            logger.warning(f"NumpyEncoder could not serialize object of type {type(obj)}, attempting string conversion.")
            try:
                # Convert to string as a final attempt
                return str(obj)
            except Exception as str_err:
                 # If even string conversion fails, return None
                 logger.error(f"String conversion failed for type {type(obj)}: {str_err}")
                 return None


def create_status_message(message, start_time, **kwargs):
    """Create a status message JSON object"""
    payload = {
        'type': 'status',
        'message': message,
        'timestamp': time.time() - start_time
    }
    payload.update(kwargs) # Add any extra fields
    return json.dumps(payload, cls=NumpyEncoder) + '\n'

def create_error_message(message, details=None, start_time=None, **kwargs):
    """Create an error message JSON object"""
    timestamp = time.time() - start_time if start_time else time.time()
    error_obj = {
        'type': 'error',
        'message': message,
        'timestamp': timestamp
    }
    if details:
        # Ensure details are serializable (e.g., convert Exception to string)
        error_obj['details'] = str(details)
    error_obj.update(kwargs) # Add any extra fields
    return json.dumps(error_obj, cls=NumpyEncoder) + '\n'

def yield_initial_dataset_info(dataset, source, all_datasets_count, start_time):
    """Yields discovery and initial dataset messages."""
    dataset_id = dataset.get('id', 'unknown_' + str(time.time())) # Add timestamp for uniqueness if no ID
    dataset_title = dataset.get('title', 'Untitled Dataset')

    # Ensure dataset has a unique ID before proceeding
    if 'id' not in dataset:
         dataset['id'] = dataset_id
         logger.warning(f"Dataset missing 'id', assigned temporary ID: {dataset_id}")

    # Set search source
    dataset['search_source'] = source

    # Check if resources are cached and set is_cached flag (if resources exist)
    resources = dataset.get('resources', [])
    dataset['is_cached'] = any(resource.get('is_cached', False) for resource in resources if isinstance(resource, dict))

    # Yield status update about finding this dataset
    yield json.dumps({
        'type': 'discovery',
        'message': f'Discovered dataset: {dataset_title}',
        'count': all_datasets_count,
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'

    # Then yield the basic dataset info (without relevance yet)
    yield json.dumps({
        'type': 'dataset',
        'data': dataset, # Send the dataset dict as is
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'


def assess_and_create_update(query, dataset, relevance_threshold, start_time):
    """
    Helper function to assess relevance and create update message.
    Intended for use in a thread pool.
    Returns a tuple: (update_message_json_string, updated_dataset_dict)
    """
    dataset_id = dataset.get('id', 'unknown')
    dataset_title = dataset.get('title', 'Unnamed Dataset')
    assessment_start = time.time()
    logger.info(f"Starting relevance assessment for dataset {dataset_id} at {assessment_start - start_time:.2f}s")

    try:
        # Call the pre-download assessment function
        # Ensure dataset passed is a dictionary
        if not isinstance(dataset, dict):
             logger.error(f"Invalid dataset type passed to assessment: {type(dataset)}. ID: {dataset_id}")
             raise TypeError("Dataset must be a dictionary.")

        assessment_result = assess_datafile_relevance_predownload(
            query,
            dataset.copy(), # Pass a copy to avoid potential thread safety issues
            relevance_threshold=relevance_threshold
        )

        # Extract values from the result dictionary
        is_relevant = assessment_result.get("is_relevant", False) # Use .get for safety
        relevance_score = assessment_result.get("relevance_score", 0.0)
        reasoning = assessment_result.get("reasoning", "Assessment failed to provide reasoning.")
        resource_url = assessment_result.get("resource_url") # Might be None

        # Update the dataset dictionary with relevance information
        dataset_update = dataset.copy() # Work on a copy
        dataset_update['relevance'] = {
            'is_relevant': is_relevant,
            'relevance_score': relevance_score,
            'reasoning': reasoning
        }
        if resource_url:
            dataset_update['resource_url'] = resource_url

        # Create the update message
        update_message = json.dumps({
            'type': 'dataset_update',
            'data': { # Only send ID and relevance block in the update message
                'id': dataset_id,
                'relevance': dataset_update['relevance']
            },
            'message': f'{"✓ Relevant" if is_relevant else "✗ Not Relevant"}: {dataset_title} (Score: {relevance_score:.2f})',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'

        assessment_duration = time.time() - assessment_start
        logger.info(f"Dataset {dataset_id} assessment completed in {assessment_duration:.2f}s. Relevant: {is_relevant}")
        return update_message, dataset_update # Return message and the *updated* dataset dict

    except Exception as e:
        assessment_duration = time.time() - assessment_start
        logger.error(f"Error assessing relevance for dataset {dataset_id} (after {assessment_duration:.2f}s): {str(e)}")
        logger.error(traceback.format_exc())

        # Create an error dataset update
        dataset_update = dataset.copy()
        dataset_update['relevance'] = {
            'is_relevant': False,
            'relevance_score': 0.0,
            'reasoning': f"Error during assessment: {str(e)}",
            'error': str(e)
        }

        # Create error update message
        error_message = json.dumps({
            'type': 'dataset_update',
            'data': {
                'id': dataset_id,
                'relevance': dataset_update['relevance'],
                'error': True # Flag the error in the update
            },
            'message': f'Error assessing dataset {dataset_title}: {str(e)}',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'

        return error_message, dataset_update # Return error message and updated dataset with error info

# --- Search Functions ---

def search_census_data(query, similarity_threshold, max_results, start_time):
    """Placeholder for Census search (currently disabled)."""
    logger.info("Census search is currently disabled.")
    yield create_status_message('Census search functionality is temporarily disabled.', start_time)
    # Keep yield [] to maintain generator interface if needed elsewhere,
    # but better to just yield the status and let the caller handle no results.
    # yield []

def search_vector_datasets(query, similarity_threshold, max_results, start_time):
    """
    Search datasets using vector search (Pinecone) and yield results one by one.
    Now acts as a generator yielding individual dataset dictionaries.
    """
    yield create_status_message('Searching vector database (e.g., Pinecone)...', start_time)

    try:
        # Initialize Pinecone early (consider if this should be outside if reused)
        from factchecker.search.pinecone_search import get_pinecone_client
        pc = get_pinecone_client()
        logger.info(f"Pinecone client initialized at {time.time() - start_time:.2f}s")

        # Use parallel_search with stream_results=True
        results_generator = parallel_search(
            query,
            search_function=vector_search_datasets,
            start_time=start_time,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
            use_variations=True,
            verbose=False, # Keep logs cleaner
            stream_results=True, # Critical: get results as they come
            pinecone_client=pc
        )

        # Yield each result as it comes from the generator
        found_count = 0
        seen_vector_ids = set() # Track IDs within this specific search call if needed
        query_variations_used = set()

        for result in results_generator:
            if isinstance(result, dict) and 'id' in result:
                dataset_id = result['id']
                # Basic check for duplicate IDs within this stream
                if dataset_id not in seen_vector_ids:
                    seen_vector_ids.add(dataset_id)
                    found_count += 1
                    # Store query variation used
                    query_variation = result.get('query_variation', query)
                    query_variations_used.add(query_variation)
                    # Set source
                    result['search_source'] = 'vector'
                    yield result # Yield the dataset dictionary
            else:
                 logger.warning(f"Received non-dict or missing 'id' item from vector search stream: {result}")

        logger.info(f"Vector search yielded {found_count} unique results using variations: {query_variations_used} at {time.time() - start_time:.2f}s")
        if query_variations_used and len(query_variations_used) > 1:
             yield create_status_message(f"Used related search terms: {', '.join([f'\"{v}\"' for v in query_variations_used if v != query])}", start_time)

    except ImportError:
         logger.error("Pinecone client library not found. Vector search unavailable.")
         yield create_error_message("Vector search component is not available.", start_time=start_time)
    except Exception as e:
        logger.error(f"Error during vector search: {str(e)}")
        logger.error(traceback.format_exc())
        yield create_error_message(f"An error occurred during vector search: {str(e)}", start_time=start_time)


def search_keyword_datasets(query, gov_api_key, keyword_threshold, start_time):
    """
    Search datasets using keyword search (data.gov API) and yield results one by one.
    Acts as a generator yielding individual dataset dictionaries.
    """
    yield create_status_message('Searching keyword sources (e.g., data.gov)...', start_time)

    try:
        # Get keyword search results (this function returns a list)
        keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)

        if isinstance(keyword_results, list):
            logger.info(f"Keyword search found {len(keyword_results)} potential results at {time.time() - start_time:.2f}s")
            for result in keyword_results:
                 if isinstance(result, dict) and 'id' in result:
                     # Set source
                     result['search_source'] = 'keyword'
                     yield result # Yield each dataset dictionary
                 else:
                     logger.warning(f"Received non-dict or missing 'id' item from keyword search results: {result}")
        else:
            logger.error(f"Keyword search function returned unexpected type: {type(keyword_results)}")
            yield create_error_message("Received unexpected data format from keyword search.", start_time=start_time)

    except Exception as e:
        logger.error(f"Error during keyword search: {str(e)}")
        logger.error(traceback.format_exc())
        yield create_error_message(f'An error occurred during keyword search: {str(e)}', start_time=start_time)


# --- Download and Preview Helper (for search_and_download mode) ---

def preview_dataset(dataset, start_time):
    """
    Downloads, loads, and generates preview messages for a single dataset.
    Yields JSON string messages.
    """
    ds_id = dataset.get('id', 'unknown_preview_' + str(time.time()))
    title = dataset.get('title', 'Untitled Dataset')
    resource_url = dataset.get('resource_url') # Assumes assessment added this
    resources = dataset.get('resources', [])

    # If resource_url wasn't determined by assessment, try finding the best one now
    if not resource_url and resources:
         logger.info(f"No pre-determined resource_url for {ds_id}, finding best resource...")
         try:
             # We need the original query to find the best resource if not pre-selected
             # This is a limitation here; ideally, the query context should be available.
             # For now, we'll just pick the first resource if URL is missing.
             # A better approach would be to ensure assessment *always* sets resource_url if relevant.
             if resources and isinstance(resources, list) and len(resources) > 0:
                  best_resource = resources[0] # Fallback: use the first resource
                  resource_url = best_resource.get('url')
                  logger.warning(f"Falling back to first resource URL for {ds_id}: {resource_url}")
             else:
                  logger.error(f"No resources found for dataset {ds_id} to determine download URL.")

         except Exception as e:
              logger.error(f"Error getting best resource for {ds_id}: {e}")
              yield create_error_message(f"Could not determine resource to download for {title}.", start_time=start_time, dataset_id=ds_id)
              return # Stop processing this dataset

    if not resource_url:
        logger.warning(f"No resource URL available for dataset {ds_id} ('{title}'). Cannot download.")
        yield create_error_message(f'No download URL found for dataset {title}.', start_time=start_time, dataset_id=ds_id)
        return # Stop processing this dataset

    # Attempt download
    yield create_status_message(f'Downloading: {title}...', start_time, dataset_id=ds_id, status='downloading')
    local_file = None
    download_dir = '/tmp/dataset_downloads' # Use specific temp subdir
    os.makedirs(download_dir, exist_ok=True)

    try:
        # Construct a filename - use dataset ID and try to get extension
        file_ext = os.path.splitext(resource_url.split('?')[0])[1] # Basic extension extraction
        if not file_ext and resources: # Fallback to format if no extension in URL
             file_ext = "." + resources[0].get('format','').lower() if resources[0].get('format') else ".data"

        filename = f"{ds_id}{file_ext}"
        logger.info(f"Attempting download of {resource_url} to {os.path.join(download_dir, filename)}")
        local_file = download_resource(resource_url, download_dir, filename=filename, max_download_time=30) # Increased timeout

    except Exception as e:
        logger.error(f"Download failed for {ds_id} ('{title}') from {resource_url}: {str(e)}")
        yield create_error_message(f'Download failed for {title}: {str(e)}', start_time=start_time, dataset_id=ds_id)
        return

    if not local_file or not os.path.exists(local_file):
        logger.error(f"Download function returned no valid file path for {ds_id} ('{title}').")
        yield create_error_message(f'Download did not produce a file for {title}.', start_time=start_time, dataset_id=ds_id)
        return

    yield create_status_message(f'Downloaded: {title}. Loading...', start_time, dataset_id=ds_id, status='loading')

    # Attempt to load via load_datafile
    df = None
    load_error = None
    try:
        # Determine format if possible (useful for load_datafile)
        file_format = None
        if resources and isinstance(resources, list) and len(resources) > 0:
            file_format = resources[0].get('format') # Use format from metadata if available

        df = load_datafile(local_file, file_format=file_format) # Pass format hint

        if df is None:
             raise ValueError("load_datafile returned None.")

        # Successfully loaded
        yield create_status_message(f'Loaded: {title}. Preparing preview...', start_time, dataset_id=ds_id, status='previewing')

        # Check if it's a DataFrame for shape/head preview
        if hasattr(df, 'shape') and hasattr(df, 'head'):
            row_count, col_count = df.shape
            # Send shape info
            shape_msg = json.dumps({
                'type': 'dataset_download', # Reusing type for simplicity
                'data': {
                    'id': ds_id,
                    'downloaded': True,
                    'loaded': True,
                    'rows': row_count,
                    'cols': col_count,
                    'preview_available': True,
                },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + "\n"
            yield shape_msg

            # Send first 5 rows preview
            head_rows = df.head(5) # Keep as DataFrame for NumpyEncoder
            head_msg = json.dumps({
                'type': 'dataset_preview',
                'data': {
                    'id': ds_id,
                    'head': head_rows # Let NumpyEncoder handle DataFrame serialization
                },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + "\n"
            yield head_msg
        else:
            # Loaded, but not a standard DataFrame (e.g., could be text, JSON dict)
            yield create_status_message(f'Loaded {title} (non-tabular data).', start_time, dataset_id=ds_id, status='complete')
            yield json.dumps({
                'type': 'dataset_download',
                'data': {
                    'id': ds_id,
                    'downloaded': True,
                    'loaded': True,
                    'message': 'Loaded non-tabular data.',
                    'preview_available': False
                 },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + "\n"

    except Exception as e:
        logger.error(f"Error loading or previewing dataset {ds_id} ('{title}') from {local_file}: {str(e)}")
        logger.error(traceback.format_exc())
        load_error = str(e)
        # Send error message related to loading/previewing
        yield create_error_message(f'Error loading/previewing {title}: {load_error}', start_time=start_time, dataset_id=ds_id)
        # Send status update that download happened but loading failed
        yield json.dumps({
                'type': 'dataset_download',
                'data': {
                    'id': ds_id,
                    'downloaded': True,
                    'loaded': False,
                    'error': f'Loading/Preview Error: {load_error}',
                    'preview_available': False
                 },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + "\n"

    finally:
        # Clean up downloaded file
        if local_file and os.path.exists(local_file):
            try:
                os.remove(local_file)
                logger.info(f"Cleaned up temporary file: {local_file}")
            except OSError as e:
                logger.warning(f"Could not remove temporary file {local_file}: {e}")


# --- Main Streaming Helper Function ---

def stream_search_datasets_helper(
    query,
    similarity_threshold=0.25,
    search_method=None, # 'vector', 'keyword', or None (hybrid)
    max_results=50, # Max results *per source* in hybrid mode before filtering
    # census_max_results=5, # Census disabled
    relevance_threshold=0.4,
    mode=None # 'search' or 'search_and_download'
):
    """
    Main helper function that generates streaming search, assessment, and optional download results.
    """
    start_time = time.time()
    processed_dataset_ids = set() # Track IDs across all sources
    final_datasets = {} # Store the final dataset dicts (with relevance) by ID
    all_datasets_count = 0
    assessment_futures = [] # List to hold futures from assessment tasks

    # Use a single executor for relevance assessment across search types
    # Adjust max_workers based on environment constraints (e.g., Cloud Functions CPU/memory)
    assessment_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix="RelevanceAssess")

    try:
        # --- Initial Setup ---
        yield create_status_message(
            f'Starting dataset search for: "{query}"...',
            start_time
        )

        gov_api_key = os.environ.get('DATA_GOV_API_KEY')
        if not gov_api_key and search_method in ['keyword', None]:
            logger.warning("DATA_GOV_API_KEY not set. Keyword search will likely fail.")
            yield create_error_message(
                'Keyword search requires an API key, which is missing.',
                start_time=start_time
            )
            # Allow vector search to proceed if enabled
            if search_method == 'keyword':
                return # Stop if only keyword was requested and key is missing

        # Higher threshold for keyword search (less precise than vector)
        keyword_threshold = similarity_threshold + 0.15 # Adjust as needed

        # --- Run Searches Concurrently (or sequentially if preferred) ---
        # We'll run them sequentially here for simplicity, but could use another executor
        # Search results generators
        vector_gen = None
        keyword_gen = None

        # Initiate Vector Search
        if search_method in ['vector', None]:
            vector_gen = search_vector_datasets(
                query, similarity_threshold, max_results, start_time
            )
            # Consume status messages from the generator immediately
            for msg in vector_gen:
                 if isinstance(msg, str) and ('"type": "status"' in msg or '"type": "error"' in msg):
                     yield msg
                 else:
                     # First non-status message is the start of results, push it back
                     # This requires a way to "peek" or buffer one item.
                     # Simpler: let the loop below handle both status and results.
                     break # Exit status loop, start processing results

        # Initiate Keyword Search
        if search_method in ['keyword', None] and gov_api_key:
            keyword_gen = search_keyword_datasets(
                query, gov_api_key, keyword_threshold, start_time
            )
            # Consume status messages
            for msg in keyword_gen:
                if isinstance(msg, str) and ('"type": "status"' in msg or '"type": "error"' in msg):
                    yield msg
                else:
                    break # Start processing results

        # --- Process Results Streams and Launch Assessments ---
        # Process Vector Results
        if vector_gen:
            logger.info("Processing vector search results...")
            for dataset in vector_gen:
                # Handle potential status/error messages yielded *during* results
                if isinstance(dataset, str):
                    yield dataset
                    continue
                if not isinstance(dataset, dict):
                     logger.warning(f"Skipping non-dict item from vector stream: {type(dataset)}")
                     continue

                dataset_id = dataset.get('id')
                if not dataset_id:
                    logger.warning(f"Skipping vector dataset with no ID: {dataset.get('title')}")
                    continue

                if dataset_id not in processed_dataset_ids:
                    processed_dataset_ids.add(dataset_id)
                    all_datasets_count += 1
                    dataset['search_source'] = 'vector' # Ensure source is set

                    # Yield initial info
                    for chunk in yield_initial_dataset_info(dataset, 'vector', all_datasets_count, start_time):
                        yield chunk

                    # Submit assessment task
                    future = assessment_executor.submit(
                        assess_and_create_update,
                        query,
                        dataset, # Pass the initial dataset dict
                        relevance_threshold,
                        start_time
                    )
                    assessment_futures.append(future)
                else:
                    # Dataset already seen (e.g., from a different query variation), ignore duplicate
                    logger.debug(f"Skipping duplicate vector dataset ID: {dataset_id}")


        # Process Keyword Results
        if keyword_gen:
            logger.info("Processing keyword search results...")
            for dataset in keyword_gen:
                # Handle potential status/error messages yielded *during* results
                if isinstance(dataset, str):
                    yield dataset
                    continue
                if not isinstance(dataset, dict):
                    logger.warning(f"Skipping non-dict item from keyword stream: {type(dataset)}")
                    continue

                dataset_id = dataset.get('id')
                if not dataset_id:
                    logger.warning(f"Skipping keyword dataset with no ID: {dataset.get('title')}")
                    continue

                if dataset_id not in processed_dataset_ids:
                    processed_dataset_ids.add(dataset_id)
                    all_datasets_count += 1
                    dataset['search_source'] = 'keyword' # Ensure source is set

                    # Yield initial info
                    for chunk in yield_initial_dataset_info(dataset, 'keyword', all_datasets_count, start_time):
                        yield chunk

                    # Submit assessment task
                    future = assessment_executor.submit(
                        assess_and_create_update,
                        query,
                        dataset,
                        relevance_threshold,
                        start_time
                    )
                    assessment_futures.append(future)
                else:
                    # Already seen (likely from vector search in hybrid mode)
                    logger.info(f"Dataset {dataset_id} also found via keyword search (originally found via vector).")
                    # Optionally update the source in the final_datasets dict later when processing futures
                    # Or just ignore, as vector is usually higher quality source info.

        # --- Process Completed Assessments ---
        yield create_status_message(f"Submitted {len(assessment_futures)} datasets for relevance assessment.", start_time)
        logger.info(f"Waiting for {len(assessment_futures)} relevance assessments...")

        completed_assessments = 0
        for future in concurrent.futures.as_completed(assessment_futures):
            try:
                update_message, updated_dataset = future.result()
                # Yield the relevance update message
                yield update_message
                # Store the fully updated dataset (including relevance info)
                if updated_dataset and 'id' in updated_dataset:
                    final_datasets[updated_dataset['id']] = updated_dataset
                    completed_assessments += 1
                    # Optional: yield progress status
                    if completed_assessments % 5 == 0 or completed_assessments == len(assessment_futures):
                        yield create_status_message(f"Assessed {completed_assessments}/{len(assessment_futures)} datasets...", start_time, progress=completed_assessments/len(assessment_futures))

            except Exception as e:
                logger.error(f"Error retrieving result from assessment future: {str(e)}")
                # Yield a generic error message? The assess_and_create_update should yield specific errors.
                yield create_error_message("An internal error occurred processing an assessment result.", details=str(e), start_time=start_time)

        logger.info(f"Completed all {completed_assessments} relevance assessments at {time.time() - start_time:.2f}s.")

        # --- Search Phase Completion ---
        search_execution_time = time.time() - start_time
        final_dataset_list = list(final_datasets.values()) # Get list of final dataset dicts

        # Sort by relevance score (descending) then maybe title?
        final_dataset_list.sort(key=lambda x: x.get('relevance', {}).get('relevance_score', 0), reverse=True)

        relevant_datasets = [d for d in final_dataset_list if d.get('relevance', {}).get('is_relevant', False)]
        total_found_unique = len(final_dataset_list)
        total_relevant = len(relevant_datasets)

        yield json.dumps({
            'type': 'phase_complete',
            'phase': 'search',
            'data': {
                'query': query,
                'execution_time': search_execution_time,
                'total_found_unique': total_found_unique,
                'total_relevant': total_relevant,
                # Optionally send final sorted list here if UI needs it before download phase
                # 'datasets': final_dataset_list # Be mindful of size
            },
            'message': f'Search phase complete. Found {total_found_unique} unique datasets, {total_relevant} deemed relevant.',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'


        # --- Optional Download and Preview Phase ---
        if mode == 'search_and_download':
            if not relevant_datasets:
                yield create_status_message("No relevant datasets found to download.", start_time)
            else:
                yield create_status_message(
                    f"Starting download and preview for {len(relevant_datasets)} relevant datasets...", start_time
                )

                download_futures = []
                # Use a separate executor for downloads to avoid blocking/exhausting the assessment pool
                download_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="DownloadPreview")

                with download_executor:
                    for dataset in relevant_datasets:
                        # Submit the preview_dataset task (which downloads, loads, yields messages)
                        future = download_executor.submit(lambda d=dataset: list(preview_dataset(d, start_time)))
                        download_futures.append(future)

                    # Process download/preview results as they complete
                    completed_downloads = 0
                    for future in concurrent.futures.as_completed(download_futures):
                        try:
                            # preview_dataset yields messages, list() collects them
                            message_chunks = future.result()
                            for chunk in message_chunks:
                                if isinstance(chunk, str):
                                    yield chunk # Yield each message from the preview process
                            completed_downloads += 1
                            yield create_status_message(f"Completed preview for {completed_downloads}/{len(relevant_datasets)} datasets.", start_time, progress=completed_downloads/len(relevant_datasets))
                        except Exception as e:
                            logger.error(f"Error processing download/preview future: {str(e)}")
                            yield create_error_message("Error during dataset download/preview.", details=str(e), start_time=start_time)

                yield create_status_message(
                    f'Finished download/preview phase for {len(relevant_datasets)} datasets.', start_time
                )


        # --- Final Completion Message ---
        final_execution_time = time.time() - start_time
        yield json.dumps({
            'type': 'complete',
            'data': {
                'query': query,
                'execution_time': final_execution_time,
                'total_found_unique': total_found_unique,
                'total_relevant': total_relevant,
                # Include the final dataset list in the completion message
                # This allows the client to have the full, assessed list at the end
                'datasets': final_dataset_list
            },
            'message': f'Search complete. Found {total_relevant} relevant dataset(s) in {final_execution_time:.1f} seconds.',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'

    except Exception as e:
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Critical error in stream_search_datasets_helper: {error_message}")
        logger.error(traceback_str)
        yield create_error_message(
            "An unexpected error occurred during the search process. Please try again.",
            details=error_message,
            start_time=start_time if 'start_time' in locals() else None
        )
        # Optionally re-raise or return an error indicator if needed by the caller
        # raise e # Or return some error structure

    finally:
        # Ensure executor is shut down
        assessment_executor.shutdown(wait=False) # Don't wait indefinitely if tasks are stuck
        logger.info("Assessment executor shutdown.")
        # Shutdown download executor if it was created
        if 'download_executor' in locals() and download_executor:
             download_executor.shutdown(wait=False)
             logger.info("Download executor shutdown.")


# --- Firebase Cloud Function Definition (Example) ---

# Set options for the Cloud Function (e.g., region, memory, timeout)
options.set_global_options(region="us-central1", memory=options.MemoryOption.GB_1, timeout_sec=300)

@https_fn.on_request(cors=options.CorsOptions(cors_origins="*", cors_methods=["post"]))
def stream_search_datasets(req: https_fn.Request) -> https_fn.Response:
    """
    Firebase HTTP Cloud Function endpoint for streaming dataset search.
    """
    if req.method != 'POST':
        return https_fn.Response("Method Not Allowed", status=405)

    try:
        # Extract parameters from request body
        req_data = req.get_json(silent=True)
        if not req_data:
            return https_fn.Response("Bad Request: No JSON body.", status=400)

        query = req_data.get('query')
        if not query:
            return https_fn.Response("Bad Request: Missing 'query' parameter.", status=400)

        # Optional parameters
        similarity_threshold = req_data.get('similarity_threshold', 0.25)
        search_method = req_data.get('search_method', None) # None for hybrid
        max_results = req_data.get('max_results', 50)
        relevance_threshold = req_data.get('relevance_threshold', 0.4)
        mode = req_data.get('mode', 'search') # 'search' or 'search_and_download'

        logger.info(f"Received search request: query='{query}', method='{search_method}', mode='{mode}'")

        # Define the generator function to stream responses
        def generate():
            try:
                # Call the helper function which yields JSON strings
                yield from stream_search_datasets_helper(
                    query=query,
                    similarity_threshold=similarity_threshold,
                    search_method=search_method,
                    max_results=max_results,
                    relevance_threshold=relevance_threshold,
                    mode=mode
                )
            except Exception as e:
                 # Catch any unexpected errors during generation
                 logger.error(f"Error during stream generation: {str(e)}")
                 logger.error(traceback.format_exc())
                 # Yield a final error message to the client
                 error_msg = create_error_message(
                     "An unexpected server error occurred during streaming.",
                     details=str(e),
                     start_time=None # start_time might not be available here
                 )
                 yield error_msg

        # Return a streaming response
        return https_fn.Response(
            generate(),
            mimetype='application/jsonlines' # Use jsonlines for streaming JSON
            # OR use 'text/event-stream' if implementing Server-Sent Events (SSE)
        )

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        logger.error(traceback.format_exc())
        return https_fn.Response(f"Internal Server Error: {str(e)}", status=500)

# --- Main block for local testing (Optional) ---
if __name__ == '__main__':
    print("Starting local test stream...")
    # Example local execution
    test_query = "renewable energy production statistics usa 2022"
    # Make sure DATA_GOV_API_KEY and PINECONE_API_KEY/ENVIRONMENT are set as env vars
    if 'DATA_GOV_API_KEY' not in os.environ:
         print("Warning: DATA_GOV_API_KEY environment variable not set.")
         # Optionally set a dummy key for testing if keyword search isn't critical
         # os.environ['DATA_GOV_API_KEY'] = 'YOUR_KEY_HERE_OR_DUMMY'

    results_generator = stream_search_datasets_helper(
        query=test_query,
        search_method=None, # Hybrid search
        mode='search_and_download', # Test download mode
        max_results=10 # Limit for testing
    )

    start = time.time()
    final_result_data = None
    try:
        for chunk in results_generator:
            print(f"[{time.time() - start:.2f}s] Received chunk:\n{chunk.strip()}")
            # Check for the completion message to grab final data for inspection
            if chunk.strip():
                try:
                     json_chunk = json.loads(chunk.strip())
                     if json_chunk.get('type') == 'complete':
                          final_result_data = json_chunk.get('data')
                except json.JSONDecodeError:
                     pass # Ignore non-JSON lines (like potential debug prints)

    except Exception as e:
         print(f"\nError during local test execution: {e}")
         print(traceback.format_exc())
    finally:
        print(f"\nLocal test finished in {time.time() - start:.2f} seconds.")
        if final_result_data:
             print("\n--- Final Completion Data ---")
             # Pretty print the final data summary
             print(json.dumps(final_result_data, indent=2, cls=NumpyEncoder))
             print(f"Total unique datasets found: {final_result_data.get('total_found_unique')}")
             print(f"Total relevant datasets: {final_result_data.get('total_relevant')}")
             # print("\nFinal Dataset List:")
             # for ds in final_result_data.get('datasets',[]):
             #      print(f"- ID: {ds.get('id')}, Title: {ds.get('title')}, Relevant: {ds.get('relevance',{}).get('is_relevant')}, Score: {ds.get('relevance',{}).get('relevance_score')}")