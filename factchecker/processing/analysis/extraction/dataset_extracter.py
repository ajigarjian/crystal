# Contains Dataset Extraction Logic

from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
import logging
import openai
from contextlib import redirect_stdout
import io
import traceback
import re

from factchecker.processing.analysis.extraction.generation import extract_section, generate_extraction_code
from factchecker.processing.analysis.extraction.shared import ExtractionPlan, ExtractedData
from factchecker.utils.openai_client import chat_completion
# Define TypedDict classes for better typing

def extract_relevant_data(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    dataset_metadata: Dict[str, Any]
) -> ExtractedData:
    """
    Extract data from a dataset that is relevant to the user's query.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        dataset_metadata: Metadata about the dataset
        
    Returns:
        ExtractedData object containing extracted data and metadata
    """
    # Set up logging
    logger = logging.getLogger("data_extraction")
    logger.setLevel(logging.DEBUG)
    
    # Add a console handler if not already present
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('[EXTRACT] %(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    logger.info(f"Starting data extraction for query: {query}")
    logger.info(f"Dataset: {dataset_metadata.get('title', 'Unknown')}")
    
    # Initialize the result with default values
    result: ExtractedData = {
        "dataset_id": dataset_metadata.get("id", ""),
        "dataset_title": dataset_metadata.get("title", ""),
        "file_path": dataset_metadata.get("file_path", ""),
        "results_dict": {},
        "printed_output": "",
        "extraction_strategy": "No strategy provided",
        "explanation": "No explanation provided",
        "code": "",
        "error": None
    }
    
    # Handle non-DataFrame data (like PDFs)
    if not isinstance(dataset_content, pd.DataFrame):
        logger.warning("Non-tabular data detected, extraction not supported")
        result["results_dict"] = {"data": "Non-tabular data, extraction not supported"}
        result["extraction_strategy"] = "Direct extraction of document content"
        result["explanation"] = "Document content extracted directly without filtering"
        return result
    
    try:
        # Log basic dataset info
        logger.info(f"Dataset shape: {dataset_content.shape}")
        logger.info(f"Columns: {list(dataset_content.columns)}")
        
        # Get basic dataset stats
        row_count = len(dataset_content)
        col_count = len(dataset_content.columns)
        
        # Get column information
        column_info = []
        for col in dataset_content.columns:
            dtype = str(dataset_content[col].dtype)
            unique_count = dataset_content[col].nunique()
            has_nulls = dataset_content[col].isna().any()
            sample_values = dataset_content[col].dropna().head(3).tolist()
            
            column_info.append({
                "name": col,
                "dtype": dtype,
                "unique_values": unique_count,
                "has_nulls": has_nulls,
                "sample_values": sample_values
            })
        
        # Get numerical column statistics
        numerical_stats = {}
        for col in dataset_content.select_dtypes(include=['number']).columns:
            numerical_stats[col] = {
                "min": dataset_content[col].min(),
                "max": dataset_content[col].max(),
                "mean": dataset_content[col].mean(),
                "median": dataset_content[col].median(),
                "std": dataset_content[col].std()
            }
        
        # Create dataset stats dictionary
        dataset_stats = {
            "row_count": row_count,
            "column_count": col_count,
            "memory_usage": dataset_content.memory_usage(deep=True).sum() / (1024 * 1024)  # Convert to MB
        }
        
        # Identify relevant columns
        logger.info("Identifying relevant columns...")
        relevant_columns = identify_relevant_columns(dataset_content, query, column_info)
        logger.info(f"Identified relevant columns: {relevant_columns}")
        
        # Analyze relevant columns and their values
        column_values_analysis = {}
        for col in relevant_columns:
            logger.info(f"Analyzing values in column: {col}")
            unique_values = get_unique_column_values(dataset_content, col)
            relevant_values = select_relevant_values(unique_values, col, query)
            
            column_values_analysis[col] = {
                "unique_values": unique_values,
                "relevant_values": relevant_values
            }

            if relevant_values:
                logger.info(f"Column {col}: Found {len(relevant_values)} relevant values out of {len(unique_values)} unique values")
        
        # Generate extraction code
        logger.info("Generating extraction code...")

        extraction_code = generate_extraction_code(dataset_content, column_values_analysis, query)
        
        print("Debug extraction code:", extraction_code)
        return {
            "dataset_stats": dataset_stats,
            "column_info": column_info,
            "numerical_stats": numerical_stats,
            "column_values_analysis": column_values_analysis,
            "extraction_code": extraction_code,
            "dataset_content": dataset_content,
            "user_query": query
        }
    
        # Skip this for now - we may not need at the moment.

        # Determine extraction strategy
        # logger.info("Determining extraction strategy...")
        # extraction_plan = determine_extraction_strategy(
        #     dataset_content, 
        #     query, 
        #     dataset_metadata, 
        #     column_info, 
        #     dataset_stats, 
        #     numerical_stats,
        #     column_values_analysis,
        #     extraction_code
        # )

        # For now, just return the code.
        
        # print("Extraction Plan:", extraction_plan)
        # # Execute the extraction plan with validation feedback loop
        # logger.info("Executing extraction plan...")
        # extracted_data = execute_extraction_plan(
        #     dataset_content, 
        #     extraction_plan,
        #     query
        # )
        
        # # Update the result with the extracted data
        # result.update(extracted_data)
        # result["dataset_id"] = dataset_metadata.get("id", "")
        # result["dataset_title"] = dataset_metadata.get("title", "")
        
        # # Log the extraction results
        # if isinstance(result["results_dict"], list):
        #     logger.info(f"Extracted {len(result['results_dict'])} records")
        # else:
        #     logger.info(f"Extracted data: {type(result['results_dict'])}")
        
        return result
        
    except Exception as e:
        # Log the error
        logger.error(f"Error extracting relevant data: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Update the result with the error
        result["error"] = str(e)
        result["extraction_strategy"] = f"Extraction failed: {str(e)}"
        result["explanation"] = f"An error occurred during extraction: {str(e)}"
        
        return result

def identify_relevant_columns(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    column_info: List[Dict]
) -> List[str]:
    """
    Identify columns that are most relevant to the user's query.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        column_info: Information about each column
        
    Returns:
        List of column names that are relevant to the query
    """
    # Format column information for the prompt
    column_details = []
    for col in column_info:
        column_details.append(
            f"- {col['name']} ({col['dtype']}): {col['unique_values']} unique values, "
            f"{'has' if col['has_nulls'] else 'no'} nulls, samples: {col['sample_values']}"
        )
    
    # Create prompt for OpenAI
    prompt = f"""
You are a data analysis expert. Given a dataset and a user query, identify which columns are most relevant to the query.

USER QUERY: "{query}"

DATASET COLUMNS:
{chr(10).join(column_details)}

SAMPLE DATA (first 5 rows):
{dataset_content.head(5).to_string()}

Based on the user query and dataset information, identify the columns that are most likely to contain relevant information.
Consider both direct matches (columns that explicitly match query terms) and indirect matches (columns that might contain 
information related to the query even if the names don't match directly).

Return ONLY a comma-separated list of the most relevant column names, with no additional text or explanation.
If no columns seem relevant, return "None".
"""
    
    response = chat_completion(
    prompt,
    system_message="You are a data analysis expert specializing in identifying relevant columns in datasets.",
    temperature=0.1 # Low temperature for more deterministic responses
    )

    # Parse response
    content = response.strip()
    
    # Handle the case where no columns are relevant
    if content.lower() == "none":
        return []
    
    # Split the comma-separated list and clean up column names
    relevant_columns = [col.strip() for col in content.split(',')]
    
    # Verify that all returned columns actually exist in the dataframe
    existing_columns = [col for col in relevant_columns if col in dataset_content.columns]
    
    return existing_columns

def get_unique_column_values(dataset_content: Union[pd.DataFrame, Dict[str, Any]], column_name: str, max_values: int = 100) -> List[Any]:
    """
    Get unique values from a column, with a limit to prevent performance issues.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        column_name: Name of the column to analyze
        max_values: Maximum number of unique values to return
        
    Returns:
        List of unique values from the column
    """
    if column_name not in dataset_content.columns:
        return []
    
    # Get unique values
    unique_values = dataset_content[column_name].dropna().unique()
    
    # Limit the number of values to prevent performance issues
    if len(unique_values) > max_values:
        unique_values = unique_values[:max_values]
        
    # Convert numpy types to Python native types for better JSON serialization
    result = []
    for val in unique_values:
        if isinstance(val, (np.integer, np.floating, np.bool_)):
            val = val.item()  # Convert numpy type to Python native type
        elif isinstance(val, np.ndarray):
            val = val.tolist()  # Convert numpy array to list
        result.append(val)
    
    return result

def select_relevant_values(
    unique_values: List[Any],
    column_name: str,
    query: str
) -> List[Any]:
    """
    Select values from a column that are relevant to the user's query.
    
    Args:
        unique_values: List of unique values from the column
        column_name: Name of the column
        query: The original user query
        
    Returns:
        List of values that are relevant to the query
    """
    if not unique_values:
        return []
    
    # Limit the number of values to include in the prompt
    display_values = unique_values
    if len(unique_values) > 50:
        display_values = unique_values[:50]
        
    # Create prompt for OpenAI
    prompt = f"""
You are a data analysis expert. Given a list of unique values from a column and a user query, identify which values are relevant to the query.

USER QUERY: "{query}"

COLUMN NAME: {column_name}

UNIQUE VALUES (showing up to 50):
{display_values}

{f"Note: Only showing first 50 of {len(unique_values)} unique values" if len(unique_values) > 50 else ""}

Based on the user query, identify which values from this column are most relevant. Consider both direct matches (values that explicitly match query terms) and indirect matches (values that might be related to the query even if they don't match directly).

Return ONLY a comma-separated list of the relevant values, with no additional text or explanation.
If no values seem relevant, return "None".
If ALL values seem relevant or if filtering by specific values doesn't make sense for this column, return "All".
"""
    response = chat_completion(
        prompt,
        system_message="You are a data analysis expert specializing in identifying relevant values in datasets.",
        temperature=0.1  # Low temperature for more deterministic responses
        )
    
    if response == None or response == "None":
        return None
    
    # Parse response
    content = response.strip()
    
    # Handle special cases
    if content.lower() == "none":
        return []
    if content.lower() == "all":
        return unique_values
    
    # Split the comma-separated list and clean up values
    relevant_values_str = [val.strip() for val in content.split(',')]
    
    # Convert string representations back to appropriate types
    relevant_values = []
    for val_str in relevant_values_str:
        # Try to find the matching value in the original list
        # This preserves the original type
        found = False
        for orig_val in unique_values:
            if str(orig_val).strip() == val_str:
                relevant_values.append(orig_val)
                found = True
                break
        
        # If not found, try to convert to appropriate type
        if not found:
            try:
                # Try as int
                relevant_values.append(int(val_str))
            except ValueError:
                try:
                    # Try as float
                    relevant_values.append(float(val_str))
                except ValueError:
                    # Keep as string
                    relevant_values.append(val_str)
    
    return relevant_values

# def determine_extraction_strategy(
#     dataset_content: Union[pd.DataFrame, Dict[str, Any]],
#     query: str,
#     dataset_metadata: Dict[str, Any],
#     column_info: List[Dict],
#     dataset_stats: Dict,
#     numerical_stats: Dict,
#     column_values_analysis: Dict,
#     extraction_code: str = None
# ) -> Dict[str, Any]:
#     """
#     Use LLM to determine the best strategy for extracting relevant data.
#     """
#     # Create a sample of the dataset
#     sample_rows = dataset_content.head(5).to_string(index=False)
    
#     # Format column information for the prompt
#     column_details = []
#     for col in column_info:
#         column_details.append(
#             f"- {col['name']} ({col['dtype']}): {col['unique_values']} unique values, "
#             f"{'has' if col['has_nulls'] else 'no'} nulls, samples: {col['sample_values']}"
#         )
    
#     # Format numerical statistics for the prompt
#     numerical_details = []
#     for col, stats in numerical_stats.items():
#         numerical_details.append(
#             f"- {col}: min={stats['min']}, max={stats['max']}, mean={stats['mean']:.2f}, "
#             f"median={stats['median']}, std={stats['std']:.2f}"
#         )
    
#     # Format column values analysis if available
#     column_analysis_summary = []
#     if column_values_analysis:
#         for col_name, analysis in column_values_analysis.items():
#             relevant_values = analysis["relevant_values"]
#             if not relevant_values:
#                 column_analysis_summary.append(f"- Column '{col_name}': No relevant values identified")
#             elif len(relevant_values) == len(analysis["unique_values"]):
#                 column_analysis_summary.append(f"- Column '{col_name}': All values are relevant")
#             else:
#                 # Limit the number of values to display
#                 display_values = relevant_values
#                 if len(relevant_values) > 10:
#                     display_values = relevant_values[:10]
#                     column_analysis_summary.append(
#                         f"- Column '{col_name}': {len(relevant_values)} relevant values, including: {display_values}"
#                     )
#                 else:
#                     column_analysis_summary.append(
#                         f"- Column '{col_name}': Relevant values: {relevant_values}"
#                     )
    
#     # Create prompt for OpenAI
#     prompt = f"""
# You are a data analysis expert. Given a dataset and a user query, your task is to determine the best strategy to extract the relevant data that answers the query.

# USER QUERY: "{query}"

# DATASET INFORMATION:
# Title: {dataset_metadata.get('title', 'Unknown')}
# Description: {dataset_metadata.get('description', '')}

# DATASET STATISTICS:
# - Rows: {dataset_stats['row_count']}
# - Columns: {dataset_stats['column_count']}

# COLUMN INFORMATION:
# {chr(10).join(column_details)}

# NUMERICAL COLUMN STATISTICS:
# {chr(10).join(numerical_details) if numerical_details else "No numerical columns found."}

# {"COLUMN VALUES ANALYSIS:\n" + chr(10).join(column_analysis_summary) if column_analysis_summary else ""}

# {"SUGGESTED EXTRACTION CODE:\n" + extraction_code if extraction_code else ""}

# SAMPLE DATA (first 5 rows):
# {sample_rows}

# Based on the user query and dataset information, please provide:

# 1. ANALYSIS: Analyze how this dataset can answer the user's query
# 2. EXTRACTION_STRATEGY: Detailed strategy for extracting the relevant data
# 3. PYTHON_CODE: Write pandas code to extract the data (use 'df' as the DataFrame variable)
# 4. EXPLANATION: Explain why this extraction method is appropriate

# Your response should be in the following format:
# ANALYSIS: [Your analysis]
# EXTRACTION_STRATEGY: [Your strategy]
# PYTHON_CODE: [Your code]
# EXPLANATION: [Your explanation]
# """

#     response = chat_completion(
#     prompt,
#     system_message="You are a data analysis expert specializing in pandas and data extraction.",
#     temperature=0.1  # Low temperature for more deterministic responses
#     )
    
#     # Parse response
#     content = response
    
#     # Extract sections
#     analysis = extract_section(content, "ANALYSIS")
#     strategy = extract_section(content, "EXTRACTION_STRATEGY")
#     code = extract_section(content, "PYTHON_CODE")
#     explanation = extract_section(content, "EXPLANATION")
    
#     return {
#         "analysis": analysis,
#         "strategy": strategy,
#         "code": code,
#         "explanation": explanation
#     }

