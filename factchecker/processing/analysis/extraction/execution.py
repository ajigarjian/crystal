# Contains Dataset Extraction Logic

from typing import Dict, Any, Union, Optional, Tuple
import pandas as pd
import numpy as np
import logging
import io
import traceback
from contextlib import redirect_stdout

from factchecker.processing.analysis.extraction.generation import generate_extraction_code
from factchecker.processing.analysis.extraction.shared import ExtractionPlan, ExtractedData
from factchecker.processing.analysis.extraction.validation import validate_extraction_results, evaluate_query_answer_quality
from factchecker.processing.analysis.extraction.helpers import check_execute_code_response
from factchecker.utils.openai_client import chat_completion

def generate_improved_code(
    df: pd.DataFrame,
    query: str,
    feedback: str,
    previous_code: str
) -> str:
    """
    Generate improved extraction code based on feedback.
    
    Args:
        df: The DataFrame to extract data from
        query: The original user query
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

    response = chat_completion(
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

def execute_relevant_data(relevant_data) -> Dict[str, Any]:
    """
    Execute the relevant data and return the extracted data
    
    Args:
        relevant_data:

        {
            "dataset_stats": dataset_stats,
            "column_info": column_info,
            "numerical_stats": numerical_stats,
            "column_values_analysis": column_values_analysis,
            "extraction_code": extraction_code,
            "dataset_content": dataset_content
        }
        
    Returns:
        extracted_data: Dictionary containing extracted data
    """
    logger = logging.getLogger("data_extraction")
    
    # Result 
    result = {}

    # Get variables
    dataset_stats = relevant_data["dataset_stats"]
    column_info = relevant_data["column_info"]
    numerical_stats = relevant_data["numerical_stats"]
    column_values_analysis = relevant_data["column_values_analysis"]
    extraction_code = relevant_data["extraction_code"]
    dataset_content = relevant_data["dataset_content"]
    query = relevant_data["user_query"]

    # Initialize result with default values
    # Track attempts
    max_attempts = 3
    attempts = 0
    success = False
    
    while attempts < max_attempts and not success:
        attempts += 1
        logger.info(f"Extraction attempt {attempts}/{max_attempts}")
        
        # Get the current code to execute
        code = relevant_data.get("extraction_code", "").strip()
        
        logger.info(f"Executing code:\n{extraction_code}")
        
        try:
            # Execute the code and capture results
            execution_result, printed_output = execute_code(dataset_content, code)

            # Check for an empty response before calling the validation LLM.
            response_check = check_execute_code_response(execution_result, printed_output)

            # If the response is None, there were no initial validation errors. Continue.
            if not response_check:

                # Debug print the extracted data
                print("Execution Result:", execution_result)

                # Validate the results
                validation_result = validate_extraction_results(
                    execution_result, 
                    dataset_content, 
                    query, 
                    printed_output,
                    code
                )
                
                if validation_result.is_valid:
                    # If valid, update the result and break the loop
                    success = True
                    
                    # Package the results
                    if isinstance(execution_result, pd.DataFrame):
                        result["results_dict"] = execution_result.to_dict(orient="records")
                    elif isinstance(execution_result, dict):
                        # Check that it conforms to the expected response
                        if "subset_df" in execution_result and "aggregations" in execution_result:
                            result["results_dict"] = execution_result["subset_df"]
                            result["aggregations"] = execution_result["aggregations"]
                        else:
                            # If it doesn't match the expected format, just use the dict as is
                            result["results_dict"] = execution_result
                    else:
                        result["results_dict"] = {"data": execution_result}
                    
                    result["printed_output"] = printed_output
                    logger.info("Extraction successful and validated")
                
                else:
                    # If not valid, update the extraction plan with new code
                    logger.info(f"Validation failed: {validation_result.reason}")
                    
                    improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, validation_result.reason, code)
                    
                    result["code"] = improved_code

            # If the initial check_execute_code_response check fails
            else:
                    # debug log
                    print(f"Debug: Initial check failed for", execution_result, printed_output, code)
                    # Generate improved code
                    improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, response_check, code)
                    
                    result["code"] = improved_code
                    
        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            
            if attempts < max_attempts:
                # Try to generate improved code that fixes the error
                improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, error_msg, code)
                        
                # Update the extraction plan with the new code
                result["code"] = improved_code
            else:
                # If this was the last attempt, record the error
                result["error"] = error_msg
                
                # Fallback to a simple extraction
                result["results_dict"] = dataset_content.head(10).to_dict(orient="records")
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

def validate_query_answer_quality(
    result: Any,
    original_df: pd.DataFrame,
    query: str,
    extraction_code: str,
    printed_output: str
) -> Dict[str, Any]:
    """
    Validate and improve the quality of the answer to the user's query through multiple iterations.
    
    Args:
        result: The result of executing the extraction code
        original_df: The original DataFrame
        query: The original user query
        extraction_code: The code used for extraction
        printed_output: Any printed output from the code execution
        
    Returns:
        Dictionary containing the final validated results and metadata
    """
    logger = logging.getLogger("query_validation")
    
    # Result dictionary to return
    final_result = {
        "results_dict": None,
        "code": extraction_code,
        "printed_output": printed_output,
        "validation_history": []
    }
    
    # Track attempts
    max_attempts = 3
    attempts = 0
    success = False
    
    while attempts < max_attempts and not success:
        attempts += 1
        logger.info(f"Query answer validation attempt {attempts}/{max_attempts}")
        
        # Evaluate the current answer quality
        evaluation = evaluate_query_answer_quality(
            result,
            original_df,
            query,
            extraction_code,
            printed_output
        )
        
        # Add to validation history
        final_result["validation_history"].append({
            "attempt": attempts,
            "answer_quality": evaluation.answer_quality,
            "reasoning": evaluation.reasoning,
            "is_optimal": evaluation.is_optimal
        })
        
        # Check if the answer is considered optimal
        if evaluation.is_optimal or evaluation.answer_quality >= 0.85:
            logger.info(f"Answer quality validation successful (Quality: {evaluation.answer_quality:.2f})")
            success = True
            
            # Package the results
            if isinstance(result, pd.DataFrame):
                final_result["results_dict"] = result.to_dict(orient="records")
            else:
                final_result["results_dict"] = {"data": result}
            
            final_result["printed_output"] = printed_output
            final_result["code"] = extraction_code
            final_result["answer_quality"] = evaluation.answer_quality
            final_result["answer_quality_reasoning"] = evaluation.reasoning
        
        # If not optimal and we have improvement suggestions, try to improve
        elif attempts < max_attempts and evaluation.improved_code:
            logger.info(f"Answer quality needs improvement (Quality: {evaluation.answer_quality:.2f})")
            logger.info(f"Reason: {evaluation.reasoning}")
            
            # Get the improved code
            improved_code = evaluation.improved_code
            
            # Clean the code if needed
            if improved_code.startswith("```python"):
                improved_code = improved_code.replace("```python", "", 1)
            if improved_code.endswith("```"):
                improved_code = improved_code[:-3]
            improved_code = improved_code.strip()
            
            # Execute the improved code
            try:
                new_result, new_printed_output = execute_code(original_df, improved_code)
                
                # Update for next iteration
                result = new_result
                printed_output = new_printed_output
                extraction_code = improved_code
                
            except Exception as e:
                logger.error(f"Error executing improved code: {str(e)}")

                improved_code = generate_extraction_code(original_df, "", query, f"Error executing improved code: {str(e)}")
                    
                # Try executing the new improved code
                try:
                    new_result, new_printed_output = execute_code(original_df, improved_code)
                    
                    # Update for next iteration
                    result = new_result
                    printed_output = new_printed_output
                    extraction_code = improved_code
                    
                except Exception as e2:
                    logger.error(f"Error executing second improved code: {str(e2)}")
                    # Keep the original result and continue
        
        # If no improved code was provided but we're not optimal
        elif attempts < max_attempts and evaluation.answer_quality < 0.85:
            logger.info(f"Generating improved code based on suggestions")
            
            # Generate improved code based on the suggestions
            improved_code = generate_extraction_code(original_df, "", query, evaluation.improvement_suggestions)
            
            result["code"] = improved_code
            
            # Execute the improved code
            try:
                new_result, new_printed_output = execute_code(original_df, improved_code)
                
                # Update for next iteration
                result = new_result
                printed_output = new_printed_output
                extraction_code = improved_code
                
            except Exception as e:
                logger.error(f"Error executing generated improved code: {str(e)}")
                # Keep the original result and continue
    
    # If we've exhausted all attempts without success, use the last result
    if not success:
        logger.info(f"Using best available result after {attempts} attempts")
        
        # Package the results
        if isinstance(result, pd.DataFrame):
            final_result["results_dict"] = result.to_dict(orient="records")
        else:
            final_result["results_dict"] = {"data": result}
        
        final_result["printed_output"] = printed_output
        final_result["code"] = extraction_code
        
        # Get the highest quality score from the validation history
        if final_result["validation_history"]:
            best_attempt = max(final_result["validation_history"], key=lambda x: x["answer_quality"])
            final_result["answer_quality"] = best_attempt["answer_quality"]
            final_result["answer_quality_reasoning"] = best_attempt["reasoning"]
    
    return final_result

def execute_relevant_data(relevant_data) -> Dict[str, Any]:
    """
    Execute the relevant data and return the extracted data
    
    Args:
        relevant_data:

        {
            "dataset_stats": dataset_stats,
            "column_info": column_info,
            "numerical_stats": numerical_stats,
            "column_values_analysis": column_values_analysis,
            "extraction_code": extraction_code,
            "dataset_content": dataset_content
        }
        
    Returns:
        extracted_data: Dictionary containing extracted data
        
        {
            "results_dict": Pandas dataframe or dict of result records,
            "code": Code used to extract the results_dict data
        }
    """
    logger = logging.getLogger("data_extraction")
    
    # Result 
    result = {}

    # Get variables
    dataset_stats = relevant_data.get("dataset_stats", {})
    column_info = relevant_data.get("column_info", {})
    numerical_stats = relevant_data.get("numerical_stats", {})
    column_values_analysis = relevant_data.get("column_values_analysis", {})
    extraction_code = relevant_data.get("extraction_code", "")
    dataset_content = relevant_data.get("dataset_content")
    query = relevant_data.get("user_query", "")
    
    # Add dataset metadata to result
    result["dataset_title"] = relevant_data.get("dataset_title", "")
    result["dataset_source"] = relevant_data.get("dataset_source", "")
    result["dataset_id"] = relevant_data.get("dataset_id", "")
    result["file_path"] = relevant_data.get("file_path", "")
    result["all_file_paths"] = relevant_data.get("all_file_paths", [])

    # Initialize result with default values
    # Track attempts
    max_attempts = 3
    attempts = 0
    success = False
    
    # Store validation history
    result["validation_history"] = []
    
    print(f"Starting extraction for query: {query}")
    print(f"Dataset shape: {dataset_content.shape if hasattr(dataset_content, 'shape') else 'Unknown'}")
    
    while attempts < max_attempts and not success:
        attempts += 1
        print(f"Extraction attempt {attempts}/{max_attempts}")
        
        # Get the current code to execute
        code = relevant_data.get("extraction_code", "").strip()
        if attempts > 1:
            # Use the improved code from previous attempt
            code = result.get("code", code)
        
        print(f"Executing code (attempt {attempts}):\n{code}")
        
        try:
            # Execute the code and capture results
            execution_result, printed_output = execute_code(dataset_content, code)
            print(f"Code execution completed. Result type: {type(execution_result)}")
            print(f"Printed output: {printed_output[:200]}..." if len(printed_output) > 200 else f"Printed output: {printed_output}")

            # Check for an empty response before calling the validation LLM.
            response_check = check_execute_code_response(execution_result, printed_output)

            # If the response is None, there were no initial validation errors. Continue.
            if not response_check:
                # Debug print the extracted data
                print(f"Execution Result: {str(execution_result)[:200]}..." if len(str(execution_result)) > 200 else f"Execution Result: {execution_result}")

                # First validate the basic extraction results
                print("Validating extraction results...")
                validation_result = validate_extraction_results(
                    execution_result, 
                    dataset_content, 
                    query, 
                    printed_output,
                    code
                )
                
                print(f"Validation result: is_valid={validation_result.is_valid}, reason={validation_result.reason}")
                
                if validation_result.is_valid:
                    # If valid, now validate and improve the answer quality
                    print("Basic extraction validated, now validating answer quality...")
                    
                    # Use the function to evaluate the answer quality
                    evaluation = evaluate_query_answer_quality(
                        execution_result,
                        dataset_content,
                        query,
                        code,
                        printed_output
                    )
                    
                    # Add to validation history
                    result["validation_history"].append({
                        "attempt": attempts,
                        "answer_quality": evaluation.answer_quality,
                        "reasoning": evaluation.reasoning,
                        "is_optimal": evaluation.is_optimal
                    })
                    
                    print(f"Answer quality: {evaluation.answer_quality:.2f}, is_optimal: {evaluation.is_optimal}")
                    print(f"Reasoning: {evaluation.reasoning}")
                    
                    # Check if the answer is considered optimal
                    if evaluation.is_optimal or evaluation.answer_quality >= 0.85:
                        print(f"Answer quality validation successful (Quality: {evaluation.answer_quality:.2f})")
                        success = True
                        
                        # Package the results
                        if isinstance(execution_result, pd.DataFrame):
                            result["results_dict"] = execution_result.to_dict(orient="records")
                        else:
                            result["results_dict"] = {"data": execution_result}
                        
                        result["printed_output"] = printed_output
                        result["code"] = code
                        result["answer_quality"] = evaluation.answer_quality
                        result["answer_quality_reasoning"] = evaluation.reasoning
                    
                    # If not optimal and we have improvement suggestions, try to improve
                    elif attempts < max_attempts and evaluation.improved_code:
                        print(f"Answer quality needs improvement (Quality: {evaluation.answer_quality:.2f})")
                        print(f"Reason: {evaluation.reasoning}")
                        
                        # Get the improved code
                        improved_code = evaluation.improved_code
                        
                        # Clean the code if needed
                        if improved_code.startswith("```python"):
                            improved_code = improved_code.replace("```python", "", 1)
                        if improved_code.endswith("```"):
                            improved_code = improved_code[:-3]
                        improved_code = improved_code.strip()
                        
                        print(f"Improved code generated:\n{improved_code}")
                        
                        # Update for next iteration
                        result["code"] = improved_code
                    
                    # If no improved code was provided but we're not optimal
                    elif attempts < max_attempts:
                        print(f"Generating improved code based on suggestions")
                        
                        # Generate improved code based on the suggestions
                        improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, evaluation.improvement_suggestions, code)

                        print(f"Generated improved code:\n{improved_code}")
                        
                        # Update for next iteration
                        result["code"] = improved_code
                
                else:
                    # If not valid, update the extraction plan with new code
                    print(f"Validation failed: {validation_result.reason}")
                    
                    # Generate improved code
                    improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, validation_result.reason, code)


                    print(f"Generated improved code:\n{improved_code}")
                    
                    result["code"] = improved_code

            # If the initial check_execute_code_response check fails
            else:
                print(f"Initial check failed: {response_check}")
                # Generate improved code
                improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, response_check, code)
                
                print(f"Generated improved code:\n{improved_code}")
                
                result["code"] = improved_code
                
        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            print(f"{error_msg}\n{traceback.format_exc()}")
            
            if attempts < max_attempts:
                # Try to generate improved code that fixes the error
                improved_code = generate_extraction_code(dataset_content, column_values_analysis, query, error_msg, code)

                print(f"Generated improved code after error:\n{improved_code}")
                
                # Update the extraction plan with the new code
                result["code"] = improved_code
            else:
                # If this was the last attempt, record the error
                result["error"] = error_msg
                
                # Fallback to a simple extraction
                result["results_dict"] = dataset_content.head(10).to_dict(orient="records")
                result["printed_output"] = f"Error occurred: {str(e)}"
                result["extraction_strategy"] = "Fallback strategy: showing first 10 rows due to error"
                result["explanation"] = f"Original extraction failed with error: {str(e)}"
    
    # If we've exhausted all attempts without success, use the last result
    if not success:
        print(f"Using best available result after {attempts} attempts")
        
        # Package the results
        if isinstance(execution_result, pd.DataFrame):
            result["results_dict"] = execution_result.to_dict(orient="records")
        else:
            result["results_dict"] = {"data": execution_result}
        
        result["printed_output"] = printed_output
        
        # Get the highest quality score from the validation history
        if result["validation_history"]:
            best_attempt = max(result["validation_history"], key=lambda x: x["answer_quality"])
            result["answer_quality"] = best_attempt["answer_quality"]
            result["answer_quality_reasoning"] = best_attempt["reasoning"]
    
    print("Extraction and answer quality validation completed")
    print(f"DEBUG PRINT EXTRACTED_DATA: {result}")
    
    return result
    