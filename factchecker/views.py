from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from factchecker.models import DatasetCatalog, WaitlistEntry, DatasetResource
from factchecker.serializers import DatasetCatalogSerializer
from factchecker.search.faiss_search import vector_search_datasets_faiss as vector_search_datasets
from factchecker.search import search_datasets
from factchecker.processing.analysis import load_datafile, assess_datafile_relevance, extract_relevant_data, analyze_dataset_overview
from factchecker.presentation.cli_tool_functions import summarize_findings, summarize_findings_alternate
from django.conf import settings
import os
from django.core.management import call_command
from io import StringIO
import sys
from factchecker.download import download_resource
import logging
import time
import concurrent.futures
from threading import Lock
import traceback
import numpy as np
import json
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from corsheaders.defaults import default_headers
from django.db import models

# Create a logger for the API
logger = logging.getLogger("factchecker_api")

# Create your views here.

class DatasetCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows datasets to be viewed.
    """
    queryset = DatasetCatalog.objects.all()
    serializer_class = DatasetCatalogSerializer

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

@api_view(['POST'])
def process_query(request):
    """
    Simplified version that returns a default set of datasets.
    """
    # Get the query parameter (we'll just log it for now)
    query = request.data.get('query', '')
    
    if not query:
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    logger.info(f"[API] Received query: '{query}' (using simplified response)")
    
    try:
        # Get 10 datasets from the database
        datasets = DatasetCatalog.objects.all().order_by('?')[:10]  # Random order
        
        # Prepare the response data
        dataset_results = []
        
        for dataset in datasets:
            # Get resources for this dataset
            resources = DatasetResource.objects.filter(dataset=dataset)
            resources_data = [
                {
                    'id': resource.resource_id,
                    'name': resource.name,
                    'url': resource.url,
                    'description': resource.description,
                    'format': resource.format
                }
                for resource in resources
            ]
            
            # Add a mock relevance score based on the dataset index
            # This gives us some variety in the UI
            relevance_score = round(0.9 - (len(dataset_results) * 0.05), 2)
            
            # Format the dataset data
            dataset_info = {
                "id": dataset.dataset_id,
                "title": dataset.title,
                "description": dataset.notes,
                "similarity": relevance_score,  # Mock similarity score
                "relevance_score": relevance_score,  # Mock relevance score
                "organization_name": dataset.organization_name,
                "organization_title": dataset.organization_title,
                "resources": resources_data,
                "tags": dataset.tags,
                "file_path": None,  # Not applicable for this simplified version
                "dataset_analysis": f"This dataset might be relevant to your query about '{query}'."
            }
            
            dataset_results.append(dataset_info)
        
        # Create a simple summary
        summary = {
            "query": query,
            "findings": f"Found {len(dataset_results)} datasets that might be relevant to your query about '{query}'."
        }
        
        # Return the response
        response_data = {
            'query': query,
            'summary': summary,
            'datasets': dataset_results,
            'execution_time': 0.5  # Mock execution time
        }
        
        return Response(response_data)
        
    except Exception as e:
        # Log the full exception with traceback
        logger.error(f"[API] Error in simplified process_query: {str(e)}")
        logger.error(traceback.format_exc())
        
        return Response({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
@api_view(['POST'])
def register_waitlist(request):
    first_name = request.data.get('first_name', '')
    email = request.data.get('email', '')
    
    # Basic validation
    if not email:
        return Response(
            {"error": "Email is required"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check for duplicates
    if WaitlistEntry.objects.filter(email=email).exists():
        return Response(
            {"error": "This email is already registered"}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Create entry
    WaitlistEntry.objects.create(
        first_name=first_name,
        email=email
    )
    
    return Response(
        {"message": "Successfully added to waitlist"},
        status=status.HTTP_201_CREATED
    )

@api_view(['GET'])
def get_datasets(request):
    """
    API endpoint to retrieve datasets for the frontend datasets page.
    """
    try:
        # Get query parameters
        search_query = request.query_params.get('search', '')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        # Base queryset
        queryset = DatasetCatalog.objects.all()
        
        # Apply search filter if provided
        if search_query:
            queryset = queryset.filter(
                models.Q(title__icontains=search_query) |
                models.Q(notes__icontains=search_query) |
                models.Q(organization_name__icontains=search_query) |
                models.Q(organization_title__icontains=search_query) |
                models.Q(search_text__icontains=search_query)
            )
        
        # Get total count for pagination
        total_count = queryset.count()
        
        # Apply ordering to avoid the UnorderedObjectListWarning
        queryset = queryset.order_by('dataset_id')
        
        # Apply pagination
        offset = (page - 1) * page_size
        paginated_queryset = queryset[offset:offset + page_size]
        
        # Prepare the response data
        datasets_list = []
        for dataset in paginated_queryset:
            # Get resources for this dataset
            resources = DatasetResource.objects.filter(dataset=dataset)
            resources_data = [
                {
                    'id': resource.resource_id,
                    'name': resource.name,
                    'url': resource.url,
                    'description': resource.description,
                    'format': resource.format
                }
                for resource in resources
            ]
            
            # Format the dataset data
            dataset_data = {
                'dataset_id': dataset.dataset_id,
                'title': dataset.title,
                'notes': dataset.notes,
                'organization_name': dataset.organization_name,
                'organization_title': dataset.organization_title,
                'resources': resources_data,
                'tags': dataset.tags,
                'image_url': dataset.image_url
            }
            
            datasets_list.append(dataset_data)
        
        # Create the response data
        response_data = {
            'datasets': datasets_list,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': max(1, (total_count + page_size - 1) // page_size)
        }
        
        # Log the response structure (not the full data)
        print(f"Response keys: {response_data.keys()}")
        print(f"Number of datasets: {len(response_data['datasets'])}")
        
        # Return the response
        return Response(response_data)
    except Exception as e:
        # Add error logging
        import traceback
        print(f"Error in get_datasets: {str(e)}")
        print(traceback.format_exc())
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
def search_datasets_api(request):
    """
    API endpoint that searches for datasets matching a query.
    Returns a list of relevant datasets without performing full analysis.
    Uses the same hybrid search approach as the factchecker CLI tool.
    """
    print("Search API endpoint called")
    # Get the query parameter
    query = request.data.get('query', '')
    
    print(f"Received query: {query}")
    
    if not query:
        print("No query provided")
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get optional parameters with defaults
    similarity_threshold = float(request.data.get('similarity_threshold', 0.3))
    search_method = request.data.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request.data.get('max_results', 15))
    
    print(f"Parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    logger.info(f"[API] Received dataset search request: '{query}' (method: {search_method}, threshold: {similarity_threshold})")
    
    try:
        start_time = time.time()
        
        # Initialize API key for Data.gov
        from django.conf import settings
        gov_api_key = settings.DATA_GOV_API_KEY
        
        print(f"Using DATA_GOV_API_KEY: {'*' * len(gov_api_key) if gov_api_key else 'None'}")
        
        if not gov_api_key:
            print("No DATA_GOV_API_KEY configured")
            return Response({'error': 'DATA_GOV_API_KEY not configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Higher threshold for keyword search
        keyword_threshold = similarity_threshold + 0.2  # 0.2 higher than vector threshold
        
        # Perform search based on method
        if search_method == 'vector':
            print("Starting vector search with query variations...")
            # Import the parallel search utility
            from factchecker.search.search_utils import parallel_search
            
            # Vector search with query variations (matches CLI behavior)
            datasets = parallel_search(
                query=query,
                search_function=vector_search_datasets,
                similarity_threshold=similarity_threshold,
                max_results=max_results,
                use_variations=True,
                verbose=False
            )
            print(f"Vector search complete. Found {len(datasets)} datasets")
            
        elif search_method == 'keyword':
            print("Starting keyword search...")
            # Keyword search only
            datasets = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
            print(f"Keyword search complete. Found {len(datasets)} datasets")
            
        else:
            print("Starting hybrid search...")
            # Hybrid search (default)
            
            # Get vector search results with query variations (matches CLI behavior)
            print("Performing vector search with query variations...")
            from factchecker.search.search_utils import parallel_search
            
            vector_datasets = parallel_search(
                query=query,
                search_function=vector_search_datasets,
                similarity_threshold=similarity_threshold,
                max_results=max_results,
                use_variations=True,
                verbose=False
            )
            print(f"Vector search complete. Found {len(vector_datasets)} datasets")
            
            # Get keyword search results
            print("Performing keyword search...")
            keyword_datasets = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
            print(f"Keyword search complete. Found {len(keyword_datasets)} datasets")
            
            # Get IDs from both search methods
            vector_ids = {dataset['id'] for dataset in vector_datasets}
            keyword_ids = {dataset['id'] for dataset in keyword_datasets}
            
            # Find overlap (datasets found by both methods)
            overlap_ids = vector_ids.intersection(keyword_ids)
            print(f"Search statistics:")
            print(f"• {len(vector_ids)} unique datasets from vector search")
            print(f"• {len(keyword_ids)} unique datasets from keyword search")
            print(f"• {len(overlap_ids)} datasets found by both methods")
            
            # Merge results, removing duplicates
            all_datasets = []
            seen_ids = set()
            
            # Process vector datasets first
            for dataset in vector_datasets:
                dataset_id = dataset['id']
                if dataset_id in overlap_ids:
                    dataset['search_source'] = 'both'
                else:
                    dataset['search_source'] = 'vector'
                all_datasets.append(dataset)
                seen_ids.add(dataset_id)
            
            # Add keyword datasets (skipping duplicates)
            for dataset in keyword_datasets:
                dataset_id = dataset['id']
                if dataset_id not in seen_ids:
                    dataset['search_source'] = 'keyword'
                    all_datasets.append(dataset)
                    seen_ids.add(dataset_id)
            
            # Sort by similarity score (higher is better)
            all_datasets.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            datasets = all_datasets
            print(f"Combined search complete. Found {len(datasets)} unique datasets after deduplication")
        
        # Enrich datasets with additional information from database where available
        enriched_datasets = []
        for dataset in datasets:
            dataset_id = dataset['id']
            
            # Try to find the dataset in our database to get additional information
            try:
                db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
                # Add image URL to the dataset
                dataset['image_url'] = db_dataset.image_url
                
                # Get resources for this dataset
                resources = DatasetResource.objects.filter(dataset=db_dataset)
                if resources:
                    # Format resources data to match the get_datasets endpoint
                    resources_data = [
                        {
                            'id': resource.resource_id,
                            'name': resource.name,
                            'url': resource.url,
                            'description': resource.description,
                            'format': resource.format
                        }
                        for resource in resources
                    ]
                    dataset['resources'] = resources_data
                
                # Add or update organization information if available
                dataset['organization_name'] = db_dataset.organization_name
                dataset['organization_title'] = db_dataset.organization_title
                
                # Add tags if available
                if db_dataset.tags:
                    dataset['tags'] = db_dataset.tags
                
            except DatasetCatalog.DoesNotExist:
                # Dataset not in our database, keep original data
                pass
            
            enriched_datasets.append(dataset)
        
        # Calculate execution time
        execution_time = time.time() - start_time
        print(f"Search completed in {execution_time:.2f} seconds")
        
        # Prepare response
        response_data = {
            'query': query,
            'datasets': enriched_datasets,
            'execution_time': execution_time,
            'search_method': search_method if search_method else 'hybrid',
            'total_count': len(enriched_datasets)
        }
        
        print("Returning response")
        return Response(response_data)
        
    except Exception as e:
        # Log the full exception with traceback
        print(f"Error in search_datasets_api: {str(e)}")
        print(traceback.format_exc())
        logger.error(f"[API] Error in search_datasets_api: {str(e)}")
        logger.error(traceback.format_exc())
        
        return Response({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.http import StreamingHttpResponse
import json

@api_view(['POST'])
def stream_search_datasets(request):
    """
    Streaming API endpoint that searches for datasets matching a query.
    Returns datasets incrementally as they are found.
    """
    print("Streaming search API endpoint called")
    
    # Get the query parameter
    query = request.data.get('query', '')
    
    if not query:
        print("No query provided")
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get optional parameters with defaults
    similarity_threshold = float(request.data.get('similarity_threshold', 0.3))
    search_method = request.data.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request.data.get('max_results', 15))
    
    print(f"Parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    logger.info(f"[API] Received streaming search request: '{query}' (method: {search_method}, threshold: {similarity_threshold})")
    
    # Create a generator function that yields dataset results as they come in
    def dataset_stream():
        try:
            start_time = time.time()
            
            # Send initial message
            yield json.dumps({
                'type': 'status',
                'message': f'Starting search for relevant datasets about "{query}"...',
                'timestamp': time.time() - start_time
            }) + '\n'
            
            # Initialize API key for Data.gov
            from django.conf import settings
            gov_api_key = settings.DATA_GOV_API_KEY
            
            if not gov_api_key:
                yield json.dumps({
                    'type': 'error',
                    'message': 'API key configuration issue. Please try again later.',
                    'timestamp': time.time() - start_time
                }) + '\n'
                return
            
            # Higher threshold for keyword search
            keyword_threshold = similarity_threshold + 0.2
            
            vector_datasets = []
            keyword_datasets = []
            all_datasets_count = 0
            
            # Helper function to enrich and yield a dataset
            def process_and_yield_dataset(dataset, source):
                nonlocal all_datasets_count
                dataset_id = dataset['id']
                dataset_title = dataset['title']
                all_datasets_count += 1
                
                # Set search source (but we'll make it less prominent in the UI)
                dataset['search_source'] = source
                
                # Try to find the dataset in our database to get additional information
                try:
                    db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
                    # Add image URL to the dataset
                    dataset['image_url'] = db_dataset.image_url
                    
                    # Get resources for this dataset
                    resources = DatasetResource.objects.filter(dataset=db_dataset)
                    if resources:
                        # Format resources data
                        resources_data = [
                            {
                                'id': resource.resource_id,
                                'name': resource.name,
                                'url': resource.url,
                                'description': resource.description,
                                'format': resource.format
                            }
                            for resource in resources
                        ]
                        dataset['resources'] = resources_data
                    
                    # Add organization information if available
                    dataset['organization_name'] = db_dataset.organization_name
                    dataset['organization_title'] = db_dataset.organization_title
                    
                    # Add tags if available
                    if db_dataset.tags:
                        dataset['tags'] = db_dataset.tags
                    
                except DatasetCatalog.DoesNotExist:
                    # Dataset not in our database, keep original data
                    pass
                
                # Yield status update about finding this dataset
                yield json.dumps({
                    'type': 'discovery',
                    'message': f'Found dataset: {dataset_title}',
                    'count': all_datasets_count,
                    'timestamp': time.time() - start_time
                }) + '\n'
                
                # Then yield the enriched dataset
                yield json.dumps({
                    'type': 'dataset',
                    'data': dataset,
                    'timestamp': time.time() - start_time
                }) + '\n'
            
            # Vector search with streaming results
            if search_method in ['vector', None]:  # Vector or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'Searching government databases...',
                    'timestamp': time.time() - start_time
                }) + '\n'
                
                # Import the parallel search utility
                from factchecker.search.search_utils import generate_similar_queries
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                # Generate query variations
                queries = generate_similar_queries(query)
                
                # Keep track of seen dataset IDs
                seen_vector_ids = set()
                
                # Function to search with a single query variation
                def search_with_variation(variation):
                    try:
                        results = vector_search_datasets(
                            variation,
                            similarity_threshold=similarity_threshold,
                            max_results=max_results,
                            verbose=False
                        )
                        
                        # Add the query variation to each result
                        for result in results:
                            result['query_variation'] = variation
                            
                        return results
                    except Exception as e:
                        print(f"Error searching with query '{variation}': {e}")
                        return []
                
                # Run searches in parallel but yield results as they come in
                with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
                    future_to_query = {executor.submit(search_with_variation, q): q for q in queries}
                    
                    for future in as_completed(future_to_query):
                        query_variation = future_to_query[future]
                        try:
                            results = future.result()
                            
                            # Process and yield each result if not seen before
                            for result in results:
                                if result['id'] not in seen_vector_ids:
                                    seen_vector_ids.add(result['id'])
                                    vector_datasets.append(result)
                                    yield from process_and_yield_dataset(result, 'vector')
                        except Exception as e:
                            print(f"Error processing results for query '{query_variation}': {e}")
                
                # Status update after vector search
                if vector_datasets:
                    yield json.dumps({
                        'type': 'status',
                        'message': f'Found {len(vector_datasets)} datasets that might be relevant',
                        'timestamp': time.time() - start_time
                    }) + '\n'
            
            # Keyword search with streaming results
            if search_method in ['keyword', None]:  # Keyword or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'Checking additional government data sources...',
                    'timestamp': time.time() - start_time
                }) + '\n'
                
                try:
                    # Get keyword search results
                    keyword_results = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
                    keyword_datasets = keyword_results
                    
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
                                        }) + '\n'
                                        break
                        
                        # Don't share technical details about vector/keyword distinction
                        # Just provide a simple update on progress
                        if keyword_datasets:
                            yield json.dumps({
                                'type': 'status',
                                'message': 'Discovering additional datasets...',
                                'timestamp': time.time() - start_time
                            }) + '\n'
                        
                        # Process and yield only new keyword datasets
                        for dataset in keyword_datasets:
                            if dataset['id'] not in vector_ids:
                                yield from process_and_yield_dataset(dataset, 'keyword')
                    else:
                        # In keyword-only mode, yield all results
                        for dataset in keyword_datasets:
                            yield from process_and_yield_dataset(dataset, 'keyword')
                except Exception as e:
                    yield json.dumps({
                        'type': 'error',
                        'message': f'Error finding additional datasets: {str(e)}',
                        'timestamp': time.time() - start_time
                    }) + '\n'
            
            # Calculate execution time and send completion message
            execution_time = time.time() - start_time
            
            # Determine total unique datasets
            if search_method is None:  # hybrid search
                all_datasets = vector_datasets.copy()
                vector_ids = {dataset['id'] for dataset in vector_datasets}
                
                # Add keyword datasets that weren't in vector results
                for dataset in keyword_datasets:
                    if dataset['id'] not in vector_ids:
                        all_datasets.append(dataset)
                
                # Sort by similarity score (higher is better)
                all_datasets.sort(key=lambda x: x.get('similarity', 0), reverse=True)
                
                total_count = len(all_datasets)
            else:
                # Either vector or keyword only
                total_count = len(vector_datasets if search_method == 'vector' else keyword_datasets)
            
            # Send completion message
            yield json.dumps({
                'type': 'complete',
                'data': {
                    'query': query,
                    'execution_time': execution_time,
                    'total_count': total_count
                },
                'message': f'Search complete. Found {total_count} datasets in {execution_time:.1f} seconds.',
                'timestamp': execution_time
            }) + '\n'
            
        except Exception as e:
            # Send error message
            error_message = str(e)
            traceback_str = traceback.format_exc()
            logger.error(f"[API] Error in stream_search_datasets: {error_message}")
            logger.error(traceback_str)
            
            yield json.dumps({
                'type': 'error',
                'message': "Sorry, we encountered an error while searching. Please try again.",
                'details': error_message,
                'timestamp': time.time() - start_time
            }) + '\n'
    
    # Create and return the streaming response
    response = StreamingHttpResponse(
        dataset_stream(),
        content_type='text/event-stream'
    )
    # Add headers to disable buffering
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
