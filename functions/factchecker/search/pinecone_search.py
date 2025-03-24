"""
This module provides Pinecone-powered vector search functionality for datasets.

It includes:
1. PineconeSearcher class - Connects to a Pinecone index and performs fast similarity searches
2. vector_search_datasets_pinecone function - A drop-in replacement for vector search using Pinecone

The interface matches the existing vector search implementation, making it easy to switch between
implementations without changing other code.
"""

import os
import pickle
import numpy as np
import threading
from typing import List, Dict, Any, Optional
import logging
import sys

# Import database utilities from shared helper module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from helpers.db_utils import execute_query, get_usable_resources

# Import pinecone
import pinecone

# Configure logging
logger = logging.getLogger(__name__)

# Add a lock for thread-safe initialization
_SEARCHER_LOCK = threading.Lock()
_GLOBAL_PINECONE_SEARCHER = None

def create_embeddings(text):
    """
    Create embeddings for the given text using OpenAI API.
    This is a simplified implementation that should be replaced with actual embedding creation.
    """
    # This is a placeholder - in a real implementation, you would call OpenAI API
    # For now, return a random vector of the correct dimension
    return np.random.rand(1536).astype(np.float32)

def get_pinecone_searcher():
    """Get or create a global PineconeSearcher instance in a thread-safe manner"""
    global _GLOBAL_PINECONE_SEARCHER
    
    # First check without the lock for efficiency
    if _GLOBAL_PINECONE_SEARCHER is None:
        # If it's None, acquire the lock and check again
        with _SEARCHER_LOCK:
            # Double-check after acquiring the lock
            if _GLOBAL_PINECONE_SEARCHER is None:
                logger.info("Initializing Pinecone connection (one-time operation)")
                _GLOBAL_PINECONE_SEARCHER = PineconeSearcher()
    
    return _GLOBAL_PINECONE_SEARCHER

class PineconeSearcher:
    """Class for performing vector searches using Pinecone"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 environment: Optional[str] = None,
                 index_name: str = "dataset-embeddings"):
        """
        Initialize the Pinecone searcher
        
        Args:
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            environment: Pinecone environment (defaults to PINECONE_ENVIRONMENT env var)
            index_name: Name of the Pinecone index to use
        """
        # Get API key and environment from environment variables
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        self.environment = environment or os.environ.get("PINECONE_ENVIRONMENT")
        
        if not self.api_key or not self.environment:
            raise ValueError(
                "Pinecone API key and environment must be provided either as parameters "
                "or as environment variables."
            )
        
        # Initialize Pinecone
        pinecone.init(api_key=self.api_key, environment=self.environment)
        
        # Connect to the index
        self.index_name = index_name
        if self.index_name not in pinecone.list_indexes():
            raise ValueError(
                f"Pinecone index '{self.index_name}' not found."
            )
        
        self.index = pinecone.Index(self.index_name)
    
    def search(self, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for the top k datasets similar to the query
        
        Args:
            query: Text query to search for
            k: Number of results to return
            
        Returns:
            List of dicts with dataset_id and score
        """
        # Create embedding for the query
        query_embedding = create_embeddings(query)
        
        # Search the index
        results = self.index.query(
            vector=query_embedding,
            top_k=k,
            include_metadata=False
        )
        
        # Format results
        formatted_results = []
        for match in results.matches:
            formatted_results.append({
                'dataset_id': match.id,
                'score': float(match.score)
            })
                
        return formatted_results
    
    def get_search_results(self, query: str, k: int = 10, similarity_threshold: float = 0.3) -> List[Dict[str, Any]]:
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
                # Query the database for dataset information
                dataset_query = """
                SELECT dataset_id, title, notes, organization_title
                FROM factchecker_datasetcatalog
                WHERE dataset_id = %s
                """
                dataset = execute_query(dataset_query, (result['dataset_id'],), fetch_all=False)
                
                if not dataset:
                    continue
                
                # Get usable resources
                resources = get_usable_resources(result['dataset_id'])
                
                # Only include datasets with usable resources
                if resources:
                    formatted_results.append({
                        "id": result['dataset_id'],
                        "title": dataset["title"],
                        "description": dataset["notes"] if dataset["notes"] else "",
                        "organization": dataset["organization_title"],
                        "similarity": result['score'],
                        "resources": resources,
                        "search_source": "vector"
                    })
            except Exception as e:
                logger.error(f"Error processing dataset {result['dataset_id']}: {e}")
                continue
                
        return formatted_results

# Add a lock for thread-safe initialization
_PINECONE_CLIENT_LOCK = threading.Lock()
_GLOBAL_PINECONE_CLIENT = None

def get_pinecone_client():
    """Get or create a global Pinecone client instance in a thread-safe manner"""
    global _GLOBAL_PINECONE_CLIENT
    
    # First check without the lock for efficiency
    if _GLOBAL_PINECONE_CLIENT is None:
        # If it's None, acquire the lock and check again
        with _PINECONE_CLIENT_LOCK:
            # Double-check after acquiring the lock
            if _GLOBAL_PINECONE_CLIENT is None:
                logger.info("Initializing Pinecone client (one-time operation)")
                
                # Get API key from environment variables
                api_key = os.environ.get("PINECONE_API_KEY")
                
                if not api_key:
                    raise ValueError(
                        "Pinecone API key must be provided as environment variable."
                    )
                
                # Create Pinecone client
                from pinecone import Pinecone
                _GLOBAL_PINECONE_CLIENT = Pinecone(api_key=api_key)
    
    return _GLOBAL_PINECONE_CLIENT

def vector_search_datasets_pinecone(
    query: str, 
    similarity_threshold: float = 0.3,
    top_k: int = 100,
    verbose: bool = False,
    max_results: int = None
) -> List[Dict]:
    """
    Search for datasets using vector similarity with Pinecone.
    
    Args:
        query: Natural language query
        similarity_threshold: Minimum similarity score (0-1) for including results
        top_k: Maximum number of results to return
        verbose: Whether to print verbose output
        max_results: Maximum number of results to return (overrides top_k if provided)
        
    Returns:
        List of dataset dictionaries with similarity scores
    """
    try:
        # Use max_results if provided, otherwise use top_k
        if max_results is not None:
            top_k = max_results
            
        if verbose:
            logger.info("Starting Pinecone vector search process...")
            
        # Create embeddings for the query
        query_embedding = create_embeddings(query)
        
        # Get the global Pinecone client (initialized only once)
        pc = get_pinecone_client()
        
        # Get index name from environment or use default
        index_name = os.environ.get("PINECONE_INDEX_NAME", "dataset-embeddings")
        
        # Check if index exists
        existing_indexes = [index.name for index in pc.list_indexes()]
        if index_name not in existing_indexes:
            if verbose:
                logger.warning(f"Pinecone index '{index_name}' not found.")
            return []
        
        # Connect to the index
        index = pc.Index(index_name)
        
        if verbose:
            logger.info(f"Searching for top {top_k} matches with similarity threshold {similarity_threshold}...")
        
        # Ensure vector is normalized for cosine similarity
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        
        # Query Pinecone - request more than we need to account for filtering
        results = index.query(
            vector=query_embedding.tolist(),
            top_k=top_k * 3,
            include_metadata=True
        )
        
        # Filter results by threshold
        filtered_matches = [match for match in results.matches if match.score >= similarity_threshold]
        
        if verbose:
            logger.info(f"Found {len(filtered_matches)} raw matches with similarity >= {similarity_threshold}")
            logger.info("Checking for usable resources...")
        
        # Get dataset IDs for batch database query
        dataset_ids = [match.id for match in filtered_matches]
        
        # Check if we have any dataset IDs before querying the database
        if not dataset_ids:
            if verbose:
                logger.info("No datasets found with similarity above threshold.")
            return []
        
        # Get all datasets in one query
        datasets_query = """
        SELECT dataset_id, title, notes, organization_title
        FROM factchecker_datasetcatalog
        WHERE dataset_id IN %s
        """
        
        # Execute the query with a tuple of dataset IDs
        datasets_result = execute_query(datasets_query, (tuple(dataset_ids),))
        
        # Convert to a dictionary for easy lookup
        datasets = {d["dataset_id"]: d for d in datasets_result}
        
        # Format results and check resources
        formatted_results = []
        for match in filtered_matches:
            # Stop once we have enough results
            if len(formatted_results) >= top_k:
                break
                
            dataset_id = match.id
            similarity = match.score
            
            # Skip if dataset doesn't exist in database
            if dataset_id not in datasets:
                continue
                
            dataset = datasets[dataset_id]
            
            # Get usable resources
            resources = get_usable_resources(dataset_id)
            
            # Only include datasets with usable resources
            if resources:
                formatted_results.append({
                    "id": dataset_id,
                    "title": dataset["title"],
                    "description": dataset["notes"] if dataset["notes"] else "",
                    "organization": dataset["organization_title"],
                    "similarity": similarity,
                    "resources": resources,
                    "search_source": "vector"
                })
        
        if verbose:
            logger.info(f"Found {len(formatted_results)} datasets with usable resources (limited to top {top_k})")
        
        # If we have results above threshold, return them
        if formatted_results:
            return formatted_results
            
        # If no datasets meet the threshold, try to find at least one with a lower threshold
        if not formatted_results and similarity_threshold > 0.1:
            if verbose:
                logger.info("No datasets meet the threshold. Trying with lower threshold...")
            
            # Try with lower threshold
            lower_threshold = 0.1
            
            # Re-filter results with lower threshold
            lower_matches = [match for match in results.matches if match.score >= lower_threshold]
            
            # Check each one until we find one with usable resources
            for match in lower_matches:
                dataset_id = match.id
                
                # Skip if dataset doesn't exist in database
                if dataset_id not in datasets:
                    continue
                    
                dataset = datasets[dataset_id]
                resources = get_usable_resources(dataset_id)
                
                if resources:
                    formatted_result = {
                        "id": dataset_id,
                        "title": dataset["title"],
                        "description": dataset["notes"] if dataset["notes"] else "",
                        "organization": dataset["organization_title"],
                        "similarity": match.score,
                        "resources": resources,
                        "search_source": "vector"
                    }
                    if verbose:
                        logger.info(f"Found top dataset with similarity {match.score:.4f}: {dataset['title']}")
                    return [formatted_result]
                
        # If we get here, no datasets have usable resources
        if verbose:
            logger.info("No datasets with usable resources found.")
        return []
        
    except Exception as e:
        logger.error(f"Error searching with query '{query}': {e}")
        return []