"""
DEPRECATED: This module is deprecated in favor of the FAISS-based vector search implementation.
Please use factchecker.search.faiss_search instead for better performance.
"""

import openai
import numpy as np
from typing import Dict, List
from factchecker.models import DatasetCatalog
from factchecker.utils.openai_client import create_embeddings
import requests
import os
from factchecker.search.search_utils import get_usable_resources

def vector_search_datasets(query: str, similarity_threshold: float = 0.5, verbose: bool = False) -> List[Dict]:
    """
    Search for datasets using vector similarity with the query.
    Always returns at least 1 dataset with the highest similarity if any exist with usable resources.
    
    Args:
        query: Natural language query
        similarity_threshold: Minimum similarity score (0-1) for including datasets (default: 0.5)
        verbose: Whether to print detailed logging information
        
    Returns:
        List of datasets with similarity scores above the threshold, or at least the top dataset
    """
    try:
        if verbose:
            print("Starting vector search process...")
            
        # Check if we have datasets with embeddings
        indexed_count = DatasetCatalog.objects.filter(indexed=True).count()
        if verbose:
            print(f"Found {indexed_count} datasets with embeddings")
            
        if indexed_count == 0:
            print("No datasets with embeddings found. Please run generate_embeddings command first.")
            return []
        
        if verbose:
            print("Generating embeddings for query...")
            
        response = create_embeddings(query)
        
        if verbose:
            print("Query embedding generated successfully")
            
        query_embedding = np.array(response, dtype=np.float32)
        
        # Get all datasets with embeddings
        datasets_with_embeddings = DatasetCatalog.objects.filter(indexed=True)
        
        if verbose:
            print(f"Calculating similarity for {datasets_with_embeddings.count()} datasets...")
        
        # Calculate similarity for all datasets
        all_candidates = []
        for dataset in datasets_with_embeddings:
            if dataset.embedding:
                # Convert binary embedding back to numpy array
                dataset_embedding = np.frombuffer(dataset.embedding, dtype=np.float32)
                
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, dataset_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(dataset_embedding)
                )
                
                all_candidates.append({
                    "id": dataset.dataset_id,
                    "title": dataset.title,
                    "description": dataset.notes[:200] if dataset.notes else "",
                    "similarity": float(similarity),
                    "resources": [],  # Will be populated later if usable resources exist
                    "search_source": "vector"
                })
        
        # Sort all candidates by similarity (highest first)
        all_candidates.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Filter candidates by threshold
        threshold_candidates = [d for d in all_candidates if d["similarity"] >= similarity_threshold]
        
        if verbose:
            print(f"Found {len(threshold_candidates)} candidate datasets via vector search with similarity >= {similarity_threshold}")
        
        # Check candidates for usable resources
        final_results = []
        for dataset in threshold_candidates:
            resources = get_usable_resources(dataset["id"])
            if resources:
                dataset["resources"] = resources
                final_results.append(dataset)
            else:
                if verbose:
                    print(f"Skipping dataset {dataset['id']} ({dataset['title']}) - no usable resources found")
        
        # If we have results above threshold, return them
        if final_results:
            if verbose:
                print(f"Final count: {len(final_results)} datasets with usable resources")
            return final_results
        
        # If no datasets meet the threshold, try to find at least one with usable resources
        if verbose:
            print("No datasets meet the threshold. Trying to find at least one dataset with usable resources...")
        
        # Check candidates in order of similarity until we find one with usable resources
        for dataset in all_candidates:
            resources = get_usable_resources(dataset["id"])
            if resources:
                dataset["resources"] = resources
                if verbose:
                    print(f"Found top dataset with similarity {dataset['similarity']:.4f}: {dataset['title']}")
                return [dataset]  # Return just this one dataset
        
        # If we get here, no datasets have usable resources
        if verbose:
            print("No datasets with usable resources found.")
        return []
        
    except Exception as e:
        if verbose:
            print(f"Error performing vector search: {e}")
        return []