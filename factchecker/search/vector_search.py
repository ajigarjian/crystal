import openai
import numpy as np
from typing import Dict, List
from factchecker.models import DatasetCatalog

def vector_search_datasets(query: str, openai_api_key: str, top_n: int = 5) -> List[Dict]:
    """
    Search for datasets using vector similarity with the query.
    
    Args:
        query: Natural language query
        openai_api_key: OpenAI API key
        top_n: Number of most relevant datasets to return
        
    Returns:
        List of the most relevant datasets
    """
    try:        
        # Check if we have datasets with embeddings
        indexed_count = DatasetCatalog.objects.filter(indexed=True).count()
        if indexed_count == 0:
            print("No datasets with embeddings found. Please run generate_embeddings command first.")
            return []
            
        # Generate embedding for the query
        client = openai.OpenAI(api_key=openai_api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        )
        query_embedding = np.array(response.data[0].embedding, dtype=np.float32)
        
        # Get all datasets with embeddings
        datasets_with_embeddings = DatasetCatalog.objects.filter(indexed=True)
        
        # Calculate similarity for each dataset
        results = []
        for dataset in datasets_with_embeddings:
            if dataset.embedding:
                # Convert binary embedding back to numpy array
                dataset_embedding = np.frombuffer(dataset.embedding, dtype=np.float32)
                
                # Calculate cosine similarity
                similarity = np.dot(query_embedding, dataset_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(dataset_embedding)
                )
                
                results.append({
                    "id": dataset.dataset_id,
                    "title": dataset.title,
                    "description": dataset.description[:200] if dataset.description else "",
                    "similarity": float(similarity),
                    # Add empty resources list to maintain compatibility with the original function
                    "resources": []
                })
        
        # Sort by similarity (highest first) and return top_n
        results.sort(key=lambda x: x["similarity"], reverse=True)
        top_results = results[:top_n]
        
        print(f"Found {len(top_results)} relevant datasets via vector search")
        return top_results
        
    except Exception as e:
        print(f"Error performing vector search: {e}")
        return []