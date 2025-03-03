# factchecker/management/commands/factchecker.py
import argparse
from django.core.management.base import BaseCommand

# For searching for the right datasets to download, we use vector search, and have support for keyword search using the gov api
from factchecker.search import vector_search_datasets
from factchecker.search import preprocess_query, search_datasets, filter_relevant_datasets

# For downloading the datasets, we use the download_dataset function for now
from factchecker.download import download_dataset

# For analyzing the datasets and extracting the relevant data, we use the following functions
from factchecker.analysis import (
    load_csv_dataset,
    assess_dataset_relevance,
    extract_relevant_data,
    analyze_dataset_overview,
    summarize_findings
)

import pandas as pd
from typing import Dict, Tuple, List, Any, Optional
import openai
import time
import concurrent.futures
from threading import Lock
import os

class Command(BaseCommand):
    help = 'Search, download, and analyze datasets from Data.gov'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create a lock for thread-safe stdout writing
        self.stdout_lock = Lock()
    
    def add_arguments(self, parser):
        parser.add_argument("query", help="Natural language query to search for datasets")
        parser.add_argument("--top", type=int, default=5, help="Number of most relevant datasets to keep")
        parser.add_argument("--output", default="downloads", help="Directory to save downloaded files")
        parser.add_argument("--preview", action="store_true", help="Show data preview")
        parser.add_argument("--relevance-threshold", type=float, default=0.7, 
                           help="Threshold for dataset relevance (0-1)")
        parser.add_argument("--force", help="Comma-separated list of local dataset paths to analyze directly, skipping search")
        parser.add_argument("--workers", type=int, default=3, 
                           help="Number of parallel workers for processing datasets")
        parser.add_argument(
            '--search-method',
            choices=['vector', 'keyword'],
            default='vector',
            help='Search method to use: vector (default) or keyword'
        )
    
    def handle(self, *args, **options):
        # Start timing the execution
        start_time = time.time()
        
        query = options['query']
        top_n = options['top']
        output_dir = options['output']
        show_preview = options['preview']
        relevance_threshold = options['relevance_threshold']
        force_datasets = options.get('force')
        workers = options.get('workers', 3)
        search_method = options['search_method']
        
        self.stdout.write(f"Factchecker query: '{query}'")
        
        # Initialize API keys
        try:
            api_keys = self.init_api_key()
            openai_api_key = api_keys["openai"]
            gov_api_key = api_keys["data_gov"]
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Error initializing API keys: {e}"))
            return
        
        # Process forced datasets if specified, otherwise do search
        relevant_datasets = []
        if force_datasets:
            self.stdout.write(f"Skipping search and using specified datasets: {force_datasets}")
            dataset_paths = [path.strip() for path in force_datasets.split(',')]
            
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
        else:
            if search_method == 'vector':
                # Use vector search to find relevant datasets
                self.stdout.write(f"Searching for datasets matching '{query}' using vector similarity...")
                relevant_datasets = vector_search_datasets(query, openai_api_key, top_n=top_n)
            else:
                # Use keyword search to find relevant datasets
                self.stdout.write(f"Searching for datasets matching '{query}' using keyword search...")
                # Preprocess the query for better results
                generalized_query = preprocess_query(query, openai_api_key)
                # Search for datasets
                search_results = search_datasets(gov_api_key, generalized_query, rows=top_n*2)
                # Filter to most relevant
                relevant_datasets = filter_relevant_datasets(query, search_results, openai_api_key, top_n=top_n)
            
            self.stdout.write(f"Found {len(relevant_datasets)} relevant datasets")
        
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
            # Create a short identifier for this dataset
            dataset_short_id = f"[{dataset_num}/{len(relevant_datasets)}] {dataset_title[:20]}..."
            
            similarity_score = dataset.get('similarity', 1.0)
            with self.stdout_lock:
                self.stdout.write(f"\n{dataset_short_id} Processing dataset (Query similarity: {similarity_score:.4f})")
            
            try:
                # Handle the dataset - either use local path or download
                if 'local_path' in dataset:
                    output_path = dataset['local_path']
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Using local dataset: {output_path}")
                else:
                    # Download the dataset
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Downloading dataset...")
                    output_path = download_dataset(gov_api_key, dataset["id"], output_dir=output_dir)
                    
                    if not output_path:
                        with self.stdout_lock:
                            self.stdout.write(self.style.WARNING(f"{dataset_short_id} Download failed. Skipping dataset."))
                        return {
                            "id": dataset["id"],
                            "title": dataset["title"],
                            "similarity": dataset.get("similarity", 0),
                            "error": "Download failed"
                        }, None, None
                        
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Downloaded to: {output_path}")
                
                # Load and analyze the dataset
                with self.stdout_lock:
                    self.stdout.write(f"{dataset_short_id} Loading dataset for analysis...")
                df = load_csv_dataset(output_path)
                
                # Record basic dataset info
                dataset_info = {
                    "id": dataset["id"],
                    "title": dataset["title"],
                    "description": dataset.get("description", ""),
                    "similarity": similarity_score,
                    "file_path": output_path,
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "columns": list(df.columns)
                }
                
                # Print preview if requested
                if show_preview:
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Data Preview:")
                        self.stdout.write(str(df.head()))
                
                # Assess dataset relevance
                with self.stdout_lock:
                    self.stdout.write(f"\n{dataset_short_id} Assessing dataset relevance...")
                is_relevant, relevance_score, reasoning = assess_dataset_relevance(
                    df, query, dataset_info, openai_api_key, relevance_threshold
                )
                
                dataset_info["relevance_score"] = relevance_score
                dataset_info["relevance_reasoning"] = reasoning
                
                extracted_data = None
                dataset_analysis = None
                
                if is_relevant:
                    with self.stdout_lock:
                        self.stdout.write(self.style.SUCCESS(
                            f"{dataset_short_id} Dataset is relevant (Score: {relevance_score:.2f})"
                        ))
                    
                    # Extract relevant data
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} Extracting relevant data...")
                    extracted_data = extract_relevant_data(df, query, dataset_info, openai_api_key)
                    
                    # Add dataset source information to the extracted data
                    if extracted_data:
                        extracted_data["dataset_title"] = dataset_info["title"]
                        extracted_data["dataset_source"] = dataset_info.get("description", "Data.gov dataset")
                        extracted_data["dataset_id"] = dataset_info["id"]
                    
                    with self.stdout_lock:
                        self.stdout.write(f"{dataset_short_id} EXTRACTED DATA:")
                        self.display_extracted_data(extracted_data)
                    
                    # Generate dataset overview analysis AFTER extraction
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(
                        df, 
                        query, 
                        dataset_info, 
                        openai_api_key,
                        column_values_analysis=extracted_data.get("column_values_analysis"),
                        relevant_columns=extracted_data.get("relevant_columns")
                    )
                    with self.stdout_lock:
                        self.display_dataset_analysis(dataset_analysis)
                    
                    # Add dataset analysis to dataset_info
                    dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                else:
                    with self.stdout_lock:
                        self.stdout.write(self.style.WARNING(
                            f"{dataset_short_id} Dataset is not relevant enough (Score: {relevance_score:.2f})"
                        ))
                    
                    # Even for non-relevant datasets, we might want a basic analysis
                    with self.stdout_lock:
                        self.stdout.write(f"\n{dataset_short_id} Analyzing dataset overview...")
                    dataset_analysis = analyze_dataset_overview(df, query, dataset_info, openai_api_key)
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
                    "file_path": output_path if 'output_path' in locals() else None,
                    "error": str(e)
                }, None, None
        
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
            self.stdout.write(f"{i}. {result['title']} (Similarity: {result.get('similarity', 0):.4f}) {relevance_info} - {result.get('row_count', 'ERROR')} rows")
        
        if extracted_data_list:
            self.stdout.write("\nGenerating summary of findings...")
            summary = summarize_findings(query, extracted_data_list, openai_api_key, dataset_analyses)
            self.stdout.write(self.style.SUCCESS("\nFINDINGS:"))
            self.stdout.write(summary)
        else:
            self.stdout.write(self.style.WARNING("\nNo relevant data found to answer the query."))
        
        # Calculate and display execution time
        execution_time = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\nQuery execution completed in {execution_time:.2f} seconds"))

    def display_dataset_analysis(self, dataset_analysis):
        """Display the dataset analysis in a readable format."""
        self.stdout.write(self.style.SUCCESS("\nDATASET ANALYSIS:"))
        self.stdout.write(dataset_analysis["analysis"])
    
    def display_extracted_data(self, extracted_data):
        """Display extracted data in a readable format"""
        self.stdout.write("\nFrom dataset: " + extracted_data.get("dataset_title", "Unknown Dataset"))
        
        # Display extraction strategy
        self.stdout.write("\nExtraction Strategy:")
        self.stdout.write(extracted_data.get("extraction_strategy", "No strategy provided"))
        
        # Display the data
        self.stdout.write("\nData:")
        data_dict = extracted_data.get("results_dict", {})
        for key, value in data_dict.items():
            self.stdout.write(f"{key}: {value}")
        
        # Display printed output if available
        if "printed_output" in extracted_data and extracted_data["printed_output"]:
            self.stdout.write("\nPrinted Output:")
            self.stdout.write(extracted_data["printed_output"])
        
        # Display explanation
        self.stdout.write("\nExplanation:")
        self.stdout.write(extracted_data.get("explanation", "No explanation provided"))
        
        # Display code used
        if "code" in extracted_data:
            self.stdout.write("\nCode Used:")
            self.stdout.write("```python")
            self.stdout.write(extracted_data["code"])
            self.stdout.write("```")

    def init_api_key(self, api_key: Optional[str] = None) -> Dict[str, str]:
        """Initialize the Data.gov API key and OpenAI API key."""
        data_gov_key = api_key or os.environ.get("DATA_GOV_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")
        
        if not data_gov_key:
            raise ValueError("Data.gov API key is required. Set DATA_GOV_API_KEY environment variable or pass it directly.")
        
        if not openai_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
        
        return {
            "data_gov": data_gov_key,
            "openai": openai_key
        }