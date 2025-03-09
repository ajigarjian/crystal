import requests
import openai
import re
from typing import Dict, List, Optional

from factchecker.utils.openai_client import chat_completion

def preprocess_query(query: str) -> str:
    """
    Preprocess a specific query into a more general form suitable for Data.gov search.
    
    Args:
        query: The original specific query (e.g., "college graduation rate in 2022")
        
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
        
        response = chat_completion(
        prompt,
        system_message="You are a helpful assistant that extracts the core subject from search queries without adding any extra terms.",
        temperature=0 # Highest determinism
        )
        
        generalized_query = response.strip()
        print(f"Original query: '{query}'")
        print(f"Generalized query: '{generalized_query}'")
        return generalized_query
        
    except Exception as e:
        print(f"Error generalizing query: {e}")
        # Fall back to the original query if there's an error
        return query

def search_datasets(query: str, api_key: str, top_n: int = 10) -> List[Dict]:
    """
    Search for datasets using a query string.
    
    Args:
        api_key: Data.gov API key
        query: Search terms
        top_n: Number of results to return
    
    Returns:
        List of dataset metadata
    """
    base_url = "https://catalog.data.gov/api/3"
    params = {
        "q": query,
        "rows": top_n
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
                    # Include Excel formats along with CSV and JSON
                    if r.get("format", "").lower() in ["csv", "json", "xlsx", "xls"]
                ],
                "similarity": 1.0,  # Default similarity for keyword matches
                "search_source": "keyword"  # Add this line
            })
            
        # Only return top_n results
        return simplified_results[:top_n]
        
    except requests.exceptions.RequestException as e:
        print(f"Error searching datasets: {e}")
        return []

def filter_relevant_datasets(query: str, datasets: List[Dict], top_n: int = 5) -> List[Dict]:
    """
    Filter datasets to only the most relevant ones using LLM.
    
    Args:
        query: Original search query
        datasets: List of dataset metadata from search_datasets
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
        
        response = chat_completion(
        prompt,
        system_message="You are a helpful assistant that identifies relevant datasets.",
        temperature=0 #As high determinism as possible.
        )
        
        # Extract content from response
        content = response
        
        # Parse the response to get dataset indices
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