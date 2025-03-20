from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from factchecker.models import DatasetCatalog, WaitlistEntry, DatasetResource
from factchecker.serializers import DatasetCatalogSerializer
from factchecker.search.pinecone_search import vector_search_datasets_pinecone as vector_search_datasets
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
import pandas as pd

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
    Also downloads, loads, and analyzes datasets for relevance after search.
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
    relevance_threshold = float(request.data.get('relevance_threshold', 0.4))
    
    print(f"Parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    logger.info(f"[API] Received streaming search request: '{query}' (method: {search_method}, threshold: {similarity_threshold})")
    
    # Create a generator function that yields dataset results as they come in
    def dataset_stream():
        try:
            start_time = time.time()
            
            # Send initial message
            yield json.dumps({
                'type': 'status',
                'message': f'I\'m starting my search for relevant datasets about "{query}"...',
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            
            # Initialize API key for Data.gov
            from django.conf import settings
            gov_api_key = settings.DATA_GOV_API_KEY
            
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
            
            # Vector search with streaming results
            if search_method in ['vector', None]:  # Vector or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'I\'m searching through government databases...',
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                # Import and use single_search instead of parallel_search
                from factchecker.search.search_utils import single_search
                
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
                        yield from process_and_yield_dataset(result, 'vector')
                
                # Status update after vector search
                if vector_datasets:
                    yield json.dumps({
                        'type': 'status',
                        'message': f'I\'ve found {len(vector_datasets)} datasets that might be relevant to your query.',
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
            
            # Keyword search with streaming results
            if search_method in ['keyword', None]:  # Keyword or hybrid
                yield json.dumps({
                    'type': 'status',
                    'message': 'I\'m checking additional government data sources...',
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
                        # Just provide a simple update on progress
                        if keyword_datasets:
                            yield json.dumps({
                                'type': 'status',
                                'message': 'I\'m discovering additional datasets that might help answer your question...',
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                        
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
                        'message': f'I ran into a problem finding additional datasets: {str(e)}',
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
            
            # Calculate execution time and send search completion message
            search_execution_time = time.time() - start_time
            
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
                all_datasets = vector_datasets if search_method == 'vector' else keyword_datasets
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
                
                # 1. Pre-download relevance assessment
                from factchecker.processing.analysis.search_result_analyzer import assess_datafile_relevance_predownload
                try:
                    is_relevant_predownload, relevance_score_predownload, reasoning_predownload = assess_datafile_relevance_predownload(
                        query, 
                        dataset,
                        relevance_threshold=0.4
                    )
                    
                    # Update dataset with pre-assessment results
                    dataset['pre_assessment'] = {
                        'is_relevant': is_relevant_predownload,
                        'relevance_score': relevance_score_predownload,
                        'reasoning': reasoning_predownload
                    }
                    
                    # Simple status update about relevance with reasoning
                    relevance_message = "relevant" if is_relevant_predownload else "not relevant"
                    yield json.dumps({
                        'type': 'status',
                        'message': f'I\'ve completed my assessment: This dataset appears to be {relevance_message}.\nReasoning: {reasoning_predownload}',
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    
                    # Store relevance assessment and update status
                    dataset['relevance'] = {
                        'is_relevant': is_relevant_predownload,
                        'relevance_score': relevance_score_predownload,
                        'reasoning': reasoning_predownload
                    }

                    # Update dataset with assessment and mark as complete
                    yield json.dumps({
                        'type': 'dataset_update',
                        'data': {
                            'id': dataset_id,
                            'status': 'relevant' if is_relevant_predownload else 'not_relevant',
                            'relevance': {
                                'is_relevant': is_relevant_predownload,
                                'relevance_score': relevance_score_predownload,
                                'reasoning': reasoning_predownload
                            },
                            'processing_complete': True
                        },
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    
                    # Skip if not relevant - but we've already sent the dataset_update message
                    if not is_relevant_predownload:
                        continue

                except Exception as e:
                    print(f"Error assessing relevance: {e}")
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
                
                # SKIP ALL THE DOWNLOADING AND POST-DOWNLOAD ASSESSMENT CODE
                # (Download resources, multi-file analysis, loading data, and final assessment)
            
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
            
        except Exception as e:
            # Send error message
            error_message = str(e)
            traceback_str = traceback.format_exc()
            logger.error(f"[API] Error in stream_search_datasets: {error_message}")
            logger.error(traceback_str)
            
            yield json.dumps({
                'type': 'error',
                'message': "I'm sorry, I encountered an error while processing your request. Please try again.",
                'details': error_message,
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
    
    # Create and return the streaming response
    response = StreamingHttpResponse(
        dataset_stream(),
        content_type='text/event-stream'
    )
    # Add headers to disable buffering
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
