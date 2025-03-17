from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
import logging
import openai
import json
import os
import time
import uuid
import datetime

from factchecker.models import DatasetCatalog
from factchecker.processing.analysis.dataset_analyzer import ExtendedJSONEncoder
from factchecker.utils.openai_client import chat_completion


def ensure_serializable(obj):
    """Convert any non-serializable objects to serializable formats."""
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'to_dict'):
        return obj.to_dict()
    return obj

def process_result_for_serialization(result_dict):
    """Process the result dictionary to ensure all values are JSON serializable."""
    if isinstance(result_dict, dict):
        return {k: process_result_for_serialization(v) for k, v in result_dict.items()}
    elif isinstance(result_dict, list):
        return [process_result_for_serialization(item) for item in result_dict]
    else:
        return ensure_serializable(result_dict)

def summarize_findings(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> str:
    """
    Summarize findings from multiple datasets into a concise response.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        Concise summary of findings
    """
    if not extracted_data_list:
        return "No relevant data was found to answer your query."
    
    # Prepare information about each dataset and its extracted data
    dataset_summaries = []
    dataset_ids = []  # Track dataset IDs for the summary
    
    for data in extracted_data_list:
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        dataset_id = data.get("dataset_id", "Unknown ID")
        
        # Get the extracted data - this is what's missing from the final output
        extracted = data.get("extracted_data")
        extraction_explanation = data.get("explanation", "")
        
        # Create a formatted sample of actual data values
        data_sample = ""
        if isinstance(extracted, pd.DataFrame):
            # For DataFrames, take a sample of rows to include in the summary
            if len(extracted) > 0:
                data_sample = "KEY DATA POINTS:\n"
                # Take up to 5 representative rows
                sample_df = extracted.head(5)
                for idx, row in sample_df.iterrows():
                    data_sample += f"- {', '.join([f'{col}: {val}' for col, val in row.items() if pd.notna(val)])}\n"
                
                # Add summary statistics if numeric columns exist
                numeric_cols = sample_df.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    data_sample += "\nSTATISTICAL SUMMARY:\n"
                    for col in numeric_cols:
                        if "unemploy" in col.lower():
                            data_sample += f"- {col}: min={extracted[col].min()}, max={extracted[col].max()}, avg={extracted[col].mean():.2f}\n"
        
        dataset_summaries.append(f"Source: {dataset_title} (ID: {dataset_id})\n{extraction_explanation}\n{data_sample}")
    
    # Include dataset analyses if provided
    dataset_context = ""
    if dataset_analyses:
        dataset_context = "DATASET CONTEXT:\n"
        for analysis in dataset_analyses:
            dataset_context += f"Dataset: {analysis.get('dataset_title', 'Unknown')}\n"
            dataset_context += f"Dataset ID: {analysis.get('dataset_id', 'Unknown ID')}\n"
            dataset_context += f"Analysis: {analysis.get('analysis', 'No analysis available')}\n\n"
    
    # Create prompt for OpenAI
    prompt = f"""
You are analyzing data to answer: "{query}"

{dataset_context}

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Present the KEY DATA POINTS that directly answer the query - include SPECIFIC NUMBERS and VALUES
2. Be concise but thorough - include all relevant data in your analysis
3. Format as bullet points where appropriate
4. Always cite the source dataset and calculation strategy in brackets [] for each data point
5. If analyzing trends over time, be sure to include the full time range and specific values in your analysis
6. Pay special attention to the most recent data points when analyzing trends

Finally, provide a "SEARCH SUMMARY" section with 2 paragraphs that:
1. Summarizes the overall context of the datasets analyzed (their scope, limitations, quality)
2. Synthesizes the findings in relation to the query in a highly factual way based on the given data.

Your response should focus on answering the query using SPECIFIC VALUES and NUMBERS from the available data.
"""
    
    response = chat_completion(
        prompt,
        system_message="You are a data analyst who provides thorough analysis of data, with special attention to recent data points.",
        max_tokens=1024
        )
    # Return the summary
    return response

def summarize_findings_alternate(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> str:
    """
    Alternative version that generates JSON output with full extracted data.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        JSON-formatted string containing comprehensive findings and extracted data
    """
    start_time = time.time()
    
    # Get the text summary from the original function
    summary_text = summarize_findings(query, extracted_data_list, dataset_analyses)
    
    # Initialize the result structure
    result = {
        "query": query,
        "status": "completed",
        "request_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "relevant_datasets": [],
        "extracted_data": [],
        "summary": {
            "text": summary_text,
            "confidence": 0.85
        },
        "analysis_steps": {
            "extraction_time_sec": 0,
            "processing_notes": ""
        }
    }
    
    # Add dataset information to the result
    for data in extracted_data_list:
        dataset_info = {
            "dataset_id": data.get("dataset_id", "Unknown ID"),
            "title": data.get("dataset_title", "Unnamed Dataset"),
            "source": data.get("dataset_source", "Unknown Source"),
            "files": []
        }
        
        # Add file information
        if "file_path" in data:
            dataset_info["files"].append({
                "path": data.get("file_path", ""),
                "format": os.path.splitext(data.get("file_path", ""))[1][1:].upper()
            })
        
        # Add all file paths if available
        if "all_file_paths" in data and data["all_file_paths"]:
            for path in data["all_file_paths"]:
                if path != data.get("file_path", ""):  # Skip the main file that's already added
                    dataset_info["files"].append({
                        "path": path,
                        "format": os.path.splitext(path)[1][1:].upper()
                    })
        
        result["relevant_datasets"].append(dataset_info)
        
        # Process the extracted data for serialization
        processed_data = process_result_for_serialization(data)
        result["extracted_data"].append(processed_data)
    
    # Add analysis steps info
    result["analysis_steps"]["extraction_time_sec"] = round(time.time() - start_time, 1)
    
    # Include dataset IDs in processing notes
    dataset_ids = [data.get("dataset_id", "unknown") for data in extracted_data_list]
    result["analysis_steps"]["processing_notes"] = f"Analysis based on {len(dataset_ids)} datasets: {', '.join(dataset_ids)}"
    
    # Return formatted JSON string
    return json.dumps(result, indent=2, cls=ExtendedJSONEncoder)
