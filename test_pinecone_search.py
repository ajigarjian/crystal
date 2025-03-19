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

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crystalproject.settings')

# Initialize Django
import django
django.setup()

from django.conf import settings
from factchecker.search.pinecone_search import vector_search_datasets_pinecone

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
    
    # We'll skip the searcher initialization and just measure the first query's connection time
    print("Running first query to initialize Pinecone connection...")
    load_start = time.time()
    first_results = vector_search_datasets_pinecone(QUERIES[0], similarity_threshold=0.5, top_k=10, verbose=False)
    load_time = time.time() - load_start
    print(f"First query completed in {load_time:.4f} seconds (includes connection time)")
    
    with open(output_file, 'w') as f:
        f.write(f"Pinecone Search Results\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"First query (with connection) completed in {load_time:.4f} seconds\n")
        f.write(f"{'='*80}\n\n")
        
        # Write results for the first query
        f.write(f"Query 1: \"{QUERIES[0]}\"\n")
        f.write(f"{'-'*80}\n\n")
        f.write(f"Pinecone search: {len(first_results)} results in {load_time:.4f} seconds\n\n")
        
        # Write top 5 results for first query
        for j, result in enumerate(first_results[:5], 1):
            f.write(f"  {j}. {result['title']}\n")
            f.write(f"     Similarity: {result['similarity']:.4f}\n")
            f.write(f"     ID: {result['id']}\n\n")
        
        f.write(f"\n{'='*80}\n\n")
        
        # Track overall stats (starting from the second query)
        total_time = 0
        total_results = len(first_results)
        
        # Process remaining queries
        for i, query in enumerate(QUERIES[1:], 2):
            print(f"Testing query {i}/{len(QUERIES)}: '{query}'")
            
            f.write(f"Query {i}: \"{query}\"\n")
            f.write(f"{'-'*80}\n\n")
            
            # Test Pinecone implementation
            start_time = time.time()
            try:
                results = vector_search_datasets_pinecone(
                    query, 
                    similarity_threshold=0.5, 
                    top_k=10, 
                    verbose=False
                )
                
                search_time = time.time() - start_time
                total_time += search_time
                total_results += len(results)
                
                f.write(f"Pinecone search: {len(results)} results in {search_time:.4f} seconds\n\n")
                
                # Write top 5 results
                for j, result in enumerate(results[:5], 1):
                    f.write(f"  {j}. {result['title']}\n")
                    f.write(f"     Similarity: {result['similarity']:.4f}\n")
                    f.write(f"     ID: {result['id']}\n\n")
                
            except Exception as e:
                f.write(f"Error with Pinecone search: {e}\n\n")
                print(f"Error with query '{query}': {e}")
            
            f.write(f"\n{'='*80}\n\n")
        
        # Calculate average time excluding the first query (which includes connection time)
        avg_time = total_time / (len(QUERIES) - 1) if len(QUERIES) > 1 else 0
        
        # Write summary
        f.write(f"SUMMARY\n")
        f.write(f"{'-'*80}\n\n")
        f.write(f"Total queries: {len(QUERIES)}\n")
        f.write(f"Total results: {total_results}\n")
        f.write(f"Average results per query: {total_results/len(QUERIES):.1f}\n")
        f.write(f"First query time (includes connection): {load_time:.4f} seconds\n")
        f.write(f"Total search time (excluding first query): {total_time:.4f} seconds\n")
        f.write(f"Average time per query (excluding first query): {avg_time:.4f} seconds\n")
    
    print(f"Pinecone search test completed!")
    print(f"Results saved to {output_file}")
    print(f"First query time (includes connection): {load_time:.4f} seconds")
    print(f"Average time per query (excluding first query): {avg_time:.4f} seconds")
    
    return output_file

if __name__ == "__main__":
    output_file = run_pinecone_test() 