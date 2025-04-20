from typing import Any, Dict, List
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
import threading
import pprint
import pandas as pd
import queue
try:
    import pyarrow.parquet as pq
except ImportError:
    # Use an alternative like pandas for Parquet
    import pandas as pd
    
    # Define wrapper functions to maintain compatibility
    def read_parquet(file_path):
        return pd.read_parquet(file_path)
    
    # Create a pq namespace with similar functions
    class ParquetCompat:
        @staticmethod
        def read_table(file_path):
            return read_parquet(file_path)
    
    pq = ParquetCompat()
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
# Import for parallel search
from factchecker.search.web_search import tavily_web_search, enhanced_web_search, combined_web_search
from factchecker.search.search_utils import generate_similar_queries
from factchecker.processing.analysis.web_search_result_analyzer import analyze_search_results, summarize_search_analysis

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
        # Handle pandas Timestamp objects
        if hasattr(obj, 'isoformat') and callable(getattr(obj, 'isoformat')):
            return obj.isoformat()
        # Fallback for any other non-serializable types
        try:
            return str(obj)  # Convert any other type to string for safety
        except:
            return None  # If string conversion fails, return None
        # This line won't be reached due to the fallbacks above, but kept for completeness
        return super(NumpyEncoder, self).default(obj)

def create_status_message(message, start_time, dataset_id=None, status=None, progress=None):
    """Create a status message JSON object, optionally with dataset status information"""
    status_obj = {
        'type': 'status',
        'message': message,
        'timestamp': time.time() - start_time
    }
    
    # If dataset_id is provided, this is a dataset status update
    if dataset_id:
        status_obj['type'] = 'dataset_status'
        status_obj['dataset_id'] = dataset_id
        
        # Include status if provided
        if status:
            status_obj['status'] = status
            
        # Include progress if provided
        if progress is not None:
            status_obj['progress'] = progress
    
    return json.dumps(status_obj, cls=NumpyEncoder) + '\n'

def create_error_message(message, details=None, start_time=None, dataset_id=None):
    """Create an error message JSON object, optionally with dataset information"""
    timestamp = time.time() - start_time if start_time else time.time()
    error_obj = {
        'type': 'error',
        'message': message,
        'timestamp': timestamp
    }
    
    # Add dataset_id if provided (for dataset-specific errors)
    if dataset_id:
        error_obj['dataset_id'] = dataset_id
        
    # Add error details if provided
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

def stream_analyze_helper(dataset_ids, query, file_path=None, parallel=True):
    """
    Helper function that generates the streaming analysis results for a dataset.
    Runs web search in parallel and streams results alongside dataset analysis.
    
    Args:
        dataset_ids: List of dataset IDs to analyze
        query: The user query
        file_path: Optional path to the dataset file (if not provided, will look in standard locations)
        parallel: Boolean flag to control whether to run web searches and dataset processing in parallel (default: True)
        
    Yields:
        Streaming analysis results as JSON strings, including web search results
    """
    start_time = time.time()
    message_queue = queue.Queue()
    web_search_results_storage = {} # Dictionary to store final web results for completion message

    # --- Web Search Runner Function (to be run in a separate thread) ---
    def run_web_search_and_process(query, message_queue, start_time, web_search_results_storage):
        try:
            message_queue.put(create_status_message(
                'Initiating parallel web searches...', start_time
            ))
            
            # Generate similar queries
            similar_queries = generate_similar_queries(query, num_variations=3)
            logger.info(f"Generated similar queries for web search: {similar_queries}")
            message_queue.put(create_status_message(
                f'Searching with variations: {", ".join(similar_queries[:2])}...', start_time
            ))

            # Function to run web search for a specific query
            def search_worker(search_query):
                try:
                    logger.info(f"Executing search for query variation: '{search_query}'")
                    # Use enhanced_web_search or combined_web_search as appropriate
                    # This example uses enhanced_web_search
                    results = enhanced_web_search(
                        query=search_query,
                        max_results=5, 
                        search_type="comprehensive" # Or other type
                    )
                    # Check structure of results - might vary based on search function used
                    # Assuming results is a dict containing a list under 'results'
                    return {"query": search_query, "results": results.get("results", []) if isinstance(results, dict) else results}
                except Exception as e:
                    logger.error(f"Error in web search worker for query '{search_query}': {str(e)}")
                    return {"query": search_query, "error": str(e), "results": []}

            all_search_results_raw = []
            # Execute searches in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(similar_queries)) as executor:
                future_to_query = {executor.submit(search_worker, q): q for q in similar_queries}
                for future in concurrent.futures.as_completed(future_to_query):
                    query_variation = future_to_query[future]
                    try:
                        result = future.result()
                        all_search_results_raw.append(result)
                        message_queue.put(create_status_message(
                            f'Completed search variation: "{query_variation}"', start_time
                        ))
                    except Exception as e:
                        logger.error(f"Error processing result for query '{query_variation}': {e}")
                        message_queue.put(create_error_message(
                            f'Error processing search result for "{query_variation}": {e}', start_time=start_time
                        ))

            # Process and combine the results
            message_queue.put(create_status_message('Processing web search results...', start_time))
            combined_results = []
            for result in all_search_results_raw:
                # Assuming 'results' key holds the list of search items
                if "results" in result and isinstance(result["results"], list):
                    combined_results.extend(result["results"])

            # Deduplicate and sort
            unique_urls = set()
            unique_results = []
            for res in combined_results:
                url = res.get("url")
                if url and url not in unique_urls:
                    unique_urls.add(url)
                    unique_results.append(res)
            unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            final_search_payload = {
                "query": query,
                "results": unique_results[:10], # Limit results
                "total_results": len(unique_results),
                "search_method": "parallel_similar_queries"
            }

            # Analyze results
            analysis = analyze_search_results(query, final_search_payload, max_results=10)
            summary = summarize_search_analysis(query, analysis)

            processed_search_results = {
                "search_results": final_search_payload,
                "analysis": analysis,
                "summary": summary
            }

            # Store results for final message
            web_search_results_storage.update(processed_search_results) 

            # Put results onto the queue for streaming
            message_queue.put(json.dumps({
                'type': 'web_search_results',
                'data': processed_search_results['search_results'], # Send the 'results' part
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n')
            
            message_queue.put(json.dumps({
                'type': 'web_search_summary',
                'data': processed_search_results['summary'], # Send the summary
                'timestamp': time.time() - start_time
            }, cls=NumpyEncoder) + '\n')

            message_queue.put(create_status_message('Web search processing complete.', start_time))

        except Exception as e:
            logger.error(f"Error in web search thread: {str(e)}")
            logger.error(traceback.format_exc())
            message_queue.put(create_error_message(
                f'An error occurred during web search: {str(e)}',
                details=traceback.format_exc(),
                start_time=start_time
            ))
            web_search_results_storage['error'] = f"Web search failed: {str(e)}" # Store error
        finally:
            # Signal completion of this thread
            message_queue.put(None) 
    # --- End Web Search Runner Function ---

    try:
        # Send initial message
        yield create_status_message(
            f'I am starting my analysis of the dataset for your query: "{query}"...',
            start_time
        )
        
        # Validate inputs
        if not dataset_ids:
            message_queue.put(create_error_message(
                'Dataset ID is required for analysis.',
                start_time=start_time
            ))
            message_queue.put(None) # Signal immediate completion if invalid input
            web_search_thread = None # No web search if input invalid
            return
        else:
            # Start the web search thread
            web_search_thread = threading.Thread(
                target=run_web_search_and_process, 
                args=(query, message_queue, start_time, web_search_results_storage)
            )
            web_search_thread.start()

        # Get the resource metadata from the DB
        resource_metadata = query_datasets_helper(dataset_ids)

        # Process it 
        datasets = process_resource_metadata(resource_metadata)

        # If we have no datasets, just return
        if not datasets:
            logger.info("No datasets with usable resources found.")
            raise Exception("No datasets with usable resources")
        
        # Lists to collect all formatted data and analyses
        all_formatted_data = []
        all_dataset_analyses = []
        
        num_dataset_tasks = 0

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

        def process_dataset(dataset_id, dataset, message_queue, start_time):
            """Helper function to process a single dataset"""
            try:
                # Set initial dataset status to queued
                message_queue.put(create_status_message(
                    f'Adding dataset "{dataset["title"]}" to processing queue',
                    start_time,
                    dataset_id=dataset_id,
                    status='queued'
                ))
                
                best_resource = dataset['best_resource']

                # Set status to downloading
                message_queue.put(create_status_message(
                    f'Downloading files for dataset "{dataset["title"]}"',
                    start_time,
                    dataset_id=dataset_id,
                    status='downloading'
                ))

                file_path = download_resource_helper(dataset_id, best_resource)
                print(file_path)

                if not file_path:
                    # Handle download failure
                    message_queue.put(create_status_message(
                        f'Failed to download dataset files',
                        start_time,
                        dataset_id=dataset_id,
                        status='error'
                    ))
                    return

                # Update status to downloaded
                message_queue.put(create_status_message(
                    f'Successfully downloaded dataset files',
                    start_time,
                    dataset_id=dataset_id,
                    status='downloaded'
                ))

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
                message_queue.put(create_status_message(
                    f'Performing initial relevance assessment...',
                    start_time
                ))
                
                # Update status to loading
                message_queue.put(create_status_message(
                    f'Loading the dataset from {file_path}...',
                    start_time,
                    dataset_id=dataset_id,
                    status='loading'
                ))
                
                try:
                    # Pass the explicit format from the resource metadata if available
                    file_format = best_resource.get('resource_format')
                    dataset_content = load_datafile(file_path, file_format=file_format)
                    
                    # Report successful loading
                    if hasattr(dataset_content, 'shape'):
                        message_queue.put(create_status_message(
                            f'Successfully loaded dataset with {dataset_content.shape[0]} rows and {dataset_content.shape[1]} columns.',
                            start_time
                        ))
                    else:
                        message_queue.put(create_status_message(
                            f'Successfully loaded dataset.',
                            start_time
                        ))
                        
                except Exception as e:
                    logger.error(f"Error loading dataset: {str(e)}")
                    logger.error(f"Failed to load resource file: {file_path} for dataset {dataset_id} error {str(e)}")
                    # Update status to error
                    message_queue.put(create_status_message(
                        f'Error loading dataset: {str(e)}',
                        start_time,
                        dataset_id=dataset_id,
                        status='error'
                    ))
                    
                    message_queue.put(create_error_message(
                        f'Error loading dataset: {str(e)}',
                        details=traceback.format_exc(),
                        start_time=start_time,
                        dataset_id=dataset_id
                    ))
                    return
                
                # Update status to assessing
                message_queue.put(create_status_message(
                    f'Assessing dataset relevance to your query...',
                    start_time,
                    dataset_id=dataset_id,
                    status='assessing'
                ))
                
                try:
                    # Create more detailed dataset info now that we have the data
                    if hasattr(dataset_content, 'shape'):
                        dataset_info = {
                            "id": dataset_id,
                            "title": dataset.get('title', os.path.basename(file_path)),
                            "description": dataset.get('description', "Dataset for analysis"),
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
                    
                    # After assessment, update status based on relevance
                    relevance_status = 'relevant' if is_relevant else 'not_relevant'
                    message_queue.put(create_status_message(
                        f'Dataset assessed as {relevance_status} (Score: {relevance_score:.2f})',
                        start_time,
                        dataset_id=dataset_id,
                        status=relevance_status
                    ))
                    
                    if is_relevant:
                        message_queue.put(create_status_message(
                            f'Dataset is relevant to your query (Score: {relevance_score:.2f})',
                            start_time
                        ))
                        message_queue.put(create_status_message(
                            f'Reasoning: {reasoning}',
                            start_time
                        ))
                    else:
                        message_queue.put(create_status_message(
                            f'Dataset may not be highly relevant to your query (Score: {relevance_score:.2f})',
                            start_time
                        ))
                        message_queue.put(create_status_message(
                            f'Reasoning: {reasoning}',
                            start_time
                        ))
                    
                except Exception as e:
                    logger.warning(f"Error in relevance assessment: {str(e)}")
                    # Update status to error for assessment
                    message_queue.put(create_status_message(
                        f'Error assessing relevance: {str(e)}',
                        start_time,
                        dataset_id=dataset_id,
                        status='error'
                    ))
                    
                    # Continue with analysis even if relevance assessment fails
                    is_relevant = True  # Assume relevant if assessment fails
                
                # Extract relevant data if the dataset is deemed relevant
                extracted_data = None
                if is_relevant:
                    # Update status to extracting
                    message_queue.put(create_status_message(
                        f'Extracting relevant data from the dataset...',
                        start_time,
                        dataset_id=dataset_id,
                        status='extracting'
                    ))
                    
                    try:
                        # Extract the relevant data
                        relevant_data = extract_relevant_data(
                            dataset_content, 
                            query, 
                            dataset_info
                        )
                        
                        # Execute the relevant data extraction
                        extracted_data = execute_relevant_data(relevant_data)
                        
                        # Update extracted_data with the dataset info - use the passed dataset param, not outer datasets
                        extracted_data["dataset_title"] = dataset.get('title', os.path.basename(file_path))
                        extracted_data["dataset_source"] = dataset.get("organization", "Unknown Source")
                        extracted_data["organization_title"] = dataset.get("organization", "")
                        extracted_data["organization_name"] = dataset.get("organization_name", "")
                        
                        # Update extracted_data with dataset identity info before formatting
                        extracted_data["dataset_id"] = dataset_id
                        extracted_data["dataset_title"] = dataset.get('title', os.path.basename(file_path))
                        extracted_data["organization"] = dataset.get('organization', "")
                        extracted_data["organization_title"] = dataset.get('organization', "")
                        extracted_data["organization_name"] = dataset.get('organization_name', "")
                        
                        # Send extracted data as part of the stream
                        message_queue.put(json.dumps({
                            'type': 'extracted_data',
                            'data': extracted_data,
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n')
                        
                        # After successful extraction
                        message_queue.put(create_status_message(
                            f'Successfully extracted relevant data',
                            start_time,
                            dataset_id=dataset_id,
                            status='extracted'
                        ))
                        
                    except Exception as e:
                        logger.error(f"Error extracting relevant data: {str(e)}")
                        # Update status for extraction error
                        message_queue.put(create_status_message(
                            f'Error extracting data: {str(e)}',
                            start_time,
                            dataset_id=dataset_id,
                            status='error'
                        ))
                        
                        message_queue.put(create_error_message(
                            f'Error extracting data: {str(e)}',
                            details=traceback.format_exc(),
                            start_time=start_time,
                            dataset_id=dataset_id
                        ))
                        # Continue with analysis even if extraction fails
                
                # Update status to analyzing
                message_queue.put(create_status_message(
                    f'Analyzing the dataset content...',
                    start_time,
                    dataset_id=dataset_id,
                    status='analyzing'
                ))
                
                try:
                    # This will perform the analysis and return a dictionary with the results
                    analysis_result = analyze_dataset_overview(
                        dataset_content,
                        query,
                        dataset_info,
                        extracted_data=extracted_data  # Pass extracted data to enhance analysis
                    )
                    
                    # Add to the list of dataset analyses via special message type
                    dataset_analysis = {
                        'dataset_id': dataset_id,
                        'dataset_title': dataset_info["title"],
                        'row_count': analysis_result.get('row_count', 0),
                        'column_count': analysis_result.get('column_count', 0),
                        'analysis': analysis_result.get('analysis', 'No analysis available'),
                        'geographic_scope': analysis_result.get('geographic_scope', 'Unknown'),
                        'temporal_scope': analysis_result.get('temporal_scope', 'Unknown'),
                        'categorical_summaries': analysis_result.get('categorical_summaries', [])
                    }
                    
                    # Put dataset analysis into queue with special type for collection in main thread
                    message_queue.put(json.dumps({
                        'type': 'dataset_analysis_result_internal',
                        'data': dataset_analysis,
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n')
                    
                    # Format the extracted data using the new helper function
                    if extracted_data:
                        message_queue.put(create_status_message(
                            f'Formatting extracted data for better readability...',
                            start_time
                        ))
                        
                        formatted_data = format_extracted_data(
                            extracted_data,
                            analysis_result,
                            query
                        )
                        
                        # Log what we're getting back
                        logger.info(f"Formatted data organization info: " + 
                                   f"source={formatted_data.get('formatted_data', {}).get('dataset_source')}")
                        
                        # Add to the list of formatted data with dataset identity preserved via special message type
                        if isinstance(formatted_data, dict) and 'formatted_data' in formatted_data:
                            # Create a copy of the formatted data with dataset identity fields
                            formatted_entry = formatted_data['formatted_data'].copy() if isinstance(formatted_data['formatted_data'], dict) else {'data': formatted_data['formatted_data']}
                            
                            # Add dataset identity fields to the entry
                            formatted_entry['dataset_id'] = dataset_id
                            formatted_entry['dataset_title'] = dataset.get('title', os.path.basename(file_path))
                            # Preserve organization information
                            formatted_entry['organization'] = dataset.get('organization', '')
                            formatted_entry['organization_title'] = dataset.get('organization', '')
                            formatted_entry['organization_name'] = dataset.get('organization_name', '')
                            
                            # Log what we're adding to all_formatted_data
                            logger.info(f"Adding formatted data with organization info: " + 
                                      f"id={dataset_id}, " +
                                      f"title={formatted_entry['dataset_title']}, " +
                                      f"org={formatted_entry['organization']}")
                            
                            # Put formatted entry into queue with special type for collection in main thread
                            message_queue.put(json.dumps({
                                'type': 'formatted_data_internal',
                                'data': formatted_entry,
                                'timestamp': time.time() - start_time
                            }, cls=NumpyEncoder) + '\n')
                        
                        # Send formatted data as part of the stream
                        message_queue.put(json.dumps({
                            'type': 'formatted_data',
                            'data': formatted_data,
                            'timestamp': time.time() - start_time
                        }, cls=NumpyEncoder) + '\n')
                    
                    # Stream each part of the analysis
                    message_queue.put(json.dumps({
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
                    }, cls=NumpyEncoder) + '\n')
                    
                    # Send the full analysis
                    message_queue.put(json.dumps({
                        'type': 'analysis',
                        'data': analysis_result.get('analysis', 'No analysis available'),
                        'timestamp': time.time() - start_time
                    }, cls=NumpyEncoder) + '\n')
                    
                    # After successful analysis, update status to complete
                    message_queue.put(create_status_message(
                        f'Dataset analysis complete',
                        start_time,
                        dataset_id=dataset_id,
                        status='complete'
                    ))
                    
                except Exception as e:
                    logger.error(f"Error analyzing dataset: {str(e)}")
                    # Update status for analysis error
                    message_queue.put(create_status_message(
                        f'Error analyzing dataset: {str(e)}',
                        start_time,
                        dataset_id=dataset_id,
                        status='error'
                    ))
                    
                    message_queue.put(create_error_message(
                        f'Error analyzing dataset: {str(e)}',
                        details=traceback.format_exc(),
                        start_time=start_time,
                        dataset_id=dataset_id
                    ))
            finally:
                # Always put sentinel value to indicate task completion, even on error
                message_queue.put(None)

        # --- Dataset Processing Execution ---
        if parallel:
            print("Processing datasets in Parallel...")
            # Process datasets in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(datasets)) as executor:
                # Submit all tasks
                num_tasks = 0
                for dataset_id, dataset in datasets.items():
                    if dataset_id in datasets: # Ensure dataset exists before submitting
                        executor.submit(process_dataset, dataset_id, datasets[dataset_id], message_queue, start_time)
                        num_dataset_tasks += 1
                    else:
                        logger.warning(f"Dataset ID {dataset_id} not found in processed datasets dict, skipping task submission.")
                        # If a task isn't submitted, we shouldn't wait for its sentinel later
                        # No need to explicitly decrement total_tasks here if calculated later
        else:
            # Process datasets sequentially
            print("Processing datasets Sequentially...")
            for dataset_id, dataset in datasets.items():
                 # Process each dataset
                process_dataset(dataset_id, dataset, message_queue, start_time)
                num_dataset_tasks += 1

        # --- Main Message Consumption Loop ---
        total_tasks = num_dataset_tasks + (1 if web_search_thread else 0)
        finished_tasks = 0
        
        while finished_tasks < total_tasks:
            message = message_queue.get()
            if message is None:
                finished_tasks += 1
            elif isinstance(message, str) and message.strip():
                try:
                    message_obj = json.loads(message)
                    message_type = message_obj.get('type', '')
                    
                    # Collect internal data for final summary
                    if message_type == 'dataset_analysis_result_internal':
                        all_dataset_analyses.append(message_obj['data'])
                    elif message_type == 'formatted_data_internal':
                        all_formatted_data.append(message_obj['data'])
                    else:
                        # Yield regular messages to the client
                        yield message
                except json.JSONDecodeError:
                    # Not a JSON message, yield as is (e.g., plain status updates)
                    yield message
                except Exception as e:
                    logger.error(f"Error processing message from queue: {e} | Message: {message}")
                    # Decide if you want to yield an error message here

        # Wait for the web search thread to finish if it was started
        if web_search_thread:
            web_search_thread.join()

        # After processing all datasets, send a message that all datasets have been analyzed
        # This message might be redundant now due to the loop structure, consider removing
        # yield create_status_message(
        #     f'All datasets have been analyzed successfully.',
        #     start_time,
        #     status='all_datasets_analyzed'
        # )

        # Generate final findings summary if data was collected
        if all_formatted_data:
            yield create_status_message(
                f'Generating summary of findings from all datasets...', start_time
            )
            try:
                findings = summarize_findings(
                    query=query,
                    formatted_data_list=all_formatted_data,
                    dataset_analyses=all_dataset_analyses
                )
                yield json.dumps({
                    'type': 'findings',
                    'data': findings,
                    'timestamp': time.time() - start_time
                }, cls=NumpyEncoder) + '\n'
            except Exception as e:
                logger.error(f"Error generating findings summary: {str(e)}")
                yield create_error_message(
                    f'Error generating findings summary: {str(e)}',
                    details=traceback.format_exc(),
                    start_time=start_time
                )

        # Final completion message
        analysis_time = time.time() - start_time
        
        # Create the complete message with both dataset and web search results
        complete_data = {
            'query': query,
            'dataset_ids': dataset_ids,
            'execution_time': analysis_time,
            # Use the stored web search results
            'web_search_results': web_search_results_storage 
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
            start_time=start_time if 'start_time' in locals() else None,
            dataset_id=None
        )

def process_resource_metadata(resource_metadata):
    """
    Process resource metadata to organize resources by dataset ID.
    """
    datasets = {}
    
    for resource_id, resource in resource_metadata.items():
        # Get the dataset ID from the resource metadata
        dataset_id = resource.get('dataset_dataset_id')
        
        if not dataset_id:
            logger.warning(f"Resource {resource_id} has no dataset ID, skipping")
            continue
            
        # Log the organization fields from the resource
        logger.info(f"Resource {resource_id} organization data: " +
                   f"organization_title={resource.get('dataset_organization_title')}, " +
                   f"organization_name={resource.get('dataset_organization_name')}")
        

        # Skip unsupported types
        if resource.get('format') not in ["CSV", "XML", "XLSX", "XLS", "JSON"]:
            logger.error(f"Unsupported ressource {resource.get('format')}, skipping adding.")
            continue
            
        # Initialize the dataset entry if it doesn't exist
        if dataset_id not in datasets:
            datasets[dataset_id] = {
                'dataset_id': dataset_id,
                'title': resource.get('dataset_title', 'Unknown Dataset'),
                'description': resource.get('dataset_notes', ''),
                # Store all organization fields
                'organization': resource.get('dataset_organization_title', ''),
                'organization_name': resource.get('dataset_organization_name', ''),
                'organization_description': resource.get('dataset_organization_description', ''),
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
    

    # If length is 0, return None. This means no datasets were processed.
    if len(datasets) == 0:
        logger.error("No usable dataset resources were identified in the provided metadata.")
        return None

    # Sort resources by position for each dataset
    for dataset_id in datasets:
        datasets[dataset_id]['resources'].sort(key=lambda x: x.get('position', 0))
    
    return datasets
