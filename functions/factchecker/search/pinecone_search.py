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
import traceback
import time

# Import database utilities from shared helper module
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from helpers.db_utils import execute_query, get_usable_resources, get_usable_resources_batch

# Import pinecone
from pinecone import Pinecone, Index, ServerlessSpec  # Updated import

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
        Initialize the Pinecone searcher using the new Pinecone client interface.
        
        Args:
            api_key: Pinecone API key (defaults to PINECONE_API_KEY env var)
            environment: Pinecone environment (defaults to PINECONE_ENVIRONMENT env var)
            index_name: Name of the Pinecone index to use
        """
        # Get API key and environment from environment variables if not provided
        self.api_key = api_key or os.environ.get("PINECONE_API_KEY")
        self.environment = environment or os.environ.get("PINECONE_ENVIRONMENT")
        
        if not self.api_key:
            raise ValueError("Pinecone API key must be provided or set via PINECONE_API_KEY env var.")
        
        # Create Pinecone client
        self.pc = Pinecone(api_key=self.api_key)
        
        # If you have a serverless region specification, set it here. Example:
        # if self.environment:
        #     self.pc.create_index(
        #         name=index_name,
        #         dimension=1536,
        #         metric='cosine',
        #         spec=ServerlessSpec(cloud='aws', region=self.environment),
        #         overwrite=False
        #     )
        #
        # For now, we simply check if the index exists:
        existing_indexes = [i.name for i in self.pc.list_indexes()]
        self.index_name = index_name
        if self.index_name not in existing_indexes:
            raise ValueError(f"Pinecone index '{self.index_name}' not found.")
        
        self.index = self.pc.Index(self.index_name)
    
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
                SELECT dataset_id, title, notes, organization_title, image_url
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
                        "search_source": "vector",
                        "image_url": dataset.get("image_url", "")
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
                logger.info("Initializing new Pinecone client (one-time operation)")
                
                # Get API key from environment variables
                api_key = os.environ.get("PINECONE_API_KEY")
                
                if not api_key:
                    raise ValueError("Pinecone API key must be provided as an environment variable.")
                
                # Create Pinecone client
                _GLOBAL_PINECONE_CLIENT = Pinecone(api_key=api_key)
    
    return _GLOBAL_PINECONE_CLIENT

def vector_search_datasets_pinecone(
    query: str,
    start_time: float,
    pinecone_api_key: Optional[str] = None,
    pinecone_environment: Optional[str] = None,
    index_name: str = "dataset-embeddings",
    similarity_threshold: float = 0.3,
    top_k: int = 100,
    max_results: Optional[int] = None,
    verbose: bool = False,
    pinecone_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Search for datasets using vector similarity with Pinecone, 
    retrieving dataset info directly via SQL queries.
    
    Args:
        query: The search query string.
        start_time: Start time for measuring Pinecone query duration
        pinecone_api_key: Pinecone API key; if None, read from env var PINECONE_API_KEY.
        pinecone_environment: Pinecone environment (e.g., 'us-east-1-gcp'); if None, read from env var PINECONE_ENVIRONMENT.
        index_name: Name of the Pinecone index to query.
        similarity_threshold: Only return matches with this score or higher.
        top_k: Maximum number of results to return (default 100).
        max_results: If provided, overrides top_k.
        verbose: If True, prints debug info to stdout.
        pinecone_client: Pre-initialized Pinecone client to use (optional)
    """
    try:
        import time  # Add import at the top of the file
        
        # Override top_k if max_results is given
        if max_results is not None:
            top_k = max_results

        # Use provided client or create a new one
        if pinecone_client:
            pc = pinecone_client
            if verbose:
                print("Using provided Pinecone client")
        else:
            # Pull Pinecone credentials from function args or environment
            api_key = pinecone_api_key or os.environ.get("PINECONE_API_KEY")
            env = pinecone_environment or os.environ.get("PINECONE_ENVIRONMENT")
            if not api_key:
                if verbose:
                    print("Pinecone credentials not provided - returning no results.")
                return []

            if verbose:
                print(f"Initializing Pinecone client (index='{index_name}')...")
            
            # Create a new Pinecone client object
            pc = Pinecone(api_key=api_key)
        
        # Create embedding with your chosen embedding function
        from factchecker.utils.openai_client import create_embeddings
        query_embedding = create_embeddings(query)

        # Ensure index exists
        existing_indexes = [i.name for i in pc.list_indexes()]
        if index_name not in existing_indexes:
            if verbose:
                print(f"Index '{index_name}' not found in Pinecone.")
            return []

        # Query index
        index = pc.Index(index_name)
        
        # Check if query_embedding is already a list or needs conversion
        if isinstance(query_embedding, np.ndarray):
            query_vector = query_embedding.tolist()
        else:
            # If it's already a list, use it directly
            query_vector = query_embedding
            
        results = index.query(
            vector=query_vector,
            top_k=top_k * 3,  # over-fetch so we can threshold
            include_metadata=False
        )

        # Log when results are returned from Pinecone API
        logger.info(f'Pinecone index.query completed for "{query}" at timestamp: {time.time() - start_time:.2f} seconds')

        if verbose:
            print(f"Retrieved {len(results.matches)} matches from Pinecone before filtering.")

        # Filter by similarity threshold
        filtered_matches = [
            match for match in results.matches if match.score >= similarity_threshold
        ]
        if verbose:
            print(f"{len(filtered_matches)} matches remain after threshold = {similarity_threshold}")

        # Collect dataset IDs
        dataset_ids = [match.id for match in filtered_matches]

        if not dataset_ids:
            if verbose:
                print("No matches above threshold, returning empty list.")
            return []

        # Add timing for database operations
        if verbose:
            print(f"Fetching dataset info for {len(dataset_ids)} datasets...")
            start_time = time.time()

        # Fetch dataset info via direct SQL (no SQLAlchemy)
        query_sql = """
            SELECT dataset_id, title, notes, organization_title, image_url
            FROM factchecker_datasetcatalog
            WHERE dataset_id = ANY(%s)
        """
        ds_rows = execute_query(query_sql, params=(dataset_ids,))

        if verbose:
            print(f"Database query for datasets completed in {time.time() - start_time:.2f} seconds")
            
        # Fetch all resources in a single batch query
        if verbose:
            print(f"Fetching resources for all datasets in a single query...")
            start_time = time.time()
            
        # Import the new batch function
        resources_by_dataset = get_usable_resources_batch(dataset_ids)
        
        if verbose:
            print(f"Resources batch query completed in {time.time() - start_time:.2f} seconds")
            print(f"Found resources for {len(resources_by_dataset)} datasets")

        # Build a map for quick lookup
        ds_map = {str(row["dataset_id"]): row for row in ds_rows}

        final_results = []
        if verbose:
            print(f"Processing {len(filtered_matches)} matches...")
            start_time = time.time()

        for match in filtered_matches:
            if len(final_results) >= top_k:
                break

            ds_id_str = str(match.id)
            if ds_id_str not in ds_map:
                # Dataset doesn't exist or wasn't found in DB
                continue

            ds_row = ds_map[ds_id_str]
            
            # Get resources from our batch results
            resources = resources_by_dataset.get(ds_id_str, [])
            
            if not resources:
                # Skip datasets with no usable resources
                continue

            final_results.append({
                "id": ds_id_str,
                "title": ds_row.get("title", ""),
                "description": ds_row.get("notes", "") or "",
                "organization": ds_row.get("organization_title", ""),
                "similarity": float(match.score),
                "resources": resources,
                "search_source": "vector",
                "image_url": ds_row.get("image_url", "")
            })

        if verbose:
            print(f"Processing matches completed in {time.time() - start_time:.2f} seconds")
            print(f"Returning {len(final_results)} final results with resources...")

        return final_results

    except Exception as e:
        if verbose:
            print(f"Error in vector_search_datasets_pinecone: {e}")
            if verbose > 1:  # Add more detailed error info for deeper debugging
                print(f"Traceback: {traceback.format_exc()}")
        return []