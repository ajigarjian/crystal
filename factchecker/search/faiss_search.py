"""
This module provides FAISS-powered vector search functionality for datasets.

It includes:
1. FAISSSearcher class - Loads a pre-built FAISS index and performs fast similarity searches
2. vector_search_datasets_faiss function - A drop-in replacement for the original vector_search_datasets
   function that uses FAISS for significantly faster performance

The interface matches the existing vector search implementation, making it easy to switch between
implementations without changing other code.

Requires running 'python manage.py build_faiss_index' first to create the necessary index files.
"""

import numpy as np
import faiss
import os
import pickle
from django.conf import settings
from factchecker.models import DatasetCatalog
from factchecker.utils.openai_client import create_embeddings
from factchecker.search.search_utils import get_usable_resources
import threading

# Add a lock for thread-safe initialization
_SEARCHER_LOCK = threading.Lock()
_GLOBAL_SEARCHER = None

def get_searcher():
    """Get or create a global FAISSSearcher instance in a thread-safe manner"""
    global _GLOBAL_SEARCHER
    
    # First check without the lock for efficiency
    if _GLOBAL_SEARCHER is None:
        # If it's None, acquire the lock and check again
        with _SEARCHER_LOCK:
            # Double-check after acquiring the lock
            if _GLOBAL_SEARCHER is None:
                print("Initializing FAISS index with 309,208 datasets (one-time operation)")
                _GLOBAL_SEARCHER = FAISSSearcher()
    
    return _GLOBAL_SEARCHER

class FAISSSearcher:
    """Class for performing vector searches using a pre-built FAISS index"""
    
    def __init__(self, index_dir='faiss_index'):
        """
        Initialize the FAISS searcher with the index and dataset IDs
        
        Args:
            index_dir: Directory containing the FAISS index files
        """
        # Default to the project's base directory + faiss_index if path is not absolute
        if not os.path.isabs(index_dir):
            base_dir = settings.BASE_DIR
            index_dir = os.path.join(base_dir, index_dir)
            
        # Check if index files exist
        index_path = os.path.join(index_dir, 'faiss.index')
        ids_path = os.path.join(index_dir, 'dataset_ids.pkl')
        
        if not os.path.exists(index_path) or not os.path.exists(ids_path):
            raise FileNotFoundError(
                f"FAISS index files not found in {index_dir}. "
                "Run 'python manage.py build_faiss_index' first."
            )
            
        # Load the index and dataset IDs
        self.index = faiss.read_index(index_path)
        with open(ids_path, 'rb') as f:
            self.dataset_ids = pickle.load(f)
            
        # Only print when initializing the global searcher
        pass  # Remove the print statement here
    
    def search(self, query, k=10):
        """
        Search for the top k datasets similar to the query
        
        Args:
            query: Text query to search for
            k: Number of results to return
            
        Returns:
            List of dicts with dataset_id and score
        """
        # Create embedding for the query
        query_embedding = np.array(create_embeddings(query), dtype=np.float32)
        
        # Reshape to a 2D array with 1 row
        query_embedding = query_embedding.reshape(1, -1)
        
        # Normalize the query vector for cosine similarity
        faiss.normalize_L2(query_embedding)
        
        # Search the index
        scores, indices = self.index.search(query_embedding, k)
        
        # Format results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.dataset_ids):  # -1 means no result
                results.append({
                    'dataset_id': self.dataset_ids[idx],
                    'score': float(scores[0][i])
                })
                
        return results
    
    def get_search_results(self, query, k=10, similarity_threshold=0.3):
        """
        Get full dataset objects for the top k results
        
        Args:
            query: Text query to search for
            k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of dataset dicts with full information
        """
        # Get raw search results
        results = self.search(query, k=k)
        
        # Filter by threshold
        results = [r for r in results if r['score'] >= similarity_threshold]
        
        # Get full dataset information
        formatted_results = []
        for result in results:
            try:
                dataset = DatasetCatalog.objects.get(dataset_id=result['dataset_id'])
                
                # Get usable resources
                resources = get_usable_resources(result['dataset_id'])
                
                # Only include datasets with usable resources
                if resources:
                    formatted_results.append({
                        "id": result['dataset_id'],
                        "title": dataset.title,
                        "description": dataset.notes[:200] if dataset.notes else "",
                        "organization": dataset.organization_title,
                        "similarity": result['score'],
                        "resources": resources,
                        "search_source": "vector"
                    })
            except DatasetCatalog.DoesNotExist:
                # Skip datasets that no longer exist
                continue
                
        return formatted_results

def vector_search_datasets_faiss(query: str, similarity_threshold: float = 0.3, verbose: bool = True, max_results: int = 10):
    """
    FAISS-powered version of vector_search_datasets with the same interface
    
    Args:
        query: Natural language query
        similarity_threshold: Minimum similarity score (0-1)
        verbose: Whether to print detailed logging information
        max_results: Maximum number of results to return
        
    Returns:
        List of datasets with similarity scores above the threshold, limited to max_results
    """
    verbose=True
    try:
        if verbose:
            print("Starting FAISS vector search process...")
            
        # Use the global searcher instead of creating a new one
        searcher = get_searcher()
        
        if verbose:
            print(f"Searching for top {max_results} matches with similarity threshold {similarity_threshold}...")
            
        # Get raw search results first (without checking resources)
        # Request more than we need to account for filtering
        raw_results = searcher.search(query, k=max_results * 3)
        
        # Filter by threshold
        filtered_results = [r for r in raw_results if r['score'] >= similarity_threshold]
        
        if verbose:
            print(f"Found {len(filtered_results)} raw matches with similarity >= {similarity_threshold}")
            print("Checking for usable resources...")
        
        # Get dataset information for all results at once
        dataset_ids = [r['dataset_id'] for r in filtered_results]
        datasets = {d.dataset_id: d for d in DatasetCatalog.objects.filter(dataset_id__in=dataset_ids)}
        
        # Format results and check resources
        formatted_results = []
        for result in filtered_results:
            # Stop once we have enough results
            if len(formatted_results) >= max_results:
                break
                
            dataset_id = result['dataset_id']
            if dataset_id not in datasets:
                continue
                
            dataset = datasets[dataset_id]
            
            # Get usable resources
            resources = get_usable_resources(dataset_id)
            
            # Only include datasets with usable resources
            if resources:
                formatted_results.append({
                    "id": dataset_id,
                    "title": dataset.title,
                    "description": dataset.notes[:200] if dataset.notes else "",
                    "organization": dataset.organization_title,
                    "similarity": result['score'],
                    "resources": resources,
                    "search_source": "vector"
                })
        
        if verbose:
            print(f"Found {len(formatted_results)} datasets with usable resources (limited to top {max_results})")
        
        # If we have results above threshold, return them
        if formatted_results:
            return formatted_results
            
        # If no datasets meet the threshold, try to find at least one
        if not formatted_results and similarity_threshold > 0.1:
            print("No datasets meet the threshold. Trying with lower threshold...")
            
            # Try with lower threshold
            lower_threshold = 0.1
            lower_results = [r for r in raw_results if r['score'] >= lower_threshold]
            
            # Check each one until we find one with usable resources
            for result in lower_results:
                dataset_id = result['dataset_id']
                if dataset_id not in datasets:
                    continue
                    
                dataset = datasets[dataset_id]
                resources = get_usable_resources(dataset_id)
                
                if resources:
                    formatted_result = {
                        "id": dataset_id,
                        "title": dataset.title,
                        "description": dataset.notes[:200] if dataset.notes else "",
                        "organization": dataset.organization_title,
                        "similarity": result['score'],
                        "resources": resources,
                        "search_source": "vector"
                    }
                    print(f"Found top dataset with similarity {result['score']:.4f}: {dataset.title}")
                    return [formatted_result]
                
        # If we get here, no datasets have usable resources
        print("No datasets with usable resources found.")
        return []
        
    except Exception as e:
        print(f"Error performing FAISS vector search: {e}")
        return []