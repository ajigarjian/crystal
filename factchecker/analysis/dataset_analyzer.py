from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
import logging
import openai
from contextlib import redirect_stdout
import io
import traceback
import re

# Define TypedDict classes for better typing
class ExtractionPlan(TypedDict):
    strategy: str
    analysis: str
    explanation: str
    code: str

class ExtractedData(TypedDict):
    dataset_id: str
    dataset_title: str
    results_dict: Dict[str, Any]
    printed_output: str
    extraction_strategy: str
    explanation: str
    code: str
    error: Optional[str]

def extract_relevant_data(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    dataset_metadata: Dict[str, Any],
    openai_api_key: str
) -> ExtractedData:
    """
    Extract data from a dataset that is relevant to the user's query.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        dataset_metadata: Metadata about the dataset
        openai_api_key: OpenAI API key
        
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
        relevant_columns = identify_relevant_columns(dataset_content, query, column_info, openai_api_key)
        logger.info(f"Identified relevant columns: {relevant_columns}")
        
        # Analyze relevant columns and their values
        column_values_analysis = {}
        for col in relevant_columns:
            logger.info(f"Analyzing values in column: {col}")
            unique_values = get_unique_column_values(dataset_content, col)
            relevant_values = select_relevant_values(unique_values, col, query, openai_api_key)
            
            column_values_analysis[col] = {
                "unique_values": unique_values,
                "relevant_values": relevant_values
            }
            logger.info(f"Column {col}: Found {len(relevant_values)} relevant values out of {len(unique_values)} unique values")
        
        # Generate extraction code
        logger.info("Generating extraction code...")
        extraction_code = generate_extraction_code(dataset_content, column_values_analysis, query, openai_api_key)
        
        # Determine extraction strategy
        logger.info("Determining extraction strategy...")
        extraction_plan = determine_extraction_strategy(
            dataset_content, 
            query, 
            dataset_metadata, 
            column_info, 
            dataset_stats, 
            numerical_stats, 
            openai_api_key,
            column_values_analysis,
            extraction_code
        )
        
        # Execute the extraction plan with validation feedback loop
        logger.info("Executing extraction plan...")
        extracted_data = execute_extraction_plan(
            dataset_content, 
            extraction_plan,
            query,
            openai_api_key
        )
        
        # Update the result with the extracted data
        result.update(extracted_data)
        result["dataset_id"] = dataset_metadata.get("id", "")
        result["dataset_title"] = dataset_metadata.get("title", "")
        
        # Log the extraction results
        if isinstance(result["results_dict"], list):
            logger.info(f"Extracted {len(result['results_dict'])} records")
        else:
            logger.info(f"Extracted data: {type(result['results_dict'])}")
        
        return result
        
    except Exception as e:
        # Log the error
        logger.error(f"Error extracting relevant data: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Update the result with the error
        result["error"] = str(e)
        result["extraction_strategy"] = f"Extraction failed: {str(e)}"
        result["explanation"] = f"An error occurred during extraction: {str(e)}"
        
        # Attempt a simple fallback extraction
        try:
            logger.info("Attempting fallback extraction...")
            # Look for any columns that might contain Greenwich Village data
            greenwich_data = dataset_content[
                dataset_content.apply(
                    lambda row: any(
                        isinstance(val, str) and 'greenwich' in str(val).lower() 
                        for val in row
                    ), 
                    axis=1
                )
            ]
            
            if not greenwich_data.empty:
                logger.info(f"Found {len(greenwich_data)} rows with Greenwich Village data")
                result["results_dict"] = greenwich_data.head(10).to_dict(orient="records")
                result["explanation"] += "\n\nFallback extraction found some rows containing 'Greenwich Village'"
            else:
                # If no Greenwich Village data, look for air quality indicators
                air_quality_indicators = ['ozone', 'o3', 'pm2.5', 'pm 2.5', 'fine particles', 'nitrogen dioxide', 'no2']
                
                air_quality_data = dataset_content[
                    dataset_content.apply(
                        lambda row: any(
                            isinstance(val, str) and any(indicator in str(val).lower() for indicator in air_quality_indicators)
                            for val in row
                        ),
                        axis=1
                    )
                ]
                
                if not air_quality_data.empty:
                    logger.info(f"Found {len(air_quality_data)} rows with air quality indicators")
                    result["results_dict"] = air_quality_data.head(10).to_dict(orient="records")
                    result["explanation"] += "\n\nFallback extraction found some rows containing air quality indicators"
                else:
                    # Last resort: just return the first 10 rows
                    logger.info("No relevant data found, returning first 10 rows")
                    result["results_dict"] = dataset_content.head(10).to_dict(orient="records")
                    result["explanation"] += "\n\nNo specific relevant data found, showing sample rows"
        except Exception as fallback_error:
            logger.error(f"Fallback extraction also failed: {str(fallback_error)}")
            result["results_dict"] = dataset_content.head(5).to_dict(orient="records")
            
        return result

def identify_relevant_columns(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    column_info: List[Dict],
    openai_api_key: str
) -> List[str]:
    """
    Identify columns that are most relevant to the user's query.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        column_info: Information about each column
        openai_api_key: OpenAI API key
        
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

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert specializing in identifying relevant columns in datasets."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1  # Low temperature for more deterministic responses
    )
    
    # Parse response
    content = response.choices[0].message.content.strip()
    
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
    query: str,
    openai_api_key: str
) -> List[Any]:
    """
    Select values from a column that are relevant to the user's query.
    
    Args:
        unique_values: List of unique values from the column
        column_name: Name of the column
        query: The original user query
        openai_api_key: OpenAI API key
        
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

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert specializing in identifying relevant values in datasets."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1  # Low temperature for more deterministic responses
    )
    
    # Parse response
    content = response.choices[0].message.content.strip()
    
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

def analyze_dataset_overview(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    dataset_metadata: Dict[str, Any],
    openai_api_key: str,
    extracted_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Analyze a dataset to provide a concise overview of its relevance to the query,
    including data quality assessment and scope limitations.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        query: The original user query
        dataset_metadata: Metadata about the dataset
        openai_api_key: OpenAI API key
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
    
    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analyst who specializes in evaluating dataset quality and relevance. Be extremely concise and accurate. Before making claims about what data is or isn't in the dataset, carefully examine all columns, sample values, and especially the extraction information. Don't assume information is missing just because it's not in an expected column."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    # Parse the response
    analysis = response.choices[0].message.content
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

def generate_extraction_code(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    column_values_analysis: Dict[str, Dict[str, List[Any]]],
    query: str,
    openai_api_key: str
) -> str:
    """
    Generate pandas code to extract relevant data based on column analysis.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        column_values_analysis: Analysis of relevant columns and values
        query: The original user query
        openai_api_key: OpenAI API key
        
    Returns:
        Python code to extract relevant data
    """
    # Create a summary of the column analysis
    column_analysis_summary = []
    for col_name, analysis in column_values_analysis.items():
        relevant_values = analysis["relevant_values"]
        if not relevant_values:
            column_analysis_summary.append(f"- Column '{col_name}': No relevant values identified")
        elif len(relevant_values) == len(analysis["unique_values"]):
            column_analysis_summary.append(f"- Column '{col_name}': All values are relevant")
        else:
            # Limit the number of values to display
            display_values = relevant_values
            if len(relevant_values) > 10:
                display_values = relevant_values[:10]
                column_analysis_summary.append(
                    f"- Column '{col_name}': {len(relevant_values)} relevant values, including: {display_values}"
                )
            else:
                column_analysis_summary.append(
                    f"- Column '{col_name}': Relevant values: {relevant_values}"
                )
    
    # Create prompt for OpenAI
    prompt = f"""
You are a data analysis expert. Given a dataset and analysis of relevant columns and values, generate pandas code to extract the relevant data.

USER QUERY: "{query}"

DATASET SHAPE: {dataset_content.shape[0]} rows × {dataset_content.shape[1]} columns

COLUMN ANALYSIS:
{chr(10).join(column_analysis_summary) if column_analysis_summary else "No relevant columns identified."}

SAMPLE DATA (first 5 rows):
{dataset_content.head(5).to_string()}

Based on the user query and column analysis, generate pandas code to extract the relevant data. The code should:
1. Filter the dataframe to include only rows with relevant values in the identified columns
2. If multiple columns have relevant values, combine the filters appropriately
3. If no relevant columns or values were identified, return a suitable subset of the data that might be relevant
4. Include any necessary data transformations or aggregations to answer the query

Return ONLY the Python code, with no additional text or explanation. Use 'df' as the variable name for the input DataFrame.
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert specializing in pandas code generation."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1  # Low temperature for more deterministic responses
    )
    
    # Parse response
    code = response.choices[0].message.content.strip()
    # only works on strings    
    if isinstance(code, str):
        # Remove markdown code block markers if present
        if code.startswith("```") and code.endswith("```"):
            code = code[3:-3].strip()
        if code.startswith("```python") and code.endswith("```"):
            code = code[9:-3].strip()
    
    return code

def determine_extraction_strategy(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    query: str,
    dataset_metadata: Dict[str, Any],
    column_info: List[Dict],
    dataset_stats: Dict,
    numerical_stats: Dict,
    openai_api_key: str,
    column_values_analysis: Dict,
    extraction_code: str = None
) -> Dict[str, Any]:
    """
    Use LLM to determine the best strategy for extracting relevant data.
    """
    # Create a sample of the dataset
    sample_rows = dataset_content.head(5).to_string(index=False)
    
    # Format column information for the prompt
    column_details = []
    for col in column_info:
        column_details.append(
            f"- {col['name']} ({col['dtype']}): {col['unique_values']} unique values, "
            f"{'has' if col['has_nulls'] else 'no'} nulls, samples: {col['sample_values']}"
        )
    
    # Format numerical statistics for the prompt
    numerical_details = []
    for col, stats in numerical_stats.items():
        numerical_details.append(
            f"- {col}: min={stats['min']}, max={stats['max']}, mean={stats['mean']:.2f}, "
            f"median={stats['median']}, std={stats['std']:.2f}"
        )
    
    # Format column values analysis if available
    column_analysis_summary = []
    if column_values_analysis:
        for col_name, analysis in column_values_analysis.items():
            relevant_values = analysis["relevant_values"]
            if not relevant_values:
                column_analysis_summary.append(f"- Column '{col_name}': No relevant values identified")
            elif len(relevant_values) == len(analysis["unique_values"]):
                column_analysis_summary.append(f"- Column '{col_name}': All values are relevant")
            else:
                # Limit the number of values to display
                display_values = relevant_values
                if len(relevant_values) > 10:
                    display_values = relevant_values[:10]
                    column_analysis_summary.append(
                        f"- Column '{col_name}': {len(relevant_values)} relevant values, including: {display_values}"
                    )
                else:
                    column_analysis_summary.append(
                        f"- Column '{col_name}': Relevant values: {relevant_values}"
                    )
    
    # Create prompt for OpenAI
    prompt = f"""
You are a data analysis expert. Given a dataset and a user query, your task is to determine the best strategy to extract the relevant data that answers the query.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {dataset_metadata.get('title', 'Unknown')}
Description: {dataset_metadata.get('description', '')}

DATASET STATISTICS:
- Rows: {dataset_stats['row_count']}
- Columns: {dataset_stats['column_count']}

COLUMN INFORMATION:
{chr(10).join(column_details)}

NUMERICAL COLUMN STATISTICS:
{chr(10).join(numerical_details) if numerical_details else "No numerical columns found."}

{"COLUMN VALUES ANALYSIS:\n" + chr(10).join(column_analysis_summary) if column_analysis_summary else ""}

{"SUGGESTED EXTRACTION CODE:\n" + extraction_code if extraction_code else ""}

SAMPLE DATA (first 5 rows):
{sample_rows}

Based on the user query and dataset information, please provide:

1. ANALYSIS: Analyze how this dataset can answer the user's query
2. EXTRACTION_STRATEGY: Detailed strategy for extracting the relevant data
3. PYTHON_CODE: Write pandas code to extract the data (use 'df' as the DataFrame variable)
4. EXPLANATION: Explain why this extraction method is appropriate

Your response should be in the following format:
ANALYSIS: [Your analysis]
EXTRACTION_STRATEGY: [Your strategy]
PYTHON_CODE: [Your code]
EXPLANATION: [Your explanation]
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert specializing in pandas and data extraction."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1  # Low temperature for more deterministic responses
    )
    
    # Parse response
    content = response.choices[0].message.content
    
    # Extract sections
    analysis = extract_section(content, "ANALYSIS")
    strategy = extract_section(content, "EXTRACTION_STRATEGY")
    code = extract_section(content, "PYTHON_CODE")
    explanation = extract_section(content, "EXPLANATION")
    
    return {
        "analysis": analysis,
        "strategy": strategy,
        "code": code,
        "explanation": explanation
    }


def execute_extraction_plan(
    df: pd.DataFrame, 
    extraction_plan: ExtractionPlan,
    query: str,
    openai_api_key: str,
    max_attempts: int = 3
) -> ExtractedData:
    """
    Execute the extraction plan generated by the LLM with validation feedback loop.
    
    Args:
        df: The DataFrame to extract data from
        extraction_plan: The extraction plan containing code and strategy
        query: The original user query
        openai_api_key: OpenAI API key
        max_attempts: Maximum number of code generation attempts
        
    Returns:
        ExtractedData object with extraction results and metadata
    """
    logger = logging.getLogger("data_extraction")
    
    # Initialize result with default values
    result: ExtractedData = {
        "dataset_id": "",
        "dataset_title": "",
        "results_dict": {},
        "printed_output": "",
        "extraction_strategy": extraction_plan.get("strategy", "No strategy provided"),
        "explanation": extraction_plan.get("explanation", "No explanation provided"),
        "code": extraction_plan.get("code", ""),
        "error": None
    }
    
    # Track attempts
    attempts = 0
    success = False
    
    while attempts < max_attempts and not success:
        attempts += 1
        logger.info(f"Extraction attempt {attempts}/{max_attempts}")
        
        # Get the current code to execute
        code = extraction_plan.get("code", "").strip()
        result["code"] = code
        
        logger.info(f"Executing code:\n{code}")
        
        try:
            # Execute the code and capture results
            execution_result, printed_output = execute_code(df, code)
            
            # Validate the results
            validation_result = validate_extraction_results(
                execution_result, 
                df, 
                query, 
                extraction_plan,
                printed_output,
                openai_api_key
            )
            
            if validation_result["is_valid"]:
                # If valid, update the result and break the loop
                success = True
                
                # Package the results
                if isinstance(execution_result, pd.DataFrame):
                    result["results_dict"] = execution_result.to_dict(orient="records")
                else:
                    result["results_dict"] = {"data": execution_result}
                
                result["printed_output"] = printed_output
                logger.info("Extraction successful and validated")
                
            else:
                # If not valid, update the extraction plan with new code
                logger.info(f"Validation failed: {validation_result['reason']}")
                
                # Generate improved code
                improved_code = generate_improved_code(
                    df, 
                    query, 
                    extraction_plan,
                    validation_result["reason"],
                    code,
                    openai_api_key
                )
                
                # Update the extraction plan with the new code
                extraction_plan["code"] = improved_code
                result["code"] = improved_code
                
        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            
            if attempts < max_attempts:
                # Try to generate improved code that fixes the error
                improved_code = generate_improved_code(
                    df, 
                    query, 
                    extraction_plan,
                    error_msg,
                    code,
                    openai_api_key
                )
                
                # Update the extraction plan with the new code
                extraction_plan["code"] = improved_code
                result["code"] = improved_code
            else:
                # If this was the last attempt, record the error
                result["error"] = error_msg
                
                # Fallback to a simple extraction
                result["results_dict"] = df.head(10).to_dict(orient="records")
                result["printed_output"] = f"Error occurred: {str(e)}"
                result["extraction_strategy"] = "Fallback strategy: showing first 10 rows due to error"
                result["explanation"] = f"Original extraction failed with error: {str(e)}"
    
    return result

def execute_code(df: pd.DataFrame, code: str) -> Tuple[Any, str]:
    """
    Execute the provided code and return the result and any printed output.
    
    Args:
        df: The DataFrame to execute the code on
        code: The Python code to execute
        
    Returns:
        Tuple of (execution_result, printed_output)
    """
    # Create a copy of the DataFrame to avoid modifying the original
    local_env = {"df": df.copy(), "pd": pd, "np": np}
    
    # Clean the code - remove markdown code block markers if present
    if code.startswith("```python"):
        code = code.replace("```python", "", 1)
    if code.endswith("```"):
        code = code[:-3]
    
    # Remove any "python" line at the beginning (common in LLM outputs)
    lines = code.strip().split('\n')
    if lines and lines[0].strip().lower() == 'python':
        code = '\n'.join(lines[1:])
    
    # Capture printed output
    captured_output = io.StringIO()
    
    try:
        # First try to evaluate as an expression
        with redirect_stdout(captured_output):
            result = eval(code, {"__builtins__": {}}, local_env)
        
        printed_output = captured_output.getvalue().strip()
        return result, printed_output
        
    except SyntaxError:
        # If not an expression, execute as a statement block
        captured_output = io.StringIO()  # Reset the captured output
        
        with redirect_stdout(captured_output):
            exec(code, {"__builtins__": __builtins__}, local_env)
        
        printed_output = captured_output.getvalue().strip()
        
        # Try to find the result in the local environment
        new_vars = [var for var in local_env if var not in ["df", "pd", "np"]]
        
        if new_vars:
            # Use the last variable created as the result
            result_var = new_vars[-1]
            result = local_env[result_var]
        else:
            # If no new variables were created, check if df was modified
            if not df.equals(local_env["df"]):
                result = local_env["df"]
            else:
                # If nothing changed, use the original DataFrame
                result = df
        
        return result, printed_output
    

def validate_extraction_results(
    result: Any, 
    original_df: pd.DataFrame, 
    query: str, 
    extraction_plan: ExtractionPlan,
    printed_output: str,
    openai_api_key: str
) -> Dict[str, Any]:
    """
    Validate the extraction results using an LLM.
    
    Args:
        result: The result of executing the extraction code
        original_df: The original DataFrame
        query: The original user query
        extraction_plan: The extraction plan
        printed_output: Any printed output from the code execution
        openai_api_key: OpenAI API key
        
    Returns:
        Dictionary with validation results
    """
    # Format the result for the prompt
    if isinstance(result, pd.DataFrame):
        result_description = f"DataFrame with shape {result.shape}"
        result_sample = result.head(5).to_string() if not result.empty else "Empty DataFrame"
    else:
        result_description = f"{type(result).__name__}"
        result_sample = str(result)[:500] + "..." if len(str(result)) > 500 else str(result)
    
    # Create prompt for OpenAI
    prompt = f"""
You are validating the results of a data extraction operation. Determine if the extraction successfully addresses the user's query.

USER QUERY: "{query}"

EXTRACTION STRATEGY:
{extraction_plan.get("strategy", "No strategy provided")}

CODE EXECUTED:
{extraction_plan.get("code", "")}


EXECUTION RESULT:
Type: {result_description}
Sample: {result_sample}

PRINTED OUTPUT:
{printed_output if printed_output else "No output printed"}

VALIDATION TASK:
1. Determine if the extraction result is relevant to the user's query
2. Check if the code executed correctly (no errors in the output)
3. Verify that the result contains the information needed to answer the query
4. Ensure the extraction follows the intended strategy

Respond with:
1. VALID: Yes or No
2. REASON: Brief explanation of your assessment
3. SUGGESTIONS: If not valid, suggest specific improvements to the code
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert who validates extraction results."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    # Parse the response
    response_text = response.choices[0].message.content
    
    # Extract validation result
    is_valid = "VALID: Yes" in response_text
    
    # Extract reason
    reason_match = re.search(r'REASON:(.*?)(?:SUGGESTIONS:|$)', response_text, re.DOTALL)
    reason = reason_match.group(1).strip() if reason_match else "No reason provided"
    
    # Extract suggestions if not valid
    suggestions = ""
    if not is_valid:
        suggestions_match = re.search(r'SUGGESTIONS:(.*?)$', response_text, re.DOTALL)
        suggestions = suggestions_match.group(1).strip() if suggestions_match else "No suggestions provided"
    
    return {
        "is_valid": is_valid,
        "reason": reason,
        "suggestions": suggestions
    }

def generate_improved_code(
    df: pd.DataFrame,
    query: str,
    extraction_plan: ExtractionPlan,
    feedback: str,
    previous_code: str,
    openai_api_key: str
) -> str:
    """
    Generate improved extraction code based on feedback.
    
    Args:
        df: The DataFrame to extract data from
        query: The original user query
        extraction_plan: The original extraction plan
        feedback: Feedback on why the previous code didn't work
        previous_code: The previous code that didn't work
        openai_api_key: OpenAI API key
        
    Returns:
        Improved extraction code
    """
    # Create a sample of the DataFrame
    df_sample = df.head(5).to_string()
    df_info = f"Shape: {df.shape}, Columns: {list(df.columns)}"
    
    # Create prompt for OpenAI
    prompt = f"""
You are improving data extraction code based on feedback. Generate a better version of the code.

USER QUERY: "{query}"

EXTRACTION STRATEGY:
{extraction_plan.get("strategy", "No strategy provided")}

DATAFRAME INFO:
{df_info}

DATAFRAME SAMPLE:
{df_sample}

PREVIOUS CODE:
{previous_code}


FEEDBACK/ERROR:
{feedback}

TASK:
Generate improved Python code that addresses the feedback/error and better extracts the relevant data.
The code should:
1. Fix any syntax or logical errors in the previous code
2. Better align with the extraction strategy
3. More effectively answer the user's query
4. Be robust against potential errors

Return ONLY the Python code, with no additional text or explanation. Use 'df' as the variable name for the input DataFrame.
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis expert specializing in pandas code generation."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    # Parse response
    code = response.choices[0].message.content.strip()
    
    # Remove markdown code block markers if present
    if isinstance(code, str):
        if code.startswith("```") and code.endswith("```"):
            code = code[3:-3].strip()
        if code.startswith("```python") and code.endswith("```"):
            code = code[9:-3].strip()
    
    return code

def extract_section(content: str, section_name: str) -> str:
    """Extract a section from the LLM response and clean any markdown formatting."""
    try:
        lines = content.split('\n')
        section_start = None
        section_end = None
        
        for i, line in enumerate(lines):
            if line.startswith(f"{section_name}:"):
                section_start = i
            elif section_start is not None and i > section_start and any(
                line.startswith(f"{other}:") for other in ["ANALYSIS", "EXTRACTION_STRATEGY", "PYTHON_CODE", "EXPLANATION"]
                if other != section_name
            ):
                section_end = i
                break
        
        if section_start is not None:
            if section_end is None:
                section_end = len(lines)
            
            section_text = '\n'.join(lines[section_start:section_end])
            section_text = section_text.replace(f"{section_name}:", "").strip()
            
            # Remove markdown code block markers if present
            if "```" in section_text:
                # Split by code block markers
                parts = section_text.split("```")
                
                if len(parts) >= 3:
                    # If we have opening and closing markers
                    # parts[0] is text before the opening ```
                    # parts[1] might contain language identifier like "python"
                    # The actual code starts after the language identifier
                    code_part = parts[1]
                    if code_part.startswith("python"):
                        code_part = code_part[6:].strip()  # Remove "python" and whitespace
                    elif code_part.strip() and code_part.strip()[0].isalpha():
                        # If there's any language identifier, remove the first line
                        code_part = '\n'.join(code_part.split('\n')[1:])
                    
                    section_text = code_part
            
            return section_text
        
        return ""
    except Exception as e:
        logging.error(f"Error extracting section: {e}")
        return ""

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

def summarize_findings(
    query: str,
    extracted_data_list: List[Dict[str, Any]],
    openai_api_key: str,
    dataset_analyses: List[Dict[str, Any]] = None
) -> str:
    """
    Summarize findings from multiple datasets into a concise response.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        openai_api_key: OpenAI API key
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

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analyst who provides thorough analysis of data, with special attention to recent data points."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=800  # Increased token limit to allow for more comprehensive analysis
    )
    
    # Return the summary
    return response.choices[0].message.content