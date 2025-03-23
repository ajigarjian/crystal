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

def calculate_similarity_scores(query: str, datasets: List[Dict]) -> None:
    """
    Calculate similarity scores for datasets using constraint-aware evaluation.
    
    Args:
        query: The original search query
        datasets: List of dataset metadata
    """
    # Extract constraints from the query
    constraints = extract_query_constraints(query)
    constraints_text = "\n".join([f"- {c}" for c in constraints])
    
    # Prepare dataset information for the LLM
    dataset_info = []
    for i, dataset in enumerate(datasets):
        # Get resource information
        resource_info = []
        for res in dataset.get("resources", []):
            format_type = res.get('format', 'unknown').lower()
            resource_info.append(
                f"- {res.get('name', 'Unnamed')} ({format_type.upper()})"
            )
        
        # Get organization name if available
        org_name = "Unknown"
        if isinstance(dataset.get("organization"), dict):
            org_name = dataset["organization"].get("name", "Unknown")
        
        # Combine all metadata for evaluation
        dataset_info.append(
            f"Dataset {i+1}:\n"
            f"Title: {dataset['title']}\n"
            f"Description: {dataset.get('description', 'No description')[:500]}...\n"
            f"Resources: {len(resource_info)} files\n"
            f"{chr(10).join(resource_info)}\n"
            f"Tags: {', '.join(dataset.get('tags', []))}\n"
            f"Organization: {org_name}\n"
        )
    
    # Create the constraint-aware prompt
    constraint_instructions = ""
    if constraints:
        constraint_instructions = f"""
        The query has the following specific constraints:
        {constraints_text}
        
        For a dataset to be highly relevant (score > 0.7), it MUST satisfy ALL or MOST of these constraints.
        Datasets that miss critical constraints should receive low scores (< 0.4), even if they match the general topic.
        """
    
    prompt = f"""
    I need to rate the relevance of datasets for the query: "{query}"
    
    {constraint_instructions}
    
    Here are the datasets:
    
    {'\n'.join(dataset_info)}
    
    For each dataset (1 to {len(datasets)}), assign a similarity score from 0.0 to 1.0 where:
    - 1.0 means perfectly relevant, satisfying all constraints in the query
    - 0.7-0.9 means highly relevant, satisfying most constraints
    - 0.4-0.6 means moderately relevant, satisfying some constraints
    - 0.1-0.3 means minimally relevant, matching the general topic but missing key constraints
    - 0.0 means completely irrelevant
    
    For each dataset, carefully evaluate:
    1. Does it cover the right subject matter?
    2. Does it satisfy the specific constraints in the query?
    3. Would the data actually be useful for answering the query?
    
    Return ONLY a JSON array of scores like this:
    [0.95, 0.82, 0.45, ...]
    """
    
    response = chat_completion(
        prompt,
        system_message="You are a helpful assistant that evaluates dataset relevance with precision.",
        temperature=0
    )
    
    if not response:
        return []
    # Parse the response to get similarity scores
    try:
        # Try to parse as JSON
        import json
        scores = json.loads(response.strip())
        
        # Update similarity scores in datasets
        for i, score in enumerate(scores):
            if i < len(datasets):
                datasets[i]["similarity"] = float(score)
        
    except json.JSONDecodeError:
        # Fallback: try to extract numbers if JSON parsing fails
        scores = re.findall(r'0\.\d+|1\.0', response)
        for i, score in enumerate(scores):
            if i < len(datasets):
                datasets[i]["similarity"] = float(score)

def search_datasets(query: str, api_key: str, similarity_threshold: float = 0.7) -> List[Dict]:
    """
    Search for datasets using a query string.
    
    Args:
        api_key: Data.gov API key
        query: Search terms
        similarity_threshold: Minimum similarity score (0-1) for including datasets (default: 0.7)
    
    Returns:
        List of dataset metadata with similarity scores above the threshold
    """
    base_url = "https://catalog.data.gov/api/3"
    params = {
        "q": query,
        "rows": 100  # Get a larger number of candidates to filter
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
            # Extract tags if available
            tags = []
            if "tags" in dataset and isinstance(dataset["tags"], list):
                tags = [tag.get("name", "") for tag in dataset["tags"] if isinstance(tag, dict)]
            
            # Filter resources to include CSV, XLSX, XLS, JSON, XML or PDF formats
            # Check both format field and URL ending
            filtered_resources = []
            for r in dataset.get("resources", []):
                # Get format from the format field (if available)
                format_field = r.get("format", "").lower()
                
                # Get format from URL ending (if available)
                url = r.get("url", "")
                url_format = ""
                if url and isinstance(url, str):
                    # Extract file extension from URL
                    if "." in url.split("/")[-1]:
                        url_format = url.split(".")[-1].lower()
                        # Remove any query parameters
                        if "?" in url_format:
                            url_format = url_format.split("?")[0]
                
                # Determine the effective format (prioritize format field if available)
                effective_format = format_field if format_field else url_format
                
                # Check if the effective format is one we can use
                if effective_format in ["csv", "json", "xlsx", "xls", "pdf", "xml"]:
                    # Store the effective format in the resource
                    resource = {
                        "url": url,
                        "format": effective_format,
                        "name": r.get("name", "Unnamed Resource")
                    }
                    filtered_resources.append(resource)
            
            # Only include datasets that have at least one resource in the desired formats
            if filtered_resources:
                simplified_results.append({
                    "id": dataset.get("id"),
                    "title": dataset.get("title"),
                    "description": dataset.get("notes", ""),
                    "resources": filtered_resources,
                    "tags": tags,
                    "organization": dataset.get("organization", {}),
                    "metadata_created": dataset.get("metadata_created", ""),
                    "metadata_modified": dataset.get("metadata_modified", ""),
                    "similarity": 0.0,  # Will be replaced with calculated score
                    "search_source": "keyword"
                })
        
        # Calculate similarity scores with constraint awareness
        if simplified_results:
            calculate_similarity_scores(query, simplified_results)
            
            # Filter by similarity threshold
            filtered_results = [d for d in simplified_results if d.get('similarity', 0) >= similarity_threshold]
            
            # Sort by similarity score (higher is better)
            filtered_results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            print(f"Found {len(filtered_results)} datasets via keyword search with similarity >= {similarity_threshold}")
            return filtered_results
        else:
            return []
        
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

def extract_query_constraints(query: str) -> List[str]:
    """
    Extract key constraints from a query in a generalized way.
    
    Args:
        query: The user's query
        
    Returns:
        List of specific constraints that must be satisfied
    """
    prompt = f"""
    Analyze this query: "{query}"
    
    Extract all specific constraints that would make a dataset relevant.
    A constraint is any specific condition that must be met for data to be useful.
    
    Examples:
    - For "unemployment rates in California 2020-2022", constraints are:
      1. Data must be about unemployment rates
      2. Data must cover California
      3. Data must include the 2020-2022 time period
    
    - For "vaccination rates among children under 5", constraints are:
      1. Data must be about vaccination rates
      2. Data must specifically cover children under 5 years old
    
    For the given query, list ONLY the specific constraints, one per line.
    Be precise and focus on what would make a dataset truly relevant.
    """
    
    response = chat_completion(
        prompt,
        system_message="You are a helpful assistant that identifies specific data constraints.",
        temperature=0
    )
    
    # Split the response into individual constraints
    constraints = [line.strip() for line in response.strip().split('\n') if line.strip()]
    return constraints 