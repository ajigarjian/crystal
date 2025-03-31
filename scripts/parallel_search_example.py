#!/usr/bin/env python3
"""
Example script to demonstrate generating similar queries and performing 
parallel web searches using ThreadPoolExecutor.
"""

import sys
import json
import concurrent.futures
from typing import List, Dict, Any

# Add parent directory to path to ensure imports work
sys.path.append('/Users/cedricfitzgerald/Documents/Startup/crystal')

from functions.factchecker.search.search_utils import generate_similar_queries
from functions.factchecker.search.web_search import tavily_web_search

def search_worker(query: str) -> Dict[str, Any]:
    """
    Worker function to perform a search with a specific query
    
    Args:
        query: The search query to use
        
    Returns:
        Dictionary containing search results and metadata
    """
    print(f"Searching for: {query}")
    try:
        results = tavily_web_search(query)
        return {
            "query": query,
            "results": results
        }
    except Exception as e:
        print(f"Error searching for '{query}': {e}")
        return {
            "query": query,
            "error": str(e),
            "results": []
        }

def parallel_query_search(original_query: str, num_variations: int = 3) -> List[Dict[str, Any]]:
    """
    Generate similar queries and search them in parallel
    
    Args:
        original_query: The original search query
        num_variations: Number of query variations to generate
        
    Returns:
        List of dictionaries containing search results for each query
    """
    # Generate similar queries
    queries = generate_similar_queries(original_query, num_variations=num_variations)
    print(f"Generated queries: {json.dumps(queries, indent=2)}")
    
    all_results = []
    
    # Execute searches in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries)) as executor:
        # Map queries to futures
        future_to_query = {executor.submit(search_worker, q): q for q in queries}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_query):
            query = future_to_query[future]
            try:
                result = future.result()
                all_results.append(result)
                print(f"Completed search for: {query}")
            except Exception as e:
                print(f"Error processing results for query '{query}': {e}")
    
    return all_results

if __name__ == "__main__":
    # Example usage
    original_query = "Rodent population in New York City neighborhoods"
    
    print(f"Original query: {original_query}")
    results = parallel_query_search(original_query)
    
    # Print summary of results
    print("\nSearch Results Summary:")
    for i, result in enumerate(results):
        query = result["query"]
        num_results = len(result.get("results", []))
        print(f"{i+1}. Query: {query}")
        print(f"   Found {num_results} results")
    
    # Save results to file
    with open("parallel_search_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print("\nResults saved to parallel_search_results.json")