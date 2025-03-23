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

# turn on emulator
if os.getenv('FUNCTIONS_EMULATOR'):
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase app
firebase_admin.initialize_app()

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
        return super(NumpyEncoder, self).default(obj)

# Helper functions for dataset search and processing
def vector_search_datasets(query, similarity_threshold=0.3, max_results=15):
    """
    Placeholder for vector search function - replace with actual implementation
    """
    # This would call your actual vector search implementation
    # For now, return empty list as placeholder
    logger.info(f"Vector search called with query: {query}")
    return []

def search_datasets(query, api_key, similarity_threshold=0.5):
    """
    Placeholder for keyword search function - replace with actual implementation
    """
    # This would call your actual keyword search implementation
    # For now, return empty list as placeholder
    logger.info(f"Keyword search called with query: {query}")
    return []

def process_census_query(query):
    """
    Placeholder for census query processing - replace with actual implementation
    """
    # Extract structured info from query for Census search
    # Return empty dict as placeholder
    return {}

def census_vector_search(query, similarity_threshold=0.3, year=None, tags=None, 
                         geo_level=None, location=None, max_results=5, verbose=False):
    """
    Placeholder for census vector search - replace with actual implementation
    """
    # This would call your actual census search implementation
    # For now, return empty list as placeholder
    logger.info(f"Census search called with query: {query}")
    return []

def single_search(query, search_function, similarity_threshold=0.3, max_results=15, verbose=False):
    """
    Placeholder for single search function - replace with actual implementation
    """
    # This would call your actual search implementation
    # For now, return empty list as placeholder
    return []

def assess_datafile_relevance_predownload(query, dataset, relevance_threshold=0.4):
    """
    Placeholder for relevance assessment - replace with actual implementation
    """
    # This would call your actual relevance assessment
    # For now, return mock values
    is_relevant = True
    relevance_score = 0.8
    reasoning = f"This dataset appears to be relevant to your query about '{query}'."
    return is_relevant, relevance_score, reasoning

def stream_search_datasets_helper(query, similarity_threshold=0.3, search_method=None, 
                                 max_results=15, census_max_results=5, relevance_threshold=0.4):
    """
    Helper function that generates the streaming search results
    """
    try:
        start_time = time.time()
        
        # Send initial message
        yield json.dumps({
            'type': 'status',
            'message': f'I\'m starting my search for relevant datasets about "{query}"...',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        # Initialize API key for Data.gov
        gov_api_key = os.environ.get('DATA_GOV_API_KEY', '')
        
        if not gov_api_key:
            yield json.dumps({
                'type': 'error',
                'message': 'I\'m having trouble with the API key configuration. Please try again later.',
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            return
        
        # Higher threshold for keyword search
        keyword_threshold = similarity_threshold + 0.2
        
        vector_datasets = []
        keyword_datasets = []
        census_datasets = []  # New list for census datasets
        all_datasets_count = 0
        
        # Helper function to enrich and yield a dataset
        def process_and_yield_dataset(dataset, source):
            nonlocal all_datasets_count
            dataset_id = dataset['id']
            dataset_title = dataset['title']
            all_datasets_count += 1
            
            # Set search source
            dataset['search_source'] = source
            
            # In a real implementation, you would fetch additional data from Firestore
            # For now, we'll just use the dataset as is
            
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
        
        # Start Census search first
        # Extract structured info from query for Census search
        query_info = process_census_query(query)
        
        # Start Census search
        yield json.dumps({
            'type': 'status',
            'message': 'I\'m searching through Census databases...',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        try:
            # Perform Census search
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
            
            # Send status update for Census results
            if census_results:
                yield json.dumps({
                    'type': 'status',
                    'message': f'I\'ve found {len(census_results)} datasets from Census sources.',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
            
            # Convert Census results to the expected format and add to datasets
            for result in census_results:
                # Format the Census dataset to match our frontend structure
                census_dataset = {
                    'id': f"census-{result['id']}",  # Prefix with 'census-' to avoid ID collisions
                    'title': result['title'],
                    'description': result['description'],
                    'similarity': result['score'],
                    'relevance_score': result['score'],
                    'organization_name': 'U.S. Census Bureau',
                    'organization_title': 'United States Census Bureau',
                    'resources': [],  # Will be populated with API endpoints
                    'search_source': 'census',
                    'vintage': result['vintage'],
                    'geographic_levels': result.get('geographic_levels', []),
                    'image_url': '/images/census_logo.png',  # Add Census logo path
                }
                
                # Add a resource for the Census API endpoint if available
                if 'dataset' in result and hasattr(result['dataset'], 'api_endpoint'):
                    census_dataset['resources'] = [{
                        'id': f"census-api-{result['id']}",
                        'name': f"{result['title']} API",
                        'url': result['dataset'].api_endpoint,
                        'description': "Census API endpoint for this dataset",
                        'format': 'API'
                    }]
                
                # Add to our collection and yield the dataset
                census_datasets.append(census_dataset)
                for chunk in process_and_yield_dataset(census_dataset, 'census'):
                    yield chunk
        
        except Exception as e:
            logger.error(f"Error processing Census results: {e}")
            yield json.dumps({
                'type': 'status',
                'message': 'I encountered an issue with Census data sources but will continue with other sources.',
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
        
        # Now launch Data.gov searches
        # Continue with regular Data.gov search as before
        with concurrent.futures.ThreadPoolExecutor() as executor:
            if search_method in ['vector', None]:  # Vector or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'I\'m searching through data.gov datasets...',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                # Keep track of seen dataset IDs
                seen_vector_ids = set()
                
                # Perform single search
                results = single_search(
                    query,
                    search_function=vector_search_datasets,
                    similarity_threshold=similarity_threshold,
                    max_results=max_results,
                    verbose=False
                )
                
                # Process and yield each result
                for result in results:
                    if result['id'] not in seen_vector_ids:
                        seen_vector_ids.add(result['id'])
                        vector_datasets.append(result)
                        for chunk in process_and_yield_dataset(result, 'vector'):
                            yield chunk
            
            # Keyword search with streaming results
            if search_method in ['keyword', None]:  # Keyword or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'I\'m checking additional data.gov datasets...',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                try:
                    # Get keyword search results
                    keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
                    keyword_datasets = keyword_results
                    
                    # In hybrid mode, only yield keyword results that weren't found by vector search
                    if search_method is None:  # hybrid mode
                        vector_ids = {dataset['id'] for dataset in vector_datasets}
                        
                        # Find datasets that appear in both searches
                        overlap_ids = set()
                        for dataset in keyword_results:
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
                        # Just provide a simple update on progress
                        if keyword_results:
                            yield json.dumps({
                                'type': 'status',
                                'message': 'I\'m discovering additional datasets that might help answer your question...',
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                        
                        # Process and yield only new keyword datasets
                        for dataset in keyword_results:
                            if dataset['id'] not in vector_ids:
                                for chunk in process_and_yield_dataset(dataset, 'keyword'):
                                    yield chunk
                    else:
                        # In keyword-only mode, yield all results
                        for dataset in keyword_results:
                            for chunk in process_and_yield_dataset(dataset, 'keyword'):
                                yield chunk
                except Exception as e:
                    yield json.dumps({
                        'type': 'error',
                        'message': f'I ran into a problem finding additional datasets: {str(e)}',
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
        
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
        yield json.dumps({
            'type': 'status',
            'message': 'I\'m now assessing the relevance of the discovered datasets...',
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        # For each dataset, perform pre-download relevance assessment only
        for dataset_index, dataset in enumerate(all_datasets):
            dataset_id = dataset.get('id', 'unknown')
            dataset_title = dataset.get('title', 'Unknown Dataset')
            current_dataset_number = dataset_index + 1
            
            # Simpler status update about starting to process this dataset
            yield json.dumps({
                'type': 'status',
                'message': f'I\'m assessing dataset {current_dataset_number}/{len(all_datasets)}: {dataset_title}',
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            
            # Update UI that we're starting to process this dataset (for the frontend dataset card)
            yield json.dumps({
                'type': 'processing_start',
                'dataset_id': dataset_id,
                'progress': {
                    'current': current_dataset_number,
                    'total': len(all_datasets),
                    'status': 'starting'
                },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            
            # Check if this is a Census dataset (ID starts with "census-")
            if dataset_id.startswith('census-'):
                # Auto-mark Census datasets as relevant
                is_relevant = True
                relevance_score = dataset.get('similarity', 0.8)  # Use the similarity score as relevance score
                reasoning = "This dataset from the U.S. Census Bureau contains official government statistics that are likely relevant to your query."
                
                # Log that we're skipping LLM check for Census data
                logger.info(f"Auto-marking Census dataset as relevant: {dataset_id}")
                
                # Update dataset with relevance info
                dataset['pre_assessment'] = {
                    'is_relevant': is_relevant,
                    'relevance_score': relevance_score,
                    'reasoning': reasoning
                }
                
                # Status update
                yield json.dumps({
                    'type': 'status',
                    'message': f'I\'ve determined this Census dataset is relevant to your query.',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
            else:
                # 1. Pre-download relevance assessment for non-Census datasets
                try:
                    is_relevant, relevance_score, reasoning = assess_datafile_relevance_predownload(
                        query, 
                        dataset,
                        relevance_threshold=0.4
                    )
                    
                    # Update dataset with pre-assessment results
                    dataset['pre_assessment'] = {
                        'is_relevant': is_relevant,
                        'relevance_score': relevance_score,
                        'reasoning': reasoning
                    }
                    
                    # Simple status update about relevance with reasoning
                    relevance_message = "relevant" if is_relevant else "not relevant"
                    yield json.dumps({
                        'type': 'status',
                        'message': f'I\'ve completed my assessment: This dataset appears to be {relevance_message}.\nReasoning: {reasoning}',
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                except Exception as e:
                    logger.error(f"Error assessing relevance: {e}")
                    yield json.dumps({
                        'type': 'dataset_update',
                        'data': {
                            'id': dataset_id,
                            'status': 'error',
                            'error': f'Assessment error: {str(e)}',
                            'processing_complete': True
                        },
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    continue
            
            # Store relevance assessment and update status (common code for both Census and non-Census)
            dataset['relevance'] = {
                'is_relevant': is_relevant,
                'relevance_score': relevance_score,
                'reasoning': reasoning
            }

            # Update dataset with assessment and mark as complete
            yield json.dumps({
                'type': 'dataset_update',
                'data': {
                    'id': dataset_id,
                    'status': 'relevant' if is_relevant else 'not_relevant',
                    'relevance': {
                        'is_relevant': is_relevant,
                        'relevance_score': relevance_score,
                        'reasoning': reasoning
                    },
                    'processing_complete': True
                },
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            
            # Skip if not relevant - but we've already sent the dataset_update message
            if not is_relevant:
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
                'processed_count': len(all_datasets)
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
            'datasets': all_datasets
        }
        
    except Exception as e:
        # Send error message
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error in stream_search_datasets: {error_message}")
        logger.error(traceback_str)
        
        yield json.dumps({
            'type': 'error',
            'message': "I'm sorry, I encountered an error while processing your request. Please try again.",
            'details': error_message,
            'timestamp': time.time() - start_time
        }, cls=NumpyEncoder) + '\n'
        
        # Return error data for the JSON response
        return {
            'error': error_message,
            'traceback': traceback_str
        }

@https_fn.on_call(
    cors=options.CorsOptions(
        cors_origins=[
            "https://crystal-2f87e.web.app/",
            "http://localhost:5173"  
            ],
        cors_methods=["get", "post"],
    )
)
def handle_crystal_request(request):
    """HTTP Cloud Function that handles dataset search requests."""
    logger.info("Function called with data: %s", request.data)
    
    # Get the query parameter
    query = request.data.get('query', '')
    
    if not query:
        return {"error": "Query is required", "status": "error"}
    
    # Get optional parameters with defaults
    similarity_threshold = float(request.data.get('similarity_threshold', 0.3))
    search_method = request.data.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request.data.get('max_results', 15))
    census_max_results = int(request.data.get('census_max_results', 5))
    relevance_threshold = float(request.data.get('relevance_threshold', 0.4))
    
    logger.info(f"Search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Process the search and return the final result
    try:
        # In a real implementation, you would call your actual search functions here
        # For now, we'll return a mock response
        return {
            "status": "success", 
            "message": "Search completed successfully", 
            "query": query,
            "execution_time": 1.5,
            "total_count": 3,
            "datasets": [
                {
                    "id": "mock-dataset-1",
                    "title": "Sample Dataset 1",
                    "description": "This is a sample dataset for testing",
                    "similarity": 0.85,
                    "relevance_score": 0.85,
                    "is_relevant": True
                },
                {
                    "id": "mock-dataset-2",
                    "title": "Sample Dataset 2",
                    "description": "Another sample dataset for testing",
                    "similarity": 0.75,
                    "relevance_score": 0.75,
                    "is_relevant": True
                },
                {
                    "id": "mock-dataset-3",
                    "title": "Sample Dataset 3",
                    "description": "A third sample dataset for testing",
                    "similarity": 0.65,
                    "relevance_score": 0.65,
                    "is_relevant": True
                }
            ]
        }
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        logger.error(traceback.format_exc())
        return {"status": "error", "error": str(e)}

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get", "post"],
    )
)
def stream_search_datasets(request):
    """HTTP Cloud Function that streams dataset search results."""
    # Parse request data
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return https_fn.Response(
            json.dumps({"error": "No JSON data provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Get the query parameter
    query = request_json.get('query', '')
    
    if not query:
        return https_fn.Response(
            json.dumps({"error": "Query is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Get optional parameters with defaults
    similarity_threshold = float(request_json.get('similarity_threshold', 0.3))
    search_method = request_json.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request_json.get('max_results', 15))
    census_max_results = int(request_json.get('census_max_results', 5))
    relevance_threshold = float(request_json.get('relevance_threshold', 0.4))
    
    logger.info(f"Streaming search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Create a generator function that yields dataset results as they come in
    def generate():
        # Initialize a variable to store the final result
        final_result = None
        
        # Process the streaming search
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
            yield chunk
        
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Get a reference to the Firestore database
                db = firestore.client()
                
                # Create a document with the search results
                search_ref = db.collection('searches').document()
                
                # Add the search data
                search_ref.set({
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'results': final_result
                })
                
                logger.info(f"Stored search results in Firestore with ID: {search_ref.id}")
            except Exception as e:
                logger.error(f"Error storing results in Firestore: {e}")
    
    # Create and return the streaming response
    return https_fn.Response(
        generate(),
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )