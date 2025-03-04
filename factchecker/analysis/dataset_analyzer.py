import pandas as pd
import os
import openai
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

def extract_relevant_data(
    df: pd.DataFrame,
    query: str,
    dataset_metadata: Dict[str, Any],
    openai_api_key: str
) -> Dict[str, Any]:
    """
    Extract relevant data from a dataset based on the user's query.
    
    Args:
        df: The dataset as a pandas DataFrame
        query: The original user query
        dataset_metadata: Metadata about the dataset
        openai_api_key: OpenAI API key
        
    Returns:
        Dictionary containing extracted data and explanation
    """
    # Step 1: Analyze dataset structure
    column_info = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        unique_count = df[col].nunique()
        has_nulls = df[col].isna().any()
        sample_values = df[col].dropna().head(3).tolist()
        
        column_info.append({
            "name": col,
            "dtype": dtype,
            "unique_values": unique_count,
            "has_nulls": has_nulls,
            "sample_values": sample_values
        })
    
    # Step 2: Generate dataset statistics
    dataset_stats = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "memory_usage": df.memory_usage(deep=True).sum() / (1024 * 1024),  # MB
    }
    
    # For numerical columns, calculate basic statistics
    numerical_stats = {}
    for col in df.select_dtypes(include=['number']).columns:
        numerical_stats[col] = {
            "min": df[col].min(),
            "max": df[col].max(),
            "mean": df[col].mean(),
            "median": df[col].median(),
            "std": df[col].std()
        }
    
    # Step 3: Identify relevant feature columns
    relevant_columns = identify_relevant_columns(df, query, column_info, openai_api_key)
    
    # Step 4: For each relevant column, get unique values and select relevant ones
    column_values_analysis = {}
    for col_name in relevant_columns:
        unique_values = get_unique_column_values(df, col_name)
        relevant_values = select_relevant_values(unique_values, col_name, query, openai_api_key)
        column_values_analysis[col_name] = {
            "unique_values": unique_values,
            "relevant_values": relevant_values
        }
    
    # Step 5: Generate extraction code based on relevant columns and values
    extraction_code = generate_extraction_code(df, column_values_analysis, query, openai_api_key)
    
    # Step 6: Ask LLM to determine extraction strategy (including the column analysis)
    extraction_plan = determine_extraction_strategy(
        df, query, dataset_metadata, column_info, dataset_stats, 
        numerical_stats, openai_api_key, column_values_analysis, extraction_code
    )
    
    # Step 7: Execute the extraction plan
    extracted_data, code_used = execute_extraction_plan(df, extraction_plan)
    
    # Step 8: Format and return results
    return {
        "dataset_id": dataset_metadata.get("id", ""),
        "dataset_title": dataset_metadata.get("title", ""),
        "query": query,
        "extraction_plan": extraction_plan,
        "extracted_data": extracted_data,
        "code_used": code_used,
        "data_shape": {
            "type": type(extracted_data).__name__,
            "dimensions": get_data_dimensions(extracted_data)
        },
        "column_values_analysis": column_values_analysis,
        "relevant_columns": relevant_columns
    }

def identify_relevant_columns(
    df: pd.DataFrame,
    query: str,
    column_info: List[Dict],
    openai_api_key: str
) -> List[str]:
    """
    Identify columns that are most relevant to the user's query.
    
    Args:
        df: The dataset as a pandas DataFrame
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
{df.head(5).to_string()}

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
    existing_columns = [col for col in relevant_columns if col in df.columns]
    
    return existing_columns

def get_unique_column_values(df: pd.DataFrame, column_name: str, max_values: int = 100) -> List[Any]:
    """
    Get unique values from a column, with a limit to prevent performance issues.
    
    Args:
        df: The dataset as a pandas DataFrame
        column_name: Name of the column to analyze
        max_values: Maximum number of unique values to return
        
    Returns:
        List of unique values from the column
    """
    if column_name not in df.columns:
        return []
    
    # Get unique values
    unique_values = df[column_name].dropna().unique()
    
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
    df: pd.DataFrame,
    query: str,
    dataset_metadata: Dict[str, Any],
    openai_api_key: str,
    column_values_analysis: Dict[str, Dict[str, List[Any]]] = None,
    relevant_columns: List[str] = None
) -> Dict[str, Any]:
    """
    Analyze a dataset to provide a concise overview of its relevance to the query,
    including data quality assessment and scope limitations.
    
    Args:
        df: The dataset as a pandas DataFrame
        query: The original user query
        dataset_metadata: Metadata about the dataset
        openai_api_key: OpenAI API key
        column_values_analysis: Analysis of relevant columns and their values
        relevant_columns: List of columns identified as relevant to the query
        
    Returns:
        Dictionary containing dataset analysis and summary
    """
    # Get basic dataset info
    row_count = len(df)
    col_count = len(df.columns)
    
    # Get column information with sample values and missing value counts
    column_info = []
    missing_values_summary = []
    
    for col in df.columns:
        dtype = str(df[col].dtype)
        missing_count = df[col].isna().sum()
        missing_percentage = (missing_count / row_count) * 100 if row_count > 0 else 0
        
        # Get sample values (first 2 rows)
        sample_values = df[col].head(2).tolist()
        
        column_info.append(f"- {col} ({dtype}): {sample_values}")
        
        if missing_count > 0:
            missing_values_summary.append(f"- {col}: {missing_count} missing values ({missing_percentage:.2f}%)")
    
    # Check for temporal and geographic scope
    temporal_cols = [col for col in df.columns if any(term in col.lower() for term in 
                    ['year', 'date', 'time', 'month', 'day', 'period'])]
    
    geographic_cols = [col for col in df.columns if any(term in col.lower() for term in 
                      ['city', 'state', 'country', 'region', 'county', 'province', 'location', 
                       'address', 'zip', 'postal', 'latitude', 'longitude', 'geo'])]
    
    # Temporal range analysis
    temporal_range = {}
    for col in temporal_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            temporal_range[col] = {
                "min": df[col].min(),
                "max": df[col].max()
            }
        elif pd.api.types.is_datetime64_dtype(df[col]):
            temporal_range[col] = {
                "min": df[col].min().strftime('%Y-%m-%d') if not pd.isna(df[col].min()) else "N/A",
                "max": df[col].max().strftime('%Y-%m-%d') if not pd.isna(df[col].max()) else "N/A"
            }
    
    # Geographic scope analysis
    geographic_scope = {}
    for col in geographic_cols:
        if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            # Get unique values if there aren't too many
            unique_values = df[col].dropna().unique()
            if len(unique_values) <= 10:  # Only include if there's a reasonable number of unique values
                geographic_scope[col] = unique_values.tolist()
            else:
                # Just count the unique values if there are too many
                geographic_scope[col] = f"{len(unique_values)} unique values"
    
    # Identify potential categorical columns (non-numeric with limited unique values)
    categorical_summaries = []
    
    for col in df.columns:
        # Check if column is non-numeric (string or object type)
        if pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
            # Count unique values
            unique_count = df[col].nunique()
            # If column has a reasonable number of unique values (not too few, not too many)
            if 2 <= unique_count <= 100:  # Adjust thresholds as needed
                # Get value counts for this column
                value_counts = df[col].value_counts().head(10)  # Top 10 values
                if not value_counts.empty:
                    values_summary = ", ".join([f"{val} ({count})" for val, count in value_counts.items()])
                    categorical_summaries.append(f"- {col} top values: {values_summary}")
    
    # Include information about relevant columns and values if provided
    relevant_column_info = []
    if relevant_columns:
        relevant_column_info.append(f"RELEVANT COLUMNS: {', '.join(relevant_columns)}")
    
    column_analysis_summary = []
    if column_values_analysis:
        column_analysis_summary.append("COLUMN VALUES ANALYSIS:")
        for col_name, analysis in column_values_analysis.items():
            relevant_values = analysis.get("relevant_values", [])
            if not relevant_values:
                column_analysis_summary.append(f"- Column '{col_name}': No relevant values identified")
            elif len(relevant_values) == len(analysis.get("unique_values", [])):
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

{chr(10).join(relevant_column_info) if relevant_column_info else ""}

{chr(10).join(column_analysis_summary) if column_analysis_summary else ""}

DATA PREVIEW (first 5 rows):
{df.head(5).to_string()}

IMPORTANT: Before making claims about what data is or isn't in the dataset, carefully check the column information and sample values. The dataset may contain information that isn't immediately obvious from column names. Be especially careful about geographic information - check all columns for location data, not just those with geographic terms in their names.

Please provide a VERY CONCISE analysis of this dataset (maximum 3-4 sentences per section):

1. RELEVANCE: How relevant is this dataset to the user's query? Can it answer the query directly?
2. DATA QUALITY: Are there any data quality issues that might affect analysis?
3. SCOPE LIMITATIONS: Is the dataset limited to a specific time period, geographic area, or other scope?
4. ALTERNATIVE INSIGHTS: If the dataset cannot answer the query directly, what related insights could it provide?

Be extremely concise but accurate. Do not make claims about missing data unless you are certain.
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analyst who specializes in evaluating dataset quality and relevance. Be extremely concise and accurate. Before making claims about what data is or isn't in the dataset, carefully examine all columns and sample values. Don't assume information is missing just because it's not in an expected column."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    # Parse the response
    analysis = response.choices[0].message.content
    
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
        "relevant_columns": relevant_columns,
        "column_values_analysis": column_values_analysis,
        "analysis": analysis
    }

def generate_extraction_code(
    df: pd.DataFrame,
    column_values_analysis: Dict[str, Dict[str, List[Any]]],
    query: str,
    openai_api_key: str
) -> str:
    """
    Generate pandas code to extract relevant data based on column analysis.
    
    Args:
        df: The dataset as a pandas DataFrame
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

DATASET SHAPE: {df.shape[0]} rows × {df.shape[1]} columns

COLUMN ANALYSIS:
{chr(10).join(column_analysis_summary) if column_analysis_summary else "No relevant columns identified."}

SAMPLE DATA (first 5 rows):
{df.head(5).to_string()}

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
    
    # Remove markdown code block markers if present
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3].strip()
    if code.startswith("```python") and code.endswith("```"):
        code = code[9:-3].strip()
    
    return code

def determine_extraction_strategy(
    df: pd.DataFrame,
    query: str,
    dataset_metadata: Dict[str, Any],
    column_info: List[Dict],
    dataset_stats: Dict,
    numerical_stats: Dict,
    openai_api_key: str,
    column_values_analysis: Dict[str, Dict[str, List[Any]]] = None,
    extraction_code: str = None
) -> Dict[str, Any]:
    """
    Use LLM to determine the best strategy for extracting relevant data.
    """
    # Create a sample of the dataset
    sample_rows = df.head(5).to_string(index=False)
    
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
- Memory Usage: {dataset_stats['memory_usage']:.2f} MB

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

def execute_extraction_plan(df: pd.DataFrame, extraction_plan: Dict[str, Any]) -> Tuple[Any, str]:
    """
    Execute the extraction plan generated by the LLM.
    
    Returns:
        Tuple of (extracted_data, code_used)
    """
    logger = logging.getLogger("data_extraction")
    
    # Log the extraction code
    code = extraction_plan["code"].strip()
    print("=" * 80)
    print("EXTRACTION CODE")
    print("=" * 80)
    print(f"Code to execute:\n{code}")
    
    try:
        # First try to evaluate the code as an expression
        local_env = {"df": df.copy(), "pd": pd, "np": np}
        
        try:
            print("=" * 80)
            print("EXECUTING CODE AS EXPRESSION")
            print("=" * 80)
            
            # Try direct evaluation first (safer and more reliable for expressions)
            result = eval(code, {"__builtins__": {}}, local_env)
            print(f"Expression evaluation successful. Result type: {type(result)}")
            
            # Add logging for the result
            if isinstance(result, pd.DataFrame):
                print(f"Result DataFrame - shape: {result.shape}")
                print(f"Result sample:\n{result.head(5).to_string() if not result.empty else 'Empty DataFrame'}")
            else:
                print(f"Result: {result}")
                
            print(f"DataFrame copy in local_env - shape: {local_env['df'].shape}")
            print(f"DataFrame copy in local_env - columns: {list(local_env['df'].columns)}")
            
            print("=" * 80)
            print("VERIFYING LOCAL ENVIRONMENT DATA")
            print("=" * 80)
            print(f"Original DataFrame shape: {df.shape}")
            print(f"Local env DataFrame shape: {local_env['df'].shape}")
            print(f"Original DataFrame columns: {list(df.columns)}")
            print(f"Local env DataFrame columns: {list(local_env['df'].columns)}")
            print(f"Original DataFrame first 3 rows:")
            print(df.head(3))
            print(f"Local env DataFrame first 3 rows:")
            print(local_env['df'].head(3))
            print("=" * 80)
            
            return result, code
        except SyntaxError as se:
            print(f"Expression evaluation failed with SyntaxError: {str(se)}")
            print("Attempting to execute as a statement block")
            
            # Capture stdout to get printed results
            import io
            from contextlib import redirect_stdout
            
            # Create a StringIO object to capture printed output
            captured_output = io.StringIO()
            
            # If it's not a simple expression, try executing as a statement block
            # Modify the code to store results in a dictionary instead of printing them
            modified_code = code
            
            # Check if the code contains print statements
            if "print(" in code:
                # Replace print statements with assignments to a results dictionary
                result_dict_code = "results_dict = {}\n"
                
                # Split the code into lines
                lines = code.strip().split('\n')
                modified_lines = []
                result_keys = []
                
                for i, line in enumerate(lines):
                    if "print(" in line:
                        # Extract the content inside print()
                        content = line.split("print(", 1)[1].rsplit(")", 1)[0]
                        
                        # Create a key for this result
                        key = f"result_{i}"
                        result_keys.append(key)
                        
                        # Replace print with assignment to results_dict
                        modified_lines.append(f"results_dict['{key}'] = {content}")
                    else:
                        modified_lines.append(line)
                
                # Join the modified lines
                modified_code = result_dict_code + "\n".join(modified_lines)
                
                # Execute the modified code with print statements replaced
                exec(modified_code, {"__builtins__": __builtins__}, local_env)
                
                # Get the results dictionary
                results_dict = local_env.get("results_dict", {})
                
                # Also execute the original code to capture the printed output
                with redirect_stdout(captured_output):
                    exec(code, {"__builtins__": __builtins__}, local_env)
                
                # Get the printed output
                printed_output = captured_output.getvalue()
                
                # Create a result that includes both the dictionary and printed output
                result = {
                    "results_dict": results_dict,
                    "printed_output": printed_output.strip()
                }
            else:
                # Check if the last line is just a variable name (likely the result)
                lines = code.strip().split('\n')
                last_line = lines[-1].strip()
                
                # If the last line is just a variable name, use that as the result
                if last_line and not last_line.startswith('#') and '=' not in last_line:
                    result_var = last_line
                    # Replace the last line with an assignment to result
                    lines[-1] = f"result = {result_var}"
                    modified_code = '\n'.join(lines)
                else:
                    # Otherwise, try to find the last variable assignment
                    var_assignments = []
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            var_name = line.split('=')[0].strip()
                            if var_name != 'result':  # Avoid existing result assignments
                                var_assignments.append(var_name)
                    
                    if var_assignments:
                        # Add a line to assign the last variable to result
                        modified_code = f"{code}\nresult = {var_assignments[-1]}"
                    else:
                        # If no variable assignments found, just use the original code
                        modified_code = f"{code}\n# No result variable found"
                
                # Execute the modified code
                exec_code = f"result = None\n{modified_code}\n"
                print(f"Executing modified code block:\n{exec_code}")
                
                # Execute the code and capture any printed output
                with redirect_stdout(captured_output):
                    exec(exec_code, {"__builtins__": __builtins__}, local_env)
                
                # Get the result from the local environment
                result = local_env.get("result")
                
                # If result is None but we have printed output, use that instead
                printed_output = captured_output.getvalue().strip()
                if result is None and printed_output:
                    result = {"printed_output": printed_output}
            
            print("=" * 80)
            print("EXECUTION RESULTS")
            print("=" * 80)
            print(f"Statement execution completed. Result type: {type(result)}")
            
            # Log the result details
            if isinstance(result, pd.DataFrame):
                print(f"Result DataFrame - shape: {result.shape}")
                print(f"Result columns: {list(result.columns)}")
                print(f"Result sample:\n{result.head(5).to_string() if not result.empty else 'Empty DataFrame'}")
            elif isinstance(result, dict) and "printed_output" in result:
                print(f"Captured printed output: {result['printed_output']}")
            else:
                print(f"Result: {result}")
                
            return result, code
    except Exception as e:
        print("=" * 80)
        print("EXECUTION ERROR")
        print("=" * 80)
        print(f"Execution failed with error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # If execution fails, fall back to a simpler approach
        print("Falling back to df.head(10)")
        fallback_result = {
            "error": str(e),
            "fallback_data": df.head(10).to_dict(orient="records")
        }
        return fallback_result, f"# Original code failed with error: {str(e)}\n# Fallback to df.head(10)"

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
    for data in extracted_data_list:
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        dataset_source = data.get("dataset_source", "Unknown Source")
        
        # Get the extracted data
        extracted = data.get("extracted_data")
        
        # Create a concise summary of the extracted data
        if isinstance(extracted, pd.DataFrame):
            # For DataFrames, include all rows without any limit
            sample = extracted.to_string()
            data_summary = f"Data:\n{sample}"
        elif isinstance(extracted, dict):
            # For dictionaries, include all key-value pairs
            data_summary = "\n".join([f"{k}: {v}" for k, v in extracted.items()])
        elif isinstance(extracted, list):
            # For lists, include all items
            data_summary = "\n".join([str(item) for item in extracted])
        else:
            data_summary = str(extracted)
        
        dataset_summaries.append(f"Source: {dataset_title} ({dataset_source})\n{data_summary}")
    
    # Include dataset analyses if provided
    dataset_context = ""
    if dataset_analyses:
        dataset_context = "DATASET CONTEXT:\n"
        for analysis in dataset_analyses:
            dataset_context += f"Dataset: {analysis.get('dataset_title', 'Unknown')}\n"
            dataset_context += f"Analysis: {analysis.get('analysis', 'No analysis available')}\n\n"
    
    # Create prompt for OpenAI
    prompt = f"""
You are analyzing data to answer: "{query}"

{dataset_context}

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Present the key data points that directly answer the query
2. Be concise but thorough - include all relevant data in your analysis
3. Format as bullet points where appropriate
4. Always cite the source dataset for each data point
5. If analyzing trends over time, be sure to include the full time range in your analysis
6. Pay special attention to the most recent data points when analyzing trends

Finally, provide a "SEARCH SUMMARY" section with 2 paragraphs that:
1. Summarizes the overall context of the datasets analyzed (their scope, limitations, quality)
2. Synthesizes the findings in relation to the query, including any external factors that might be relevant

Your response should -focus on answering the query using all available data.
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