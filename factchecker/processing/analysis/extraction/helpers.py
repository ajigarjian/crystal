# Helper functions for Data Extracter

def check_execute_code_response(response, printed_output):
    """
    Checks the response of execute_code() to ensure it contains data.
    Returns None if there is a response.

    Params: response: Dict: Response from execute_code()
            printed_output: str: Printed output from execute_code()
    """

    empty_response = {
        "result": "empty",
        "result_prompt": "The code returned an empty response. Try again."
    }

    if response is None:
        return empty_response
    
    # Check if response is an empty dictionary
    if isinstance(response, dict) and not response:
        return empty_response
    
    # Check if response is an empty DataFrame
    try:
        import pandas as pd
        if isinstance(response, pd.DataFrame) and response.empty:
            return empty_response
    except ImportError:
        pass  # pandas not available, skip DataFrame check
    
    # Check for other empty containers (list, tuple, set)
    if hasattr(response, '__len__') and len(response) == 0:
        return empty_response
    
    # If there's a printed output, let's pass it along to the LLM.
    if printed_output and "No" not in printed_output:
        return None
    # If we get here, the response has content
    return None
