import requests
import os
import openai
import numpy as np
from typing import Dict, List, Optional
import pandas as pd
from factchecker.models import DatasetCatalog

def init_api_key(api_key: Optional[str] = None) -> Dict[str, str]:
    """Initialize the Data.gov API key and OpenAI API key."""
    data_gov_key = api_key or os.environ.get("DATA_GOV_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if not data_gov_key:
        raise ValueError("Data.gov API key is required. Set DATA_GOV_API_KEY environment variable or pass it directly.")
    
    if not openai_key:
        raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")
    
    return {
        "data_gov": data_gov_key,
        "openai": openai_key
    }

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

def preprocess_query(query: str, openai_api_key: str) -> str:
    """
    Preprocess a specific query into a more general form suitable for Data.gov search.
    
    Args:
        query: The original specific query (e.g., "college graduation rate in 2022")
        openai_api_key: OpenAI API key
        
    Returns:
        A generalized query suitable for dataset discovery (e.g., "college graduation rate")
    """
    try:
        prompt = f"""
        I need to search for government datasets about: "{query}"
        
        The Data.gov search engine works better with general topics rather than specific qualifiers.
        Please provide a generalized version of this query that:
        1. Focuses ONLY on the core subject matter
        2. Removes specific years, states, or other narrow qualifiers
        3. Contains NO phrases like "government datasets", "datasets on", or similar prefixes
        4. Is as concise as possible while maintaining the core search intent
        
        For example:
        - "college graduation rate in 2022" → "college graduation rate"
        - "orange grove emissions factors" -> "emissions factors"
        - "New York unemployment 2019-2020" → "unemployment"
        - "global warming by year" → "global warming" or "climate change"
        
        Return ONLY the generalized query text with no explanation or additional text.
        """
        
        # Call OpenAI API
        client = openai.OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts the core subject from search queries without adding any extra terms."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        
        generalized_query = response.choices[0].message.content.strip()
        print(f"Original query: '{query}'")
        print(f"Generalized query: '{generalized_query}'")
        return generalized_query
        
    except Exception as e:
        print(f"Error generalizing query: {e}")
        # Fall back to the original query if there's an error
        return query

def search_datasets(api_key: str, query: str, rows: int = 10) -> List[Dict]:
    """
    Search for datasets using a query string.
    
    Args:
        api_key: Data.gov API key
        query: Search terms
        rows: Number of results to return (default: 10)
    
    Returns:
        List of dataset metadata
    """
    base_url = "https://catalog.data.gov/api/3"
    params = {
        "q": query,
        "rows": rows
    }
    headers = {
        "Authorization": api_key
    }
    
    try:
        response = requests.get(
            f"{base_url}/action/package_search", 
            params=params,
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # Simplified response structure
        simplified_results = []
        for dataset in data["result"]["results"]:
            simplified_results.append({
                "id": dataset.get("id"),
                "title": dataset.get("title"),
                "description": dataset.get("notes", "")[:200],  # Truncate description
                "resources": [
                    {
                        "url": r.get("url"),
                        "format": r.get("format", "").lower(),
                        "name": r.get("name")
                    }
                    for r in dataset.get("resources", [])
                    if r.get("format", "").lower() in ["csv", "json"]  # Only keep parseable formats
                ]
            })
        return simplified_results
    except requests.exceptions.RequestException as e:
        print(f"Error searching datasets: {e}")
        return []

def filter_relevant_datasets(query: str, datasets: List[Dict], openai_api_key: str, top_n: int = 5) -> List[Dict]:
    """
    Filter datasets to only the most relevant ones using LLM.
    
    Args:
        query: Original search query
        datasets: List of dataset metadata from search_datasets
        openai_api_key: OpenAI API key for LLM access
        top_n: Number of most relevant datasets to return
        
    Returns:
        List of the most relevant datasets
    """
    if not datasets:
        return []
    
    # If we have fewer datasets than requested, return all
    if len(datasets) <= top_n:
        return datasets
    
    try:
        # Prepare dataset information for the LLM
        dataset_info = []
        for i, dataset in enumerate(datasets):
            dataset_info.append(
                f"Dataset {i+1}:\n"
                f"Title: {dataset['title']}\n"
                f"ID: {dataset['id']}\n"
                f"Description: {dataset.get('description', 'No description')[:300]}...\n"
            )
        
        # Create the prompt
        prompt = f"""
        I need to find the most relevant datasets for the query: "{query}"
        
        Here are the datasets returned by the search:
        
        {'\n'.join(dataset_info)}
        
        Please identify the {top_n} most relevant datasets for this query. 
        Return only the dataset numbers (e.g., 1, 5, 10) in a comma-separated list.
        Base your selection on how well each dataset matches the query intent and data needs.
        """
        
        # Call OpenAI API directly with provided key
        client = openai.OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that identifies relevant datasets."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        
        # Extract content from response
        content = response.choices[0].message.content
        
        # Parse the response to get dataset indices
        import re
        numbers = re.findall(r'\d+', content)
        
        # Convert to integers and adjust for 0-indexing
        indices = [int(num) - 1 for num in numbers[:top_n] if 0 < int(num) <= len(datasets)]
        
        # If we couldn't parse any indices, return the first top_n datasets
        if not indices:
            return datasets[:top_n]
        
        # Return the selected datasets
        return [datasets[i] for i in indices]
        
    except Exception as e:
        print(f"Error filtering datasets: {e}")
        # Fallback to returning the first top_n datasets
        return datasets[:top_n]

def download_dataset(api_key: str, dataset_id: str, output_dir: str = "downloads") -> Optional[str]:
    """
    Download a dataset by its ID and save to CSV if possible.
    
    Args:
        api_key: Data.gov API key
        dataset_id: The dataset identifier
        output_dir: Directory to save downloaded files
        
    Returns:
        Path to downloaded file or None if download failed
    """
    base_url = "https://catalog.data.gov/api/3"
    try:
        # Get dataset metadata
        response = requests.get(
            f"{base_url}/action/package_show", 
            params={"id": dataset_id},
            headers={"Authorization": api_key}
        )
        response.raise_for_status()
        dataset = response.json()["result"]
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get dataset title and clean it for use as filename
        dataset_title = dataset.get("title", "dataset")
        # Replace spaces and special characters with underscores
        clean_title = "".join(c if c.isalnum() else "_" for c in dataset_title)
        # Remove multiple consecutive underscores and limit length
        clean_title = "_".join(filter(None, clean_title.split("_")))[:100]
        
        # Look for CSV resources
        for resource in dataset.get("resources", []):
            if resource.get("format", "").lower() == "csv":
                url = resource["url"]
                filename = f"{clean_title}.csv"
                output_path = os.path.join(output_dir, filename)
                
                # Download the CSV file
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return output_path
        
        print(f"No CSV resource found for dataset {dataset_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading dataset: {e}")
        return None

def main():
    # Example usage
    api_keys = init_api_key()

    openai_api_key = api_keys["openai"]
    gov_api_key = api_keys["data_gov"]
    
    # Natural language search query (original raw input)
    query = "college graduation rate in 2022"
    print(f"Searching for {query}...")
    
    # Use vector search on the dataset catalog to get the most relevant datasets
    datasets = vector_search_datasets(query, openai_api_key, top_n=5)
    
    if not datasets:
        print("No relevant datasets found.")
        return
    
    print(f"Found {len(datasets)} relevant datasets:")
    for i, dataset in enumerate(datasets, 1):
        print(f"{i}. {dataset['title']} (Similarity: {dataset['similarity']:.4f})")
        
        # Download the datasets
        print("Attempting to download...")
        output_path = download_dataset(gov_api_key, dataset["id"])
        if output_path:
            print(f"Downloaded to: {output_path}")

if __name__ == "__main__":
    main()