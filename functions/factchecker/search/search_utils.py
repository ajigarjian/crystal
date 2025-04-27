"""
Utility functions for search operations across the factchecker app.

This module provides helper functions used by both vector search and keyword search,
including resource checking and query expansion.
"""

import requests
import json
import concurrent.futures
import time  # Add time import
import logging  # Add logging import
from typing import Dict, List, Tuple, Callable, Any
from factchecker.utils.openai_client import chat_completion
import os

# Add logger
logger = logging.getLogger(__name__)


def generate_similar_queries(original_query: str, num_variations: int = 5) -> List[str]:
    """
    Generate similar queries to the original query using LLM.
    Also creates a shortened version of long or specific queries.
    
    Args:
        original_query: The original search query
        num_variations: Number of variations to generate (default: 5)
        
    Returns:
        List of queries including the original plus variations
    """
    try:
        # Prepare the prompt for the LLM
        prompt = f"""You are looking for datasets on the web. Generate {num_variations} simple similar search queries for locating related datasets. 

Additionally, if the original query is long or very specific, include a shortened, more general version.
For example:
- "Rodent population on the east coast over the past 5 years" → "rodents"
- "Average household income in rural counties of Texas 2010-2020" → "Texas income"
- "COVID-19 vaccination rates by demographic groups in California" → "vaccination demographics"

Format the response as a JSON array of strings.

Original query: "{original_query}"

EXAMPLES:
User Query 1: Real estate prices in San Francisco since 2020

Example response format:
["San Francisco housing prices", "real estate San Francisco", "California Pandemic Home Pricing", "SF real estate", "housing market"]

User Query 2: vaccination rates by demographic groups

Example response format:
["Immunizations", "vaccines", "immunized", "vaccination demographics", "vaccine uptake"]

User Query 3: how has the high school graduation rate in Philadelphia changed over time?

Example response format:
["Philly schools", "Philadelphia schools", "School performance PA", "School performance Philadelphia", "graduation rates"]

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

def parallel_search(query: str, search_function: Callable, start_time: float, similarity_threshold: float = 0.3, 
                   max_results: int = 10, use_variations: bool = True, verbose: bool = False, 
                   stream_results: bool = False, pinecone_client=None) -> List[Dict]:
    """
    Perform parallel searches with the original query and variations.
    
    Args:
        query: The original search query
        search_function: Function to use for searching (e.g., vector_search_datasets)
        start_time: The start time of the overall operation for relative timestamps
        similarity_threshold: Minimum similarity score (0-1)
        max_results: Maximum number of results to return per query
        use_variations: Whether to generate and use query variations
        verbose: Whether to print detailed logging information
        stream_results: If True, generate variations sequentially and yield results as they become available
        pinecone_client: Pre-initialized Pinecone client to use for searches
        
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
    def search_worker(search_query, worker_start_time):
        try:
            # Log start of individual search
            logger.info(f'Starting search for variation "{search_query}" at timestamp: {time.time() - worker_start_time:.2f} seconds')
            
            # Use the provided Pinecone client or get a new one
            if pinecone_client:
                results = search_function(
                    search_query, 
                    start_time=worker_start_time,
                    similarity_threshold=similarity_threshold,
                    max_results=max_results,
                    verbose=False,  # Suppress verbose output from search function
                    pinecone_client=pinecone_client  # Pass the pre-initialized client
                )
            else:
                results = search_function(
                    search_query, 
                    start_time=worker_start_time,
                    similarity_threshold=similarity_threshold,
                    max_results=max_results,
                    verbose=False
                )
            
            # Log end of individual search
            logger.info(f'Completed search for variation "{search_query}" at timestamp: {time.time() - worker_start_time:.2f} seconds')
            
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
    
    if stream_results:
        # Sequential/Streaming approach: generate one variation, start its search, and while that search runs, generate the next variation.
        # This allows us to yield results as soon as they are available from each search.
        for search_query in queries:
            # Start search for the current variation
            results = search_worker(search_query, start_time)
            # Yield results immediately for this variation
            for result in results:
                dataset_id = result['id']
                if dataset_id not in seen_ids:
                    seen_ids.add(dataset_id)
                    all_results.append(result)
                    yield result
    else:
        # Original parallel approach: generate all variations upfront and run searches in parallel
        # Limit max_workers to avoid resource contention
        max_workers_limit = 4
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries), max_workers_limit)) as executor:
            # Pass start_time to the worker
            future_to_query = {executor.submit(search_worker, q, start_time): q for q in queries}
            
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
    
    # Limit to max_results
    final_results = deduplicated_results[:max_results]

    # Print a simple summary
    print(f"Search results by variation:")
    for q, count in results_by_query.items():
        print(f"  • \"{q}\": {count} results")
    print(f"Found {len(all_results)} total results, {len(deduplicated_results)} unique results")
    print(f"Returning top {len(final_results)} results after deduplication")
    
    if not stream_results:
        return final_results
    else:
        # For streaming, we've already yielded individual results, so return the final list
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
