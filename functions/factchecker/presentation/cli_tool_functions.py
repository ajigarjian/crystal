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
    # Debug print 
    if not extracted_data_list:
        return {
            "summary": "No relevant data was found to answer your query.",
            "key_data_points": [],
            "sources": []
        }
    
    # Prepare information about each dataset and its extracted data
    dataset_summaries = []
    dataset_ids = []  # Track dataset IDs for the summary
    sources = []  # Track sources for citation
    
    for data in extracted_data_list:
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        dataset_id = data.get("dataset_id", "Unknown ID")
        
        # Extract organization info, checking multiple possible locations
        organization = (
            data.get("organization_title") or
            data.get("organization") or
            data.get("dataset_source") or
            data.get("organization_name") or
            "Unknown Source"
        )
        
        # Add to sources list with enhanced organization info
        sources.append({
            "citation_id": dataset_id[:8] if dataset_id and dataset_id != "Unknown ID" else f"DS-{i+1}",
            "title": dataset_title if dataset_title != "Unnamed Dataset" else f"Dataset {i+1}",
            "organization": organization
        })
        
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
            # Include basic dataset information
            dataset_context += f"Dataset: {analysis.get('dataset_title', 'Unknown')}\n"
            dataset_context += f"Dataset ID: {analysis.get('dataset_id', 'Unknown ID')}\n"
            
            # Include row and column counts
            if 'row_count' in analysis and 'column_count' in analysis:
                dataset_context += f"Size: {analysis['row_count']} rows, {analysis['column_count']} columns\n"
            
            # Include categorical summaries
            if 'categorical_summaries' in analysis and analysis['categorical_summaries']:
                dataset_context += "Categories: " + "; ".join(analysis['categorical_summaries']) + "\n"
            
            # Include geographic scope
            if 'geographic_scope' in analysis and analysis['geographic_scope']:
                geo_info = [f"{k}: {v}" for k, v in analysis['geographic_scope'].items()]
                dataset_context += "Geographic scope: " + "; ".join(geo_info) + "\n"
            
            # Include analysis if available
            if 'analysis' in analysis:
                dataset_context += f"Analysis: {analysis['analysis']}\n\n"

    # Create prompt for OpenAI with instruction to return JSON
    prompt = f"""
You are analyzing data to answer: "{query}"

{dataset_context}

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Create a detailed analysis with the following structure:
   - A "summary" section with 2-3 paragraphs that synthesizes findings and context
   - A "key_data_points" section with 3-8 bullet points highlighting the most important specific findings
   - Each bullet point should be prefixed with "- " and include specific numbers and values
   - Each bullet point should cite its source using the dataset ID in square brackets [Source: Dataset ID]

2. Format your response as a clean JSON object with these exact keys:
   - "summary": A string with the overall summary
   - "key_data_points": An array of strings, each string being a complete bullet point
   - Do not use JSON.stringify or add any markdown formatting outside of the content

For example:
{{
  "summary": "This is the overall summary of findings...",
  "key_data_points": [
    "- First key finding with specifics [Source: Dataset XYZ]",
    "- Second key finding with specifics [Source: Dataset ABC]"
  ]
}}

Make sure your JSON is valid - use double quotes for keys and string values.
"""
    
    # Call OpenAI with instruction to return JSON
    response = chat_completion(
        prompt,
        system_message="You are a data analyst who provides analysis in structured JSON format. Always return a valid JSON object without any surrounding text.",
        max_tokens=2048,
        model_name="gpt-4o"
    )
    
    # The response should now be a JSON string, so we need to parse it and return as dict
    try:
        # Parse the JSON response
        result = json.loads(response)
        
        # Add the pre-built sources list
        result["sources"] = sources
        
        return result
    except json.JSONDecodeError:
        # If parsing fails, return a simple structure with the raw response
        logger.error(f"Failed to parse JSON response: {response[:100]}...")
        return {
            "summary": "There was an issue processing the analysis results.",
            "key_data_points": [
                "- The analysis could not be properly formatted. Please try again."
            ],
            "sources": sources
        }

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
        "dataset_context": [],  # New field for dataset context
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
        
        # Include subset_df in the extracted data if it exists
        if "subset_df" in data:
            processed_data["subset_df"] = process_result_for_serialization(data["subset_df"])
        
        result["extracted_data"].append(processed_data)
    
    # Add dataset context from analyses
    if dataset_analyses:
        for analysis in dataset_analyses:
            dataset_context = {
                "dataset_id": analysis.get("dataset_id", "Unknown ID"),
                "title": analysis.get("dataset_title", "Unnamed Dataset"),
                "overview": analysis.get("analysis", "No analysis available"),
                "row_count": analysis.get("row_count", 0),
                "column_count": analysis.get("column_count", 0),
                "missing_values_summary": analysis.get("missing_values_summary", []),
                "temporal_scope": analysis.get("temporal_scope", {}),
                "geographic_scope": analysis.get("geographic_scope", {}),
                "categorical_summaries": analysis.get("categorical_summaries", []),
                "column_info": analysis.get("column_info", {}),
                "numerical_stats": analysis.get("numerical_stats", {}),
                "temporal_coverage": analysis.get("temporal_coverage", {}),
                "missing_values": analysis.get("missing_values", {}),
                "data_quality": analysis.get("data_quality", {})
            }
            
            # Add any additional metadata that might be useful
            if "dataset_metadata" in analysis:
                dataset_context["metadata"] = analysis["dataset_metadata"]
                
            # Add any dataset statistics
            if "dataset_stats" in analysis:
                dataset_context["statistics"] = analysis["dataset_stats"]
                
            result["dataset_context"].append(dataset_context)
    
    # Add analysis steps info
    result["analysis_steps"]["extraction_time_sec"] = round(time.time() - start_time, 1)
    
    # Include dataset IDs in processing notes
    dataset_ids = [data.get("dataset_id", "unknown") for data in extracted_data_list]
    result["analysis_steps"]["processing_notes"] = f"Analysis based on {len(dataset_ids)} datasets: {', '.join(dataset_ids)}"
    
    # Add query processing details
    result["analysis_steps"]["query_processing"] = {
        "original_query": query,
        "datasets_analyzed": len(dataset_ids),
        "extraction_methods_used": [data.get("extraction_strategy", "Unknown strategy") 
                                   for data in extracted_data_list if "extraction_strategy" in data]
    }
    
    # Return formatted JSON string
    return json.dumps(result, indent=2, cls=ExtendedJSONEncoder)
