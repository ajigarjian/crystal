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
from factchecker.processing.analysis.dataset_result_analyzer import assess_datafile_relevance_predownload

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

def process_and_yield_dataset(dataset, source, all_datasets_count, start_time):
    """Process a dataset and yield appropriate messages"""
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

def search_census_data(query, similarity_threshold, max_results, start_time):
    """Search Census data and yield status updates and results"""
    yield create_status_message('Census search functionality is temporarily disabled.', start_time)
    return []

def search_vector_datasets(query, similarity_threshold, max_results, start_time):
    """Search datasets using vector search and yield results"""
    yield create_status_message('I\'m searching through data.gov datasets...', start_time)
    
    try:
        # Perform parallel search
        results = parallel_search(
            query,
            search_function=vector_search_datasets,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
            use_variations=True,
            verbose=False
        )
        
        # Convert generator to list if needed
        if hasattr(results, '__iter__') and not isinstance(results, list):
            results = list(results)
        
        yield results  # Yield the results instead of returning them
    except Exception as e:
        logger.error(f"Error in vector search: {e}")
        yield []  # Yield empty list instead of returning it

def search_keyword_datasets(query, gov_api_key, keyword_threshold, start_time):
    """Search datasets using keyword search and yield results"""
    yield create_status_message('I\'m checking additional data.gov datasets...', start_time)
    
    try:
        # Get keyword search results
        keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
        return keyword_results
    except Exception as e:
        yield create_error_message(
            f'I ran into a problem finding additional datasets: {str(e)}',
            start_time=start_time
        )
        return []

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
def assess_datasets_concurrently(query, datasets, relevance_threshold, start_time, max_workers=3):
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

def stream_search_datasets_helper(query, similarity_threshold=0.3, search_method=None, 
                                 max_results=15, census_max_results=5, relevance_threshold=0.35):
    """
    Helper function that generates the streaming search results
    """
    try:
        start_time = time.time()
        all_datasets_count = 0
        
        # Send initial message
        yield create_status_message(
            f'I\'m starting my search for relevant datasets about "{query}"...',
            start_time
        )

        # Reject requests where max_results exceeds 15
        if max_results > 15:
            print("ERROR! Max results may not exceed 15. Capping at 15.")
            max_results = 15
        
        # Initialize API key for Data.gov
        gov_api_key = os.environ.get('DATA_GOV_API_KEY', '')
        
        if not gov_api_key:
            yield create_error_message(
                'I\'m having trouble with the API key configuration. Please try again later.',
                start_time=start_time
            )
            return
        
        # Higher threshold for keyword search
        keyword_threshold = similarity_threshold + 0.2
        
        vector_datasets = []
        keyword_datasets = []
        census_datasets = []
        
        # Search Census data - this is a generator that yields status updates
        # We need to collect the actual datasets separately
        for chunk in search_census_data(query, similarity_threshold, census_max_results, start_time):
            yield chunk
        
        # Census functionality is temporarily disabled
        census_datasets = []
        
        # Now launch Data.gov searches
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Vector search
            if search_method in ['vector', None]:  # Vector or hybrid
                try:
                    # Get vector search results - this is now a generator that yields both status and results
                    vector_generator = search_vector_datasets(query, similarity_threshold, max_results, start_time)
                    
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
                                yield create_status_message(
                                    f"Trying related search terms: {', '.join(query_variations)}",
                                    start_time
                                )
                            
                            # Process and yield each result
                            seen_vector_ids = set()
                            # Check if vector_results is a list of dictionaries
                            if isinstance(vector_results, list) and all(isinstance(item, dict) for item in vector_results):
                                for result in vector_results:
                                    seen_vector_ids.add(result['id'])
                                    vector_datasets.append(result)
                                    all_datasets_count += 1
                                    for chunk in process_and_yield_dataset(result, 'vector', all_datasets_count, start_time):
                                        yield chunk
                            else:
                                # Log error about unexpected format
                                logger.error(f"Unexpected vector search results format: {type(vector_results)}")
                                yield create_error_message(
                                    "I received unexpected data format from the vector search. Continuing with other search methods.",
                                    start_time=start_time
                                )
                except Exception as e:
                    logger.error(f"Error in vector search: {str(e)}")
                    yield create_status_message(
                        "I encountered an issue with vector search. Continuing with other methods...",
                        start_time
                    )
            
            # Keyword search
            if search_method in ['keyword', None]:  # Keyword or hybrid
                try:
                    # Get keyword search results
                    for chunk in search_keyword_datasets(query, gov_api_key, keyword_threshold, start_time):
                        yield chunk
                    
                    keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
                    
                    # Ensure keyword_results is a list
                    if hasattr(keyword_results, '__iter__') and not isinstance(keyword_results, list):
                        keyword_results = list(keyword_results)
                    
                    keyword_datasets = keyword_results if isinstance(keyword_results, list) else []
                    
                    # In hybrid mode, only yield keyword results that weren't found by vector search
                    if search_method is None:  # hybrid mode
                        vector_ids = {dataset['id'] for dataset in vector_datasets}
                        
                        # Find datasets that appear in both searches
                        overlap_ids = set()
                        for dataset in keyword_datasets:
                            if dataset['id'] in vector_ids:
                                overlap_ids.add(dataset['id'])
                                # Update the search source for overlapping datasets
                                for vd in vector_datasets:
                                    if vd['id'] == dataset['id']:
                                        vd['search_source'] = 'both'
                                        # Re-yield the updated dataset
                                        yield json.dumps({
                                            'type': 'dataset_update',
                                            'data': vd,
                                            'timestamp': time.time() - start_time
                                        }, cls=NumpyEncoder) + '\n'
                                        break
                    
                        # Don't share technical details about vector/keyword distinction
                        if keyword_datasets:
                            yield create_status_message(
                                'I\'m discovering additional datasets that might help answer your question...',
                                start_time
                            )
                        
                        # Process and yield only new keyword datasets
                        for dataset in keyword_datasets:
                            if dataset['id'] not in vector_ids:
                                all_datasets_count += 1
                                for chunk in process_and_yield_dataset(dataset, 'keyword', all_datasets_count, start_time):
                                    yield chunk
                    else:
                        # In keyword-only mode, yield all results
                        for dataset in keyword_datasets:
                            all_datasets_count += 1
                            for chunk in process_and_yield_dataset(dataset, 'keyword', all_datasets_count, start_time):
                                yield chunk
                except Exception as e:
                    logger.error(f"Error in keyword search: {str(e)}")
                    yield create_status_message(
                        "I encountered an issue with keyword search. Continuing with available results...",
                        start_time
                    )
        
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
            'message': f'I\'ve completed my search! I found {total_count} datasets in {search_execution_time:.1f} seconds.',
            'timestamp': search_execution_time
        }, cls=NumpyEncoder) + '\n'
        
        # Now begin pre-download assessment of the datasets
        yield create_status_message(
            'I\'m now assessing the relevance of the discovered datasets...',
            start_time
        )
        
        # Use concurrent assessment instead of sequential
        try:
            # Process datasets concurrently in batches of 3
            relevant_datasets = []
            for chunk in assess_datasets_concurrently(
                query, 
                all_datasets, 
                relevance_threshold, 
                start_time, 
                max_workers=3
            ):
                yield chunk
            
            # Filter relevant datasets
            relevant_datasets = [d for d in all_datasets if d.get('relevance', {}).get('is_relevant', False)]
        except Exception as e:
            logger.error(f"Error in concurrent dataset assessment: {str(e)}")
            yield create_error_message(
                "I encountered an issue while assessing datasets. Some results may be incomplete.",
                details=str(e),
                start_time=start_time
            )
        
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
            'message': f'I\'ve completed my analysis! I assessed {len(all_datasets)} datasets in {final_execution_time:.1f} seconds.',
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
        # Send error message
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error in stream_search_datasets: {error_message}")
        logger.error(traceback_str)
        
        yield create_error_message(
            "I'm sorry, I encountered an error while processing your request. Please try again.",
            details=error_message,
            start_time=start_time
        )
        
        # Return error data for the JSON response
        return {
            'error': error_message,
            'traceback': traceback_str
        }