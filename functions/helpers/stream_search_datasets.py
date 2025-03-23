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
from factchecker.search.search_utils import single_search
from factchecker.search import search_datasets
from factchecker.search.pinecone_search import vector_search_datasets_pinecone as vector_search_datasets
from factchecker.search.census_search import vector_search as census_vector_search
from factchecker.processing.analysis.search_result_analyzer import assess_datafile_relevance_predownload

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

def search_census_data(query, similarity_threshold, census_max_results, start_time):
    """Search Census data sources and yield results"""
    # Extract structured info from query for Census search
    query_info = process_census_query(query)
    
    # Start Census search
    yield create_status_message('I\'m searching through Census databases...', start_time)
    
    census_datasets = []
    
    try:
        # Perform Census search with error handling
        try:
            # Get results as a list from census_vector_search
            census_results = census_vector_search(
                query=query,
                similarity_threshold=similarity_threshold,
                year=query_info.get('year'),
                tags=query_info.get('tags'),
                geo_level=query_info.get('geo_level'),
                location=query_info.get('location'),
                max_results=census_max_results,
                verbose=False
            )
            
            # Convert CensusDataset objects to dictionaries before processing
            if census_results:
                census_results = [
                    {
                        'id': f"census-{i}",  # Ensure ID is a string with prefix
                        'title': getattr(dataset, 'title', 'Census Dataset'),
                        'description': getattr(dataset, 'description', ''),
                        'organization': 'U.S. Census Bureau',
                        'similarity': getattr(dataset, 'similarity', 0.8),
                        'resources': getattr(dataset, 'resources', []),
                        'search_source': 'census'
                    } for i, dataset in enumerate(census_results)
                ]
            
            # Ensure we have a list for processing
            if not isinstance(census_results, list):
                logger.info(f"Converting census_results from {type(census_results)} to list")
                census_results = list(census_results) if census_results is not None else []
            
            # Process each dataset
            all_datasets_count = len(census_results)
            
            # Store the datasets for later return
            census_datasets = census_results
            
            # Stream each dataset to the client
            for dataset in census_results:
                for chunk in process_and_yield_dataset(dataset, 'census', all_datasets_count, start_time):
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Error in Census search: {str(e)}")
            logger.error(traceback.format_exc())
            census_datasets = []
    
    except Exception as e:
        logger.error(f"Error in search_census_data: {str(e)}")
        logger.error(traceback.format_exc())
        yield create_error_message(
            "I encountered an error while searching Census data. I'll continue with other sources.",
            details=str(e),
            start_time=start_time
        )
    
    # Return the list of datasets (not a generator)
    # This is used by the calling function to aggregate results
    return census_datasets

def search_vector_datasets(query, similarity_threshold, max_results, start_time):
    """Search datasets using vector search and yield results"""
    yield create_status_message('I\'m searching through data.gov datasets...', start_time)
    
    try:
        # Perform single search
        results = single_search(
            query,
            search_function=vector_search_datasets,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
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

def stream_search_datasets_helper(query, similarity_threshold=0.3, search_method=None, 
                                 max_results=15, census_max_results=5, relevance_threshold=0.4):
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
        
        # Now get the actual census datasets
        try:
            # Extract structured info from query for Census search
            query_info = process_census_query(query)
            
            # Perform Census search with proper error handling
            try:
                # Use empty lists for tags if None to avoid Boolean clause issues
                tags = query_info.get('tags', []) if query_info.get('tags') is not None else []
                
                census_results = census_vector_search(
                    query=query,
                    similarity_threshold=similarity_threshold,
                    year=query_info.get('year'),
                    tags=tags,  # Pass empty list instead of None
                    geo_level=query_info.get('geo_level'),
                    location=query_info.get('location'),
                    max_results=census_max_results,
                    verbose=False
                )
                
                # Ensure we have a list
                if hasattr(census_results, '__iter__') and not isinstance(census_results, list):
                    census_results = list(census_results)
                elif not isinstance(census_results, list):
                    census_results = []
                
                # Process census results
                census_datasets = census_results
                
                # We've already yielded the datasets in the search_census_data function,
                # so we don't need to yield them again here
            except Exception as e:
                logger.error(f"Error in census search: {e}")
                yield create_status_message(
                    "I encountered an issue with Census data. Continuing with other sources...",
                    start_time
                )
        except Exception as e:
            logger.error(f"Error processing Census results: {str(e)}")
            yield create_status_message(
                "I encountered an issue with Census data. Continuing with other sources...",
                start_time
            )
        
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
        
        # For each dataset, perform pre-download relevance assessment
        relevant_datasets = []
        for dataset_index, dataset in enumerate(all_datasets):
            try:
                is_relevant = None
                for chunk in assess_dataset_relevance(
                    query, 
                    dataset, 
                    relevance_threshold, 
                    start_time, 
                    dataset_index, 
                    len(all_datasets)
                ):
                    yield chunk
                    # Try to extract the relevance information from the yielded chunks
                    try:
                        chunk_data = json.loads(chunk.strip())
                        if chunk_data.get('type') == 'dataset_update' and 'data' in chunk_data:
                            if 'relevance' in chunk_data['data']:
                                is_relevant = chunk_data['data']['relevance'].get('is_relevant', False)
                    except:
                        pass
                
                # If we couldn't determine relevance from chunks, use a default
                if is_relevant is None:
                    is_relevant = dataset.get('relevance', {}).get('is_relevant', False)
                
                # Skip if not relevant
                if is_relevant:
                    relevant_datasets.append(dataset)
            except Exception as e:
                logger.error(f"Error assessing dataset {dataset.get('id', 'unknown')}: {str(e)}")
                continue
        
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