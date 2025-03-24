"""
Optimized script to test Pinecone search with 20 diverse queries.
This version connects to Pinecone once for all queries.

Usage:
    python test_pinecone_search.py
"""

import time
import os
import sys
import datetime

# Add the parent directory to sys.path so Python can find your Django project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Initialize Django
import django
django.setup()

from factchecker.search.pinecone_search import vector_search_datasets_pinecone
from factchecker.search.search_utils import generate_similar_queries, parallel_search, single_search

# List of 20 diverse queries to test
QUERIES = [
    "air quality in greenwich village",
    "electric vehicle adoption rates by state",
    "gun murder rates in the southwest since 2015",
    "climate change impact on coastal communities",
    "public school funding disparities",
    "healthcare access in rural areas",
    "renewable energy production by state",
    "income inequality trends 2010-2020",
    "opioid crisis statistics by county",
    "water quality in the great lakes",
    "affordable housing availability in major cities",
    "broadband internet access in underserved communities",
    "vaccination rates by demographic groups",
    "food deserts in urban areas",
    "public transportation usage trends",
    "small business growth after covid-19",
    "forest fire frequency and severity",
    "student loan debt distribution by age",
    "maternal mortality rates by state",
    "solar panel adoption in residential areas"
]

def run_pinecone_test(output_file="pinecone_search_results.txt"):
    """Run Pinecone search on all queries and save results to file"""
    
    print(f"Testing Pinecone search with {len(QUERIES)} queries...")
    
    # Create output file path
    if not os.path.isabs(output_file):
        output_file = os.path.join(settings.BASE_DIR, output_file)
    
    with open(output_file, 'w') as f:
        f.write(f"Pinecone Search Results\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*80}\n\n")
        
        # Process each query
        for i, query in enumerate(QUERIES, 1):
            print(f"\nTesting query {i}/{len(QUERIES)}: '{query}'")
            f.write(f"Query {i}: \"{query}\"\n")
            f.write(f"{'-'*80}\n\n")
            
            # Test 1: Without variations (single query)
            print(f"Testing without variations...")
            start_time = time.time()
            try:
                results_without = single_search(
                    query=query,
                    search_function=vector_search_datasets_pinecone,
                    similarity_threshold=0.35,
                    max_results=10,
                    verbose=True
                )
                
                search_time_without = time.time() - start_time
                
                f.write(f"WITHOUT VARIATIONS: {len(results_without)} results in {search_time_without:.4f} seconds\n\n")
                
                # Write top 5 results
                for j, result in enumerate(results_without[:5], 1):
                    f.write(f"  {j}. {result['title']}\n")
                    f.write(f"     Similarity: {result['similarity']:.4f}\n")
                    f.write(f"     ID: {result['id']}\n\n")
                
            except Exception as e:
                f.write(f"Error with single search: {e}\n\n")
                print(f"Error with query '{query}': {e}")
            
            f.write(f"\n{'-'*40}\n\n")
            
            # Test 2: With variations (parallel search)
            print(f"Testing with variations...")
            start_time = time.time()
            try:
                # First, generate and display the variations
                variations = generate_similar_queries(query, num_variations=5)
                f.write(f"QUERY VARIATIONS:\n")
                for v_idx, variation in enumerate(variations):
                    f.write(f"  {v_idx}. \"{variation}\"\n")
                f.write("\n")
                
                # Then run parallel search with variations
                results_with = parallel_search(
                    query=query,
                    search_function=vector_search_datasets_pinecone,
                    similarity_threshold=0.5,
                    max_results=10,
                    use_variations=True,
                    verbose=True
                )
                
                search_time_with = time.time() - start_time
                
                f.write(f"WITH VARIATIONS: {len(results_with)} results in {search_time_with:.4f} seconds\n\n")
                
                # Write top 5 results
                for j, result in enumerate(results_with[:5], 1):
                    f.write(f"  {j}. {result['title']}\n")
                    f.write(f"     Similarity: {result['similarity']:.4f}\n")
                    f.write(f"     ID: {result['id']}\n")
                    f.write(f"     From query: \"{result.get('query_variation', 'unknown')}\"\n\n")
                
                # Compare results
                without_ids = {r['id'] for r in results_without}
                with_ids = {r['id'] for r in results_with}
                
                unique_to_variations = with_ids - without_ids
                
                f.write(f"\nCOMPARISON:\n")
                f.write(f"  Results only in variations search: {len(unique_to_variations)}\n")
                if unique_to_variations:
                    f.write(f"  Unique datasets found with variations:\n")
                    for unique_id in unique_to_variations:
                        # Find the result with this ID
                        unique_result = next((r for r in results_with if r['id'] == unique_id), None)
                        if unique_result:
                            f.write(f"    - {unique_result['title']} (from: \"{unique_result.get('query_variation', 'unknown')}\")\n")
                
            except Exception as e:
                f.write(f"Error with parallel search: {e}\n\n")
                print(f"Error with query '{query}': {e}")
            
            f.write(f"\n{'='*80}\n\n")
        
        # Write summary
        f.write(f"SUMMARY\n")
        f.write(f"{'-'*80}\n\n")
        f.write(f"Total queries tested: {len(QUERIES)}\n")
        f.write(f"Each query was tested both with and without variations.\n")
        f.write(f"See individual query results for details on performance and result differences.\n")
    
    print(f"Pinecone search test completed!")
    print(f"Results saved to {output_file}")
    
    return output_file

if __name__ == "__main__":
    output_file = run_pinecone_test() 