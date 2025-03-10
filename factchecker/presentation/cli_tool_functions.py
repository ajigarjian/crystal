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
4. Always cite the source dataset for each data point
5. If analyzing trends over time, be sure to include the full time range and specific values in your analysis
6. Pay special attention to the most recent data points when analyzing trends

Finally, provide a "SEARCH SUMMARY" section with 2 paragraphs that:
1. Summarizes the overall context of the datasets analyzed (their scope, limitations, quality)
2. Synthesizes the findings in relation to the query, including any external factors that might be relevant

Your response should focus on answering the query using SPECIFIC VALUES and NUMBERS from the available data.
"""
    
    response = chat_completion(
        prompt,
        system_message="You are a data analyst who provides thorough analysis of data, with special attention to recent data points.",
        max_tokens=2048
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
    if not extracted_data_list:
        return json.dumps({"error": "No relevant data was found to answer your query."})
    
    # Initialize the result structure
    result = {
        "query": query,
        "status": "completed",
        "request_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.datetime.now().isoformat(),
        "relevant_datasets": [],
        "extracted_data": [],
        "summary": {},
        "analysis_steps": {
            "processing_notes": ""
        }
    }
    
    # Debug information - log what fields are available
    logging.debug(f"Keys in first extracted_data item: {extracted_data_list[0].keys() if extracted_data_list else 'None'}")
    
    # Add relevant_datasets info
    start_time = time.time()
    
    # Add debug logging
    debug_file_paths = True  # Always log for now
    
    # Create dictionaries to store dataset metadata fetched from the database
    dataset_descriptions = {}
    dataset_org_names = {}
    
    # Fetch all needed dataset metadata in one query for efficiency
    dataset_ids = [data.get("dataset_id", "") for data in extracted_data_list]
    try:
        db_datasets = DatasetCatalog.objects.filter(dataset_id__in=dataset_ids)
        
        # Create lookup dictionaries for quick access
        for db_dataset in db_datasets:
            dataset_descriptions[db_dataset.dataset_id] = db_dataset.description
            dataset_org_names[db_dataset.dataset_id] = db_dataset.organization_name
        
        # Debug log the information found
        if debug_file_paths:  # Reuse existing debug flag
            print(f"\n[DEBUG] Found {len(db_datasets)} datasets in database")
            for dataset_id in dataset_ids:
                if dataset_id in dataset_descriptions:
                    org_name = dataset_org_names.get(dataset_id, "Unknown")
                    print(f"  Dataset {dataset_id}: Org={org_name}")
                else:
                    print(f"  Dataset {dataset_id}: Not found in database")
    except Exception as e:
        print(f"[ERROR] Failed to fetch dataset metadata: {e}")
        # Continue with empty dictionaries
    
    # Process each dataset with the metadata
    for data in extracted_data_list:
        dataset_id = data.get("dataset_id", "unknown-id")
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        
        # Get description from our cached lookup
        description = dataset_descriptions.get(dataset_id, "")
        
        # Get organization name
        organization_name = dataset_org_names.get(dataset_id, "")
        
        # If not found in database, try the existing fields or fall back to defaults
        if not description:
            description = data.get("description", "")
            if not description and "dataset_metadata" in data:
                description = data.get("dataset_metadata", {}).get("description", "")
        
        # Try multiple paths to get the file_path
        file_path = data.get("file_path", "")
        
        # If file_path is missing but we have dataset_id, try to reconstruct
        if not file_path and data.get("dataset_id"):
            # Use default data directory - can be updated to match your command
            output_dir = "data_files"  # This should match the --output parameter
            possible_files = []
            
            # Try to find files in output directory that might match
            if os.path.exists(output_dir):
                for filename in os.listdir(output_dir):
                    # Look for files that contain dataset id or have a name similar to the title
                    if (data.get("dataset_id") in filename or 
                        any(word in filename.lower() for word in data.get("dataset_title", "").lower().split())):
                        possible_files.append(os.path.join(output_dir, filename))
            
            if possible_files:
                # Use the first matching file
                file_path = possible_files[0]
                if debug_file_paths:
                    print(f"    Reconstructed file_path: {file_path}")
        
        # Validate file paths
        if "all_file_paths" in data:
            valid_paths = []
            for path in data["all_file_paths"]:
                if os.path.exists(path):
                    valid_paths.append(path)
                else:
                    if debug_file_paths:
                        print(f"    Warning: File path does not exist: {path}")
            
            # Update all_file_paths with only valid paths
            data["all_file_paths"] = valid_paths
        
        # Determine filename and format
        filename = "unknown"
        file_format = "unknown"
        
        if file_path:
            filename = os.path.basename(file_path)
            _, ext = os.path.splitext(file_path)
            if ext:
                file_format = ext.lstrip(".").lower()
        
        # Add to relevant_datasets section with flat organization_name field
        dataset_info = {
            "dataset_id": dataset_id,
            "title": dataset_title,
            "description": description or "No description available",
            "organization_name": organization_name or "Unknown",
            "score": data.get("relevance_score", data.get("similarity", 1.0)),
            "files": []
        }

        # Add file information for each file path
        if "all_file_paths" in data and data["all_file_paths"]:
            for i, path in enumerate(data["all_file_paths"]):
                filename = os.path.basename(path)
                _, ext = os.path.splitext(path)
                file_format = ext.lstrip(".").lower() if ext else "unknown"
                
                dataset_info["files"].append({
                    "file_id": f"{dataset_id}-file-{i+1}",
                    "filename": filename,
                    "format": file_format,
                    "description": "Extracted data file"
                })
        else:
            # Fallback to single file if all_file_paths is not available
            filename = os.path.basename(file_path) if file_path else "unknown"
            _, ext = os.path.splitext(file_path) if file_path else ("", "")
            file_format = ext.lstrip(".").lower() if ext else "unknown"
            
            dataset_info["files"].append({
                "file_id": f"{dataset_id}-file-1",
                "filename": filename,
                "format": file_format,
                "description": "Extracted data file"
            })

        result["relevant_datasets"].append(dataset_info)
        
        # Get the actual extracted data - try multiple possible keys
        extracted = None
        for extracted_key in ["extracted_data", "results_dict", "data", "result"]:
            if extracted_key in data and data[extracted_key]:
                extracted = data[extracted_key]
                break
                
        # Get printed output if available
        printed_output = data.get("printed_output", "")
                
        # Add to extracted_data section
        extraction_data = {
            "dataset_id": dataset_id,
            "dataset_title": dataset_title,
            "file_extractions": []
        }
        
        file_extraction = {
            "file_id": f"{dataset_id}-file-1",
            "filename": filename,
        }
        
        # Format the extracted data based on its type
        if isinstance(extracted, pd.DataFrame):
            # For DataFrames, include column info and sample rows
            file_extraction["columns"] = extracted.columns.tolist()
            
            # Get up to 10 sample rows
            sample_rows = min(10, len(extracted))
            rows_data = []
            
            for i in range(sample_rows):
                row = extracted.iloc[i]
                # Convert to a simple dict instead of a list for better readability
                row_dict = {col: row[col] for col in extracted.columns}
                rows_data.append(row_dict)
            
            file_extraction["rows"] = rows_data
            
            # Add statistics for numerical columns
            stats = {}
            numeric_cols = extracted.select_dtypes(include=[np.number]).columns
            for col in numeric_cols:
                stats[col] = {
                    "min": float(extracted[col].min()) if not pd.isna(extracted[col].min()) else None,
                    "max": float(extracted[col].max()) if not pd.isna(extracted[col].max()) else None,
                    "mean": float(extracted[col].mean()) if not pd.isna(extracted[col].mean()) else None,
                }
            
            if stats:
                file_extraction["statistics"] = stats
                
        elif isinstance(extracted, dict):
            # For dictionaries, include as key-value pairs
            file_extraction["key_value_data"] = extracted
        elif isinstance(extracted, (list, tuple)):
            # For lists of data
            file_extraction["array_data"] = extracted
        else:
            # For other formats or None
            file_extraction["extraction_notes"] = f"Data format: {type(extracted).__name__}"
            if extracted:
                file_extraction["data_preview"] = str(extracted)[:500]
            elif printed_output:
                file_extraction["data_preview"] = printed_output[:500]
            else:
                file_extraction["data_preview"] = "No data extracted"
        
        # Add code used for extraction if available
        if "code" in data:
            file_extraction["extraction_code"] = data.get("code", "")
            
        # Add extraction strategy from multiple possible sources
        explanation = ""
        for exp_key in ["explanation", "extraction_strategy", "strategy", "extraction_explanation"]:
            if exp_key in data and data[exp_key]:
                explanation = data[exp_key]
                break
                
        file_extraction["relevance_notes"] = explanation
        
        # Add any error information
        if "error" in data and data["error"]:
            file_extraction["error"] = data["error"]
            
        extraction_data["file_extractions"].append(file_extraction)
        result["extracted_data"].append(extraction_data)
        
        if debug_file_paths:
            print(f"\n[DEBUG] Processing dataset: {dataset_id}")
            print(f"    Title: {dataset_title}")
            print(f"    file_path: {data.get('file_path', 'Not provided')}")
            print(f"    all_file_paths: {data.get('all_file_paths', 'Not provided')}")
            if "all_file_paths" in data and data["all_file_paths"]:
                for i, path in enumerate(data["all_file_paths"]):
                    print(f"      {i+1}: {path}")
    
    # Create a prompt for OpenAI to generate the text summary
    prompt = f"""
    You are analyzing data to answer: "{query}"
    
    The following datasets were analyzed:
    {chr(10).join([f"- {data.get('dataset_title', 'Unnamed Dataset')}" for data in extracted_data_list])}
    
    Based on the extracted data, please provide:
    1. A concise summary paragraph of the findings (max 3 sentences)
    2. A confidence score (0-1) representing how well the data answers the query
    
    Format your response as a JSON object with these fields:
    {{
      "text": "Your summary paragraph here",
      "confidence": 0.XX
    }}
    
    Only return the JSON object, nothing else.
    """
    
    # Call OpenAI API for summary
    response = chat_completion(
    prompt,
    system_message="You are a data analyst who provides concise data summaries in JSON format.",
    max_tokens=400
    )

    try:
        # Parse the JSON response - handle the case where it might include ```json wrapping
        content = response.strip()
        if content.startswith('```json'):
            content = content.replace('```json', '', 1).strip()
        if content.endswith('```'):
            content = content[:-3].strip()
        
        # Parse the cleaned JSON
        summary_json = json.loads(content)
        result["summary"] = summary_json
    except Exception as e:
        # Log the error
        logging.error(f"Error parsing summary JSON: {e}")
        # Fallback if JSON parsing fails
        result["summary"] = {
            "text": response,
            "confidence": 0.7
        }
    
    # Add analysis steps info
    result["analysis_steps"]["extraction_time_sec"] = round(time.time() - start_time, 1)
    
    # Include dataset IDs in processing notes
    dataset_ids = [data.get("dataset_id", "unknown") for data in extracted_data_list]
    result["analysis_steps"]["processing_notes"] = f"Analysis based on {len(dataset_ids)} datasets: {', '.join(dataset_ids)}"
    
    # Return formatted JSON string
    return json.dumps(result, indent=2, cls=ExtendedJSONEncoder)
