"""
Functions for extracting relevant data from Census datasets.
"""

import json
import logging
import os
import re
import requests
import pandas as pd
from typing import Dict, List, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)

def recommend_census_variables(
    query: str,
    dataset: Any,
    available_variables: List[Dict[str, Any]],
    max_recommendations: int = 10
) -> Dict[str, str]:
    """
    Use LLM to recommend Census variables for a given query.
    
    Args:
        query: User's natural language query (e.g., "air quality in NYC")
        dataset: CensusDataset object with metadata
        available_variables: List of variable dictionaries with 'variable_name', 'label', etc.
        max_recommendations: Maximum number of variables to recommend
        
    Returns:
        Dictionary mapping variable IDs to explanations of why they're relevant
    """
    try:
        # Use our existing OpenAI client instead of a custom client
        from factchecker.utils.openai_client import chat_completion
        
        # Prepare prompt with context about the query and dataset
        prompt = f"""
        I need to find Census data variables that would be relevant to answering this query: "{query}"
        
        The Census dataset I'm using is: "{dataset.title}" from {dataset.vintage}
        Dataset description: {dataset.description or "No description available"}
        Dataset path: {dataset.dataset_path}
        API endpoint: {dataset.api_endpoint}
        
        The user is looking for data about {query}, and I need to identify which Census variables would 
        provide the most relevant information for this query.
        
        Here are all available variables in this dataset:
        """
        
        # Include ALL variables in the prompt - no sampling or truncating
        for i, var in enumerate(available_variables):
            var_name = var.get('variable_name', 'Unknown')
            label = var.get('label', 'No label')
            concept = var.get('concept', 'No concept')
            
            prompt += f"{i+1}. {var_name}: {label}\n   Concept: {concept}\n\n"
        
        # Add instructions
        prompt += f"""
        Based on the query "{query}", please identify the {max_recommendations} most relevant variables from this dataset.
        For each recommended variable, provide:
        1. The variable_name (e.g., CP03_2023_038E)
        2. A brief explanation of why it's relevant to the query
        
        For example, if the query is about "poverty rates in New York", you might recommend variables like:
        - CP03_2023_120E: Important because it shows the percentage of families below poverty level
        - CP03_2023_122E: Important because it provides data on individuals below poverty level by age group
        
        Your response should be formatted as a JSON object with variable IDs as keys and explanations as values.
        Example:
        {{
          "CP03_2023_120E": "This variable shows the percentage of families with income below poverty level, directly relevant to measuring poverty rates.",
          "CP03_2023_122E": "This variable breaks down poverty by age groups, providing more detailed poverty demographics."
        }}
        
        Only include variables that are DIRECTLY relevant to answering the query. Focus on quality over quantity.
        """
        
        # Set a system message that helps generate structured output
        system_message = """You are a data specialist selecting the most relevant Census variables for a user query.
        Your response must be valid JSON with variable IDs as keys and explanations as values."""
        
        # Before calling the LLM
        logger.info(f"Calling LLM to recommend Census variables for query: '{query}' on dataset {dataset.title}")
        logger.info(f"Available variables count: {len(available_variables)}")
        
        # Call OpenAI API using our existing utility
        response_text = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.2,
            max_tokens=1500,
            model_name="gpt-4o"  # Use GPT-4o for best accuracy
        )
        
        # Parse response (assuming JSON format)
        try:
            # Extract JSON portion if there's surrounding text
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text
                
            # Parse JSON
            recommended_variables = json.loads(json_str)
            
            # Validate response format
            if not isinstance(recommended_variables, dict):
                logger.warning(f"LLM did not return a dictionary: {recommended_variables}")
                recommended_variables = {}
                
            # Filter out any variables that don't exist in our dataset
            valid_var_names = {var['variable_name'] for var in available_variables}
            valid_recommendations = {
                var_name: explanation
                for var_name, explanation in recommended_variables.items()
                if var_name in valid_var_names
            }
            
            # Log the recommendations
            if valid_recommendations:
                logger.info(f"LLM recommended {len(valid_recommendations)} Census variables: {list(valid_recommendations.keys())}")
                for var_name, explanation in valid_recommendations.items():
                    logger.info(f"  - {var_name}: {explanation[:100]}..." if len(explanation) > 100 else f"  - {var_name}: {explanation}")
            else:
                logger.warning(f"No valid Census variables were recommended by the LLM for query: '{query}'")
            
            return valid_recommendations
            
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            logger.error(f"Error parsing LLM response: {e}")
            logger.error(f"Raw response: {response_text}")
            return {}
            
    except Exception as e:
        logger.error(f"Error recommending Census variables: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

def fetch_census_data(
    api_endpoint: str,
    variables: List[str],
    geo_level: str,
    output_dir: str,
    filename: str,
    location: Optional[str] = None,
    vintage: Optional[int] = None,
    dataset_path: Optional[str] = None
) -> Optional[str]:
    """
    Fetch data from Census API using the recommended variables and save directly to JSON.
    """
    try:
        # Normalize the API endpoint (remove trailing slash if present)
        if api_endpoint.endswith('/'):
            api_endpoint = api_endpoint[:-1]
        
        # Use only the variables passed in, don't add NAME automatically
        get_clause = ','.join(variables) if variables else ''
        
        if not get_clause:
            logger.warning("No variables specified for API call")
            return None
        
        # Build the 'for' part of the URL based on geography level
        # Default to national level if geo_level is None
        if not geo_level:
            logger.info("No geo_level specified, defaulting to national level")
            for_clause = "us:*"  # National level
        elif geo_level.lower() == 'national':
            # For national level, use 'us' as the geography level
            for_clause = "us:*"
        elif geo_level.lower() == 'state':
            # For state level, need to convert state name to FIPS code if provided
            if location and location.lower() != 'united states' and location != '*':
                # Try to get state FIPS code from database
                from factchecker.models import CensusFIPSCode
                try:
                    fips_obj = CensusFIPSCode.objects.get(geo_type='state', name__iexact=location)
                    for_clause = f"state:{fips_obj.fips_code}"
                except CensusFIPSCode.DoesNotExist:
                    # Fallback to wildcard if state not found
                    logger.warning(f"State '{location}' not found in FIPS database, using wildcard")
                    for_clause = "state:*"
            else:
                # Get all states
                for_clause = "state:*"
        elif geo_level.lower() == 'county':
            # For county level, need state and county FIPS codes
            if location and ',' in location:
                # Format expected: "County Name, State Name"
                county_name, state_name = [part.strip() for part in location.split(',', 1)]
                
                # Try to get state and county FIPS codes from database
                from factchecker.models import CensusFIPSCode
                try:
                    state_fips = CensusFIPSCode.objects.get(geo_type='state', name__iexact=state_name)
                    county_fips = CensusFIPSCode.objects.get(
                        geo_type='county', 
                        name__iexact=county_name,
                        parent_geo_type='state',
                        parent_fips_code=state_fips.fips_code
                    )
                    for_clause = f"county:{county_fips.fips_code}&in=state:{state_fips.fips_code}"
                except CensusFIPSCode.DoesNotExist:
                    # Fallback to all counties in all states
                    logger.warning(f"County '{location}' not found in FIPS database, using wildcard")
                    for_clause = "county:*"
            else:
                # Get all counties
                for_clause = "county:*"
        else:
            # For other geography levels, use the standard format
            location_value = location if location else '*'
            for_clause = f"{geo_level}:{location_value}"
        
        # Log when we start handling variables
        logger.info(f"Census API: Processing {len(variables)} variables for geo_level={geo_level}, location={location}")
        
        # After building get_clause
        if get_clause:
            logger.info(f"Census API: Using variables in get clause: {get_clause}")
        else:
            logger.warning("Census API: No variables specified for API call - this may result in an invalid request")
        
        # After building for_clause
        logger.info(f"Census API: Geography clause constructed as: for={for_clause}")
        
        # Build the complete URL with JSON format
        url = f"{api_endpoint}?get={get_clause}&for={for_clause}"
        
        # Add any additional predicates needed
        if vintage:
            url += f"&year={vintage}"
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Set the output path
        output_path = os.path.join(output_dir, filename)
        
        # Now we can reference output_path in the log
        logger.info(f"Census API: Making request with URL: {url}")
        logger.info(f"Census API: Will save downloaded data to {output_path}")
        
        # Make the API request and download the file
        from factchecker.download.download_gov_data import download_file
        
        # Download with a reasonable timeout
        success = download_file(url, output_path, max_download_time=120)
        
        if success:
            logger.info(f"Census API: Successfully downloaded JSON data to {output_path}")
            try:
                # Log info about the JSON file
                file_size = os.path.getsize(output_path)
                logger.info(f"Census API: Downloaded JSON file size: {file_size} bytes")
                
                # Optionally check and log the structure
                with open(output_path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Census API: JSON data contains {len(data)} records")
                    if len(data) > 0:
                        logger.info(f"Census API: Headers: {data[0]}")
                        logger.info(f"Census API: First record: {data[1] if len(data) > 1 else 'No data records'}")
            except Exception as e:
                logger.warning(f"Census API: Could not analyze downloaded JSON file: {str(e)}")
            
            return output_path
        else:
            logger.error(f"Census API: Failed to download data from {url}")
            return None
        
    except Exception as e:
        logger.error(f"Error fetching Census data: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None