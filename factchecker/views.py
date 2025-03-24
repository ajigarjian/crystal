from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from factchecker.models import DatasetCatalog, WaitlistEntry, DatasetResource
from factchecker.serializers import DatasetCatalogSerializer
from factchecker.search.pinecone_search import vector_search_datasets_pinecone as vector_search_datasets
from factchecker.search import search_datasets
from factchecker.processing.analysis import load_datafile, assess_datafile_relevance, extract_relevant_data, analyze_dataset_overview
from factchecker.presentation.cli_tool_functions import summarize_findings, summarize_findings_alternate, summarize_findings_structured
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

# Census vector search
from factchecker.search.census_search import vector_search, process_query

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
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        if isinstance(obj, pd.Series):
            return obj.to_list()
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
    max_results = int(request.data.get('max_results', 3))
    census_max_results = int(request.data.get('census_max_results', 1))  # New parameter with default of 5
    relevance_threshold = float(request.data.get('relevance_threshold', 0.4))
    
    print(f"Parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}, census_max_results={census_max_results}")
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
            census_datasets = []  # New list for census datasets
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
            
            # Start Census search first
            from factchecker.search.census_search import vector_search as census_vector_search
            
            # Process the query to extract structured parameters
            from factchecker.search.census_search import process_query as process_census_query
            
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
                    max_results=census_max_results,  # Use census-specific max results
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
                    
                    # Get and add tags from the dataset
                    if 'dataset' in result and hasattr(result['dataset'], 'tags'):
                        # Get tag names from the CensusTag objects
                        tag_names = list(result['dataset'].tags.all().values_list('name', flat=True))
                        census_dataset['tags'] = tag_names
                    
                    # Add a resource for the Census API endpoint
                    if hasattr(result.get('dataset', {}), 'api_endpoint'):
                        census_dataset['resources'] = [{
                            'id': f"census-api-{result['id']}",
                            'name': f"{result['title']} API",
                            'url': result['dataset'].api_endpoint,
                            'description': "Census API endpoint for this dataset",
                            'format': 'API'
                        }]
                    
                    # Add to our collection and yield the dataset
                    census_datasets.append(census_dataset)
                    yield from process_and_yield_dataset(census_dataset, 'census')
            
            except Exception as e:
                print(f"Error processing Census results: {e}")
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
                    
                    # Import the single_search function
                    from factchecker.search.search_utils import single_search
                    
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
                                    yield from process_and_yield_dataset(dataset, 'keyword')
                        else:
                            # In keyword-only mode, yield all results
                            for dataset in keyword_results:
                                yield from process_and_yield_dataset(dataset, 'keyword')
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
                    print(f"Auto-marking Census dataset as relevant: {dataset_id}")
                    
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
                    
                    # Set variables for later use
                    is_relevant_predownload = is_relevant
                    relevance_score_predownload = relevance_score
                    reasoning_predownload = reasoning
                else:
                    # 1. Pre-download relevance assessment for non-Census datasets
                    from factchecker.processing.analysis.search_result_analyzer import assess_datafile_relevance_predownload
                    try:
                        assessment_result = assess_datafile_relevance_predownload(
                            query, 
                            dataset,
                            relevance_threshold=0.4
                        )
                        
                        # Handle the new dictionary return format
                        if isinstance(assessment_result, dict):
                            is_relevant_predownload = assessment_result.get('is_relevant', False)
                            relevance_score_predownload = assessment_result.get('relevance_score', 0.0)
                            reasoning_predownload = assessment_result.get('reasoning', 'No reasoning provided')
                        else:
                            # Fallback for backward compatibility
                            is_relevant_predownload, relevance_score_predownload, reasoning_predownload = assessment_result
                        
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
                
                # Store relevance assessment and update status (common code for both Census and non-Census)
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

@api_view(['POST'])
def stream_analyze_datasets(request):
    """
    Streaming API endpoint that analyzes selected datasets.
    Downloads, loads, analyzes, extracts data from, and summarizes the selected datasets.
    Returns results incrementally as they are processed.
    """
    # Make sure pandas is imported at the function level
    import pandas as pd
    
    print("Streaming analyze datasets API endpoint called")
    
    # Get the query parameter and selected dataset IDs
    query = request.data.get('query', '')
    dataset_ids = request.data.get('dataset_ids', [])
    
    if not query:
        print("No query provided")
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not dataset_ids:
        print("No datasets selected")
        return Response({'error': 'At least one dataset must be selected'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get optional parameters with defaults
    relevance_threshold = float(request.data.get('relevance_threshold', 0.4))
    max_download_time = float(request.data.get('max_download_time', 60))
    
    print(f"Parameters: query={query}, dataset_ids={dataset_ids}, relevance_threshold={relevance_threshold}")
    logger.info(f"[API] Received analyze datasets request: '{query}' with {len(dataset_ids)} datasets")
    
    # Create a generator function that yields analysis results as they come in
    def dataset_analysis_stream():
        # Ensure pandas is imported in the generator function scope as well
        import pandas as pd
        
        try:
            start_time = time.time()
            
            # Send initial message
            yield json.dumps({
                'type': 'status',
                'message': f"I'm starting to analyze {len(dataset_ids)} selected datasets for your query: \"{query}\"",
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
            
            # Create temporary directory for downloads
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = temp_dir
                
                # Process each dataset in sequence
                results = []
                dataset_analyses = []
                extracted_data_list = []
                
                for idx, dataset_id in enumerate(dataset_ids):
                    try:
                        current_dataset_number = idx + 1
                        
                        # Check if it's a Census dataset
                        is_census = dataset_id.startswith('census-')
                        
                        # Get dataset metadata
                        try:
                            if is_census:
                                # For Census datasets, we need to handle them differently
                                # Extract the actual ID from the "census-{id}" format
                                census_id = dataset_id.replace('census-', '')
                                
                                # In a real implementation, we would get census dataset info from database
                                # For now, create a minimal dataset info
                                dataset = {
                                    'id': dataset_id,
                                    'title': f"Census Dataset {census_id}",
                                    'description': "Census data",
                                    'is_census': True,
                                    'census_id': census_id
                                }
                                
                                logger.info(f"Processing Census dataset: {dataset_id}")
                            else:
                                # For Data.gov datasets, get from our database
                                db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
                                
                                # Get resources for this dataset
                                resources = DatasetResource.objects.filter(dataset=db_dataset)
                                
                                if not resources:
                                    yield json.dumps({
                                        'type': 'error',
                                        'message': f"No resources found for dataset: {db_dataset.title}",
                                        'timestamp': time.time() - start_time
                                    }, cls=NumpyEncoder) + '\n'
                                    continue
                                
                                # Create dataset info dictionary from database
                                dataset = {
                                    'id': db_dataset.dataset_id,
                                    'title': db_dataset.title,
                                    'description': db_dataset.notes or "",
                                    'organization_name': db_dataset.organization_name,
                                    'organization_title': db_dataset.organization_title,
                                    'resources': [
                                        {
                                            'id': resource.resource_id,
                                            'name': resource.name,
                                            'url': resource.url,
                                            'description': resource.description,
                                            'format': resource.format
                                        }
                                        for resource in resources
                                    ],
                                    'is_census': False
                                }
                                
                                logger.info(f"Processing Data.gov dataset: {dataset['title']}")
                            
                        except DatasetCatalog.DoesNotExist:
                            yield json.dumps({
                                'type': 'error',
                                'message': f"Dataset {dataset_id} not found in database",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                            continue
                        
                        # Initial status update
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Processing dataset {current_dataset_number}/{len(dataset_ids)}: {dataset['title']}",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # Update dataset status to downloading
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'downloading',
                            'progress': 0,
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # 1. DOWNLOAD: Get the resource
                        if is_census:
                            # Handle Census data differently
                            # For now, we'll create a placeholder CSV with some sample data
                            import pandas as pd
                            import os
                            
                            # Create a sample DataFrame for Census data
                            df = pd.DataFrame({
                                'Year': [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020],
                                'Value': [100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150],
                                'Location': ['San Francisco'] * 11
                            })
                            
                            # Save to temporary file
                            output_path = os.path.join(output_dir, f"{dataset_id}.csv")
                            df.to_csv(output_path, index=False)
                            
                            logger.info(f"Created Census sample data: {output_path}")
                            
                            # Set output paths
                            output_paths = [output_path]
                            
                        else:
                            # For Data.gov datasets, find suitable resources
                            # Find the first CSV/XLSX resource
                            resource = None
                            for res in dataset['resources']:
                                if res.get('format', '').lower() in ['csv', 'xlsx', 'xls']:
                                    resource = res
                                    break
                            
                            if not resource:
                                yield json.dumps({
                                    'type': 'error',
                                    'message': f"No suitable tabular data resource found for dataset: {dataset['title']}",
                                    'timestamp': time.time() - start_time
                                }, cls=NumpyEncoder) + '\n'
                                continue
                            
                            yield json.dumps({
                                'type': 'status',
                                'message': f"Downloading resource: {resource['name']}",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                            
                            # Download the resource
                            try:
                                output_path = download_resource(
                                    resource['url'], 
                                    output_dir, 
                                    filename=dataset['id'],
                                    max_download_time=max_download_time
                                )
                                
                                if not output_path:
                                    yield json.dumps({
                                        'type': 'error',
                                        'message': f"Failed to download resource for dataset: {dataset['title']}",
                                        'timestamp': time.time() - start_time
                                    }, cls=NumpyEncoder) + '\n'
                                    continue
                                
                                # Set output paths 
                                output_paths = [output_path]
                                
                            except Exception as e:
                                yield json.dumps({
                                    'type': 'error',
                                    'message': f"Error downloading resource: {str(e)}",
                                    'timestamp': time.time() - start_time
                                }, cls=NumpyEncoder) + '\n'
                                continue
                        
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Downloaded dataset: {dataset['title']}",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # Send download progress updates periodically
                        # This would be integrated into your download_resource function
                        # For now, we'll simulate it with a simple progress update
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'downloading',
                            'progress': 50,  # This would be the actual percentage
                            'downloaded_size': 5000000,  # Sample size in bytes
                            'file_size': 10000000,  # Sample total size
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # Mark download as complete
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'downloaded',
                            'progress': 100,
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # Update to loading state
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'loading',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # 2. LOAD: Load the datafile 
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Loading data from file...",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        try:
                            datafile_content = load_datafile(output_paths[0])
                        except Exception as e:
                            yield json.dumps({
                                'type': 'error',
                                'message': f"Error loading datafile: {str(e)}",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                            continue
                        
                        # Update dataset_info based on the content type
                        is_pdf = isinstance(datafile_content, dict) and datafile_content.get('type') == 'pdf'
                        
                        if is_pdf:
                            dataset_info = {
                                "id": dataset['id'],
                                "title": dataset['title'],
                                "description": dataset.get('description', ''),
                                "similarity": 1.0,  # Since these are pre-selected, set similarity to 1.0
                                "file_path": output_paths[0],
                                "all_file_paths": output_paths,
                                "is_census": is_census
                            }
                            
                            dataset_info.update({
                                "document_type": "pdf",
                                "num_pages": datafile_content.get("num_pages", 0),
                                "text_sample": datafile_content.get("text_sample", "")[:200] + "..."
                            })
                            
                            yield json.dumps({
                                'type': 'status',
                                'message': f"Loaded PDF document with {datafile_content.get('num_pages', 0)} pages",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                        else:
                            dataset_info = {
                                "id": dataset['id'],
                                "title": dataset['title'],
                                "description": dataset.get('description', ''),
                                "similarity": 1.0,  # Since these are pre-selected, set similarity to 1.0
                                "file_path": output_paths[0],
                                "all_file_paths": output_paths,
                                "is_census": is_census
                            }
                            
                            dataset_info.update({
                                "row_count": len(datafile_content),
                                "column_count": len(datafile_content.columns),
                                "columns": list(datafile_content.columns)
                            })
                            
                            yield json.dumps({
                                'type': 'status',
                                'message': f"Loaded tabular data with {len(datafile_content)} rows and {len(datafile_content.columns)} columns",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                        
                        # 3. ASSESS: Since we're analyzing pre-selected datasets, we'll assume they're relevant
                        # But we can still calculate a relevance score for information
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'assessing',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Assessing dataset relevance...",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        is_relevant, relevance_score, reasoning = assess_datafile_relevance(
                            datafile_content, 
                            query, 
                            dataset_info,
                            relevance_threshold
                        )
                        
                        dataset_info["relevance_score"] = relevance_score
                        dataset_info["relevance_reasoning"] = reasoning
                        dataset_info["is_relevant"] = is_relevant
                        
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Relevance assessment: Score {relevance_score:.2f}\nReasoning: {reasoning}",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        # 4. EXTRACT: Extract relevant data
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'extracting',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Extracting relevant data...",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        try:
                            # Extract relevant data
                            from factchecker.processing.analysis.extraction.execution import execute_relevant_data
                            
                            relevant_data = extract_relevant_data(
                                datafile_content, 
                                query, 
                                dataset_info
                            )
                            
                            # Execute the data extraction
                            extracted_data = execute_relevant_data(relevant_data)
                            
                            # Add dataset source information to the extracted data
                            if extracted_data:
                                extracted_data["dataset_title"] = dataset_info["title"]
                                extracted_data["dataset_source"] = dataset_info.get("description", "Data.gov dataset")
                                extracted_data["dataset_id"] = dataset_info["id"]
                                extracted_data["file_path"] = dataset_info["file_path"]
                                extracted_data["all_file_paths"] = dataset_info["all_file_paths"]
                                
                                # Check if this dataset is already in the list
                                existing_ids = [data.get('dataset_id') for data in extracted_data_list]
                                print(f"[DEBUG] Current extracted_data_list contains {len(extracted_data_list)} datasets with IDs: {existing_ids}")
                                
                                current_id = extracted_data.get('dataset_id')
                                if current_id in existing_ids:
                                    print(f"[DUPLICATE WARNING] Dataset {current_id} is already in the extraction list!")
                                
                                print(f"[DEBUG] Dataset {current_id} will be added to extracted_data_list after conversion")
                        except Exception as e:
                            logger.error(f"Error extracting data: {str(e)}")
                            yield json.dumps({
                                'type': 'error',
                                'message': f"Error extracting data: {str(e)}",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                            # Continue with analysis even if extraction fails
                        
                        # 5. ANALYZE: Generate dataset overview analysis
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'analyzing',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        yield json.dumps({
                            'type': 'status',
                            'message': f"Analyzing dataset overview...",
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                        try:
                            dataset_analysis = analyze_dataset_overview(
                                datafile_content, 
                                query, 
                                dataset_info, 
                                extracted_data=extracted_data if 'extracted_data' in locals() else None
                            )
                            
                            # Add dataset analysis to dataset_info
                            dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                            
                            # Add to dataset_analyses list for summary
                            dataset_analyses.append(dataset_analysis)
                            
                            yield json.dumps({
                                'type': 'status',
                                'message': f"Analysis complete",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                        except Exception as e:
                            logger.error(f"Error analyzing dataset: {str(e)}")
                            yield json.dumps({
                                'type': 'error',
                                'message': f"Error analyzing dataset: {str(e)}",
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n'
                            continue
                        
                        # Add dataset_info to results
                        results.append(dataset_info)
                        
                        # Update dataset card with results
                        update_data = {
                            'id': dataset_id,
                            'status': 'analyzed',
                            'processing_complete': True,
                            'relevance': {
                                'is_relevant': dataset_info["is_relevant"],
                                'relevance_score': dataset_info["relevance_score"],
                                'reasoning': dataset_info["relevance_reasoning"]
                            }
                        }
                        
                        # Add dataset analysis if available
                        if "dataset_analysis" in dataset_info:
                            update_data['dataset_analysis'] = dataset_info["dataset_analysis"]
                        
                        # Add extracted data preview if available
                        if 'extracted_data' in locals() and extracted_data:
                            # Enhanced debugging for extracted data
                            print(f"\n[DEBUG] Extracted data from dataset {dataset_id}:")
                            print(f"  - Dataset title: {extracted_data.get('dataset_title', 'Unknown')}")
                            
                            # Log the results_dict structure (not the full data)
                            if 'results_dict' in extracted_data:
                                results_dict = extracted_data['results_dict']
                                if isinstance(results_dict, pd.DataFrame):
                                    print(f"  - Results type: DataFrame with shape {results_dict.shape}")
                                    print(f"  - Columns: {list(results_dict.columns)}")
                                    print(f"  - Sample data (first 2 rows):")
                                    print(results_dict.head(2))
                                elif isinstance(results_dict, dict):
                                    print(f"  - Results type: Dictionary with {len(results_dict)} keys")
                                    print(f"  - Keys: {list(results_dict.keys())}")
                                elif isinstance(results_dict, list):
                                    print(f"  - Results type: List with {len(results_dict)} items")
                                else:
                                    print(f"  - Results type: {type(results_dict)}")
                            
                            # Ensure we don't have DataFrame objects in the extracted_data
                            print("[DEBUG] Converting any DataFrame objects to serializable form...")
                            if 'results_dict' in extracted_data and isinstance(extracted_data['results_dict'], pd.DataFrame):
                                print("  - Converting results_dict DataFrame to records")
                                extracted_data['results_dict'] = extracted_data['results_dict'].to_dict(orient='records')
                            
                            # Add to the list for summary generation
                            print(f"  - Adding extracted data to summary generation list")
                            extracted_data_list.append(extracted_data)
                        
                        yield json.dumps({
                            'type': 'dataset_processing',
                            'dataset_id': dataset_id,
                            'status': 'analyzed',
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                            
                    except Exception as e:
                        logger.error(f"Error processing dataset {dataset_id}: {str(e)}")
                        logger.error(traceback.format_exc())
                        print(f"[ERROR] Failed to process dataset {dataset_id}: {str(e)}")
                        print(traceback.format_exc())
                        # Continue with next dataset
                
                # 6. SUMMARIZE: Generate summary of findings
                print(f"\n[DEBUG] Starting summary generation with {len(extracted_data_list)} datasets")
                print(f"  - Dataset titles included in summary:")
                for data in extracted_data_list:
                    print(f"    * {data.get('dataset_title', 'Unknown')}")
                
                # NEW CODE: Detailed logging of data being passed to the summary function
                print("\n======= DATA BEING PASSED TO SUMMARY FUNCTION =======")
                print(f"QUERY: {query}")
                
                print("\nEXTRACTED_DATA_LIST DETAILS:")
                for i, data in enumerate(extracted_data_list, 1):
                    print(f"\n--- DATASET #{i}: {data.get('dataset_title', 'Unknown')} ---")
                    
                    # Dataset identifiers
                    print(f"  dataset_id: {data.get('dataset_id', 'None')}")
                    print(f"  organization: {data.get('organization', 'None')}")
                    print(f"  dataset_source: {data.get('dataset_source', 'None')}")
                    
                    # DataFrame info
                    if 'results_dict' in data:
                        results_dict = data['results_dict']
                        if isinstance(results_dict, pd.DataFrame):
                            print(f"  results_dict: DataFrame with {len(results_dict)} rows, {len(results_dict.columns)} columns")
                            print(f"  columns: {list(results_dict.columns)}")
                            if not results_dict.empty:
                                print("  sample (first row):")
                                print(f"    {results_dict.iloc[0].to_dict()}")
                        elif isinstance(results_dict, dict):
                            print(f"  results_dict: Dictionary with {len(results_dict)} keys")
                            print(f"  keys: {list(results_dict.keys())}")
                            # If there's a 'subset_df' key containing a DataFrame, print details about it
                            if 'subset_df' in results_dict and isinstance(results_dict['subset_df'], pd.DataFrame):
                                subset_df = results_dict['subset_df']
                                print(f"  subset_df: DataFrame with {len(subset_df)} rows, {len(subset_df.columns)} columns")
                                print(f"  subset_df columns: {list(subset_df.columns)}")
                                if not subset_df.empty:
                                    print("  subset_df sample (first row):")
                                    print(f"    {subset_df.iloc[0].to_dict()}")
                        elif isinstance(results_dict, list):
                            print(f"  results_dict: List with {len(results_dict)} items")
                        else:
                            print(f"  results_dict: {type(results_dict)}")
                    else:
                        print(f"  results_dict: Not found")
                    
                    # Check for explanation field
                    if 'explanation' in data:
                        explanation = data['explanation']
                        print(f"  explanation: {explanation[:100]}..." if len(explanation) > 100 else explanation)
                
                print("\nDATASET_ANALYSES DETAILS:")
                if dataset_analyses:
                    for i, analysis in enumerate(dataset_analyses, 1):
                        print(f"\n--- ANALYSIS #{i}: {analysis.get('dataset_title', 'Unknown')} ---")
                        print(f"  dataset_id: {analysis.get('dataset_id', 'None')}")
                        if 'geographic_scope' in analysis:
                            print(f"  geographic_scope: {analysis.get('geographic_scope', {})}")
                        if 'temporal_scope' in analysis:
                            print(f"  temporal_scope: {analysis.get('temporal_scope', {})}")
                else:
                    print("  No dataset analyses available")
                print("=======================================================\n")
                
                yield json.dumps({
                    'type': 'status',
                    'message': f"Generating structured summary of findings from all datasets...",
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                try:
                    # Enhance extracted_data_list with organization info from datasets
                    for data in extracted_data_list:
                        dataset_id = data.get('dataset_id')
                        if not dataset_id:
                            continue
                            
                        # For datasets that were processed through the full pipeline
                        for dataset_info in results:
                            if dataset_info.get('id') == dataset_id:
                                # Copy organization info if available
                                if 'organization' in dataset_info:
                                    data['organization'] = dataset_info['organization']
                                break
                            
                            # If we didn't find organization data yet, check if this is a Data.gov dataset
                            if 'organization' not in data and not dataset_id.startswith('census-'):
                                try:
                                    # Get dataset from database
                                    db_dataset = DatasetCatalog.objects.get(dataset_id=dataset_id)
                                    data['organization'] = db_dataset.organization_title or db_dataset.organization_name
                                except Exception as e:
                                    print(f"[WARNING] Could not get organization for {dataset_id}: {str(e)}")
                    
                    # Generate structured summary
                    print(f"[DEBUG] Calling summarize_findings_structured function...")
                    from factchecker.presentation.cli_tool_functions import summarize_findings_structured
                    
                    structured_summary = summarize_findings_structured(
                        query, 
                        extracted_data_list,
                        dataset_analyses
                    )
                    
                    # Debug the key_findings structure
                    print("\n======= KEY FINDINGS STRUCTURE ANALYSIS =======")
                    if 'key_findings' in structured_summary:
                        findings = structured_summary['key_findings']
                        print(f"Number of findings: {len(findings)}")
                        for i, finding in enumerate(findings):
                            print(f"Finding #{i+1}:")
                            print(f"  Type: {type(finding)}")
                            print(f"  Length: {len(finding)}")
                            print(f"  Content: '{finding}'")
                            if finding.startswith('•') or finding.startswith('-'):
                                print(f"  Note: Finding starts with bullet point character")
                            if not finding.strip():
                                print(f"  Warning: Empty finding")
                            print()
                    else:
                        print("No key_findings in structured_summary")
                    print("==============================================\n")
                    
                    # Print the summary info
                    print("\n======= GENERATED STRUCTURED SUMMARY =======")
                    print(f"Query: {structured_summary.get('query', 'N/A')}")

                    # Print actual summary text
                    print("\nSUMMARY:")
                    print(structured_summary.get('summary', 'No summary generated'))

                    # Print key findings with numbers
                    print("\nKEY FINDINGS:")
                    for i, finding in enumerate(structured_summary.get('key_findings', []), 1):
                        print(f"{i}. {finding}")

                    # Print sources
                    print("\nSOURCES:")
                    for i, source in enumerate(structured_summary.get('sources', []), 1):
                        print(f"{i}. [{source.get('citation_id', 'UNKNOWN')}] {source.get('title', 'Untitled')} ({source.get('organization', 'No organization')})")

                    print("=================================\n")
                    
                    # Format the summary for the frontend
                    frontend_summary = {
                        'text': structured_summary.get('summary', ''),
                        'key_findings': structured_summary.get('key_findings', []),
                        'sources': [
                            {
                                'citation_id': source.get('citation_id', ''),
                                'title': source.get('title', ''),
                                'organization': source.get('organization', '')
                            }
                            for source in structured_summary.get('sources', [])
                        ],
                        'temporal_context': structured_summary.get('context', {}).get('temporal', {}),
                        'geographic_context': structured_summary.get('context', {}).get('geographic', {}),
                        'datasets_analyzed': [
                            {
                                'id': r.get('id', ''),
                                'title': r.get('title', ''),
                                'relevance_score': r.get('relevance_score', 0)
                            }
                            for r in results if r.get('id') and r.get('title')
                        ]
                    }
                    
                    # Send status message about completion
                    yield json.dumps({
                        'type': 'status',
                        'message': f"Summary generated with {len(structured_summary.get('key_findings', []))} key findings",
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    
                    # Send the structured summary
                    yield json.dumps({
                        'type': 'structured_summary',
                        'data': frontend_summary,
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    
                    # Also send the original summary format for backward compatibility
                    yield json.dumps({
                        'type': 'summary',
                        'data': {
                            'text': structured_summary.get('summary', ''),
                            'confidence': structured_summary.get('confidence', {}).get('score', 0) / 5.0,  # Scale to 0-1
                            'datasets_analyzed': frontend_summary['datasets_analyzed']
                        },
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                    
                except Exception as e:
                    error_msg = f"Error generating summary: {str(e)}"
                    logger.error(error_msg)
                    logger.error(traceback.format_exc())
                    print(f"[ERROR] {error_msg}")
                    print(traceback.format_exc())
                    
                    yield json.dumps({
                        'type': 'error',
                        'message': error_msg,
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                else:
                    no_data_msg = "No data could be extracted from any datasets. Unable to generate summary."
                    print(f"[DEBUG] {no_data_msg}")
                    yield json.dumps({
                        'type': 'status',
                        'message': no_data_msg,
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
            
            # Calculate final execution time
            final_execution_time = time.time() - start_time
            
            # Send completion message
            yield json.dumps({
                'type': 'complete',
                'data': {
                    'query': query,
                    'execution_time': final_execution_time,
                    'total_datasets': len(dataset_ids),
                    'successful_datasets': len(results)
                },
                'message': f"Analysis complete! Processed {len(results)} datasets in {final_execution_time:.1f} seconds.",
                'timestamp': final_execution_time
            }, cls=NumpyEncoder) + '\n'
            
        except Exception as e:
            # Send error message for any uncaught exceptions
            error_message = str(e)
            traceback_str = traceback.format_exc()
            logger.error(f"[API] Error in stream_analyze_datasets: {error_message}")
            logger.error(traceback_str)
            print(f"[ERROR] Uncaught exception in stream_analyze_datasets: {error_message}")
            print(traceback_str)
            
            yield json.dumps({
                'type': 'error',
                'message': "I'm sorry, I encountered an error while analyzing the datasets. Please try again.",
                'details': error_message,
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n'
    
    # Create and return the streaming response
    response = StreamingHttpResponse(
        dataset_analysis_stream(),
        content_type='text/event-stream'
    )
    # Add headers to disable buffering
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

def format_source_citation(dataset, dataset_id):
    """Format a consistent citation for a dataset"""
    # Truncate description if it's too long (e.g., first 100 characters)
    description = dataset.get('dataset_source', '')
    short_description = description[:100] + '...' if len(description) > 100 else description
    
    organization = dataset.get('organization', 'Unknown Organization')
    title = dataset.get('title', 'Untitled Dataset')
    
    # Format the citation consistently
    return f"[{dataset_id.upper()[:8]}] {title} ({organization})"