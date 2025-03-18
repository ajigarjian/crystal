# Contains Dataset Extraction Logic

from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
from contextlib import redirect_stdout
import re
import logging
from pydantic import BaseModel

from factchecker.utils.openai_client import chat_completion

# Define TypedDict classes for better typing
class ExtractionPlan(TypedDict):
    strategy: str
    analysis: str
    explanation: str
    code: str

class ValidationResult(BaseModel):
    """Pydantic model for extraction validation results"""
    is_valid: bool
    reason: str
    suggestions: Optional[str] = ""
    improved_code: Optional[str] = None

class QueryAnswerValidation(BaseModel):
    """Pydantic model for query answer quality validation"""
    answer_quality: float
    is_optimal: bool
    reasoning: str
    improvement_suggestions: Optional[str] = ""
    improved_code: Optional[str] = ""

def validate_extraction_results(
    result: Any, 
    original_df: pd.DataFrame, 
    query: str, 
    printed_output: str,
    code: str
) -> ValidationResult:
    """
    Validate the extraction results using an LLM.
    
    Args:
        result: The result of executing the extraction code
        original_df: The original DataFrame
        query: The original user query
        extraction_plan: The extraction plan containing the code
        printed_output: Any printed output from the code execution
        
    Returns:
        ValidationResult: Pydantic model with validation results
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
You are validating the results of a data extraction operation.

USER QUERY: "{query}"

CODE EXECUTED:
{code}

EXECUTION RESULT:
Type: {result_description}
Sample: {result_sample}

PRINTED OUTPUT:
{printed_output if printed_output else "No output printed"}

VALIDATION TASK:
1. Determine if the extraction result could have relevance to the user's query (doesn't need to be exact)
2. Check if the code executed correctly (no errors in the output)

Respond with a JSON object containing these fields:
- is_valid: boolean (true if valid, false if not)
- reason: string (brief explanation of your assessment)
- suggestions: string (if not valid, suggest specific improvements to the code, otherwise empty string)
"""    
    response = chat_completion(
        prompt,
        system_message="You are a data analysis expert who validates extraction results.",
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    
    # Parse the JSON response
    try:
        import json
        validation_data = json.loads(response)
        
        # Create and return the Pydantic model
        return ValidationResult(
            is_valid=validation_data.get("is_valid", False),
            reason=validation_data.get("reason", "No reason provided"),
            suggestions=validation_data.get("suggestions", "")
        )
    except json.JSONDecodeError:
        # Fallback in case JSON parsing fails
        print(f"Error parsing JSON response: {response}")
        return ValidationResult(
            is_valid=False,
            reason="Error parsing validation response",
            suggestions="The validation system returned an invalid response format."
        )

def evaluate_query_answer_quality(
    result: Any,
    original_df: pd.DataFrame,
    query: str,
    extraction_code: str,
    printed_output: str
) -> QueryAnswerValidation:
    """
    Evaluate how well the extracted data answers the user's query.
    
    Args:
        result: The result of executing the extraction code
        original_df: The original DataFrame
        query: The original user query
        extraction_code: The code used for extraction
        printed_output: Any printed output from the code execution
        
    Returns:
        QueryAnswerValidation: Pydantic model with quality assessment
    """
    # Format the original DataFrame info for the prompt
    df_info = f"Shape: {original_df.shape}, Columns: {list(original_df.columns)}"
    df_sample = original_df.head(5).to_string()
    
    # Format the current result for the prompt
    if isinstance(result, pd.DataFrame):
        result_description = f"DataFrame with shape {result.shape}"
        result_sample = result.head(5).to_string() if not result.empty else "Empty DataFrame"
    else:
        result_description = f"{type(result).__name__}"
        result_sample = str(result)[:500] + "..." if len(str(result)) > 500 else str(result)
    
    # Create prompt for OpenAI to evaluate answer quality
    prompt = f"""
You are evaluating how well the extracted data answers the user's query. Your goal is to ensure the data provides the most relevant and complete answer possible from this dataset.

USER QUERY: "{query}"

DATAFRAME INFO:
{df_info}

DATAFRAME SAMPLE:
{df_sample}

CURRENT EXTRACTION CODE:
{extraction_code}

CURRENT RESULT:
Type: {result_description}
Sample: {result_sample}

PRINTED OUTPUT:
{printed_output if printed_output else "No output printed"}

EVALUATION TASK:
1. Assess how well the current result answers the user's query
2. Determine if there are ways to improve the answer using the available data
3. Consider if additional analysis, filtering, or aggregation would better address the query
4. Consider if the user's query may benefit from a comparison against other values in the dataset.

Respond with a JSON object containing these fields:
- answer_quality: float (0.0 to 1.0, where 1.0 is perfect)
- is_optimal: boolean (true if this is the best possible answer from this dataset)
- reasoning: string (explanation of your assessment)
- improvement_suggestions: string (specific suggestions to improve the answer if not optimal) (Max 3 sentences.)
"""
    
    response = chat_completion(
        prompt,
        system_message="You are a data analysis expert who evaluates and improves query answers.",
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    
    try:
        import json
        evaluation = json.loads(response)
        
        # Create and return the Pydantic model - no improved_code field
        return QueryAnswerValidation(
            answer_quality=evaluation.get("answer_quality", 0.0),
            is_optimal=evaluation.get("is_optimal", False),
            reasoning=evaluation.get("reasoning", "No reasoning provided"),
            improvement_suggestions=evaluation.get("improvement_suggestions", "")
        )
    except json.JSONDecodeError as e:
        # Improved error handling with more details
        logging.error(f"JSON parsing error: {e}")
        logging.error(f"Response content (first 500 chars): {response[:500]}...")
        
        # Fallback in case JSON parsing fails
        return QueryAnswerValidation(
            answer_quality=0.0,
            is_optimal=False,
            reasoning="Error parsing evaluation response",
            improvement_suggestions="The evaluation system returned an invalid response format."
        )