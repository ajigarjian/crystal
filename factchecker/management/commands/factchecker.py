# factchecker/management/commands/factchecker.py
import argparse
from django.core.management.base import BaseCommand

# For searching for the right datasets to download, we use vector search, and have support for keyword search using the gov api
from factchecker.search import vector_search_datasets
from factchecker.search import preprocess_query, search_datasets, filter_relevant_datasets

# For downloading the resources in the datasets, we use the download_resource function for now
from factchecker.download import download_resource

# For analyzing the datasets and extracting the relevant data, we use the following functions
from factchecker.processing.analysis import (
    load_datafile,
    assess_datafile_relevance,
    extract_relevant_data,
    analyze_dataset_overview
)

from factchecker.presentation.cli_tool_functions import summarize_findings, summarize_findings_alternate

# Import Django settings including API keys
from django.conf import settings

import pandas as pd
from typing import Dict, Tuple, List, Any, Optional
import openai
import time
import concurrent.futures
from threading import Lock
import os
import json

class Command(BaseCommand):
    help = 'Search for and analyze datasets based on a user query. Uses hybrid search (combination of vector and keyword) by default.'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create a lock for thread-safe stdout writing
        self.stdout_lock = Lock()
    
    def add_arguments(self, parser):
        parser.add_argument("query", help="Natural language query to search for datasets")
        parser.add_argument("--similarity-threshold", type=float, default=0.5, 
                           help="Minimum similarity score (0-1) for including datasets in vector search results")
        parser.add_argument("--output", default="downloads", help="Directory to save downloaded files")
        parser.add_argument("--preview", action="store_true", help="Show data preview")
        parser.add_argument("--relevance-threshold", type=float, default=0.4, 
                           help="Threshold for dataset relevance (0-1)")
        parser.add_argument("--force", help="Comma-separated list of local dataset paths to analyze directly, skipping search")
        parser.add_argument("--workers", type=int, default=3, 
                           help="Number of parallel workers for processing datasets")
        parser.add_argument(
            '--search-method',
            choices=['vector', 'keyword'],
            help='Specify a single search method to use instead of the default hybrid search'
        )
        parser.add_argument(
            '--sequential',
            action='store_true',
            help='Process datasets sequentially instead of in parallel (useful for debugging)'
        )
        parser.add_argument(
            '--json-output',
            action='store_true',
            help='Generate comprehensive JSON output with full extracted data instead of text summary'
        )
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Print debug information about data flow'
        )
    
    def handle(self, *args, **options):
        # Start timing the execution
        start_time = time.time()
        
        query = options['query']
        similarity_threshold = options.get('similarity_threshold', 0.5)
        output_dir = options['output']
        show_preview = options['preview']
        relevance_threshold = options['relevance_threshold']
        force_datasets = options.get('force')
        workers = options.get('workers', 3)
        search_method = options.get('search_method', None)
        sequential = options.get('sequential', False)
        json_output = options.get('json_output', False)
        debug_file_paths = options.get('debug', False)
                
        self.stdout.write(f"Factchecker query: '{query}'")
        
        # Initialize API keys
        try:
            api_keys = self.init_api_key()
            gov_api_key = api_keys["data_gov"]
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Error initializing API keys: {e}"))
            return
        
        # Base threshold for vector search
        similarity_threshold = options.get('similarity_threshold', 0.5)  # Default to 0.5 if not specified
        
        # Higher threshold for keyword search
        keyword_threshold = similarity_threshold + 0.2  # 0.2 higher than vector threshold (so default 0.7)
        
        # Modified dataset search logic
        if force_datasets:
            self.stdout.write(f"Skipping search and using specified datasets: {force_datasets}")
            dataset_paths = [path.strip() for path in force_datasets.split(',')]
            
            relevant_datasets = []

            for path in dataset_paths:
                # Create a minimal dataset info dict for each forced dataset
                dataset_name = path.split('/')[-1] if '/' in path else path
                relevant_datasets.append({
                    "id": f"local-{dataset_name}",
                    "title": dataset_name,
                    "description": "Locally specified dataset",
                    "similarity": 1.0,  # Assume perfect similarity since user specified it
                    "local_path": path  # Add the local path directly
                })
        elif search_method:
            # User explicitly specified a single search method
            if search_method == 'vector':
                # Vector search with specified threshold
                self.stdout.write(f"Searching for datasets matching '{query}' using vector search with similarity threshold {similarity_threshold:.2f}...")
                relevant_datasets = vector_search_datasets(query, similarity_threshold=similarity_threshold)
                
                # Display all results
                if relevant_datasets:
                    self.stdout.write(f"Found {len(relevant_datasets)} datasets with similarity >= {similarity_threshold:.2f}")
                    for i, dataset in enumerate(relevant_datasets):
                        self.stdout.write(f"  {i+1}. {dataset['title']} - Similarity: {dataset.get('similarity', 0):.4f}")
                else:
                    self.stdout.write("No datasets found.")
            else:
                # Keyword search with higher threshold
                self.stdout.write(f"Searching for datasets matching '{query}' using keyword search with similarity threshold {keyword_threshold:.2f}...")
                relevant_datasets = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)
                
                # Display all results
                if relevant_datasets:
                    self.stdout.write(f"Found {len(relevant_datasets)} datasets with similarity >= {keyword_threshold:.2f}")
                    for i, dataset in enumerate(relevant_datasets):
                        self.stdout.write(f"  {i+1}. {dataset['title']} - Similarity: {dataset.get('similarity', 0):.4f}")
                else:
                    self.stdout.write("No datasets found.")
        else:
            # DEFAULT: Use hybrid search approach with vector search as primary method
            self.stdout.write(f"Searching for datasets matching '{query}' using hybrid search...")
            self.stdout.write(f"Vector search threshold: {similarity_threshold:.2f}, Keyword search threshold: {keyword_threshold:.2f}")

            # Get vector search results with threshold (primary method)
            self.stdout.write(f"Performing vector search (primary method)...")
            vector_datasets = vector_search_datasets(query, similarity_threshold=similarity_threshold)

            if vector_datasets:
                # Display similarity scores for ALL vector search results
                self.stdout.write(f"Found {len(vector_datasets)} datasets via vector search with similarity >= {similarity_threshold:.2f}")
                self.stdout.write("Vector search results with similarity scores:")
                for i, dataset in enumerate(vector_datasets):  # Show all datasets
                    self.stdout.write(f"  {i+1}. {dataset['title']} - Similarity: {dataset.get('similarity', 0):.4f}")
            else:
                self.stdout.write("No datasets found via vector search. Will rely on keyword search.")

            # Get keyword search results with higher threshold (supplementary method)
            self.stdout.write(f"Performing keyword search (supplementary method) with threshold {keyword_threshold:.2f}...")
            keyword_datasets = search_datasets(query, gov_api_key, similarity_threshold=keyword_threshold)

            if keyword_datasets:
                self.stdout.write(f"Found {len(keyword_datasets)} datasets via keyword search with similarity >= {keyword_threshold:.2f}")
                self.stdout.write("Keyword search results with similarity scores:")
                for i, dataset in enumerate(keyword_datasets):  # Show all datasets
                    self.stdout.write(f"  {i+1}. {dataset['title']} - Similarity: {dataset.get('similarity', 0):.4f}")
            else:
                self.stdout.write("No datasets found via keyword search.")
            
            # Get IDs from both search methods
            vector_ids = {dataset['id'] for dataset in vector_datasets}
            keyword_ids = {dataset['id'] for dataset in keyword_datasets}
            
            # Find overlap (datasets found by both methods)
            overlap_ids = vector_ids.intersection(keyword_ids)
            self.stdout.write(f"Found {len(overlap_ids)} datasets in both search results")
            
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
            
            # Then process keyword datasets, skipping duplicates
            for dataset in keyword_datasets:
                dataset_id = dataset['id'] 
                if dataset_id not in seen_ids:
                    dataset['search_source'] = 'keyword'
                    all_datasets.append(dataset)
                    seen_ids.add(dataset_id)
            
            self.stdout.write(f"Combined into {len(all_datasets)} unique datasets after deduplication")
            
            # Sort by similarity score (higher is better)
            all_datasets.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            relevant_datasets = all_datasets
        
        if not relevant_datasets:
            self.stdout.write("No datasets found. Try a different query.")
            # Calculate and display execution time before returning
            execution_time = time.time() - start_time
            self.stdout.write(self.style.SUCCESS(f"\nQuery execution completed in {execution_time:.2f} seconds"))
            return
        
        # Download and analyze each dataset
        results = []
        extracted_data_list = []
        dataset_analyses = []  # Store dataset analyses for final summary
        
        # Define the worker function that processes a single dataset
        def process_dataset(dataset_index, dataset):
            dataset_num = dataset_index + 1
            dataset_id = dataset['id']
            dataset_title = dataset['title']
            # Create an identifier for this dataset (no truncation)
            dataset_short_id = f"[{dataset_num}/{len(relevant_datasets)}] {dataset_title}"
            
            similarity_score = dataset.get('similarity', 1.0)
            with self.stdout_lock:
                self.stdout.write(f"\n{dataset_short_id} Processing dataset (Query similarity: {similarity_score:.4f})")
            
            try:
                # Handle the dataset - either use local path or download
                if 'local_path' in dataset:
                    output_path = dataset['local_path']
                    output_paths = [output_path]  # Single file for local datasets
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Using local dataset: {output_path}")
                else:
                    # Download all CSV/XLSX resources in the dataset
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Downloading dataset resources...")
                    
                    # Modified to download all CSV/XLSX resources
                    from factchecker.download.download_gov_data import download_all_resources
                    output_paths = download_all_resources(gov_api_key, dataset["id"], output_dir=output_dir)
                    
                    if not output_paths:
                        with self.stdout_lock:
                            self.stdout.write(self.style.WARNING(f"{dataset_short_id} Download failed. Skipping dataset."))
                        return {
                            "id": dataset["id"],
                            "title": dataset["title"],
                            "similarity": dataset.get("similarity", 0),
                            "error": "Download failed"
                        }, None, None
                        
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Downloaded {len(output_paths)} files")
                        for i, path in enumerate(output_paths):
                            self.stdout.write(f"  File {i+1}: {path}")
                
                # Initialize primary_file_path here, before the conditional branches
                primary_file_path = output_paths[0]
                
                # Initialize file_analysis to None for single-file datasets
                file_analysis = None
                
                # If multiple files, analyze them together
                if len(output_paths) > 1:
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Analyzing multiple dataset files...")

                    
                    from factchecker.processing.analysis.dataset_analyzer import analyze_dataset_files
                    
                    # Use the function to analyze all files
                    file_analysis = analyze_dataset_files(
                        output_paths, 
                        query, 
                        dataset
                    )
                    
                    # Display file summaries
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Dataset contains {len(output_paths)} files:")
                        for summary in file_analysis["file_summaries"]:
                            if "row_count" in summary:
                                self.stdout.write(f"  - {summary['file_name']}: {summary['row_count']} rows, {summary['column_count']} columns")
                            else:
                                self.stdout.write(f"  - {summary['file_name']}: PDF with {summary.get('num_pages', 'N/A')} pages")
                        
                        # Display combined analysis if available
                        if file_analysis.get("combined_analysis"):
                            self.stdout.write(self.style.SUCCESS("\nCOMBINED FILE ANALYSIS:"))
                            self.stdout.write(file_analysis["combined_analysis"])
                    
                    # Check if we have suggested files from the analysis
                    if "suggested_files" in file_analysis and file_analysis["suggested_files"]:
                        suggested_files = file_analysis["suggested_files"]
                        
                        # Find the paths for the suggested files
                        suggested_file_paths = []
                        for suggested_file in suggested_files:
                            # Find the matching file path
                            matching_paths = [path for path in output_paths if os.path.basename(path) == suggested_file]
                            if matching_paths:
                                suggested_file_paths.append(matching_paths[0])
                        
                        if suggested_file_paths:
                            # Use the first suggested file as primary
                            primary_file_path = suggested_file_paths[0]
                            with self.stdout_lock:
                                self.stdout.write(f"\n{dataset_short_id} Using suggested file {os.path.basename(primary_file_path)} as primary file for detailed analysis")
                                
                            # Store other suggested files for potential use
                            secondary_file_paths = suggested_file_paths[1:] if len(suggested_file_paths) > 1 else []
                            if secondary_file_paths:
                                with self.stdout_lock:
                                    self.stdout.write(f"{dataset_short_id} Additional suggested files for analysis: {', '.join([os.path.basename(p) for p in secondary_file_paths])}")
                        else:
                            # primary_file_path already initialized above, no need to set it again
                            with self.stdout_lock:
                                self.stdout.write(f"\n{dataset_short_id} No matching suggested files found. Using {os.path.basename(primary_file_path)} as primary file for detailed analysis")
                    else:
                        # primary_file_path already initialized above, no need to set it again
                        with self.stdout_lock:
                            self.stdout.write(f"\n{dataset_short_id} Using {os.path.basename(primary_file_path)} as primary file for detailed analysis")
                else:
                    # For single file datasets, we already set primary_file_path above
                    # Just add a log message for clarity
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Single file dataset. Using {os.path.basename(primary_file_path)} for analysis")
                
                # Load the primary dataset file
                datafile_content = load_datafile(primary_file_path)
                
                # Record basic dataset info
                is_pdf = isinstance(datafile_content, dict) and datafile_content.get('type') == 'pdf'

                if is_pdf:
                    # Handle PDF document
                    dataset_info = {
                        "id": dataset["id"],
                        "title": dataset["title"],
                        "description": dataset.get("description", ""),
                        "similarity": similarity_score,
                        "file_path": primary_file_path if primary_file_path else None,
                        "all_file_paths": output_paths,
                        "file_analysis": file_analysis,
                        "document_type": "pdf",
                        "num_pages": datafile_content.get("num_pages", 0),
                        "text_sample": datafile_content.get("text_sample", "")[:200] + "..."  # First 200 chars of text sample
                    }
                else:
                    # Handle DataFrame (tabular data)
                    dataset_info = {
                        "id": dataset["id"],
                        "title": dataset["title"],
                        "description": dataset.get("description", ""),
                        "similarity": similarity_score,
                        "file_path": primary_file_path if primary_file_path else None,
                        "all_file_paths": output_paths,
                        "file_analysis": file_analysis,
                        "row_count": len(datafile_content),
                        "column_count": len(datafile_content.columns),
                        "columns": list(datafile_content.columns)
                    }
                
                # Print preview if requested
                if show_preview:
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Data Preview:")
                        # Check if we're dealing with a PDF
                        if isinstance(datafile_content, dict) and datafile_content.get('type') == 'pdf':
                            # Display PDF preview with enhanced summary if available
                            self.stdout.write(f"PDF Document: {datafile_content.get('file_name', '')}")
                            self.stdout.write(f"Number of Pages: {datafile_content.get('num_pages', 0)}")
                            
                            # Check if enhanced summary is available
                            if "enhanced_summary" in datafile_content:
                                self.stdout.write("\nSummary:")
                                self.stdout.write(datafile_content.get('enhanced_summary', ''))
                                
                                # Display key points if available
                                if datafile_content.get('key_points'):
                                    self.stdout.write("\nKey Points:")
                                    for point in datafile_content.get('key_points', []):
                                        self.stdout.write(f"- {point}")
                            else:
                                self.stdout.write("\nText Sample:")
                                self.stdout.write(f"{datafile_content.get('text_sample', '')[:500]}...")
                        else:
                            # Display DataFrame preview
                            self.stdout.write(str(datafile_content.head()))
                
                # Assess dataset relevance with Azure options
                with self.stdout_lock:
                    self.stdout.write(f"\n{dataset_short_id} Assessing datafile relevance...")
                is_relevant, relevance_score, reasoning = assess_datafile_relevance(
                    datafile_content, 
                    query, 
                    dataset_info,
                    relevance_threshold
                )
                
                dataset_info["relevance_score"] = relevance_score
                dataset_info["relevance_reasoning"] = reasoning
                
                extracted_data = None
                dataset_analysis = None
                
                if is_relevant:
                    with self.stdout_lock:
                        self.stdout.write(self.style.SUCCESS(
                            f"{dataset_short_id} Datafile is relevant (Score: {relevance_score:.2f})"
                        ))
                    
                    # Extract relevant data with Azure options
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Extracting relevant data...")
                    if debug_file_paths:
                        self.stdout.write(f"\n[DEBUG] Before extract_relevant_data:")
                        self.stdout.write(f"  dataset_info keys: {list(dataset_info.keys())}")
                        if 'file_path' in dataset_info:
                            self.stdout.write(f"  file_path: {dataset_info['file_path']}")
                        else:
                            self.stdout.write(f"  file_path missing from dataset_info!")
                    extracted_data = extract_relevant_data(
                        datafile_content, 
                        query, 
                        dataset_info
                    )
                    
                    # Add dataset source information to the extracted data
                    if extracted_data:
                        extracted_data["dataset_title"] = dataset_info["title"]
                        extracted_data["dataset_source"] = dataset_info.get("description", "Data.gov dataset")
                        extracted_data["dataset_id"] = dataset_info["id"]
                        extracted_data["file_path"] = dataset_info["file_path"]
                        extracted_data["all_file_paths"] = dataset_info["all_file_paths"]
                    
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} EXTRACTED DATA:")
                        self.display_extracted_data(extracted_data)
                    
                    # Generate dataset overview analysis with Azure options
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(
                        datafile_content, 
                        query, 
                        dataset_info, 
                        extracted_data=extracted_data
                    )
                    with self.stdout_lock:
                        self.display_dataset_analysis(dataset_analysis)
                    
                    # Add dataset analysis to dataset_info
                    dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                else:
                    with self.stdout_lock:
                        self.stdout.write(self.style.WARNING(
                            f"{dataset_short_id} Datafile is not relevant enough (Score: {relevance_score:.2f})"
                        ))
                    
                    # Even for non-relevant datasets, get a basic analysis with Azure options
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(
                        datafile_content, 
                        query, 
                        dataset_info
                    )
                    with self.stdout_lock:
                        self.display_dataset_analysis(dataset_analysis)
                    dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                
                return dataset_info, dataset_analysis, extracted_data
                
            except Exception as e:
                with self.stdout_lock:
                    self.stderr.write(self.style.ERROR(f"{dataset_short_id} Error analyzing dataset: {e}"))
                # Return error info
                return {
                    "id": dataset["id"],
                    "title": dataset["title"],
                    "similarity": dataset.get("similarity", 0),
                    "file_path": primary_file_path if primary_file_path else None,
                    "error": str(e)
                }, None, None
        
        if sequential:
            self.stdout.write(self.style.NOTICE("Processing datasets sequentially (parallel processing disabled)"))
            results = []
            for i, dataset in enumerate(relevant_datasets):
                dataset_info, dataset_analysis, extracted_data = process_dataset(i, dataset)
                results.append(dataset_info)
                if dataset_analysis:
                    dataset_analyses.append(dataset_analysis)
                if extracted_data:
                    extracted_data_list.append(extracted_data)
        else:
            # Use ThreadPoolExecutor to process datasets in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                # Submit all tasks and store the futures
                future_to_index = {
                    executor.submit(process_dataset, i, dataset): i 
                    for i, dataset in enumerate(relevant_datasets)
                }
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_index):
                    dataset_info, dataset_analysis, extracted_data = future.result()
                    
                    # Add results to our lists
                    results.append(dataset_info)
                    
                    if dataset_analysis:
                        dataset_analyses.append(dataset_analysis)
                    
                    if extracted_data:
                        extracted_data_list.append(extracted_data)
        
        # Sort results to maintain the original order
        results.sort(key=lambda x: next((i for i, d in enumerate(relevant_datasets) if d['id'] == x['id']), 999))
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully processed {len(results)} datasets"))
        for i, result in enumerate(results, 1):
            relevance_info = f"(Relevance: {result.get('relevance_score', 0):.2f})" if 'relevance_score' in result else ""
            
            # Add a visual indicator for the search source
            search_source = result.get('search_source', 'unknown')
            if search_source == 'vector':
                source_indicator = "[VECTOR]"
            elif search_source == 'keyword':
                source_indicator = "[KEYWORD]"
            elif search_source == 'both':  # For datasets found by both methods
                source_indicator = "[BOTH]"
            else:
                source_indicator = ""
            
            self.stdout.write(f"{i}. {source_indicator} {result['title']} (Similarity: {result.get('similarity', 0):.4f}) {relevance_info} - {result.get('row_count', 'ERROR')} rows")
        
        if extracted_data_list:
            self.stdout.write("\nGenerating summary of findings...")
            
            # Use Azure options for summarizing findings
            if options.get('json_output'):
                # Use alternate function for JSON output
                self.stdout.write("Using comprehensive JSON output format...")
                output = summarize_findings_alternate(
                    query, 
                    extracted_data_list,
                    dataset_analyses
                )
                
                # For command line, print a readable summary version
                try:
                    output_dict = json.loads(output)
                    
                    self.stdout.write(self.style.SUCCESS("\nSUMMARY:"))
                    
                    # Handle case where 'text' might be nested inside summary or directly present
                    if isinstance(output_dict["summary"], dict) and "text" in output_dict["summary"]:
                        summary_text = output_dict["summary"]["text"]
                    else:
                        summary_text = str(output_dict["summary"])
                    self.stdout.write(summary_text)
                    
                    # Handle case where confidence score might be nested or directly present
                    if isinstance(output_dict["summary"], dict) and "confidence" in output_dict["summary"]:
                        confidence = output_dict["summary"]["confidence"] 
                        self.stdout.write(f"Confidence: {confidence:.2f}")
                    
                    # Display datasets analyzed
                    self.stdout.write(self.style.SUCCESS("\nDATASETS ANALYZED:"))
                    for dataset in output_dict["relevant_datasets"]:
                        format_info = ""
                        if dataset["files"] and "format" in dataset["files"][0]:
                            format_info = f" ({dataset['files'][0]['format']})"
                        
                        self.stdout.write(f"- {dataset['title']} (ID: {dataset['dataset_id']}){format_info}")
                    
                    # Save JSON to file
                    output_file = f"results_{int(time.time())}.json"
                    with open(output_file, 'w') as f:
                        f.write(output)
                    self.stdout.write(f"\nFull JSON output saved to: {output_file}")
                    
                except Exception as e:
                    # Log the error
                    self.stderr.write(self.style.ERROR(f"Error processing JSON output: {str(e)}"))
                    self.stdout.write(self.style.SUCCESS("\nRAW OUTPUT:"))
                    self.stdout.write(output)
            else:
                # Use original function for text output
                summary = summarize_findings(
                    query, 
                    extracted_data_list,
                    dataset_analyses
                )
                self.stdout.write(self.style.SUCCESS("\nFINDINGS:"))
                self.stdout.write(summary)
        else:
            self.stdout.write(self.style.WARNING("\nNo relevant data found to answer the query."))
        
        # Calculate and display execution time
        execution_time = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\nQuery execution completed in {execution_time:.2f} seconds"))

    def display_dataset_analysis(self, dataset_analysis):
        """Display the dataset analysis in a readable format."""
        if not dataset_analysis:
            self.stdout.write(self.style.WARNING("\nNo dataset analysis available."))
            return
        
        self.stdout.write(self.style.SUCCESS("\nDATASET ANALYSIS:"))
        self.stdout.write(dataset_analysis.get("analysis", "No analysis available"))

    def display_extracted_data(self, extracted_data):
        """Display extracted data in a readable format"""
        if not extracted_data:
            self.stdout.write(self.style.WARNING("\nNo extracted data available."))
            return
        
        self.stdout.write("\nFrom dataset: " + extracted_data.get("dataset_title", "Unknown Dataset"))
        
        # Display extraction strategy
        self.stdout.write(f"Extraction Strategy:")
        self.stdout.write(extracted_data.get("extraction_strategy", "No strategy provided"))

        # Display the data
        self.stdout.write("\nData:")
        data_dict = extracted_data.get("results_dict", {})
        
        # Check if data_dict is a list (records format) or a dictionary
        if isinstance(data_dict, list):
            # Handle list of records (first 5 records)
            if not data_dict:
                self.stdout.write("No data records found.")
            else:
                for i, record in enumerate(data_dict[:5]):
                    self.stdout.write(f"Record {i+1}:")
                    for key, value in record.items():
                        self.stdout.write(f"  {key}: {value}")
                    if i < len(data_dict) - 1 and i < 4:  # Add separator between records
                        self.stdout.write("---")
                if len(data_dict) > 5:
                    self.stdout.write(f"... and {len(data_dict) - 5} more records")
        elif isinstance(data_dict, dict):
            # Handle dictionary
            if not data_dict:
                self.stdout.write("No data found.")
            else:
                for key, value in data_dict.items():
                    self.stdout.write(f"{key}: {value}")
        else:
            self.stdout.write(f"Unexpected data format: {type(data_dict)}")
            self.stdout.write(str(data_dict)[:500])
        
        # Display printed output if available
        if "printed_output" in extracted_data and extracted_data["printed_output"]:
            self.stdout.write("\nPrinted Output:")
            self.stdout.write(extracted_data["printed_output"])
        
        # Display explanation
        self.stdout.write("\nExplanation:")
        self.stdout.write(extracted_data.get("explanation", "No explanation provided"))
        
        # Display code used
        if "code" in extracted_data and extracted_data["code"]:
            self.stdout.write("\nCode Used:")
            self.stdout.write("```python")
            self.stdout.write(extracted_data["code"])
            self.stdout.write("```")
        
        # Display any errors
        if "error" in extracted_data and extracted_data["error"]:
            self.stdout.write(self.style.ERROR(f"\nErrors encountered:"))
            self.stdout.write(self.style.ERROR(extracted_data["error"]))

    def init_api_key(self, api_key: Optional[str] = None) -> Dict[str, str]:
        """Initialize the Data.gov API key and OpenAI API key."""
        data_gov_key = settings.DATA_GOV_API_KEY or os.environ.get("DATA_GOV_API_KEY")

        if settings.AZURE_OPENAI_API_KEY:
            openai_key = settings.AZURE_OPENAI_API_KEY

        else:
            "Azure OpenAI key not found. Falling back to native OpenAI key in .env."
            openai_key = settings.OPENAI_API_KEY
        
        if not data_gov_key:
            raise ValueError("Data.gov API key is required. Set Put DATA_GOV_API_KEY environment variable in .env.")
        
        if not openai_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY environment variable in .env.")
        
        return {
            "data_gov": data_gov_key,
            "openai": openai_key
        }