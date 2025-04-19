import json
import logging
from typing import Dict, List, Any, Optional

from factchecker.utils.openai_client import chat_completion

logger = logging.getLogger(__name__)

def evaluate_query(query: str) -> Dict[str, Any]:
    """
    Evaluates a search query and returns quality assessment and suggestions.
    
    Args:
        query: The user's current query string
        
    Returns:
        Dictionary with quality assessment and suggestions
    """
    # For very short queries, return early with a basic response
    if not query or len(query.strip()) < 3:
        return {
            "quality": "typing",
            "rating": 0,
            "message": "Keep typing your query...",
            "suggestions": []
        }
    
    try:
        # Construct prompt for query evaluation
        prompt = f"""
        Evaluate the following search query that will be used to find government datasets. Rate the query quality as one of:
        - "poor" (1): Very generic, likely to return too many irrelevant results
        - "basic" (2): General topic but lacks specificity
        - "good" (3): Clear topic with good specificity

        Query: "{query}"

        If the query is not "good", create exactly THREE improved versions of the query that would be more effective for finding datasets, focusing on these three enhancement types:

        1. SPECIFICITY: Add more precise details about the subject matter or type of data needed
        2. GEOGRAPHIC SCOPE: Specify a relevant geographic area (national, state, city, county, region)
        3. TIME PERIOD: Add a relevant time frame or date range

        Make sure each suggested query focuses on enhancing the ORIGINAL query in exactly ONE of these three dimensions.

        Format your response as a JSON object with this structure:
        {{
            "quality": "poor|basic|good",
            "rating": 1-3,
            "message": "<brief explanation of the rating>",
            "suggestions": [
                {{
                    "category": "SPECIFICITY",
                    "query": "<improved query with more specific details>"
                }},
                {{
                    "category": "GEOGRAPHIC SCOPE",
                    "query": "<improved query with geographic information>"
                }},
                {{
                    "category": "TIME PERIOD",
                    "query": "<improved query with time period>"
                }}
            ]
        }}
        """
        
        # Add JSON response format parameter
        response_format = {"type": "json_object"}
        
        # Call the OpenAI model to evaluate the query
        completion_response = chat_completion(
            prompt=prompt,
            system_message="You are an AI assistant that evaluates search queries for government datasets and suggests improvements. Respond with only a valid JSON object.",
            temperature=0.0,
            max_tokens=500,
            response_format=response_format,
            model_name="gpt-4.1-nano"
        )
        
        # Parse the JSON response
        try:
            result = json.loads(completion_response)
            
            # Validate response structure
            required_keys = ["quality", "rating", "message", "suggestions"]
            for key in required_keys:
                if key not in result:
                    if key == "suggestions":
                        result[key] = []
                    elif key == "rating":
                        result[key] = 1  # Default to lowest rating
                    else:
                        result[key] = ""
            
            # Ensure rating is an integer between 1-3
            if not isinstance(result["rating"], int) or result["rating"] < 1 or result["rating"] > 3:
                # Try to convert string representations of integers
                try:
                    result["rating"] = int(result["rating"])
                except (ValueError, TypeError):
                    # Map quality to rating if conversion fails
                    quality_to_rating = {
                        "poor": 1,
                        "basic": 2,
                        "good": 3
                    }
                    result["rating"] = quality_to_rating.get(result["quality"], 1)
            
            # Ensure suggestions is a list with at most 3 items and extract just the query strings for compatibility
            if not isinstance(result["suggestions"], list):
                result["suggestions"] = []
            
            # For backward compatibility, transform the structured suggestions to simple strings
            # but keep the category information in the objects
            if result["suggestions"] and isinstance(result["suggestions"][0], dict):
                categorized_suggestions = result["suggestions"][:3]
                simple_suggestions = []
                
                # Ensure we have one suggestion for each category
                categories = {"SPECIFICITY", "GEOGRAPHIC SCOPE", "TIME PERIOD"}
                suggestion_by_category = {}
                
                # First, process the suggestions we have
                for sugg in categorized_suggestions:
                    if "category" in sugg and "query" in sugg:
                        cat = sugg["category"].upper()
                        # Normalize category names
                        if "SPECIFIC" in cat:
                            cat = "SPECIFICITY"
                        elif "GEO" in cat or "LOCATION" in cat or "REGION" in cat:
                            cat = "GEOGRAPHIC SCOPE"
                        elif "TIME" in cat or "DATE" in cat or "PERIOD" in cat:
                            cat = "TIME PERIOD"
                        
                        if cat in categories:
                            suggestion_by_category[cat] = sugg["query"]
                            simple_suggestions.append(sugg["query"])
                
                # Fill in any missing categories with default suggestions
                for cat in categories:
                    if cat not in suggestion_by_category:
                        if cat == "SPECIFICITY":
                            modified_query = f"{query} specific dataset indicators"
                        elif cat == "GEOGRAPHIC SCOPE":
                            modified_query = f"{query} by state"
                        else:  # TIME PERIOD
                            modified_query = f"{query} 2020-2023"
                        
                        simple_suggestions.append(modified_query)
                
                # Update result with categorized suggestions
                result["suggestions"] = simple_suggestions
                result["categorized_suggestions"] = [
                    {"category": "SPECIFICITY", "query": next((q for i, q in enumerate(simple_suggestions) if i == 0), "")},
                    {"category": "GEOGRAPHIC SCOPE", "query": next((q for i, q in enumerate(simple_suggestions) if i == 1), "")},
                    {"category": "TIME PERIOD", "query": next((q for i, q in enumerate(simple_suggestions) if i == 2), "")}
                ]
            
            # Log the evaluation result
            logger.info(f"Query evaluation: {result['quality']} ({result['rating']}) for query: '{query}'")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {completion_response}")
            logger.error(f"Error: {str(e)}")
            # Return a basic response
            return {
                "quality": "error",
                "rating": 0,
                "message": "Unable to evaluate query",
                "suggestions": []
            }
        
    except Exception as e:
        logger.error(f"Error evaluating query: {str(e)}")
        return {
            "quality": "error",
            "rating": 0,
            "message": "Unable to evaluate query at this time",
            "suggestions": []
        }

def get_suggestions_for_query(query: str) -> List[str]:
    """
    Gets a list of suggested improved queries for the given input query.
    
    Args:
        query: The user's current query string
        
    Returns:
        List of suggested queries
    """
    evaluation = evaluate_query(query)
    return evaluation.get("suggestions", [])
