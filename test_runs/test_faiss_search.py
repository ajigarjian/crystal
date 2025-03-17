"""
Optimized script to test FAISS search with 20 diverse queries.
This version loads the FAISS index only once for all queries.

Usage:
    python test_faiss_optimized.py
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
from factchecker.search.faiss_search import FAISSSearcher

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

def run_faiss_test(output_file="faiss_search_results.txt"):
    """Run FAISS search on all queries and save results to file"""
    
    print(f"Testing FAISS search with {len(QUERIES)} queries...")
    
    # Create output file path
    if not os.path.isabs(output_file):
        output_file = os.path.join(settings.BASE_DIR, output_file)
    
    # Load FAISS index once for all queries
    print("Loading FAISS index (one time)...")
    load_start = time.time()
    searcher = FAISSSearcher()
    load_time = time.time() - load_start
    print(f"FAISS index loaded in {load_time:.4f} seconds with {len(searcher.dataset_ids)} entries")
    
    with open(output_file, 'w') as f:
        f.write(f"FAISS Search Results (Optimized - Single Load)\n")
        f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"FAISS index loaded in {load_time:.4f} seconds\n")
        f.write(f"{'='*80}\n\n")
        
        # Track overall stats
        total_time = 0
        total_results = 0
        
        # Process each query
        for i, query in enumerate(QUERIES, 1):
            print(f"Testing query {i}/{len(QUERIES)}: '{query}'")
            
            f.write(f"Query {i}: \"{query}\"\n")
            f.write(f"{'-'*80}\n\n")
            
            # Test FAISS implementation using the pre-loaded searcher
            start_time = time.time()
            try:
                results = searcher.get_search_results(query, k=10, similarity_threshold=0.3)
                search_time = time.time() - start_time
                total_time += search_time
                total_results += len(results)
                
                f.write(f"FAISS search: {len(results)} results in {search_time:.4f} seconds\n\n")
                
                # Write top 5 results
                for j, result in enumerate(results[:5], 1):
                    f.write(f"  {j}. {result['title']}\n")
                    f.write(f"     Similarity: {result['similarity']:.4f}\n")
                    f.write(f"     ID: {result['id']}\n\n")
                
            except Exception as e:
                f.write(f"Error with FAISS search: {e}\n\n")
                print(f"Error with query '{query}': {e}")
            
            f.write(f"\n{'='*80}\n\n")
        
        # Write summary
        f.write(f"SUMMARY\n")
        f.write(f"{'-'*80}\n\n")
        f.write(f"Total queries: {len(QUERIES)}\n")
        f.write(f"Total results: {total_results}\n")
        f.write(f"Average results per query: {total_results/len(QUERIES):.1f}\n")
        f.write(f"Total search time: {total_time:.4f} seconds\n")
        f.write(f"Average time per query: {total_time/len(QUERIES):.4f} seconds\n")
        f.write(f"FAISS index load time: {load_time:.4f} seconds\n")
    
    print(f"FAISS search test completed!")
    print(f"Results saved to {output_file}")
    print(f"Total search time: {total_time:.4f} seconds")
    print(f"Average time per query: {total_time/len(QUERIES):.4f} seconds")
    
    return output_file

if __name__ == "__main__":
    output_file = run_faiss_test()