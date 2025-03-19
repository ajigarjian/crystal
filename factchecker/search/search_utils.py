"""
Utility functions for search operations across the factchecker app.

This module provides helper functions used by both vector search and keyword search,
including resource checking and query expansion.
"""

import requests
import json
import concurrent.futures
from typing import Dict, List, Tuple, Callable, Any
from django.conf import settings
from factchecker.utils.openai_client import chat_completion

def get_usable_resources(dataset_id: str, verbose: bool = False) -> List[Dict]:
    """
    Get a list of usable resources for a dataset by making an API call to data.gov.
    
    Args:
        dataset_id: The dataset ID to check
        verbose: Whether to print detailed logging information
        
    Returns:
        List of resource dictionaries with url, format, and name
    """
    try:
        # Get API key from settings
        api_key = settings.DATA_GOV_API_KEY
        
        if not api_key:
            if verbose:
                print("DATA_GOV_API_KEY not found in settings")
            return []
        
        # Make API call to data.gov
        base_url = "https://catalog.data.gov/api/3"
        headers = {"Authorization": api_key}
        
        # Simple retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{base_url}/action/package_show?id={dataset_id}", 
                    headers=headers
                )
                
                # Check for rate limiting or other errors
                if response.status_code == 403:
                    print(f"Rate limited by Data.gov API (403 Forbidden). Attempt {attempt+1}/{max_retries}")
                    if attempt < max_retries - 1:
                        # Simple backoff: wait longer with each retry
                        wait_time = 2 * (attempt + 1)  # 2, 4, 6 seconds
                        print(f"Waiting {wait_time} seconds before retrying...")
                        import time
                        time.sleep(wait_time)
                        continue
                    else:
                        print("Maximum retry attempts reached for Data.gov API.")
                        return []
                
                # For other error codes, raise the exception
                response.raise_for_status()
                
                # If we get here, the request was successful
                data = response.json()
                break
                
            except requests.exceptions.RequestException as e:
                if verbose:
                    print(f"Error on attempt {attempt+1}: {e}")
                if attempt == max_retries - 1:
                    raise  # Re-raise on last attempt
                # Simple backoff for other exceptions too
                import time
                time.sleep(2 * (attempt + 1))
        
        if "result" not in data or "resources" not in data["result"]:
            return []
        
        # Filter resources to only include usable formats
        filtered_resources = []
        for resource in data["result"]["resources"]:
            # Check format field
            format_field = resource.get("format", "").lower() if resource.get("format") else ""
            
            # Check URL ending
            url = resource.get("url", "")
            url_format = ""
            if url and isinstance(url, str):
                # Extract file extension from URL
                if "." in url.split("/")[-1]:
                    url_format = url.split(".")[-1].lower()
                    # Remove any query parameters
                    if "?" in url_format:
                        url_format = url_format.split("?")[0]
            
            # Determine the effective format
            effective_format = format_field if format_field else url_format
            
            # Check if it's a format we can use
            if effective_format in ["csv", "json", "xlsx", "xls", "pdf", "xml"]:
                filtered_resources.append({
                    "url": url,
                    "format": effective_format,
                    "name": resource.get("name", "Unnamed Resource")
                })
        
        return filtered_resources
        
    except Exception as e:
        if verbose:
            print(f"Error getting resources for dataset {dataset_id}: {e}")
        return []

def generate_similar_queries(original_query: str, num_variations: int = 5) -> List[str]:
    """
    Generate similar queries to the original query using LLM.
    
    Args:
        original_query: The original search query
        num_variations: Number of variations to generate (default: 2)
        
    Returns:
        List of queries including the original plus variations
    """
    try:
        # Prepare the prompt for the LLM
        prompt = f"""You are looking for datasets on the web. Generate {num_variations} simple similar search queries for locating related datasets. Format the response as a JSON array of strings.

Original query: "{original_query}"

EXAMPLES:
User Query 1: Real estate prices in San Francisco since 2020

Example response format:
["San Franscio housing prices", "real estate San Francisco", "California Pandemic Home Pricing", "SF real estate"]

User Query 2: vaccination rates by demographic groups

Example response format:
["Immunizations", "vaccines", "immunized"]

User Query 3: how has the high school graduation rate in Philadelphia changed over time?

Example response format:
["Philly schools", "Philadelphia schools", "School performance PA", "School performance Philadelphia", "High Schools PA"]

Your response (JSON array only):"""

        # Call the LLM using the correct function name
        response = chat_completion(
            prompt=prompt,
            system_message="You are a helpful assistant that generates dataset search queries.",
            temperature=0.7,
            max_tokens=150
        )
        
        # Parse the response
        try:
            # Try to parse as JSON
            variations = json.loads(response)
            if not isinstance(variations, list):
                variations = [str(variations)]
        except:
            # If not valid JSON, try to extract from text
            import re
            matches = re.findall(r'"([^"]+)"', response)
            variations = matches if matches else [response]
        
        # Ensure we have the right number of variations
        variations = variations[:num_variations]
        
        # Add the original query and return
        all_queries = [original_query] + variations
        
        # No need to print here, we'll handle it in parallel_search
        
        return all_queries
        
    except Exception as e:
        print(f"Error generating similar queries: {e}")
        # Return just the original query if there's an error
        return [original_query]

def parallel_search(query: str, search_function: Callable, similarity_threshold: float = 0.3, 
                   max_results: int = 10, use_variations: bool = True, verbose: bool = False) -> List[Dict]:
    """
    Perform parallel searches with the original query and variations.
    
    Args:
        query: The original search query
        search_function: Function to use for searching (e.g., vector_search_datasets)
        similarity_threshold: Minimum similarity score (0-1)
        max_results: Maximum number of results to return per query
        use_variations: Whether to generate and use query variations
        verbose: Whether to print detailed logging information
        
    Returns:
        Combined and deduplicated list of search results
    """
    # Generate query variations if requested
    queries = generate_similar_queries(query) if use_variations else [query]
    
    # Print a simple message about the variations
    print(f"Searching with {len(queries)} variations: {', '.join([f'"{q}"' for q in queries])}")
    
    # Prepare for parallel execution
    all_results = []
    seen_ids = set()
    results_by_query = {}
    
    # Define worker function
    def search_worker(search_query):
        try:
            # Use the global searcher for all queries
            results = search_function(
                search_query, 
                similarity_threshold=similarity_threshold,
                max_results=max_results,
                verbose=False  # Suppress verbose output from search function
            )
            
            # Add the query variation to each result
            for result in results:
                result['query_variation'] = search_query
                
            # Store results count by query for reporting
            results_by_query[search_query] = len(results)
            
            return results
        except Exception as e:
            print(f"Error searching with query '{search_query}': {e}")
            results_by_query[search_query] = 0
            return []
    
    # Execute searches in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries)) as executor:
        future_to_query = {executor.submit(search_worker, q): q for q in queries}
        
        for future in concurrent.futures.as_completed(future_to_query):
            query_variation = future_to_query[future]
            try:
                results = future.result()
                all_results.extend(results)
            except Exception as e:
                print(f"Error processing results for query '{query_variation}': {e}")
    
    # Deduplicate results
    deduplicated_results = []
    for result in all_results:
        dataset_id = result['id']
        if dataset_id not in seen_ids:
            deduplicated_results.append(result)
            seen_ids.add(dataset_id)
    
    # Sort by similarity score
    deduplicated_results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
    
    # Limit to max_results * 2
    final_results = deduplicated_results[:int(max_results * 2)]

    # Print a simple summary
    print(f"Search results by variation:")
    for q, count in results_by_query.items():
        print(f"  • \"{q}\": {count} results")
    print(f"Found {len(all_results)} total results, {len(deduplicated_results)} unique results")
    print(f"Returning top {len(final_results)} results after deduplication")
    
    return final_results

def single_search(query: str, search_function: Callable, similarity_threshold: float = 0.3, 
                  max_results: int = 10, verbose: bool = False) -> List[Dict]:
    """
    Perform a search with only the original query (no variations).
    
    Args:
        query: The search query
        search_function: Function to use for searching (e.g., vector_search_datasets)
        similarity_threshold: Minimum similarity score (0-1)
        max_results: Maximum number of results to return
        verbose: Whether to print detailed logging information
        
    Returns:
        List of search results
    """
    try:
        # Use the provided search function
        results = search_function(
            query, 
            similarity_threshold=similarity_threshold,
            max_results=max_results,
            verbose=verbose
        )
        
        # Add the query to each result for consistency with parallel_search
        for result in results:
            result['query_variation'] = query
        
        if verbose:
            print(f"Found {len(results)} results for query: \"{query}\"")
        
        return results
    except Exception as e:
        print(f"Error searching with query '{query}': {e}")
        return []
