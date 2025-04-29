from firebase_functions import https_fn, options
from firebase_admin import initialize_app, firestore
import requests
from datetime import datetime
import firebase_admin
import os
import logging
import time
import json
import traceback
import numpy as np
import concurrent.futures
from threading import Lock

# Factchecker imports
from factchecker.search.census_search import process_query as process_census_query
from factchecker.search.search_utils import parallel_search, single_search
from factchecker.search import search_datasets
from factchecker.search.pinecone_search import vector_search_datasets_pinecone as vector_search_datasets
from factchecker.search.census_search import vector_search as census_vector_search
from factchecker.processing.analysis.dataset_result_analyzer import assess_datafile_relevance_predownload, get_best_resource
from factchecker.processing.analysis.dataset_loader import load_datafile, assess_datafile_relevance
from factchecker.download.download_gov_data import download_resource
import pandas as pd
import queue
from factchecker.enrich.enrich import enrich_dataset_metadata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add this class to handle NaN values in JSON serialization
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            if np.isnan(obj) or np.isinf(obj):
                return None  # Convert NaN and Inf to None (null in JSON)
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # Add handling for CensusDataset objects
        if hasattr(obj, '__class__') and obj.__class__.__name__ == 'CensusDataset':
            # Convert CensusDataset to a dictionary with its attributes
            return {key: getattr(obj, key) for key in dir(obj) 
                    if not key.startswith('_') and not callable(getattr(obj, key))}
        return super(NumpyEncoder, self).default(obj)

def create_status_message(message, start_time):
    """Create a status message JSON object"""
    return json.dumps({
        'type': 'status',
        'message': message,
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'

def create_error_message(message, details=None, start_time=None):
    """Create an error message JSON object"""
    timestamp = time.time() - start_time if start_time else time.time()
    error_obj = {
        'type': 'error',
        'message': message,
        'timestamp': timestamp
    }
    if details:
        error_obj['details'] = details
    return json.dumps(error_obj, cls=NumpyEncoder) + '\n'

def process_and_yield_dataset(dataset, source, all_datasets_count, start_time, query=None, relevance_threshold=None, executor=None):
    """Process a dataset and yield appropriate messages without relevance assessment"""
    dataset_id = dataset['id']
    dataset_title = dataset['title']
    
    # Set search source
    dataset['search_source'] = source
    
    # Check if resources are cached and set is_cached flag
    resources = dataset.get('resources', [])
    dataset['is_cached'] = any(resource.get('is_cached', False) for resource in resources)
    
    # Yield status update about finding this dataset
    yield json.dumps({
        'type': 'discovery',
        'message': f'I\'ve found a dataset: {dataset_title}',
        'count': all_datasets_count,
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'
    
    # Then yield the enriched dataset
    yield json.dumps({
        'type': 'dataset',
        'data': dataset,
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'

def assess_and_create_update(query, dataset, relevance_threshold, start_time):
    """Helper function to assess relevance and create update message, intended for thread pool"""
    # Pull out only the fields we need to minimize memory footprint
    dataset_id = dataset.get('id', 'unknown')
    dataset_title = dataset.get('title', 'Unnamed Dataset')
    # Time tracking for performance monitoring
    assessment_start = time.time()
    
    try:
        # Call the pre-download assessment function
        assessment_result = assess_datafile_relevance_predownload(
            query, 
            dataset,
            relevance_threshold=relevance_threshold
        )
        
        # Extract values from the result dictionary
        is_relevant = assessment_result["is_relevant"]
        relevance_score = assessment_result["relevance_score"]
        reasoning = assessment_result["reasoning"]
        
        # Store the relevance information in the dataset
        dataset['relevance'] = {
            'is_relevant': is_relevant,
            'relevance_score': relevance_score,
            'reasoning': reasoning
        }
        
        # If resource_url is in the assessment result, add it to the dataset
        if "resource_url" in assessment_result:
            dataset['resource_url'] = assessment_result["resource_url"]
        
        # Create update message
        update_message = json.dumps({
            'type': 'dataset_update',
            'data': {
                'id': dataset_id,
                'relevance': dataset['relevance']
            },
            'message': f'{"✓" if is_relevant else "✗"} Dataset {dataset_title} is {"likely relevant" if is_relevant else "not relevant"} (Score: {relevance_score:.2f})',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        # If the dataset is relevant, enrich it with download and loading information
        if is_relevant:
            try:
                enriched_dataset = enrich_dataset_after_relevance_check(dataset, query, start_time)
                
                # Add the enrichment information to the return message
                enrichment_message = json.dumps({
                    'type': 'dataset_enrichment',
                    'data': {
                        'id': dataset_id,
                        'download_status': enriched_dataset.get('download_status', {}),
                        'content_info': enriched_dataset.get('content_info', {})
                    },
                    'message': f'Enhanced dataset {dataset_title} with detailed metadata',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                return [update_message, enrichment_message], enriched_dataset
            except Exception as e:
                logger.error(f"Error during dataset enrichment: {str(e)}")
                # Return the original update message if enrichment fails
                return [update_message], dataset
        
        assessment_duration = time.time() - assessment_start
        logger.info(f"Dataset {dataset_id} assessment completed in {assessment_duration:.2f}s")
        return [update_message], dataset
        
    except Exception as e:
        assessment_duration = time.time() - assessment_start
        logger.error(f"Error assessing relevance (after {assessment_duration:.2f}s): {str(e)}")
        # Store error information in the dataset
        dataset['relevance'] = {
            'is_relevant': False,
            'relevance_score': 0.0,
            'reasoning': f"Error during assessment: {str(e)}",
            'error': str(e)
        }
        
        # Create and return error update
        error_message = json.dumps({
            'type': 'dataset_update',
            'data': {
                'id': dataset_id,
                'relevance': dataset['relevance']
            },
            'message': f'Error assessing dataset {dataset_title}: {str(e)}',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        return [error_message], dataset

def search_census_data(query, similarity_threshold, max_results, start_time):
    """Search Census data and yield status updates and results"""
    yield create_status_message('Census search functionality is temporarily disabled.', start_time)
    return []

def search_vector_datasets(query, similarity_threshold, max_results, start_time, relevance_threshold=0.4):
    """Search datasets using vector search and yield results"""
    yield create_status_message('I\'m searching through data.gov datasets...', start_time)
    
    try:
        # Initialize Pinecone early
        from factchecker.search.pinecone_search import get_pinecone_client
        pc = get_pinecone_client()
        logger.info(f"Pinecone client initialized at timestamp: {time.time() - start_time:.2f} seconds")
        
        # Log start of parallel search
        logger.info(f"Starting parallel search at timestamp: {time.time() - start_time:.2f} seconds")
        
        # Initialize vector_datasets list
        vector_datasets = []
        
        # Perform parallel search with streaming enabled
        results = parallel_search(
            query,
            search_function=vector_search_datasets,
            start_time=start_time,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
            use_variations=True,
            verbose=False,
            stream_results=True,  # Enable streaming results
            pinecone_client=pc  # Pass the initialized client
        )
        
        # For streaming, we need to process the results as they come in
        seen_vector_ids = set()
        all_datasets_count = 0
        
        # Process results by query variation batches
        current_variation = None
        current_batch = []
        
        # Process each result as it's yielded
        for result in results:
            dataset_id = result['id']
            if dataset_id not in seen_vector_ids:
                seen_vector_ids.add(dataset_id)
                all_datasets_count += 1
                vector_datasets.append(result)
                
                # Get the query variation
                query_variation = result.get('query_variation', query)
                
                # First just yield the dataset without relevance assessment for immediate display
                for chunk in process_and_yield_dataset(result, 'vector', all_datasets_count, start_time):
                    yield chunk
                
                # Check if this is a new variation batch
                if current_variation != query_variation and current_batch:
                    # Process the previous complete batch
                    logger.info(f"Processing vector batch for variation '{current_variation}' with {len(current_batch)} datasets")
                    batch_start = time.time()
                    
                    # Process this batch in parallel
                    for update in process_dataset_batch(current_batch, query, relevance_threshold, start_time):
                        yield update
                        
                    logger.info(f"Vector batch processed in {time.time() - batch_start:.2f}s")
                    current_batch = []
                
                # Track this result in the current batch
                current_batch.append(result)
                current_variation = query_variation
        
        # Process the final batch
        if current_batch:
            logger.info(f"Processing final vector batch for variation '{current_variation}' with {len(current_batch)} datasets")
            batch_start = time.time()
            
            # Process this batch in parallel
            for update in process_dataset_batch(current_batch, query, relevance_threshold, start_time):
                yield update
                
            logger.info(f"Final vector batch processed in {time.time() - batch_start:.2f}s")
        
        # Log completion of parallel search
        logger.info(f"Parallel search completed at timestamp: {time.time() - start_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in vector search: {e}")
        yield []  # Yield empty list instead of returning it

def search_keyword_datasets(query, gov_api_key, keyword_threshold, start_time):
    """Search datasets using keyword search and yield results"""
    yield create_status_message('I\'m checking additional sources...', start_time)
    
    try:
        # Get keyword search results
        keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
        # Return the results - they'll be processed by the caller
        # Wrap the results in a JSON object so it's a string not a list
        yield json.dumps({
            'type': 'keyword_results',
            'data': keyword_results,
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
    except Exception as e:
        yield create_error_message(
            f'I ran into a problem finding additional datasets: {str(e)}',
            start_time=start_time
        )

def assess_dataset_relevance(query, dataset, relevance_threshold, start_time, dataset_index, total_datasets):
    """Assess dataset relevance before downloading and yield status updates"""
    dataset_id = dataset.get('id', 'unknown')
    dataset_title = dataset.get('title', 'Unnamed Dataset')
    
    # Yield status update
    yield json.dumps({
        'type': 'status',
        'message': f'Assessing relevance of dataset {dataset_index+1}/{total_datasets}: {dataset_title}',
        'timestamp': time.time() - start_time
    }, cls=NumpyEncoder) + '\n'
    
    try:
        # Call the pre-download assessment function
        assessment_result = assess_datafile_relevance_predownload(
            query, 
            dataset,
            relevance_threshold=relevance_threshold
        )
        
        # Extract values from the result dictionary
        is_relevant = assessment_result["is_relevant"]
        relevance_score = assessment_result["relevance_score"]
        reasoning = assessment_result["reasoning"]
        
        # Store the relevance information in the dataset
        dataset['relevance'] = {
            'is_relevant': is_relevant,
            'relevance_score': relevance_score,
            'reasoning': reasoning
        }
        
        # If resource_url is in the assessment result, add it to the dataset
        if "resource_url" in assessment_result:
            dataset['resource_url'] = assessment_result["resource_url"]
        
        # Yield dataset update with relevance information
        yield json.dumps({
            'type': 'dataset_update',
            'data': {
                'id': dataset_id,
                'relevance': dataset['relevance']
            },
            'message': f'{"✓" if is_relevant else "✗"} Dataset {dataset_title} is {"likely relevant" if is_relevant else "not relevant"} (Score: {relevance_score:.2f})',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        return dataset
        
    except Exception as e:
        logger.error(f"Error assessing relevance: {str(e)}")
        # Store error information in the dataset
        dataset['relevance'] = {
            'is_relevant': False,
            'relevance_score': 0.0,
            'reasoning': f"Error during assessment: {str(e)}",
            'error': str(e)
        }
        
        # Yield error update
        yield json.dumps({
            'type': 'dataset_update',
            'data': {
                'id': dataset_id,
                'relevance': dataset['relevance']
            },
            'message': f'Error assessing dataset {dataset_title}: {str(e)}',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        return dataset

# Add this new function for concurrent assessment
def assess_datasets_concurrently(query, datasets, relevance_threshold, start_time, max_workers=20):
    """Assess multiple datasets concurrently and yield status updates"""
    total_datasets = len(datasets)
    processed_datasets = []
    
    # Create batches of datasets to process concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_dataset = {
            executor.submit(
                assess_datafile_relevance_predownload,
                query, 
                dataset,
                relevance_threshold=relevance_threshold
            ): (dataset, i) 
            for i, dataset in enumerate(datasets)
        }
        
        # Process completed tasks as they finish
        for future in concurrent.futures.as_completed(future_to_dataset):
            dataset, dataset_index = future_to_dataset[future]
            dataset_id = dataset.get('id', 'unknown')
            dataset_title = dataset.get('title', 'Unnamed Dataset')
            
            try:
                # Get the result from the completed task
                assessment_result = future.result()
                
                # Extract values from the result dictionary
                is_relevant = assessment_result["is_relevant"]
                relevance_score = assessment_result["relevance_score"]
                reasoning = assessment_result["reasoning"]
                
                # Store the relevance information in the dataset
                dataset['relevance'] = {
                    'is_relevant': is_relevant,
                    'relevance_score': relevance_score,
                    'reasoning': reasoning
                }
                
                # If resource_url is in the assessment result, add it to the dataset
                if "resource_url" in assessment_result:
                    dataset['resource_url'] = assessment_result["resource_url"]
                
                # Yield dataset update with relevance information
                yield json.dumps({
                    'type': 'dataset_update',
                    'data': {
                        'id': dataset_id,
                        'relevance': dataset['relevance']
                    },
                    'message': f'{"✓" if is_relevant else "✗"} Dataset {dataset_title} is {"likely relevant" if is_relevant else "not relevant"} (Score: {relevance_score:.2f})',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                processed_datasets.append(dataset)
                
            except Exception as e:
                logger.error(f"Error assessing relevance: {str(e)}")
                # Store error information in the dataset
                dataset['relevance'] = {
                    'is_relevant': False,
                    'relevance_score': 0.0,
                    'reasoning': f"Error during assessment: {str(e)}",
                    'error': str(e)
                }
                
                # Yield error update
                yield json.dumps({
                    'type': 'dataset_update',
                    'data': {
                        'id': dataset_id,
                        'relevance': dataset['relevance']
                    },
                    'message': f'Error assessing dataset {dataset_title}: {str(e)}',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                processed_datasets.append(dataset)
    
    return processed_datasets

def process_dataset_batch(datasets, query, relevance_threshold, start_time):
    """
    Process a batch of datasets for relevance in parallel and enrich relevant ones.
    
    Args:
        datasets: List of datasets to assess
        query: User query
        relevance_threshold: Threshold for relevance
        start_time: Start time for timestamp calculation
        
    Returns:
        Generator of results messages (dataset_update and dataset_enrichment)
    """
    # Create a thread pool just for this batch
    # Use a slightly larger pool size if needed, but len(datasets) might be too many
    max_workers_batch = min(len(datasets), 20) # Cap workers per batch
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_batch) as executor:
        # Submit all assessments to the thread pool
        future_to_dataset = {
            executor.submit(
                assess_datafile_relevance_predownload,
                query,
                dataset,
                relevance_threshold=relevance_threshold
            ): dataset 
            for dataset in datasets
        }
        
        # Process as they complete
        for future in concurrent.futures.as_completed(future_to_dataset):
            dataset = future_to_dataset[future]
            dataset_id = dataset.get('id', 'unknown')
            dataset_title = dataset.get('title', 'Unnamed Dataset')
            
            try:
                # Get the assessment result
                assessment_result = future.result()
                
                # Extract values from the result dictionary
                is_relevant = assessment_result["is_relevant"]
                relevance_score = assessment_result["relevance_score"]
                reasoning = assessment_result["reasoning"]
                
                # Store the relevance information in the dataset
                dataset['relevance'] = {
                    'is_relevant': is_relevant,
                    'relevance_score': relevance_score,
                    'reasoning': reasoning
                }
                
                # If resource_url is in the assessment result, add it to the dataset
                if "resource_url" in assessment_result:
                    dataset['resource_url'] = assessment_result["resource_url"]
                
                # Yield dataset update with relevance information FIRST
                update_message = json.dumps({
                    'type': 'dataset_update',
                    'data': {
                        'id': dataset_id,
                        'relevance': dataset['relevance']
                    },
                    'message': f'{"✓" if is_relevant else "✗"} Dataset {dataset_title} is {"likely relevant" if is_relevant else "not relevant"} (Score: {relevance_score:.2f})',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                yield update_message

                # If the dataset is relevant, NOW proceed to enrich it
                if is_relevant:
                    try:
                        # Call the enrichment function (which handles download, load, enrich)
                        enriched_dataset = enrich_dataset_after_relevance_check(dataset, query, start_time)
                        
                        # Yield the enrichment message
                        enrichment_message = json.dumps({
                            'type': 'dataset_enrichment',
                            'data': {
                                'id': dataset_id,
                                # Include key enrichment info if available
                                'download_status': enriched_dataset.get('download_status', {}), 
                                'content_info': enriched_dataset.get('content_info', {})    
                            },
                            'message': f'Enhanced dataset {dataset_title} with detailed metadata',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        yield enrichment_message
                        
                    except Exception as enrich_e:
                        logger.error(f"Error during enrichment for dataset {dataset_id}: {str(enrich_e)}")
                        # Yield an error message specific to enrichment failure
                        yield json.dumps({
                             'type': 'dataset_enrichment', # Use same type but indicate error
                             'data': {
                                 'id': dataset_id,
                                 'enrichment_error': str(enrich_e)
                             },
                             'message': f'Error enhancing dataset {dataset_title}: {str(enrich_e)}',
                             'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'

            except Exception as assess_e:
                logger.error(f"Error assessing dataset {dataset_id}: {str(assess_e)}")
                # Store error information in the dataset
                dataset['relevance'] = {
                    'is_relevant': False,
                    'relevance_score': 0.0,
                    'reasoning': f"Error during assessment: {str(assess_e)}",
                    'error': str(assess_e)
                }
                
                # Yield error update for assessment failure
                yield json.dumps({
                    'type': 'dataset_update',
                    'data': {
                        'id': dataset_id,
                        'relevance': dataset['relevance'] # Include error info here
                    },
                    'message': f'Error assessing dataset {dataset_title}: {str(assess_e)}',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'

def stream_search_datasets_helper(query, similarity_threshold=0.25, search_method=None, 
                                 max_results=50, census_max_results=5, relevance_threshold=0.4):
    """
    Helper function that generates the streaming search results
    """
    try:
        start_time = time.time()
        all_datasets_count = 0
        
        # Data structures to hold batches of datasets for parallel processing
        vector_batch = []
        keyword_batch = []
        batch_size = 20  # Process 20 datasets at a time
        
        # Initialize thread pool for relevance assessment and enrichment
        relevance_executor = concurrent.futures.ThreadPoolExecutor(max_workers=batch_size)
        futures = []
        
        # Send initial message
        yield create_status_message(
            f'I\'m starting my search for relevant datasets about "{query}"...',
            start_time
        )
        
        # Initialize API key for Data.gov
        gov_api_key = os.environ.get('DATA_GOV_API_KEY', '')
        
        if not gov_api_key:
            yield create_error_message(
                'I\'m having trouble with the API key configuration. Please try again later.',
                start_time=start_time
            )
            relevance_executor.shutdown() # Shutdown executor before returning
            return
        
        # Higher threshold for keyword search
        keyword_threshold = similarity_threshold + 0.2
        
        vector_datasets = []
        keyword_datasets = []
        census_datasets = []
        processed_dataset_ids = set()
        
        # Census functionality is temporarily disabled
        census_datasets = []
        
        # No more complex functions for assessment - everything is done directly in process_and_yield_dataset
        
        # Now launch Data.gov searches
        # Note: Removed the outer 'with concurrent.futures.ThreadPoolExecutor() as executor:' 
        # because we now use a dedicated relevance_executor managed below.
        
        # Vector search
        if search_method in ['vector', None]:  # Vector or hybrid
            try:
                # Get vector search results - this is now a generator that yields both status and results
                vector_generator = search_vector_datasets(query, similarity_threshold, max_results, start_time, relevance_threshold)
                
                # Process the generator - first item is status message, second is the actual results
                for item in vector_generator:
                    if isinstance(item, str):
                        # This is a status message
                        yield item
                    else:
                        # This is the actual results list
                        vector_results = item
                        
                        # Get the query variations used and yield them as a status message
                        if isinstance(vector_results, list) and len(vector_results) > 0 and 'query_variation' in vector_results[0]:
                            query_variations = list(set(result['query_variation'] for result in vector_results))
                            # Add quotes around each query variation
                            quoted_variations = [f'"{variation}"' for variation in query_variations]
                            yield create_status_message(
                                f"Trying related search terms: {', '.join(quoted_variations)}",
                                start_time
                            )
                        
                        # Process and yield each result immediately
                        if isinstance(vector_results, list) and all(isinstance(item, dict) for item in vector_results):
                            # Start processing results immediately
                            for result in vector_results:
                                dataset_id = result.get('id')
                                if dataset_id and dataset_id not in processed_dataset_ids:
                                    processed_dataset_ids.add(dataset_id)
                                    vector_datasets.append(result)
                                    all_datasets_count += 1
                                    
                                    # Process the dataset and submit async assessment
                                    for chunk in process_and_yield_dataset(result, 'vector', all_datasets_count, start_time):
                                        yield chunk
                                    
                                    # Submit assessment to the thread pool
                                    future = relevance_executor.submit(
                                        assess_and_create_update,
                                        query,
                                        result,
                                        relevance_threshold,
                                        start_time
                                    )
                                    futures.append(future)
                                    
                                    # Check for completed futures periodically 
                                    # (every 5 datasets or if we have more than 10 pending)
                                    # Process completed futures non-blockingly
                                    done_futures = [f for f in futures if f.done()]
                                    for future_obj in done_futures:
                                        futures.remove(future_obj) # Remove from list
                                        try:
                                            # Expect a list of messages now
                                            messages, updated_dataset = future_obj.result() 
                                            # Yield each message in the list
                                            for message in messages:
                                                yield message
                                        except Exception as e:
                                            # Log error from completed future
                                            logger.error(f"Error processing completed future: {str(e)}")
                                            # Optionally yield an error message to frontend
                                            # yield create_error_message(f"Error processing dataset result: {str(e)}", start_time=start_time)

            except Exception as e:
                logger.error(f"Error in vector search processing: {str(e)}")
                yield create_error_message(f"Error processing vector search results: {str(e)}", start_time=start_time)

        # After submitting all keyword searches (if any)
        # Process any remaining futures
        while futures:
            done_futures, futures = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)
            for future_obj in done_futures:
                try:
                    # Expect a list of messages now
                    messages, updated_dataset = future_obj.result()
                    # Yield each message in the list
                    for message in messages:
                        yield message
                except Exception as e:
                    # Log error from completed future
                    logger.error(f"Error processing remaining future: {str(e)}")
                    # Optionally yield an error message
                    # yield create_error_message(f"Error processing final dataset result: {str(e)}", start_time=start_time)

        relevance_executor.shutdown() # Shutdown the executor cleanly

        # Calculate execution time and send search completion message
        search_execution_time = time.time() - start_time
        
        # Determine total unique datasets (combining all sources)
        if search_method is None:  # hybrid search
            # Start with vector datasets
            all_datasets = vector_datasets.copy()
            all_dataset_ids = {dataset['id'] for dataset in all_datasets}
            
            # Add keyword datasets that weren't in vector results
            for dataset in keyword_datasets:
                if dataset['id'] not in all_dataset_ids:
                    all_datasets.append(dataset)
                    all_dataset_ids.add(dataset['id'])
            
            # Add census datasets (they have unique IDs with 'census-' prefix)
            all_datasets.extend(census_datasets)
            
            # Sort by similarity score (higher is better)
            all_datasets.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            total_count = len(all_datasets)
        else:
            # Either vector or keyword only (plus census)
            all_datasets = vector_datasets if search_method == 'vector' else keyword_datasets
            all_datasets.extend(census_datasets)  # Add census datasets
            total_count = len(all_datasets)
        
        # Send search phase completion message
        yield json.dumps({
            'type': 'phase_complete',
            'phase': 'search',
            'data': {
                'query': query,
                'execution_time': search_execution_time,
                'total_count': total_count
            },
            'message': f'I\'ve found some potential datasets. I found {total_count} datasets that might be relevant.',
            'timestamp': search_execution_time
        }, cls=NumpyEncoder) + '\n'
        
        # Log final search status
        logger.info(f"Completed all dataset relevance checks at timestamp: {time.time() - start_time:.2f} seconds")
        
        # Filter relevant datasets
        relevant_datasets = [d for d in all_datasets if d.get('relevance', {}).get('is_relevant', False)]
        
        # Final execution time
        final_execution_time = time.time() - start_time
        
        # Send completion message
        yield json.dumps({
            'type': 'complete',
            'data': {
                'query': query,
                'execution_time': final_execution_time,
                'total_count': total_count,
                'processed_count': len(all_datasets),
                'relevant_count': len(relevant_datasets)
            },
            'message': f'I\'ve completed my search! I found {len(relevant_datasets)} dataset{"s" if len(relevant_datasets) != 1 else ""} in {final_execution_time:.1f} seconds.',
            'timestamp': final_execution_time
        }, cls=NumpyEncoder) + '\n'
        
        # Return the final summary data for the JSON response
        return {
            'query': query,
            'execution_time': final_execution_time,
            'total_count': total_count,
            'processed_count': len(all_datasets),
            'relevant_count': len(relevant_datasets),
            'datasets': all_datasets
        }
        
    except Exception as e:
        # Ensure executor is shut down even on general errors
        if 'relevance_executor' in locals() and relevance_executor:
             relevance_executor.shutdown(wait=False) # Don't wait if there was an error
        # ... existing error handling ...
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error in stream_search_datasets: {error_message}")
        logger.error(traceback_str)
        
        yield create_error_message(
            "I'm sorry, I encountered an error while processing your request. Please try again.",
            details=error_message,
            start_time=start_time if 'start_time' in locals() else None
        )
        
        # Return error data for the JSON response
        return {
            'error': error_message,
            'traceback': traceback_str
        }

def parquet_to_csv(parquet_file_path):
    """
    Convert a Parquet file to CSV format.
    
    Args:
        parquet_file_path: Path to the Parquet file
        
    Returns:
        Path to the converted CSV file
    """
    try:
        # Log the conversion process
        logger.info(f"Converting Parquet file to CSV: {parquet_file_path}")
        
        # Read the Parquet file
        df = pd.read_parquet(parquet_file_path)
        
        # Create CSV file path by replacing the extension
        csv_file_path = os.path.splitext(parquet_file_path)[0] + '.csv'
        
        # Write to CSV
        df.to_csv(csv_file_path, index=False)
        
        logger.info(f"Successfully converted Parquet to CSV: {csv_file_path}")
        
        return csv_file_path
        
    except Exception as e:
        logger.error(f"Error converting Parquet to CSV: {str(e)}")
        # Return the original file path if conversion fails
        return parquet_file_path

def download_resource_helper(dataset_id, best_resource, output_dir="./downloads"):
    """
    Helper function for downloading resources for a given dataset
    
    Args:
        dataset_id: ID of the dataset
        best_resource: Dictionary containing resource information
        output_dir: Directory to save downloaded files
        
    Returns:
        Path to the downloaded file or None if download failed
    """
    # Extract resource information
    resource_url = best_resource.get('resource_url')
    resource_id = best_resource.get('resource_id')
    resource_format = best_resource.get('format', '').lower()
    
    # Check if resource is cached
    if best_resource.get('is_cached') and best_resource.get('cache_uri'):
        cache_uri = best_resource.get('cache_uri')
        logger.info(f"Using cached resource from GCS: {cache_uri}")
        
        try:
            from google.cloud import storage
            
            # Extract bucket and blob path from gs:// URI
            parts = cache_uri[5:].split('/', 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ''
            
            # Create local path with proper extension
            os.makedirs(output_dir, exist_ok=True)
            
            # Determine file extension from cache_uri or format
            file_ext = os.path.splitext(blob_name)[1]
            if not file_ext and resource_format:
                file_ext = f".{resource_format}"
            
            local_path = os.path.join(output_dir, f"{dataset_id}{file_ext}")
            
            # Download the file
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # Download to local file
            blob.download_to_filename(local_path)
            logger.info(f"Successfully downloaded cached file from GCS to {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"Error retrieving cached file from GCS: {str(e)}")
            logger.info(f"Falling back to direct download from URL")
            # Continue to regular download if GCS retrieval fails
    
    # If not cached or cache retrieval failed, download the resource
    if not resource_url:
        logger.warning(f"No URL provided for resource {resource_id}")
        return None
    
    logger.info(f"Downloading resource from {resource_url}")
    max_download_time = 15
    
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Determine file extension from URL or format
        url_ext = os.path.splitext(resource_url.split('?')[0])[1]
        file_ext = url_ext if url_ext else f".{resource_format}" if resource_format else ""
        
        # Download the resource with proper extension
        output_path = download_resource(
            resource_url, 
            output_dir, 
            filename=f"{dataset_id}{file_ext}", 
            max_download_time=max_download_time
        )
        
        if output_path:
            logger.info(f"Downloaded file to {output_path}")
            return output_path
        else:
            logger.warning(f"Download failed for dataset {dataset_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error downloading resource: {str(e)}")
        return None

def enrich_dataset_after_relevance_check(dataset, query, start_time):
    """
    Enrich a dataset that has passed the pre-download relevance check by downloading
    and loading the best resource.
    
    Args:
        dataset: The dataset object that passed relevance check (contains title, description, org, etc.)
        query: The user query
        start_time: Start time for timing calculations
        
    Returns:
        Updated dataset object with download and loading information
    """
    dataset_id = dataset.get('id', 'unknown')
    dataset_title = dataset.get('title', 'Unnamed Dataset')
    
    try:
        # Step 1: Find the best resource
        best_resource = get_best_resource(query, dataset)
        
        # Add the best resource to the dataset object
        dataset['best_resource'] = best_resource
        
        # Step 2: Download the resource
        file_path = download_resource_helper(dataset_id, best_resource)
        
        if not file_path:
            dataset['download_status'] = {
                'success': False,
                'error': 'Failed to download dataset file'
            }
            # Add placeholder content_info for consistency if download fails
            dataset['content_info'] = {
                'loaded': False,
                'error': 'Download failed',
                'dimensions': {'rows': 0, 'columns': 0}, 'column_names': [],
                'quality': {'quality_score': 0, 'quality_label': 'unknown', 'error': 'Download failed'},
                'granularity': {'granularity': 'unknown', 'confidence': 0, 'reasoning': 'Download failed'},
                'time_range': {'has_time_data': False, 'reason': 'Download failed'}
            }
            return dataset
        
        # Add download information to the dataset
        dataset['download_status'] = {
            'success': True,
            'file_path': file_path
        }
        
        # Step 3: Convert Parquet to CSV if needed
        if ".parquet" in file_path:
            csv_file_path = parquet_to_csv(file_path)
            os.remove(file_path)  # Remove original parquet file
            file_path = csv_file_path
            dataset['download_status']['file_path'] = file_path
        
        # Step 4: Load the dataset
        try:
            file_format = best_resource.get('resource_format')
            dataset_content = load_datafile(file_path, file_format=file_format)
            
            # Step 5: Enrich dataset metadata using the loaded content AND the original dataset metadata
            if isinstance(dataset_content, pd.DataFrame):
                # Pass the original dataset dictionary as dataset_metadata
                enriched_metadata = enrich_dataset_metadata(dataset_content, query, dataset)
                
                # Add enriched metadata to the dataset object
                dataset['content_info'] = {
                    'loaded': True,
                    **enriched_metadata # Unpack the enriched results
                }
            else:
                # Handle non-DataFrame content (e.g., PDF or load error)
                dataset['content_info'] = {
                    'loaded': True, # Indicates loading was attempted
                    'dimensions': {'rows': 0, 'columns': 0}, 'column_names': [],
                    'quality': {'quality_score': 0, 'quality_label': 'unknown', 'error': 'Not a DataFrame'},
                    'granularity': {'granularity': 'unknown', 'confidence': 0, 'reasoning': 'Not a DataFrame'},
                    'time_range': {'has_time_data': False, 'reason': 'Not a DataFrame'},
                    'load_error': 'Content is not tabular data' if dataset_content else 'Loading failed'
                }
            
            logger.info(f"Successfully loaded and enriched dataset {dataset_id}")
            
        except Exception as e:
            logger.error(f"Error loading or enriching dataset {dataset_id}: {str(e)}")
            dataset['content_info'] = {
                'loaded': False,
                'error': str(e),
                 # Add placeholders even if loading fails
                'dimensions': {'rows': 0, 'columns': 0}, 'column_names': [],
                'quality': {'quality_score': 0, 'quality_label': 'unknown', 'error': f'Load error: {str(e)}'},
                'granularity': {'granularity': 'unknown', 'confidence': 0, 'reasoning': f'Load error: {str(e)}'},
                'time_range': {'has_time_data': False, 'reason': f'Load error: {str(e)}'}
            }
        
        return dataset
        
    except Exception as e:
        logger.error(f"Error in top-level enrichment function for dataset {dataset_id}: {str(e)}")
        dataset['enrichment_error'] = str(e)
        # Ensure content_info exists even on top-level error
        if 'content_info' not in dataset:
             dataset['content_info'] = {
                'loaded': False, 'error': str(e),
                'dimensions': {'rows': 0, 'columns': 0}, 'column_names': [],
                'quality': {'quality_score': 0, 'quality_label': 'unknown', 'error': str(e)},
                'granularity': {'granularity': 'unknown', 'confidence': 0, 'reasoning': str(e)},
                'time_range': {'has_time_data': False, 'error': str(e)}
            }
        return dataset