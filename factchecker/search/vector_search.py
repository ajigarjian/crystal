import openai
import numpy as np
from typing import Dict, List
from factchecker.models import DatasetCatalog
from factchecker.utils.openai_client import create_embeddings
import requests
import os

def vector_search_datasets(query: str, similarity_threshold: float = 0.5) -> List[Dict]:
    """
    Search for datasets using vector similarity with the query.
    Always returns at least 1 dataset with the highest similarity if any exist with usable resources.
    
    Args:
        query: Natural language query
        similarity_threshold: Minimum similarity score (0-1) for including datasets (default: 0.5)
        
    Returns:
        List of datasets with similarity scores above the threshold, or at least the top dataset
    """
    try:        
        # Check if we have datasets with embeddings
        indexed_count = DatasetCatalog.objects.filter(indexed=True).count()
        if indexed_count == 0:
            print("No datasets with embeddings found. Please run generate_embeddings command first.")
            return []
            
        response = create_embeddings(query)
        
        query_embedding = np.array(response, dtype=np.float32)
        
        # Get all datasets with embeddings
        datasets_with_embeddings = DatasetCatalog.objects.filter(indexed=True)
        
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
                    "description": dataset.description[:200] if dataset.description else "",
                    "similarity": float(similarity),
                    "resources": [],  # Will be populated later if usable resources exist
                    "search_source": "vector"
                })
        
        # Sort all candidates by similarity (highest first)
        all_candidates.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Filter candidates by threshold
        threshold_candidates = [d for d in all_candidates if d["similarity"] >= similarity_threshold]
        
        print(f"Found {len(threshold_candidates)} candidate datasets via vector search with similarity >= {similarity_threshold}")
        
        # Check candidates for usable resources
        final_results = []
        for dataset in threshold_candidates:
            resources = get_usable_resources(dataset["id"])
            if resources:
                dataset["resources"] = resources
                final_results.append(dataset)
            else:
                print(f"Skipping dataset {dataset['id']} ({dataset['title']}) - no usable resources found")
        
        # If we have results above threshold, return them
        if final_results:
            print(f"Final count: {len(final_results)} datasets with usable resources")
            return final_results
        
        # If no datasets meet the threshold, try to find at least one with usable resources
        print("No datasets meet the threshold. Trying to find at least one dataset with usable resources...")
        
        # Check candidates in order of similarity until we find one with usable resources
        for dataset in all_candidates:
            resources = get_usable_resources(dataset["id"])
            if resources:
                dataset["resources"] = resources
                print(f"Found top dataset with similarity {dataset['similarity']:.4f}: {dataset['title']}")
                return [dataset]  # Return just this one dataset
        
        # If we get here, no datasets have usable resources
        print("No datasets with usable resources found.")
        return []
        
    except Exception as e:
        print(f"Error performing vector search: {e}")
        return []

def get_usable_resources(dataset_id: str) -> List[Dict]:
    """
    Get a list of usable resources for a dataset by making an API call to data.gov.
    
    Args:
        dataset_id: The dataset ID to check
        
    Returns:
        List of resource dictionaries with url, format, and name
    """
    try:
        # Get API key from settings
        from django.conf import settings
        api_key = settings.DATA_GOV_API_KEY
        
        if not api_key:
            print("DATA_GOV_API_KEY not found in settings")
            return []
        
        # Make API call to data.gov
        base_url = "https://catalog.data.gov/api/3"
        headers = {"Authorization": api_key}
        
        response = requests.get(
            f"{base_url}/action/package_show?id={dataset_id}", 
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
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
        print(f"Error getting resources for dataset {dataset_id}: {e}")
        return []