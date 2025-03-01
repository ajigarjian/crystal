import pandas as pd
import os
import openai
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

def load_csv_dataset(file_path: str) -> pd.DataFrame:
    """
    Load a CSV dataset with appropriate error handling.
    
    Args:
        file_path: Path to the CSV file
        
    Returns:
        Pandas DataFrame containing the dataset
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading dataset from {file_path}")
    
    try:
        # Try different loading approaches
        loading_attempts = [
            # Standard loading
            lambda: pd.read_csv(file_path),
            # Try with Latin-1 encoding
            lambda: pd.read_csv(file_path, encoding='latin1'),
            # Try with explicit quoting
            lambda: pd.read_csv(file_path, quoting=pd.io.common.csv.QUOTE_NONNUMERIC),
            # Try with different engine
            lambda: pd.read_csv(file_path, engine='python'),
            # Try with auto delimiter detection
            lambda: pd.read_csv(file_path, sep=None, engine='python')
        ]
        
        df = None
        errors = []
        
        for i, attempt in enumerate(loading_attempts):
            try:
                logger.info(f"Attempt {i+1} to load CSV")
                df = attempt()
                # If we got here, loading succeeded
                logger.info(f"Successfully loaded CSV with attempt {i+1}")
                
                # Log the DataFrame info
                logger.info(f"DataFrame shape: {df.shape}")
                logger.info(f"DataFrame columns: {list(df.columns)}")
                logger.info(f"DataFrame sample:\n{df.head(5).to_string()}")
                
                break
            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Attempt {i+1} failed: {str(e)}")
                continue
        
        if df is None:
            raise ValueError(f"All loading attempts failed: {errors}")
            
        # Handle common issues
        if len(df.columns) == 1:
            # Try different delimiter if only one column detected
            logger.warning("Only one column detected, trying different delimiter")
            df = pd.read_csv(file_path, sep=None, engine='python')
            
        return df
    except Exception as e:
        logger.error(f"Error loading dataset: {str(e)}")
        raise ValueError(f"Error loading dataset: {e}")

def assess_dataset_relevance(
    df: pd.DataFrame, 
    query: str, 
    dataset_metadata: Dict[str, Any],
    openai_api_key: str,
    relevance_threshold: float = 0.7
) -> Tuple[bool, float, str]:
    """
    Assess if a dataset is relevant to the user's query using OpenAI.
    
    Args:
        df: The dataset as a pandas DataFrame
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description, etc.)
        openai_api_key: OpenAI API key
        relevance_threshold: Threshold for considering a dataset relevant (0-1)
        
    Returns:
        Tuple of (is_relevant, relevance_score, reasoning)
    """
    # Get dataset information
    title = dataset_metadata.get('title', 'Unknown')
    description = dataset_metadata.get('description', '')
    
    # Get column information
    columns = list(df.columns)
    column_info = []
    for col in columns:
        dtype = str(df[col].dtype)
        sample_values = df[col].dropna().head(3).tolist()
        column_info.append(f"- {col} ({dtype}): {sample_values}")
    
    # Get sample rows
    sample_rows = df.head(5).to_string(index=False)
    
    # Search for key terms from the query in the entire dataset
    # Extract key terms from query
    key_terms = query.lower().split()
    
    # Search for these terms in the dataset
    term_presence = {}
    for term in key_terms:
        if len(term) > 3:  # Only search for meaningful terms (longer than 3 chars)
            # Check if term appears in any string column
            found = False
            for col in df.select_dtypes(include=['object']).columns:
                # Sample a subset of the data to avoid performance issues with large datasets
                sample_size = min(1000, len(df))
                if df[col].sample(sample_size).astype(str).str.contains(term, case=False).any():
                    found = True
                    break
            term_presence[term] = found
    
    # Create prompt for OpenAI
    prompt = f"""
You are assessing whether a dataset is relevant to a user's query.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {title}
Description: {description}

DATASET STRUCTURE:
Columns: {', '.join(columns)}

Column Details:
{chr(10).join(column_info)}

Sample Data (first 5 rows):
{sample_rows}

KEY TERM SEARCH RESULTS:
The following key terms from the query were searched in the dataset:
{chr(10).join([f"- '{term}': {'Found' if found else 'Not found'}" for term, found in term_presence.items()])}

ASSESSMENT GUIDELINES:
1. PRIORITIZE the dataset's title, description, and column names when determining relevance
2. Consider that the sample rows may not represent all data in the dataset
3. If the dataset contains columns that could plausibly contain information related to the query, consider it potentially relevant
4. Consider that specific categories or terms might be present in the full dataset even if not in the sample
5. Look for patterns in the data structure that suggest relevance to the query topic

Provide your assessment in the following format:
RELEVANCE_SCORE: [Score between 0 and 1, where 1 is highly relevant]
REASONING: [Your detailed reasoning]
DECISION: [YES or NO - whether to use this dataset]
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analysis assistant that evaluates dataset relevance. Be generous in your assessment - if there's a reasonable chance the dataset contains relevant information, give it a higher score."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    
    # Parse response
    content = response.choices[0].message.content
    
    # Extract relevance score
    try:
        relevance_score_line = [line for line in content.split('\n') if 'RELEVANCE_SCORE:' in line][0]
        relevance_score = float(relevance_score_line.split(':')[1].strip())
    except:
        relevance_score = 0.0
    
    # Extract reasoning
    try:
        reasoning_lines = []
        reasoning_started = False
        for line in content.split('\n'):
            if 'REASONING:' in line:
                reasoning_started = True
                reasoning_lines.append(line.replace('REASONING:', '').strip())
            elif reasoning_started and 'DECISION:' not in line:
                reasoning_lines.append(line.strip())
            elif 'DECISION:' in line:
                break
        reasoning = ' '.join(reasoning_lines)
    except:
        reasoning = "Could not extract reasoning."
    
    # Determine if relevant based on threshold
    is_relevant = relevance_score >= relevance_threshold
    
    return is_relevant, relevance_score, reasoning

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
    
    # Step 3: Ask LLM to determine extraction strategy
    extraction_plan = determine_extraction_strategy(
        df, query, dataset_metadata, column_info, dataset_stats, numerical_stats, openai_api_key
    )
    
    # Step 4: Execute the extraction plan
    extracted_data, code_used = execute_extraction_plan(df, extraction_plan)
    
    # Step 5: Format and return results
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
        }
    }

def determine_extraction_strategy(
    df: pd.DataFrame,
    query: str,
    dataset_metadata: Dict[str, Any],
    column_info: List[Dict],
    dataset_stats: Dict,
    numerical_stats: Dict,
    openai_api_key: str
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
            
            # If it's not a simple expression, try executing as a statement block
            # IMPORTANT CHANGE: Modify the code to explicitly return the result
            modified_code = code
            
            # Check if the code ends with a variable name (likely the result)
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
            
            exec(exec_code, {"__builtins__": __builtins__}, local_env)
            
            # Get the result from the local environment
            result = local_env.get("result")
            
            print("=" * 80)
            print("EXECUTION RESULTS")
            print("=" * 80)
            print(f"Statement execution completed. Result type: {type(result)}")
            
            # Log the result details
            if isinstance(result, pd.DataFrame):
                print(f"Result DataFrame - shape: {result.shape}")
                print(f"Result columns: {list(result.columns)}")
                print(f"Result sample:\n{result.head(5).to_string() if not result.empty else 'Empty DataFrame'}")
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
    openai_api_key: str
) -> str:
    """
    Summarize findings from multiple datasets into a concise response.
    
    Args:
        query: The original user query
        extracted_data_list: List of dictionaries containing extracted data
        openai_api_key: OpenAI API key
        
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
            # For DataFrames, just include the first 3 rows
            if not extracted.empty:
                sample = extracted.head(3).to_string()
                data_summary = f"Data sample:\n{sample}"
            else:
                data_summary = "Empty dataset"
        elif isinstance(extracted, dict):
            # For dictionaries, just list the key-value pairs
            data_summary = "\n".join([f"{k}: {v}" for k, v in list(extracted.items())[:5]])
            if len(extracted) > 5:
                data_summary += f"\n... and {len(extracted) - 5} more items"
        elif isinstance(extracted, list):
            # For lists, show first few items
            data_summary = "\n".join([str(item) for item in extracted[:3]])
            if len(extracted) > 3:
                data_summary += f"\n... and {len(extracted) - 3} more items"
        else:
            data_summary = str(extracted)
        
        dataset_summaries.append(f"Source: {dataset_title} ({dataset_source})\n{data_summary}")
    
    # Create prompt for OpenAI
    prompt = f"""
You are analyzing data to answer: "{query}"

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Present ONLY the key data points that directly answer the query
2. Be extremely concise - no lengthy explanations
3. Format as bullet points where appropriate
4. Always cite the source dataset for each data point
5. If data is insufficient, briefly state what's missing

Your response should be no more than 2-3 short paragraphs or 5-7 bullet points.
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analyst who provides only essential information with minimal text."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=300  # Limit response length
    )
    
    # Return the summary
    return response.choices[0].message.content