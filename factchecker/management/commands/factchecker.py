# factchecker/management/commands/factchecker.py
import argparse
from django.core.management.base import BaseCommand
from factchecker import download_gov_data as dgd
from factchecker import data_analysis as da
import pandas as pd
from typing import Dict, Tuple
import openai
import time

class Command(BaseCommand):
    help = 'Search, download, and analyze datasets from Data.gov'
    
    def add_arguments(self, parser):
        parser.add_argument("query", help="Natural language query to search for datasets")
        parser.add_argument("--top", type=int, default=5, help="Number of most relevant datasets to keep")
        parser.add_argument("--output", default="downloads", help="Directory to save downloaded files")
        parser.add_argument("--preview", action="store_true", help="Show data preview")
        parser.add_argument("--relevance-threshold", type=float, default=0.7, 
                           help="Threshold for dataset relevance (0-1)")
        parser.add_argument("--force", help="Comma-separated list of local dataset paths to analyze directly, skipping search")
    
    def handle(self, *args, **options):
        # Start timing the execution
        start_time = time.time()
        
        query = options['query']
        top_n = options['top']
        output_dir = options['output']
        show_preview = options['preview']
        relevance_threshold = options['relevance_threshold']
        force_datasets = options.get('force')
        
        self.stdout.write(f"Factchecker query: '{query}'")
        
        # Initialize API keys
        try:
            api_keys = dgd.init_api_key()
            openai_api_key = api_keys["openai"]
            gov_api_key = api_keys["data_gov"]
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Error initializing API keys: {e}"))
            return
        
        # Process forced datasets if specified, otherwise do vector search
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
            # Use vector search to find relevant datasets
            self.stdout.write(f"Searching for datasets matching '{query}' using vector similarity...")
            relevant_datasets = dgd.vector_search_datasets(query, openai_api_key, top_n=top_n)
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
        
        for i, dataset in enumerate(relevant_datasets, 1):
            self.stdout.write(f"\n[{i}/{len(relevant_datasets)}] Processing: {dataset['title']} (Query similarity: {dataset['similarity']:.4f})")
            
            # Handle the dataset - either use local path or download
            if 'local_path' in dataset:
                output_path = dataset['local_path']
                self.stdout.write(f"Using local dataset: {output_path}")
            else:
                # Download the dataset
                self.stdout.write("Downloading dataset...")
                output_path = dgd.download_dataset(gov_api_key, dataset["id"], output_dir=output_dir)
                
                if not output_path:
                    self.stdout.write(self.style.WARNING("Download failed. Skipping dataset."))
                    continue
                    
                self.stdout.write(f"Downloaded to: {output_path}")
            
            # Load and analyze the dataset
            try:
                self.stdout.write("Loading dataset for analysis...")
                df = da.load_csv_dataset(output_path)
                
                # Record basic dataset info
                dataset_info = {
                    "id": dataset["id"],
                    "title": dataset["title"],
                    "description": dataset.get("description", ""),
                    "similarity": dataset.get("similarity", 0),
                    "file_path": output_path,
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "columns": list(df.columns)
                }
                
                # Generate dataset overview analysis
                self.stdout.write("\nAnalyzing dataset overview...")
                dataset_analysis = da.analyze_dataset_overview(df, query, dataset_info, openai_api_key)
                self.display_dataset_analysis(dataset_analysis)
                dataset_analyses.append(dataset_analysis)  # Store for final summary
                
                # Print preview if requested
                if show_preview:
                    self.stdout.write("\nData Preview:")
                    self.stdout.write(str(df.head()))
                
                # Assess dataset relevance
                self.stdout.write("\nAssessing dataset relevance...")
                is_relevant, relevance_score, reasoning = da.assess_dataset_relevance(
                    df, query, dataset_info, openai_api_key, relevance_threshold
                )
                
                dataset_info["relevance_score"] = relevance_score
                dataset_info["relevance_reasoning"] = reasoning
                dataset_info["dataset_analysis"] = dataset_analysis["analysis"]
                
                if is_relevant:
                    self.stdout.write(self.style.SUCCESS(
                        f"Dataset is relevant (Score: {relevance_score:.2f})"
                    ))
                    
                    # Extract relevant data
                    self.stdout.write("Extracting relevant data...")
                    extracted_data = da.extract_relevant_data(df, query, dataset_info, openai_api_key)
                    extracted_data_list.append(extracted_data)
                    self.display_extracted_data(extracted_data)
                else:
                    self.stdout.write(self.style.WARNING(
                        f"Dataset is not relevant enough (Score: {relevance_score:.2f})"
                    ))
                
                results.append(dataset_info)
                
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error analyzing dataset: {e}"))
                # Still add to results, but with error info
                results.append({
                    "id": dataset["id"],
                    "title": dataset["title"],
                    "similarity": dataset.get("similarity", 0),
                    "file_path": output_path,
                    "error": str(e)
                })
        
        # Summary
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully processed {len(results)} datasets"))
        for i, result in enumerate(results, 1):
            relevance_info = f"(Relevance: {result.get('relevance_score', 0):.2f})" if 'relevance_score' in result else ""
            self.stdout.write(f"{i}. {result['title']} (Similarity: {result.get('similarity', 0):.4f}) {relevance_info} - {result.get('row_count', 'ERROR')} rows")
        
        if extracted_data_list:
            self.stdout.write("\nGenerating summary of findings...")
            summary = da.summarize_findings(query, extracted_data_list, openai_api_key, dataset_analyses)
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
        """Display extracted data in a readable format in the CLI."""
        self.stdout.write(self.style.SUCCESS("\nEXTRACTED DATA:"))
        
        # Display dataset info
        self.stdout.write(f"\nFrom dataset: {extracted_data.get('dataset_title', 'Unknown')}")
        
        # Display extraction strategy
        self.stdout.write("\nExtraction Strategy:")
        self.stdout.write(extracted_data.get("extraction_plan", {}).get("strategy", "No strategy provided"))
        
        # Display the data itself
        self.stdout.write("\nData:")
        data = extracted_data.get("extracted_data")
        
        if isinstance(data, pd.DataFrame):
            # For DataFrames, print all rows without any limit
            self.stdout.write(data.to_string())
            self.stdout.write(f"\n[{len(data)} rows x {len(data.columns)} columns]")
        elif isinstance(data, pd.Series):
            # For Series, show all values
            self.stdout.write(data.to_string())
            self.stdout.write(f"\n[{len(data)} values]")
        elif isinstance(data, dict):
            # For dictionaries
            import json
            self.stdout.write(json.dumps(data, indent=2, default=str))
        elif isinstance(data, list):
            # For lists
            import json
            self.stdout.write(json.dumps(data, indent=2, default=str))
        else:
            # For other types
            self.stdout.write(str(data))
        
        # Display explanation
        self.stdout.write("\nExplanation:")
        self.stdout.write(extracted_data.get("extraction_plan", {}).get("explanation", "No explanation provided"))
        
        # Display code used
        self.stdout.write("\nCode Used:")
        self.stdout.write(f"```python\n{extracted_data.get('code_used', 'No code provided')}\n```")