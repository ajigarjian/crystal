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

from factchecker.utils.openai_client import chat_completion
from factchecker.utils.claude_client import chat_completion_claude
from factchecker.processing.analysis.extraction.shared import ExtractionPlan

# Define TypedDict classes for better typing
class ExtractionPlan(TypedDict):
    strategy: str
    analysis: str
    explanation: str
    code: str

class ExtractedData(TypedDict):
    dataset_id: str
    dataset_title: str
    file_path: str
    results_dict: Dict[str, Any]
    printed_output: str
    extraction_strategy: str
    explanation: str
    code: str
    error: Optional[str]

def generate_extraction_code(
    dataset_content: Union[pd.DataFrame, Dict[str, Any]],
    column_values_analysis: Dict[str, Dict[str, List[Any]]],
    query: str,
    reason=None,
    code=None
) -> str:
    """
    Generate pandas code to extract relevant data based on column analysis.
    
    Args:
        dataset_content: The dataset content (either a pandas DataFrame or a dictionary)
        column_values_analysis: Analysis of potentially relevant columns and values
        query: The original user query
        
    Returns:
        Python code to extract relevant data
    """
    # Create a summary of the column analysis
    column_analysis_summary = []
    for col_name, analysis in column_values_analysis.items():
        relevant_values = analysis["relevant_values"]
        if not relevant_values:
            column_analysis_summary.append(f"- Column '{col_name}': No potentially relevant values identified")
        elif len(relevant_values) == len(analysis["unique_values"]):
            column_analysis_summary.append(f"- Column '{col_name}': All values are potentially relevant")
        else:
            # Limit the number of values to display
            display_values = relevant_values
            if len(relevant_values) > 10:
                display_values = relevant_values[:10]
                column_analysis_summary.append(
                    f"- Column '{col_name}': {len(relevant_values)} potentially relevant values, including: {display_values}"
                )
            else:
                column_analysis_summary.append(
                    f"- Column '{col_name}': Potentially relevant values: {relevant_values}"
                )
    
    # Create prompt for OpenAI
    prompt = f"""
You are a data analysis expert. Given a dataset and analysis of potentially relevant columns and values, generate pandas code to extract the relevant data.

USER QUERY: "{query}"

DATASET SHAPE: {dataset_content.shape[0]} rows × {dataset_content.shape[1]} columns

POTENTIAL COLUMN ANALYSIS:
{chr(10).join(column_analysis_summary) if column_analysis_summary else "No relevant columns identified."}

SAMPLE DATA (first 5 rows):
{dataset_content.head(5).to_string()}

A PREVIOUS VALIDATION FAILURE REASON:
{reason if reason else "N/A"}

PREVIOUSLY GENERATED CODE TO IMPROVE UPON:
{code}

Based on the user query and column analysis, generate pandas code to extract the relevant data. The code should:
1. Consider how specific a user query is. If they dont mention any geographical or spatial "filters" etc, dont filter by identified columns.
2. If applicable, filter the dataframe to include only rows with relevant values in the identified columns
3. If multiple columns have relevant values, combine the filters appropriately
4. If no relevant columns or values were identified, return a suitable subset of the data that might be relevant
5. Include aggregate and comparison values to improve the response.
6. Do not use any libraries besides pandas or numpy.

Return ONLY the Python code, with no additional text or explanation. Use 'df' as the variable name for the input DataFrame.

Object to return at end of the Python code:

{{
    "subset_df": "A subset DataFrame generated in the program that contains helpful information.,
    "aggregations": {{"key": "value"}} # A dict of key-value pairs for any aggregate and comparison values.
}}

"""

    response = chat_completion_claude(
        prompt,
        system_message="You are a data analysis expert specializing in pandas code generation.",
        temperature=0.1  # Low temperature for more deterministic responses
        )
    
    # Parse response
    code = response.strip()
    # only works on strings    
    if isinstance(code, str):
        # Remove markdown code block markers if present
        if code.startswith("```") and code.endswith("```"):
            code = code[3:-3].strip()
        if code.startswith("```python") and code.endswith("```"):
            code = code[9:-3].strip()
    
    return code

def generate_improved_code(
    df: pd.DataFrame,
    query: str,
    extraction_plan: Dict[str, Any],
    feedback: str,
    previous_code: str
) -> str:
    """
    Generate improved extraction code based on feedback.
    
    Args:
        df: The DataFrame to extract data from
        query: The original user query
        extraction_plan: The original extraction plan
        feedback: Feedback on why the previous code didn't work
        previous_code: The previous code that didn't work
        
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
1. Consider how specific a user query is. If they dont mention any geographical or spatial "filters" etc, dont filter by identified columns.
1. If applicable, filter the dataframe to include only rows with relevant values in the identified columns
2. If multiple columns have relevant values, combine the filters appropriately
3. If no relevant columns or values were identified, return a suitable subset of the data that might be relevant
4. Include aggregate and comparison values to improve the response.

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

Object to return at end of the Python code:

{{
    "subset_df": "A subset DataFrame generated in the program that contains helpful information.,
    "aggregations": {{"key": "value"}} # A dict of key-value pairs for any aggregate and comparison values.
}}

"""

    response = chat_completion_claude(
        prompt,
        system_message="You are a data analysis expert specializing in pandas code generation.",
        temperature=0.2
    )
    
    # Parse response
    code = response.strip()
    
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