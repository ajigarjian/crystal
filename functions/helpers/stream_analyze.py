from typing import Any, Dict
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
import pprint
import pandas as pd
import pyarrow.parquet as pq
import re

# Factchecker imports
from factchecker.processing.analysis.dataset_analyzer import analyze_dataset_overview
from factchecker.processing.analysis.dataset_loader import assess_datafile_relevance, load_datafile
# Add new imports for enhanced functionality
from factchecker.processing.analysis.extraction.execution import execute_relevant_data
from factchecker.processing.analysis.dataset_result_analyzer import assess_datafile_relevance_predownload, get_best_resource, format_extracted_data
from factchecker.download.download_gov_data import download_resource
# Import search_and_analyze
from factchecker.search_and_analyze import search_and_analyze
# Import the summarize_findings function
from factchecker.presentation.summarization import summarize_findings, format_findings_for_display

# Import models
from factchecker.models import DatasetResource
from factchecker.processing.analysis.extraction.dataset_extracter import extract_relevant_data

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
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient="records")  # Convert DataFrame to list of records
        if isinstance(obj, pd.Series):
            return obj.to_dict()  # Convert Series to dict
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

def query_datasets_helper(dataset_ids):
    """
    Query the database for all records matching any of the given dataset_ids
    and return the results as a dictionary.
    
    Args:
        dataset_ids: A list of dataset IDs to search for
        
    Returns:
        A dictionary where keys are row IDs and values are the row data with all columns
    """
    results = {}
    
    try:
        # Query all records matching any of the dataset_ids
        queryset = DatasetResource.objects.filter(dataset__dataset_id__in=dataset_ids)
        
        print(f"Found {queryset.count()} records matching dataset_ids: {dataset_ids}")
        
        # Convert QuerySet to dictionary
        for record in queryset:
            # Get all fields from the model instance
            record_dict = {}
            
            # Add all fields from the model
            for field in record._meta.fields:
                field_name = field.name
                field_value = getattr(record, field_name)
                
                # Handle datetime objects
                if isinstance(field_value, datetime):
                    field_value = field_value.isoformat()
                
                record_dict[field_name] = field_value
            
            # Add related dataset fields
            if record.dataset:
                for field in record.dataset._meta.fields:
                    field_name = f"dataset_{field.name}"
                    field_value = getattr(record.dataset, field.name)
                    
                    # Handle datetime objects
                    if isinstance(field_value, datetime):
                        field_value = field_value.isoformat()
                    
                    # Skip the dataset_embedding field
                    if field_name == "dataset_embedding":
                        continue
                    
                    record_dict[field_name] = field_value
            
            # Add to results dict with ID as key
            results[record.resource_id] = record_dict
            
    except Exception as e:
        print(f"Error querying the database: {e}")
            
    return results


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
    
    print("best_resource", best_resource)
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

def stream_analyze_helper(dataset_ids, query, file_path=None):
    """
    Helper function that generates the streaming analysis results for a dataset.
    Now includes web search results from search_and_analyze at the beginning.
    
    Args:
        dataset_id: ID of the dataset to analyze
        query: The user query
        file_path: Optional path to the dataset file (if not provided, will look in standard locations)
        
    Yields:
        Streaming analysis results as JSON strings, including web search results
    """
    try:
        start_time = time.time()
        
        # Send initial message
        yield create_status_message(
            f'I\'m starting my analysis of the dataset for your query: "{query}"...',
            start_time
        )
        
        # Validate inputs
        if not dataset_ids:
            yield create_error_message(
                'Dataset ID is required for analysis.',
                start_time=start_time
            )
            return
        
        # Call search_and_analyze at the beginning
        yield create_status_message(
            f'Performing web search and analysis for your query...',
            start_time
        )
        
        # Call search_and_analyze with default parameters and handle errors
        search_results = {}
        try:
            search_results = search_and_analyze(
                query=query,
                max_results=5,  # Limit to 5 results for performance
                search_type="comprehensive",
                analyze_results=True
            )
        except Exception as e:
            logger.error(f"Error in web search: {str(e)}")
            logger.error(traceback.format_exc())
            # Continue with empty search results rather than failing
            search_results = {}
        
        # Stream search results as they become available
        if search_results:
            try:
                yield json.dumps({
                    'type': 'web_search_results',
                    'data': search_results.get('search_results', search_results),
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                # If there's a summary, send it as a separate message
                if 'summary' in search_results:
                    # Direct summary from search_results structure
                    yield json.dumps({
                        'type': 'web_search_summary',
                        'data': search_results['summary'],
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                # Check for summary in search_results.search_results (nested structure)
                elif 'search_results' in search_results and 'summary' in search_results.get('search_results', {}):
                    yield json.dumps({
                        'type': 'web_search_summary',
                        'data': search_results['search_results']['summary'],
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
            except Exception as e:
                logger.error(f"Error streaming web search results: {str(e)}")
                # Continue execution without search results
        
        # Get the resource metadata from the DB
        resource_metadata = query_datasets_helper(dataset_ids)

        # Process it 
        datasets = process_resource_metadata(resource_metadata)
        
        # Lists to collect all formatted data and analyses
        all_formatted_data = []
        all_dataset_analyses = []
        
        # For each dataset, find and add the best resource
        for dataset_id, dataset in datasets.items():
            # Pretty print the dataset for debugging
            print(f"\nDataset {dataset_id}:")
            pprint.pprint(dataset)
            
            # Get the best resource for this specific dataset
            best_resource = get_best_resource(query, dataset)

            print(best_resource)
            # Add the best resource directly to the dataset dictionary
            datasets[dataset_id]['best_resource'] = best_resource

        # For each dataset, Download the best resource
        for dataset_id, dataset in datasets.items():
            best_resource = datasets[dataset_id]['best_resource']

            file_path = download_resource_helper(dataset_id, best_resource)
            print(file_path)

            # Extract into CSV if the file path contains ".parquet":
            if ".parquet" in file_path:
                csv_file_path = parquet_to_csv(file_path)
                os.remove(file_path)
                file_path = csv_file_path

        
            # Create dataset metadata
            dataset_metadata = {
                "id": dataset_id,
                "title": os.path.basename(file_path),
                "description": "Dataset for analysis"
            }
            
            # Pre-download relevance assessment (new functionality)
            yield create_status_message(
                f'Performing initial relevance assessment...',
                start_time
            )
            
            # Load the dataset
            yield create_status_message(
                f'Loading the dataset from {file_path}...',
                start_time
            )
        
            try:
                dataset_content = load_datafile(file_path)
                
                # Report successful loading
                if hasattr(dataset_content, 'shape'):
                    yield create_status_message(
                        f'Successfully loaded dataset with {dataset_content.shape[0]} rows and {dataset_content.shape[1]} columns.',
                        start_time
                    )
                else:
                    yield create_status_message(
                        f'Successfully loaded dataset.',
                        start_time
                    )
                    
            except Exception as e:
                logger.error(f"Error loading dataset: {str(e)}")
                yield create_error_message(
                    f'Error loading dataset: {str(e)}',
                    details=traceback.format_exc(),
                    start_time=start_time
                )
                return
            
            # Assess dataset relevance (more detailed assessment with the actual data)
            yield create_status_message(
                f'Assessing dataset relevance to your query...',
                start_time
            )
        
            try:
                # Create more detailed dataset info now that we have the data
                if hasattr(dataset_content, 'shape'):
                    dataset_info = {
                        "id": dataset_id,
                        "title": os.path.basename(file_path),
                        "description": "Dataset for analysis",
                        "file_path": file_path,
                        "row_count": dataset_content.shape[0],
                        "column_count": dataset_content.shape[1],
                        "columns": list(dataset_content.columns)
                    }
                else:
                    # Handle non-DataFrame content (like PDFs)
                    dataset_info = {
                        "id": dataset_id,
                        "title": os.path.basename(file_path),
                        "description": "Dataset for analysis",
                        "file_path": file_path,
                        "document_type": "pdf" if isinstance(dataset_content, dict) and dataset_content.get('type') == 'pdf' else "unknown"
                    }
                
                # Assess relevance with the actual data
                is_relevant, relevance_score, reasoning = assess_datafile_relevance(
                    dataset_content, 
                    query, 
                    dataset_info,
                    relevance_threshold=0.4
                )
                
                if is_relevant:
                    yield create_status_message(
                        f'Dataset is relevant to your query (Score: {relevance_score:.2f})',
                        start_time
                    )
                    yield create_status_message(
                        f'Reasoning: {reasoning}',
                        start_time
                    )
                else:
                    yield create_status_message(
                        f'Dataset may not be highly relevant to your query (Score: {relevance_score:.2f})',
                        start_time
                    )
                    yield create_status_message(
                        f'Reasoning: {reasoning}',
                        start_time
                    )
                
            
            except Exception as e:
                logger.warning(f"Error in relevance assessment: {str(e)}")
                # Continue with analysis even if relevance assessment fails
                is_relevant = True  # Assume relevant if assessment fails
            
            # Extract relevant data if the dataset is deemed relevant
            extracted_data = None
            if is_relevant:
                yield create_status_message(
                    f'Extracting relevant data from the dataset...',
                    start_time
                )
                
                try:
                    # Extract the relevant data
                    relevant_data = extract_relevant_data(
                        dataset_content, 
                        query, 
                        dataset_info
                    )
                    
                    # Execute the relevant data extraction
                    extracted_data = execute_relevant_data(relevant_data)
                    
                    # Debug print extracted_data
                    print("extracted_data", extracted_data)
                    
                    # Add dataset source information to the extracted data
                    if extracted_data:
                        extracted_data["dataset_title"] = dataset_info["title"]
                        extracted_data["dataset_source"] = dataset_info.get("description", "Dataset")
                        extracted_data["dataset_id"] = dataset_info["id"]
                        extracted_data["file_path"] = dataset_info["file_path"]
                        
                        # Send extracted data as part of the stream
                        yield json.dumps({
                            'type': 'extracted_data',
                            'data': extracted_data,
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n'
                        
                except Exception as e:
                    logger.error(f"Error extracting relevant data: {str(e)}")
                    yield create_status_message(
                        f'Error extracting data: {str(e)}',
                        start_time
                    )
                    # Continue with analysis even if extraction fails
            
            # Analyze the dataset
            yield create_status_message(
                f'Analyzing the dataset content...',
                start_time
            )
        
            try:
                # This will perform the analysis and return a dictionary with the results
                analysis_result = analyze_dataset_overview(
                    dataset_content,
                    query,
                    dataset_info,
                    extracted_data=extracted_data  # Pass extracted data to enhance analysis
                )
                
                # Add to the list of dataset analyses
                all_dataset_analyses.append({
                    'dataset_id': dataset_id,
                    'dataset_title': dataset_info["title"],
                    'row_count': analysis_result.get('row_count', 0),
                    'column_count': analysis_result.get('column_count', 0),
                    'analysis': analysis_result.get('analysis', 'No analysis available'),
                    'geographic_scope': analysis_result.get('geographic_scope', 'Unknown'),
                    'temporal_scope': analysis_result.get('temporal_scope', 'Unknown'),
                    'categorical_summaries': analysis_result.get('categorical_summaries', [])
                })
                
                # Format the extracted data using the new helper function
                if extracted_data:
                    yield create_status_message(
                        f'Formatting extracted data for better readability...',
                        start_time
                    )
                    
                    formatted_data = format_extracted_data(
                        extracted_data,
                        analysis_result,
                        query
                    )
                    
                    # Add to the list of formatted data
                    if isinstance(formatted_data, dict) and 'formatted_data' in formatted_data:
                        all_formatted_data.append(formatted_data['formatted_data'])
                    
                    # Send formatted data as part of the stream
                    yield json.dumps({
                        'type': 'formatted_data',
                        'data': formatted_data,
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n'
                
                # Stream each part of the analysis
                yield json.dumps({
                    'type': 'analysis_result',
                    'data': {
                        'dataset_info': {
                            'id': dataset_id,
                            'title': dataset_metadata.get('title', ''),
                            'rows': analysis_result.get('row_count', 0),
                            'columns': analysis_result.get('column_count', 0),
                            'relevance_score': relevance_score if 'relevance_score' in locals() else None,
                            'relevance_reasoning': reasoning if 'reasoning' in locals() else None
                        }
                    },
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                # Send the full analysis
                yield json.dumps({
                    'type': 'analysis',
                    'data': analysis_result.get('analysis', 'No analysis available'),
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
            
            except Exception as e:
                logger.error(f"Error analyzing dataset: {str(e)}")
                yield create_error_message(
                    f'Error analyzing dataset: {str(e)}',
                    details=traceback.format_exc(),
                    start_time=start_time
                )
                return
        
        # After processing all datasets, generate the findings summary
        if all_formatted_data:
            yield create_status_message(
                f'Generating summary of findings from all datasets...',
                start_time
            )
            
            try:
                # Generate findings summary from all formatted data
                findings = summarize_findings(
                    query=query,
                    formatted_data_list=all_formatted_data,
                    dataset_analyses=all_dataset_analyses
                )
                
                # Send the findings as part of the stream
                yield json.dumps({
                    'type': 'findings',
                    'data': findings,
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
                # Format the findings for display
                formatted_findings = format_findings_for_display(findings)
                
                # Send the formatted findings as part of the stream
                yield json.dumps({
                    'type': 'formatted_findings',
                    'data': formatted_findings,
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
                
            except Exception as e:
                logger.error(f"Error generating findings summary: {str(e)}")
                yield create_error_message(
                    f'Error generating findings summary: {str(e)}',
                    details=traceback.format_exc(),
                    start_time=start_time
                )
                # Continue with completion even if findings summary fails
        
        # Final completion message
        analysis_time = time.time() - start_time
        
        # Create the complete message with both dataset and web search results
        complete_data = {
            'query': query,
            'dataset_ids': dataset_ids,
            'execution_time': analysis_time
        }
        
        # Add web search results (ensuring it's a valid dictionary)
        if search_results and isinstance(search_results, dict):
            # Extract the search_results nested dictionary if it exists
            if 'search_results' in search_results:
                complete_data['web_search_results'] = search_results['search_results']
            else:
                complete_data['web_search_results'] = search_results
        else:
            complete_data['web_search_results'] = {
                "query": query,
                "results": [],
                "error": "Web search results unavailable or in unexpected format"
            }
        
        yield json.dumps({
            'type': 'complete',
            'data': complete_data,
            'message': f'Analysis completed in {analysis_time:.2f} seconds',
            'timestamp': analysis_time
        }, cls=NumpyEncoder) + '\n'
            
    except Exception as e:
        # Send error message
        error_message = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Error in stream_analyze: {error_message}")
        logger.error(traceback_str)
        
        yield create_error_message(
            "I'm sorry, I encountered an error while processing your request. Please try again.",
            details=error_message,
            start_time=start_time if 'start_time' in locals() else None
        )

def process_resource_metadata(resource_metadata):
    """
    Process resource metadata to organize resources by dataset ID.
    
    Args:
        resource_metadata: Dictionary where keys are resource IDs and values are resource metadata
        
    Returns:
        Dictionary where keys are dataset IDs and values are lists of resources
    """
    datasets = {}
    
    for resource_id, resource in resource_metadata.items():
        # Get the dataset ID from the resource metadata
        dataset_id = resource.get('dataset_dataset_id')
        
        if not dataset_id:
            logger.warning(f"Resource {resource_id} has no dataset ID, skipping")
            continue
            
        # Initialize the dataset entry if it doesn't exist
        if dataset_id not in datasets:
            datasets[dataset_id] = {
                'dataset_id': dataset_id,
                'title': resource.get('dataset_title', 'Unknown Dataset'),
                'description': resource.get('dataset_notes', ''),
                'organization': resource.get('dataset_organization_title', ''),
                'resources': []
            }
            
        # Add the resource to the dataset's resources list
        resource_entry = {
            'resource_id': resource_id,
            'name': resource.get('name', ''),
            'description': resource.get('description', ''),
            'format': resource.get('format', ''),
            'url': resource.get('url', ''),
            'size': resource.get('size'),
            'mimetype': resource.get('mimetype', ''),
            'is_cached': resource.get('is_cached', False),
            'cache_uri': resource.get('cache_uri'),
            'position': resource.get('position', 0)
        }
        
        datasets[dataset_id]['resources'].append(resource_entry)
    
    # Sort resources by position for each dataset
    for dataset_id in datasets:
        datasets[dataset_id]['resources'].sort(key=lambda x: x.get('position', 0))
    
    return datasets
