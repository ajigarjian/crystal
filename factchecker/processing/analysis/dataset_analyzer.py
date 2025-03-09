from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
import logging
import openai
from contextlib import redirect_stdout
import io
import traceback
import re
import json
import datetime
from factchecker.models import DatasetCatalog  # Import here to avoid circular imports
import os
from factchecker.utils.openai_client import chat_completion

def analyze_dataset_overview(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    dataset_metadata: Dict[str, Any],
    extracted_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Analyze a dataset to provide a concise overview of its relevance to the query,
    including data quality assessment and scope limitations.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        dataset_metadata: Metadata about the dataset
        extracted_data: The data extracted from the dataset
        
    Returns:
        Dictionary containing dataset analysis and summary
    """
    # Set up logging
    logger = logging.getLogger("dataset_analysis")
    logger.setLevel(logging.DEBUG)
    
    # Add a console handler if not already present
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[ANALYSIS] %(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info(f"Starting dataset analysis for query: {query}")
    logger.info(f"Dataset: {dataset_metadata.get('title', 'Unknown')}")
    
    # Get basic dataset info
    row_count = len(dataset_content)
    col_count = len(dataset_content.columns)
    
    # Get column information with sample values and missing value counts
    column_info = []
    missing_values_summary = []
    
    for col in dataset_content.columns:
        dtype = str(dataset_content[col].dtype)
        missing_count = dataset_content[col].isna().sum()
        missing_percentage = (missing_count / row_count) * 100 if row_count > 0 else 0
        
        # Get sample values (first 2 rows)
        sample_values = dataset_content[col].head(2).tolist()
        
        column_info.append(f"- {col} ({dtype}): {sample_values}")
        
        if missing_count > 0:
            missing_values_summary.append(f"- {col}: {missing_count} missing values ({missing_percentage:.2f}%)")
    
    # Check for temporal and geographic scope
    temporal_cols = [col for col in dataset_content.columns if any(term in col.lower() for term in 
                    ['year', 'date', 'time', 'month', 'day', 'period'])]
    
    geographic_cols = [col for col in dataset_content.columns if any(term in col.lower() for term in 
                      ['city', 'state', 'country', 'region', 'county', 'province', 'location', 
                       'address', 'zip', 'postal', 'latitude', 'longitude', 'geo'])]
    
    # Temporal range analysis
    temporal_range = {}
    for col in temporal_cols:
        if pd.api.types.is_numeric_dtype(dataset_content[col]):
            temporal_range[col] = {
                "min": dataset_content[col].min(),
                "max": dataset_content[col].max()
            }
        elif pd.api.types.is_datetime64_dtype(dataset_content[col]):
            temporal_range[col] = {
                "min": dataset_content[col].min().strftime('%Y-%m-%d') if not pd.isna(dataset_content[col].min()) else "N/A",
                "max": dataset_content[col].max().strftime('%Y-%m-%d') if not pd.isna(dataset_content[col].max()) else "N/A"
            }
    
    # Geographic scope analysis
    geographic_scope = {}
    for col in geographic_cols:
        if pd.api.types.is_string_dtype(dataset_content[col]) or pd.api.types.is_object_dtype(dataset_content[col]):
            # Get unique values if there aren't too many
            unique_values = dataset_content[col].dropna().unique()
            if len(unique_values) <= 10:  # Only include if there's a reasonable number of unique values
                geographic_scope[col] = unique_values.tolist()
            else:
                # Just count the unique values if there are too many
                geographic_scope[col] = f"{len(unique_values)} unique values"
    
    # Identify potential categorical columns (non-numeric with limited unique values)
    categorical_summaries = []
    
    for col in dataset_content.columns:
        # Check if column is non-numeric (string or object type)
        if pd.api.types.is_string_dtype(dataset_content[col]) or pd.api.types.is_object_dtype(dataset_content[col]):
            # Count unique values
            unique_count = dataset_content[col].nunique()
            # If column has a reasonable number of unique values (not too few, not too many)
            if 2 <= unique_count <= 100:  # Adjust thresholds as needed
                # Get value counts for this column
                value_counts = dataset_content[col].value_counts().head(10)  # Top 10 values
                if not value_counts.empty:
                    values_summary = ", ".join([f"{val} ({count})" for val, count in value_counts.items()])
                    categorical_summaries.append(f"- {col} top values: {values_summary}")
    
    # Include information about relevant columns and values if provided
    relevant_column_info = []
    column_values_analysis = extracted_data.get("column_values_analysis", {}) if extracted_data else {}
    
    if column_values_analysis:
        for col_name, analysis in column_values_analysis.items():
            relevant_values = analysis.get("relevant_values", [])
            if relevant_values:
                relevant_column_info.append(f"- Column '{col_name}' has relevant values: {relevant_values[:5]}")
    
    # Include extraction information if provided
    extraction_info = []
    if extracted_data:
        logger.info("Processing extracted data for analysis")
        
        if "extraction_strategy" in extracted_data and extracted_data["extraction_strategy"]:
            extraction_info.append(f"EXTRACTION STRATEGY: {extracted_data['extraction_strategy']}")
        
        if "explanation" in extracted_data and extracted_data["explanation"]:
            extraction_info.append(f"EXTRACTION EXPLANATION: {extracted_data['explanation']}")
        
        if "code" in extracted_data and extracted_data["code"]:
            extraction_info.append(f"EXTRACTION CODE: \n{extracted_data['code']}")
        
        if "printed_output" in extracted_data and extracted_data["printed_output"]:
            extraction_info.append(f"EXTRACTION OUTPUT: \n{extracted_data['printed_output']}")
        
        # Include information about the extracted data
        if "results_dict" in extracted_data:
            results = extracted_data["results_dict"]
            if isinstance(results, list) and results:
                # Include all extracted records (up to a reasonable limit)
                max_records = min(len(results), 10)
                extraction_info.append(f"EXTRACTED DATA RECORDS ({len(results)} total):")
                
                for i, record in enumerate(results[:max_records]):
                    if isinstance(record, dict):
                        # For dictionaries, include key-value pairs
                        record_info = []
                        for key, value in record.items():
                            if key in ['Name', 'Geo Place Name', 'Time Period', 'Data Value']:
                                record_info.append(f"{key}: {value}")
                        
                        extraction_info.append(f"Record {i+1}: {', '.join(record_info)}")
                    else:
                        # For other types, just include the record
                        extraction_info.append(f"Record {i+1}: {record}")
            elif isinstance(results, dict) and results:
                extraction_info.append(f"EXTRACTED DATA: {results}")
    
    # Create prompt for OpenAI
    prompt = f"""
You are analyzing a dataset to determine its relevance to a user's query.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {dataset_metadata.get('title', 'Unknown')}
Description: {dataset_metadata.get('description', '')}
Rows: {row_count}
Columns: {col_count}

COLUMN INFORMATION (with first 2 rows as samples):
{chr(10).join(column_info)}

MISSING VALUES:
{chr(10).join(missing_values_summary) if missing_values_summary else "No missing values detected."}

TEMPORAL SCOPE:
{str(temporal_range) if temporal_range else "No clear temporal columns identified."}

GEOGRAPHIC SCOPE:
{str(geographic_scope) if geographic_scope else "No clear geographic columns identified."}

CATEGORICAL SUMMARIES (Top values):
{chr(10).join(categorical_summaries) if categorical_summaries else "No categorical columns analyzed."}

EXTRACTION INFORMATION:
{chr(10).join(extraction_info) if extraction_info else "No extraction information available."}

DATA PREVIEW (first 5 rows):
{dataset_content.head(5).to_string()}

IMPORTANT: Before making claims about what data is or isn't in the dataset, carefully check the column information, sample values, and especially the EXTRACTION INFORMATION. The dataset may contain information that isn't immediately obvious from column names. Be especially careful about geographic information - check all columns for location data, not just those with geographic terms in their names.

Please provide a VERY CONCISE analysis of this dataset (maximum 3-4 sentences per section):

1. RELEVANCE: How relevant is this dataset to the user's query? Can it answer the query directly?
2. DATA QUALITY: Are there any data quality issues that might affect analysis?
3. SCOPE LIMITATIONS: Is the dataset limited to a specific time period, geographic area, or other scope?
4. ALTERNATIVE INSIGHTS: If the dataset cannot answer the query directly, what related insights could it provide?

Be extremely concise but accurate. Do not make claims about missing data unless you are certain. Pay special attention to the EXTRACTION INFORMATION which shows what data was successfully extracted from the dataset.
"""

    logger.info("Sending analysis prompt to OpenAI")
    
    # Use the chat_completion helper function
    system_message = "You are a data analyst who specializes in evaluating dataset quality and relevance. Be extremely concise and accurate. Before making claims about what data is or isn't in the dataset, carefully examine all columns, sample values, and especially the extraction information. Don't assume information is missing just because it's not in an expected column."
    
    analysis = chat_completion(
        prompt=prompt,
        system_message=system_message,
        temperature=0.2
    )
    
    logger.info("Received analysis from OpenAI")
    
    # Return the analysis
    return {
        "dataset_id": dataset_metadata.get("id", ""),
        "dataset_title": dataset_metadata.get("title", ""),
        "row_count": row_count,
        "column_count": col_count,
        "missing_values_summary": missing_values_summary,
        "temporal_scope": temporal_range,
        "geographic_scope": geographic_scope,
        "categorical_summaries": categorical_summaries,
        "extraction_info": extraction_info,
        "extracted_data": extracted_data,  # Include the full extracted data
        "analysis": analysis
    }

def analyze_dataset_files(
    file_paths: List[str],
    query: str,
    dataset_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze multiple files from a dataset to provide summaries for each file
    and a combined overview.
    
    Args:
        file_paths: List of paths to dataset files
        query: The original user query
        dataset_metadata: Metadata about the dataset
        
    Returns:
        Dictionary containing file summaries and combined analysis
    """
    # Set up logging
    logger = logging.getLogger("dataset_analysis")
    logger.setLevel(logging.DEBUG)
    
    # Add a console handler if not already present
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[ANALYSIS] %(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info(f"Starting multi-file dataset analysis for query: {query}")
    logger.info(f"Dataset: {dataset_metadata.get('title', 'Unknown')}")
    logger.info(f"Analyzing {len(file_paths)} files")
    
    # List to store file summaries
    file_summaries = []
    combined_analysis = ""
    
    # Process each file
    for i, file_path in enumerate(file_paths):
        file_name = os.path.basename(file_path)
        logger.info(f"Analyzing file {i+1}/{len(file_paths)}: {file_name}")
        
        try:
            # Load the dataset file
            from factchecker.processing.analysis.dataset_loader import load_dataset
            file_content = load_dataset(file_path)
            
            # Create file metadata
            file_metadata = {
                "title": f"{dataset_metadata.get('title', 'Unknown')} - {file_name}",
                "id": f"{dataset_metadata.get('id', 'unknown')}_{i}",
                "file_path": file_path,
            }
            
            # Generate summary for this file
            if isinstance(file_content, pd.DataFrame):
                # For DataFrame (tabular data)
                file_summary = {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_index": i,
                    "row_count": len(file_content),
                    "column_count": len(file_content.columns),
                    "columns": list(file_content.columns)
                }
                
                # Get a brief analysis of this file
                file_analysis = analyze_dataset_overview(
                    file_content, 
                    query, 
                    file_metadata
                )
                file_summary["analysis"] = file_analysis.get("analysis", "No analysis available")
                
            else:
                # For PDF documents
                file_summary = {
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_index": i,
                    "document_type": "pdf",
                    "num_pages": file_content.get("num_pages", 0)
                }
                
                # Get a brief analysis of this PDF
                file_analysis = analyze_dataset_overview(
                    file_content, 
                    query, 
                    file_metadata
                )
                file_summary["analysis"] = file_analysis.get("analysis", "No analysis available")
            
            file_summaries.append(file_summary)
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_name}: {str(e)}")
            file_summaries.append({
                "file_name": file_name,
                "file_path": file_path,
                "file_index": i,
                "error": str(e)
            })
    
    # Generate a combined analysis if there are multiple files
    if len(file_summaries) > 1:
        # Create a prompt for OpenAI to summarize all files
        file_descriptions = []
        for summary in file_summaries:
            if "row_count" in summary:
                file_descriptions.append(
                    f"File: {summary['file_name']}\n"
                    f"Rows: {summary.get('row_count', 'N/A')}\n"
                    f"Columns: {summary.get('column_count', 'N/A')}\n"
                    f"Analysis: {summary.get('analysis', 'No analysis available')}"
                )
            else:
                file_descriptions.append(
                    f"File: {summary['file_name']}\n"
                    f"Type: PDF\n"
                    f"Pages: {summary.get('num_pages', 'N/A')}\n"
                    f"Analysis: {summary.get('analysis', 'No analysis available')}"
                )
        
        prompt = f"""
You are analyzing multiple files from the same dataset to determine their relevance to a user's query.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {dataset_metadata.get('title', 'Unknown')}
Description: {dataset_metadata.get('description', '')}

FILE SUMMARIES:
{chr(10).join(file_descriptions)}

Please provide a VERY CONCISE combined analysis of these files (maximum 3-4 sentences per section):

1. DATASET STRUCTURE: How are the files related? Do they contain complementary information or different aspects of the same data?
2. RELEVANCE: How relevant is this dataset (considering all files) to the user's query? Can it answer the query directly?
3. RECOMMENDED APPROACH: Which file(s) would be most useful for answering the query and why?

Be extremely concise but accurate.
"""

        logger.info("Sending combined analysis prompt to OpenAI")
        
        # Use the chat_completion helper function
        system_message = "You are a data analyst who specializes in evaluating multi-file datasets. Be extremely concise and accurate."
        
        combined_analysis = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.2
        )
        
        logger.info("Received combined analysis from OpenAI")
    
    # Return the file summaries and combined analysis
    return {
        "dataset_id": dataset_metadata.get("id", ""),
        "dataset_title": dataset_metadata.get("title", ""),
        "file_count": len(file_paths),
        "file_summaries": file_summaries,
        "combined_analysis": combined_analysis if len(file_summaries) > 1 else ""
    }

def get_data_dimensions(data: Any) -> Dict[str, Any]:
    """Get dimensions of the extracted data."""
    if isinstance(data, pd.DataFrame):
        return {"rows": len(data), "columns": len(data.columns)}
    elif isinstance(data, pd.Series):
        return {"length": len(data)}
    elif isinstance(data, dict):
        return {"keys": list(data.keys())}
    elif isinstance(data, list):
        return {"length": len(data)}
    else:
        return {"type": "scalar"}

# Add a custom JSON encoder to handle numpy types and other non-serializable objects
class ExtendedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, datetime.date):
            return obj.isoformat()
        if pd.isna(obj):
            return None
        return super().default(obj)