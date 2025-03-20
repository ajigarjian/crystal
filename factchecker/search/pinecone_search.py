"""
This module provides Pinecone-powered vector search functionality for datasets.

It includes:
1. PineconeSearcher class - Connects to a Pinecone index and performs fast similarity searches
2. vector_search_datasets_pinecone function - A drop-in replacement for vector search using Pinecone
3. migrate_faiss_to_pinecone function - Utility to migrate existing FAISS index to Pinecone

The interface matches the existing vector search implementation, making it easy to switch between
implementations without changing other code.
"""

import os
import pickle
import numpy as np
import threading
from typing import List, Dict, Any, Optional
from django.conf import settings
from factchecker.models import DatasetCatalog
from factchecker.utils.openai_client import create_embeddings
from factchecker.search.search_utils import get_usable_resources

# Import pinecone
import pinecone

# Add a lock for thread-safe initialization
_SEARCHER_LOCK = threading.Lock()
_GLOBAL_PINECONE_SEARCHER = None

def get_pinecone_searcher():
    """Get or create a global PineconeSearcher instance in a thread-safe manner"""
    global _GLOBAL_PINECONE_SEARCHER
    
    # First check without the lock for efficiency
    if _GLOBAL_PINECONE_SEARCHER is None:
        # If it's None, acquire the lock and check again
        with _SEARCHER_LOCK:
            # Double-check after acquiring the lock
            if _GLOBAL_PINECONE_SEARCHER is None:
                print("Initializing Pinecone connection (one-time operation)")
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
        # Get API key and environment from settings or environment variables
        self.api_key = api_key or settings.PINECONE_API_KEY or os.environ.get("PINECONE_API_KEY")
        self.environment = environment or os.environ.get("PINECONE_ENVIRONMENT")
        
        if not self.api_key or not self.environment:
            raise ValueError(
                "Pinecone API key and environment must be provided either as parameters, "
                "in Django settings, or as environment variables."
            )
        
        # Initialize Pinecone
        pinecone.init(api_key=self.api_key, environment=self.environment)
        
        # Connect to the index
        self.index_name = index_name
        if self.index_name not in pinecone.list_indexes():
            raise ValueError(
                f"Pinecone index '{self.index_name}' not found. "
                "Run 'python manage.py migrate_to_pinecone' first."
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
                dataset = DatasetCatalog.objects.get(dataset_id=result['dataset_id'])
                
                # Get usable resources
                resources = get_usable_resources(result['dataset_id'])
                
                # Only include datasets with usable resources
                if resources:
                    formatted_results.append({
                        "id": result['dataset_id'],
                        "title": dataset.title,
                        "description": dataset.notes if dataset.notes else "",
                        "organization": dataset.organization_title,
                        "similarity": result['score'],
                        "resources": resources,
                        "search_source": "vector"
                    })
            except DatasetCatalog.DoesNotExist:
                # Skip datasets that no longer exist
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
                print("Initializing Pinecone client (one-time operation)")
                
                # Get API key and environment from settings or environment variables
                api_key = settings.PINECONE_API_KEY or os.environ.get("PINECONE_API_KEY")
                
                if not api_key:
                    raise ValueError(
                        "Pinecone API key must be provided in Django settings or as environment variables."
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
            print("Starting Pinecone vector search process...")
            
        # Create embeddings for the query
        query_embedding = create_embeddings(query)
        
        # Get the global Pinecone client (initialized only once)
        pc = get_pinecone_client()
        
        # Get index name from settings or use default
        index_name = getattr(settings, "PINECONE_INDEX_NAME", "dataset-embeddings")
        
        # Check if index exists
        existing_indexes = [index.name for index in pc.list_indexes()]
        if index_name not in existing_indexes:
            if verbose:
                print(f"Pinecone index '{index_name}' not found. Please run 'python manage.py migrate_to_pinecone' first.")
            return []
        
        # Connect to the index
        index = pc.Index(index_name)
        
        if verbose:
            print(f"Searching for top {top_k} matches with similarity threshold {similarity_threshold}...")
        
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
            print(f"Found {len(filtered_matches)} raw matches with similarity >= {similarity_threshold}")
            print("Checking for usable resources...")
        
        # Get dataset IDs for batch database query
        dataset_ids = [match.id for match in filtered_matches]
        
        # Get all datasets in one query
        datasets = {d.dataset_id: d for d in DatasetCatalog.objects.filter(dataset_id__in=dataset_ids)}
        
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
                    "title": dataset.title,
                    "description": dataset.notes if dataset.notes else "",
                    "organization": dataset.organization_title,
                    "similarity": similarity,
                    "resources": resources,
                    "search_source": "vector"
                })
        
        if verbose:
            print(f"Found {len(formatted_results)} datasets with usable resources (limited to top {top_k})")
        
        # If we have results above threshold, return them
        if formatted_results:
            return formatted_results
            
        # If no datasets meet the threshold, try to find at least one with a lower threshold
        if not formatted_results and similarity_threshold > 0.1:
            if verbose:
                print("No datasets meet the threshold. Trying with lower threshold...")
            
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
                        "title": dataset.title,
                        "description": dataset.notes if dataset.notes else "",
                        "organization": dataset.organization_title,
                        "similarity": match.score,
                        "resources": resources,
                        "search_source": "vector"
                    }
                    if verbose:
                        print(f"Found top dataset with similarity {match.score:.4f}: {dataset.title}")
                    return [formatted_result]
                
        # If we get here, no datasets have usable resources
        if verbose:
            print("No datasets with usable resources found.")
        return []
        
    except Exception as e:
        print(f"Error searching with query '{query}': {e}")
        return []

def migrate_faiss_to_pinecone(
    faiss_index_dir: str = 'faiss_index',
    pinecone_api_key: Optional[str] = None,
    pinecone_environment: Optional[str] = None,
    pinecone_index_name: str = "dataset-embeddings",
    dimension: int = 1536,  # OpenAI embedding dimension
    batch_size: int = 100,
    cloud_provider: str = "aws"  # Default cloud provider
) -> None:
    """
    Migrate a FAISS index to Pinecone using embeddings from the database
    
    Args:
        faiss_index_dir: Directory containing the FAISS index files
        pinecone_api_key: Pinecone API key
        pinecone_environment: Pinecone environment
        pinecone_index_name: Name for the new Pinecone index
        dimension: Vector dimension (1536 for OpenAI embeddings)
        batch_size: Number of vectors to upload in each batch
        cloud_provider: Cloud provider for Pinecone (aws, gcp, or azure)
    """
    import faiss
    from factchecker.models import DatasetCatalog
    
    # Get API key and environment from settings or environment variables
    api_key = pinecone_api_key or settings.PINECONE_API_KEY or os.environ.get("PINECONE_API_KEY")
    environment = pinecone_environment or settings.PINECONE_ENVIRONMENT or os.environ.get("PINECONE_ENVIRONMENT")
    
    if not api_key or not environment:
        raise ValueError(
            "Pinecone API key and environment must be provided either as parameters, "
            "in Django settings, or as environment variables."
        )
    
    # Default to the project's base directory + faiss_index if path is not absolute
    if not os.path.isabs(faiss_index_dir):
        base_dir = settings.BASE_DIR
        faiss_index_dir = os.path.join(base_dir, faiss_index_dir)
        
    # Check if dataset_ids file exists
    ids_path = os.path.join(faiss_index_dir, 'dataset_ids.pkl')
    
    if not os.path.exists(ids_path):
        raise FileNotFoundError(
            f"Dataset IDs file not found at {ids_path}. "
            "Run 'python manage.py build_faiss_index' first."
        )
    
    print(f"Loading dataset IDs from {ids_path}...")
    
    # Load dataset IDs
    with open(ids_path, 'rb') as f:
        dataset_ids = pickle.load(f)
    
    print(f"Loaded {len(dataset_ids)} dataset IDs")
    
    # Fetch embeddings directly from the database
    print("Fetching embeddings from database...")
    
    # Process dataset IDs in smaller batches to avoid SQLite limitations
    db_batch_size = 500  # SQLite typically has a limit of 999 variables
    embeddings_map = {}
    missing_count = 0
    
    for i in range(0, len(dataset_ids), db_batch_size):
        batch_end = min(i + db_batch_size, len(dataset_ids))
        batch_ids = dataset_ids[i:batch_end]
        
        print(f"Processing database batch {i//db_batch_size + 1}/{(len(dataset_ids) + db_batch_size - 1)//db_batch_size}: IDs {i} to {batch_end-1}")
        
        # Get datasets for this batch
        batch_datasets = DatasetCatalog.objects.filter(
            dataset_id__in=batch_ids, 
            indexed=True
        ).exclude(embedding=None)
        
        # Add embeddings to the map
        for dataset in batch_datasets:
            # Convert binary embedding to numpy array
            embedding = np.frombuffer(dataset.embedding, dtype=np.float32)
            embeddings_map[dataset.dataset_id] = embedding
        
        # Count missing embeddings in this batch
        batch_missing = set(batch_ids) - set(d.dataset_id for d in batch_datasets)
        missing_count += len(batch_missing)
    
    print(f"Found {len(embeddings_map)} embeddings in the database")
    
    # Check if we found all embeddings
    if missing_count > 0:
        print(f"Warning: {missing_count} datasets don't have embeddings in the database")
    
    # Prepare vectors and IDs for Pinecone
    print("Preparing vectors for Pinecone...")
    vectors = []
    final_ids = []
    
    for dataset_id in dataset_ids:
        if dataset_id in embeddings_map:
            vectors.append(embeddings_map[dataset_id])
            final_ids.append(dataset_id)
    
    print(f"Prepared {len(vectors)} vectors for upload to Pinecone")
    
    # Initialize Pinecone with the new API
    print(f"Initializing Pinecone with API key {api_key[:4]}...{api_key[-4:]} and environment {environment}...")
    from pinecone import Pinecone, ServerlessSpec
    
    # Create Pinecone client
    pc = Pinecone(api_key=api_key)
    
    # Parse region from environment string (typically format like "us-east-1")
    region = environment
    
    # Check if index exists
    existing_indexes = [index.name for index in pc.list_indexes()]
    if pinecone_index_name not in existing_indexes:
        print(f"Creating new Pinecone index '{pinecone_index_name}' with dimension {dimension}...")
        print(f"Using cloud provider: {cloud_provider}, region: {region}")
        
        # Create a new serverless index
        pc.create_index(
            name=pinecone_index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=cloud_provider,
                region=region
            )
        )
    else:
        print(f"Pinecone index '{pinecone_index_name}' already exists.")
    
    # Connect to the index
    index = pc.Index(pinecone_index_name)
    
    # Upload vectors in batches
    print(f"Uploading {len(vectors)} vectors to Pinecone in batches of {batch_size}...")
    
    for i in range(0, len(vectors), batch_size):
        batch_end = min(i + batch_size, len(vectors))
        batch_ids = final_ids[i:batch_end]
        batch_vectors = vectors[i:batch_end]
        
        # Create vector records
        vector_batch = [
            {"id": str(id), "values": vec.tolist()} 
            for id, vec in zip(batch_ids, batch_vectors)
        ]
        
        # Upsert to Pinecone
        index.upsert(vectors=vector_batch)
        
        print(f"Uploaded batch {i//batch_size + 1}/{(len(vectors) + batch_size - 1)//batch_size}: vectors {i} to {batch_end-1}")
    
    print(f"Migration complete! {len(vectors)} vectors uploaded to Pinecone index '{pinecone_index_name}'")
    print("You can now use PineconeSearcher for vector search.")