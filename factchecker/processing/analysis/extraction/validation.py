# Contains Dataset Extraction Logic

from typing import Dict, List, Tuple, Any, Union, TypedDict, Optional
import pandas as pd
import numpy as np
from contextlib import redirect_stdout
import re
from pydantic import BaseModel

from factchecker.utils.openai_client import chat_completion
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

class ValidationResult(BaseModel):
    """Pydantic model for extraction validation results"""
    is_valid: bool
    reason: str
    suggestions: Optional[str] = ""

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