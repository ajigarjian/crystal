#!/usr/bin/env python3
"""
Test script for the parallel web search functionality in stream_analyze.py
"""

import sys
import os
import json
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add parent directory to path to ensure imports work
sys.path.append('/Users/cedricfitzgerald/Documents/Startup/crystal')

from functions.factchecker.search.search_utils import generate_similar_queries
from functions.factchecker.search.web_search import enhanced_web_search
import concurrent.futures

def test_parallel_web_search():
    """
    Test the parallel web search functionality
    """
    # Example query
    query = "Rodent population in New York City neighborhoods"
    
    print(f"Original query: {query}")
    
    # Step 1: Generate similar queries
    similar_queries = generate_similar_queries(query, num_variations=3)
    print(f"Generated similar queries: {similar_queries}")
    
    # Step 2: Define search worker function
    def search_worker(search_query):
        try:
            print(f"Executing search for query variation: '{search_query}'")
            return {
                "query": search_query,
                "results": enhanced_web_search(
                    query=search_query,
                    max_results=3,
                    search_type="comprehensive"
                )
            }
        except Exception as e:
            print(f"Error in web search for query '{search_query}': {str(e)}")
            return {
                "query": search_query,
                "error": str(e),
                "results": []
            }
    
    all_search_results = []
    
    # Step 3: Execute searches in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(similar_queries)) as executor:
        # Submit all search tasks
        future_to_query = {executor.submit(search_worker, q): q for q in similar_queries}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_query):
            query_variation = future_to_query[future]
            try:
                result = future.result()
                all_search_results.append(result)
                print(f"Completed search for variation: {query_variation}")
            except Exception as e:
                print(f"Error processing results for query '{query_variation}': {e}")
    
    # Step 4: Process and combine the search results
    combined_results = []
    for result in all_search_results:
        if "results" in result and isinstance(result["results"], dict) and "results" in result["results"]:
            combined_results.extend(result["results"]["results"])
        elif "results" in result and isinstance(result["results"], list):
            combined_results.extend(result["results"])
    
    # Step 5: Remove duplicates and sort
    unique_urls = set()
    unique_results = []
    for result in combined_results:
        url = result.get("url")
        if url and url not in unique_urls:
            unique_urls.add(url)
            unique_results.append(result)
    
    # Step 6: Print summary
    print(f"\nSearch Results Summary:")
    print(f"Total unique results: {len(unique_results)}")
    
    # Print top 5 results
    for i, result in enumerate(unique_results[:5]):
        print(f"{i+1}. {result.get('title', 'No Title')} - {result.get('url', 'No URL')}")
    
    # Save results to file
    with open("parallel_search_results.json", "w") as f:
        json.dump({
            "query": query,
            "similar_queries": similar_queries,
            "results": unique_results[:10]  # Save top 10 results
        }, f, indent=2)
    
    print("\nResults saved to parallel_search_results.json")

if __name__ == "__main__":
    test_parallel_web_search()