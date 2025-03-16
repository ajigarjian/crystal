from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from factchecker.models import DatasetCatalog, WaitlistEntry
from factchecker.serializers import DatasetCatalogSerializer
from factchecker.search import vector_search_datasets, preprocess_query, search_datasets, filter_relevant_datasets
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
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from corsheaders.defaults import default_headers

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
    Process a natural language query to find and analyze relevant datasets.
    """
    # Start timing the execution
    start_time = time.time()
    
    # Get parameters from request
    query = request.data.get('query', '')
    top_n = request.data.get('top_n', 3)  # Default to fewer datasets for API response
    search_method = request.data.get('search_method', 'vector')
    relevance_threshold = request.data.get('relevance_threshold', 0.3)
    workers = request.data.get('workers', 3)
    
    # Create a lock for thread-safe logging
    stdout_lock = Lock()
    
    if not query:
        return Response({'error': 'Query is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    logger.info(f"[API] Factchecker query: '{query}'")
    
    try:
        # 1. Search for datasets
        logger.info(f"[API] Searching for datasets matching '{query}' using {search_method} search...")
        
        if search_method == 'vector':
            # Use vector search to find relevant datasets
            datasets = vector_search_datasets(
                query=query, 
                openai_api_key=settings.OPENAI_API_KEY, 
                top_n=top_n
            )
        else:
            # Use keyword search to find relevant datasets
            processed_query = preprocess_query(query, settings.OPENAI_API_KEY)
            search_results = search_datasets(
                api_key=settings.DATA_GOV_API_KEY,
                query=processed_query,
                rows=top_n*2
            )
            # Filter to most relevant
            datasets = filter_relevant_datasets(
                query, 
                search_results, 
                settings.OPENAI_API_KEY, 
                top_n=top_n
            )
        
        logger.info(f"[API] Found {len(datasets)} relevant datasets via {search_method} search")
        
        if not datasets:
            logger.warning("[API] No datasets found. Try a different query.")
            return Response({
                'query': query,
                'message': 'No relevant datasets found',
                'results': []
            })
        
        # 2. Download and analyze datasets
        output_dir = os.path.join(settings.BASE_DIR, 'downloads')
        os.makedirs(output_dir, exist_ok=True)
        
        dataset_results = []
        extracted_data_list = []
        dataset_analyses = []
        
        # Define the worker function that processes a single dataset
        def process_dataset(dataset_index, dataset):
            dataset_num = dataset_index + 1
            dataset_id = dataset['id']
            dataset_title = dataset['title']
            # Create an identifier for this dataset (no truncation)
            dataset_short_id = f"[{dataset_num}/{len(datasets)}] {dataset_title}"
            
            similarity_score = dataset.get('similarity', 1.0)
            with stdout_lock:
                logger.info(f"[API] {dataset_short_id} Processing dataset (Query similarity: {similarity_score:.4f})")
            
            try:
                # Download the dataset
                with stdout_lock:
                    logger.info(f"[API] {dataset_short_id} Downloading dataset...")
                output_path = download_resource(settings.DATA_GOV_API_KEY, dataset_id, output_dir=output_dir)
                
                if not output_path:
                    with stdout_lock:
                        logger.warning(f"[API] {dataset_short_id} Download failed. Skipping dataset.")
                    return {
                        "id": dataset_id,
                        "title": dataset_title,
                        "similarity": dataset.get("similarity", 0),
                        "error": "Download failed"
                    }, None, None
                    
                with stdout_lock:
                    logger.info(f"[API] {dataset_short_id} Downloaded to: {output_path}")
                
                # Load and analyze the dataset
                with stdout_lock:
                    logger.info(f"[API] {dataset_short_id} Loading dataset for analysis...")
                dataset_content = load_datafile(output_path, settings.OPENAI_API_KEY)
                
                # Record basic dataset info
                is_pdf = isinstance(dataset_content, dict) and dataset_content.get('type') == 'pdf'

                if is_pdf:
                    # Handle PDF document
                    dataset_info = {
                        "id": dataset_id,
                        "title": dataset_title,
                        "description": dataset.get("description", ""),
                        "similarity": similarity_score,
                        "file_path": output_path,
                        "document_type": "pdf",
                        "num_pages": dataset_content.get("num_pages", 0),
                        "text_sample": dataset_content.get("text_sample", "")[:200] + "..."  # First 200 chars of text sample
                    }
                else:
                    # Handle DataFrame (tabular data)
                    dataset_info = {
                        "id": dataset_id,
                        "title": dataset_title,
                        "description": dataset.get("description", ""),
                        "similarity": similarity_score,
                        "file_path": output_path,
                        "row_count": len(dataset_content),
                        "column_count": len(dataset_content.columns),
                        "columns": list(dataset_content.columns)
                    }
                
                # Assess dataset relevance
                with stdout_lock:
                    logger.info(f"[API] {dataset_short_id} Assessing dataset relevance...")
                is_relevant, relevance_score, reasoning = assess_datafile_relevance(
                    dataset_content, 
                    query, 
                    dataset_info,
                    settings.OPENAI_API_KEY,
                    relevance_threshold
                )
                
                dataset_info["relevance_score"] = relevance_score
                dataset_info["relevance_reasoning"] = reasoning
                
                extracted_data = None
                dataset_analysis = None
                
                if is_relevant:
                    with stdout_lock:
                        logger.info(f"[API] {dataset_short_id} Dataset is relevant (Score: {relevance_score:.2f})")
                    
                    # Extract relevant data
                    with stdout_lock:
                        logger.info(f"[API] {dataset_short_id} Extracting relevant data...")
                    extracted_data = extract_relevant_data(
                        dataset_content, 
                        query, 
                        dataset_info, 
                        settings.OPENAI_API_KEY
                    )
                    
                    # Add dataset source information to the extracted data
                    if extracted_data:
                        extracted_data["dataset_title"] = dataset_info["title"]
                        extracted_data["dataset_source"] = dataset_info.get("description", "Data.gov dataset")
                        extracted_data["dataset_id"] = dataset_info["id"]
                    
                    with stdout_lock:
                        logger.info(f"[API] {dataset_short_id} Data extraction completed")
                    
                    # Generate dataset overview analysis AFTER extraction
                    with stdout_lock:
                        logger.info(f"[API] {dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(
                        dataset_content, 
                        query, 
                        dataset_info, 
                        settings.OPENAI_API_KEY,
                        extracted_data=extracted_data
                    )
                    
                    # Add dataset analysis to dataset_info
                    dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                else:
                    with stdout_lock:
                        logger.warning(f"[API] {dataset_short_id} Dataset is not relevant enough (Score: {relevance_score:.2f})")
                    
                    # Even for non-relevant datasets, we might want a basic analysis
                    with stdout_lock:
                        logger.info(f"[API] {dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(
                        dataset_content, 
                        query, 
                        dataset_info, 
                        settings.OPENAI_API_KEY
                    )
                    dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                
                return dataset_info, dataset_analysis, extracted_data
                
            except Exception as e:
                with stdout_lock:
                    logger.error(f"[API] {dataset_short_id} Error analyzing dataset: {str(e)}")
                    logger.error(traceback.format_exc())
                # Return error info
                return {
                    "id": dataset_id,
                    "title": dataset_title,
                    "similarity": dataset.get("similarity", 0),
                    "file_path": output_path if 'output_path' in locals() else None,
                    "error": str(e)
                }, None, None
        
        # Use ThreadPoolExecutor to process datasets in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks and store the futures
            future_to_index = {
                executor.submit(process_dataset, i, dataset): i 
                for i, dataset in enumerate(datasets)
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_index):
                dataset_info, dataset_analysis, extracted_data = future.result()
                
                # Add results to our lists
                dataset_results.append(dataset_info)
                
                if dataset_analysis:
                    dataset_analyses.append(dataset_analysis)
                
                if extracted_data:
                    extracted_data_list.append(extracted_data)
        
        # Sort results to maintain the original order
        dataset_results.sort(key=lambda x: next((i for i, d in enumerate(datasets) if d['id'] == x['id']), 999))
        
        # Generate summary if we have extracted data
        summary = None
        if extracted_data_list:
            logger.info("[API] Generating summary of findings...")
            summary = summarize_findings(
                query, 
                extracted_data_list,
                dataset_analyses
            )
        
        # Calculate and log execution time
        execution_time = time.time() - start_time
        logger.info(f"[API] Query execution completed in {execution_time:.2f} seconds")
        
        # Before returning the response, clean the data to handle NaN values
        def clean_nan_values(data):
            if isinstance(data, dict):
                return {k: clean_nan_values(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [clean_nan_values(item) for item in data]
            elif isinstance(data, float) and (np.isnan(data) or np.isinf(data)):
                return None
            else:
                return data
        
        # Clean the response data
        response_data = {
            'query': query,
            'summary': summary,
            'datasets': dataset_results,
            'extracted_data': extracted_data_list if extracted_data_list else None,
            'execution_time': execution_time
        }
        
        cleaned_response = clean_nan_values(response_data)
        
        # Return the cleaned response
        return Response(cleaned_response)
        
    except Exception as e:
        # Log the full exception with traceback
        logger.error(f"[API] Error processing query: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Calculate execution time even for errors
        execution_time = time.time() - start_time
        logger.info(f"[API] Query execution failed after {execution_time:.2f} seconds")
        
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
