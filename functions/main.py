from firebase_functions import https_fn, options
from firebase_admin import initialize_app, firestore
import requests
from datetime import datetime
import firebase_admin
import os
import logging
import time
import json
import traceback
import numpy as np
import concurrent.futures
from threading import Lock
import psycopg2
from psycopg2.extras import RealDictCursor

from helpers import search_helpers

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# turn on emulator
if os.getenv('FUNCTIONS_EMULATOR'):
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase app
firebase_admin.initialize_app()

# PostgreSQL connection configuration
def get_db_connection():
    """Create and return a connection to the PostgreSQL database"""
    try:
        # Check if running in production or local environment
        if os.getenv('FUNCTIONS_EMULATOR'):
            # Local development - connect via local Cloud SQL Proxy
            conn = psycopg2.connect(
                host=os.environ.get('DB_HOST', 'localhost'),
                database=os.environ.get('DB_NAME'),
                user=os.environ.get('DB_USER'),
                password=os.environ.get('DB_PASSWORD'),
                port=os.environ.get('DB_PORT', 1234)
            )
        else:
            # Production environment - use Unix socket
            db_instance = os.environ.get('DB_INSTANCE')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = os.environ.get('DB_PASSWORD')
            
            # Unix socket path for Cloud SQL
            socket_dir = os.environ.get('DB_SOCKET_DIR', '/cloudsql')
            unix_socket = f'{socket_dir}/{db_instance}'
            
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_user,
                password=db_password,
                host=unix_socket  # Use Unix socket in production
            )
        
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def execute_query(query, params=None, fetch_all=True):
    """Execute a query and return results"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            if fetch_all:
                return cursor.fetchall()
            else:
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Helper functions for dataset search and processing
def vector_search_datasets(query, similarity_threshold=0.3, max_results=15):
    """
    Placeholder for vector search function - replace with actual implementation
    """
    # This would call your actual vector search implementation
    # For now, return empty list as placeholder
    logger.info(f"Vector search called with query: {query}")
    return []

def search_datasets(query, api_key, similarity_threshold=0.5):
    """
    Placeholder for keyword search function - replace with actual implementation
    """
    # This would call your actual keyword search implementation
    # For now, return empty list as placeholder
    logger.info(f"Keyword search called with query: {query}")
    return []

def process_census_query(query):
    """
    Placeholder for census query processing - replace with actual implementation
    """
    # Extract structured info from query for Census search
    # Return empty dict as placeholder
    return {}

def census_vector_search(query, similarity_threshold=0.3, year=None, tags=None, 
                         geo_level=None, location=None, max_results=5, verbose=False):
    """
    Placeholder for census vector search - replace with actual implementation
    """
    # This would call your actual census search implementation
    # For now, return empty list as placeholder
    logger.info(f"Census search called with query: {query}")
    return []

def single_search(query, search_function, similarity_threshold=0.3, max_results=15, verbose=False):
    """
    Placeholder for single search function - replace with actual implementation
    """
    # This would call your actual search implementation
    # For now, return empty list as placeholder
    return []

def assess_datafile_relevance_predownload(query, dataset, relevance_threshold=0.4):
    """
    Placeholder for relevance assessment - replace with actual implementation
    """
    # This would call your actual relevance assessment
    # For now, return mock values
    is_relevant = True
    relevance_score = 0.8
    reasoning = f"This dataset appears to be relevant to your query about '{query}'."
    return is_relevant, relevance_score, reasoning



@https_fn.on_call(
    cors=options.CorsOptions(
        cors_origins=[
            "https://crystal-2f87e.web.app/",
            "http://localhost:5173"  
            ],
        cors_methods=["get", "post"],
    )
)
def handle_crystal_request(request):
    """HTTP Cloud Function that handles dataset search requests."""
    logger.info("Function called with data: %s", request.data)
    
    # Get the query parameter
    query = request.data.get('query', '')
    
    if not query:
        return {"error": "Query is required", "status": "error"}
    
    # Get optional parameters with defaults
    similarity_threshold = float(request.data.get('similarity_threshold', 0.3))
    search_method = request.data.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request.data.get('max_results', 15))
    census_max_results = int(request.data.get('census_max_results', 5))
    relevance_threshold = float(request.data.get('relevance_threshold', 0.4))
    
    logger.info(f"Search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Process the search and return the final result
    try:
        # In a real implementation, you would call your actual search functions here
        # For now, we'll return a mock response
        return {
            "status": "success", 
            "message": "Search completed successfully", 
            "query": query,
            "execution_time": 1.5,
            "total_count": 3,
            "datasets": [
                {
                    "id": "mock-dataset-1",
                    "title": "Sample Dataset 1",
                    "description": "This is a sample dataset for testing",
                    "similarity": 0.85,
                    "relevance_score": 0.85,
                    "is_relevant": True
                },
                {
                    "id": "mock-dataset-2",
                    "title": "Sample Dataset 2",
                    "description": "Another sample dataset for testing",
                    "similarity": 0.75,
                    "relevance_score": 0.75,
                    "is_relevant": True
                },
                {
                    "id": "mock-dataset-3",
                    "title": "Sample Dataset 3",
                    "description": "A third sample dataset for testing",
                    "similarity": 0.65,
                    "relevance_score": 0.65,
                    "is_relevant": True
                }
            ]
        }
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        logger.error(traceback.format_exc())
        return {"status": "error", "error": str(e)}

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get", "post"],
    )
)
def stream_search_datasets(request):
    """HTTP Cloud Function that streams dataset search results."""
    # Parse request data
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return https_fn.Response(
            json.dumps({"error": "No JSON data provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Get the query parameter
    query = request_json.get('query', '')
    
    if not query:
        return https_fn.Response(
            json.dumps({"error": "Query is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Get optional parameters with defaults
    similarity_threshold = float(request_json.get('similarity_threshold', 0.3))
    search_method = request_json.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request_json.get('max_results', 15))
    census_max_results = int(request_json.get('census_max_results', 5))
    relevance_threshold = float(request_json.get('relevance_threshold', 0.4))
    
    logger.info(f"Streaming search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Create a generator function that yields dataset results as they come in
    def generate():
        # Initialize a variable to store the final result
        final_result = None
        
        # Process the streaming search
        for chunk in search_helpers.stream_search_datasets_helper(
            query=query,
            similarity_threshold=similarity_threshold,
            search_method=search_method,
            max_results=max_results,
            census_max_results=census_max_results,
            relevance_threshold=relevance_threshold
        ):
            # If this is a JSON object and it's the 'complete' type, store it as the final result
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
            except:
                pass
            
            # Yield the chunk
            yield chunk
        
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Get a reference to the Firestore database
                db = firestore.client()
                
                # Create a document with the search results
                search_ref = db.collection('searches').document()
                
                # Add the search data
                search_ref.set({
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'results': final_result
                })
                
                logger.info(f"Stored search results in Firestore with ID: {search_ref.id}")
            except Exception as e:
                logger.error(f"Error storing results in Firestore: {e}")
    
    # Create and return the streaming response
    return https_fn.Response(
        generate(),
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=["*"],
        cors_methods=["get", "post"],
    )
)
def test_db_connection(request):
    """HTTP Cloud Function that tests database connection."""
    try:
        # Try to connect to the database
        conn = get_db_connection()
        
        # Execute a simple query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 as connection_test")
            result = cursor.fetchone()
        
        conn.close()
        
        return https_fn.Response(
            json.dumps({
                "status": "success",
                "message": "Database connection successful",
                "result": result
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return https_fn.Response(
            json.dumps({
                "status": "error",
                "message": f"Database connection failed: {str(e)}"
            }),
            status=500,
            headers={"Content-Type": "application/json"}
        )