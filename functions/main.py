import os
import django
from django.conf import settings

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factchecker.settings")

# Initialize Django
django.setup()

from firebase_functions import https_fn, options
from firebase_admin import initialize_app, firestore
import requests
from datetime import datetime
import firebase_admin
import logging
import time
import json
import traceback
import numpy as np
import concurrent.futures
from threading import Lock
import random
import django

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# turn on emulator
if os.getenv('FUNCTIONS_EMULATOR'):
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'factchecker.settings')

# Set up Django with error handling for database connection
try:
    django.setup()
except Exception as django_setup_error:
    logger = logging.getLogger(__name__)
    logger.error(f"Error in django.setup(): {django_setup_error}")
    
    # If running in production and error might be related to database connection
    if not os.getenv('FUNCTIONS_EMULATOR') and 'database' in str(django_setup_error).lower():
        try:
            # Import settings to access the fallback configuration
            from factchecker import settings
            
            # Apply fallback database configuration
            if hasattr(settings, 'DB_FALLBACK'):
                logger.info("Attempting to use fallback database configuration")
                settings.DATABASES = settings.DB_FALLBACK
                
                # Retry Django setup with fallback configuration
                django.setup()
        except Exception as fallback_error:
            logger.error(f"Fallback configuration also failed: {fallback_error}")
            raise

# After Django is set up, import helpers that might use Django models
from helpers.db_utils import execute_query, get_db_connection, get_connection_pool
from helpers.stream_search_datasets import stream_search_datasets_helper
from helpers.stream_analyze import stream_analyze_helper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase app
firebase_admin.initialize_app()

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post"],
    ),
    memory=options.MemoryOption.MB_512
)
def stream_search_datasets(request):
    """HTTP Cloud Function that streams dataset search results."""

    # Initialize db
    db = firestore.client()
    
    # Parse request data
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return https_fn.Response(
            json.dumps({"error": "No JSON data provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
        # Handle warming requests quickly
    if request_json.get('warming'):
        logger.info("Warming request received for stream_search_datasets")
        return https_fn.Response(
            json.dumps({"status": "warmed"}),
            status=200,
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
    relevance_threshold = 0.35 #hardcoded for now #float(request_json.get('relevance_threshold', 0.3)) 
    
    logger.info(f"Streaming search parameters: method={search_method}, threshold={similarity_threshold}, max_results={max_results}")
    
    # Create a generator function that yields dataset results as they come in
    def generate():
        # Initialize a variable to store the final result
        final_result = None
        
        # Process the streaming search
        for chunk in stream_search_datasets_helper(
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
            yield chunk + "\n"  # Add newline to ensure proper parsing on client side
        
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Get a reference to the Firestore database
                db = firestore.client()
                
                # Create a document with the search results
                search_ref = db.collection('queries').document()
                
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
        cors_origins=[
            "https://crystal-2f87e.web.app",
            "https://askcrystal.info",
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"]
    )
)
def register_waitlist(request):
    """HTTP Cloud Function that registers a user to the waitlist."""
    logger.info("Starting register_waitlist function")

    # Parse the request data from bytes to JSON
    try:
        if request.data:
            data = json.loads(request.data)
        else:
            data = {}
    except json.JSONDecodeError:
        logger.error("Invalid JSON data")
        return https_fn.Response(
            json.dumps({"error": "Invalid JSON data", "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Handle warming requests quickly
    if data.get('warming'):
        logger.info("Warming request received for register_waitlist")
        return https_fn.Response(
            json.dumps({"status": "warmed"}),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    if not data:
        logger.error("No data provided")
        return https_fn.Response(
            json.dumps({"error": "No data provided", "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    email = data.get('email', '')
    first_name = data.get('first_name', '')
    logger.info(f"Received registration request for email: {email}, first_name: {first_name}")

    if not email:
        logger.error("Email is required but was not provided")
        return https_fn.Response(
            json.dumps({"error": "Email is required", "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    try:
        # Get connection from pool
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Use a prepared statement for better performance
                cursor.execute("SELECT id FROM factchecker_waitlistentry WHERE email = %s", (email,))
                existing = cursor.fetchone()
                
                if existing:
                    logger.info(f"Email {email} already registered with ID: {existing[0]}")
                    return https_fn.Response(
                        json.dumps({"error": "This email is already registered", "status": "error"}),
                        status=400,
                        headers={"Content-Type": "application/json"}
                    )
                
                unique_id = int(time.time() * 1000) + random.randint(1, 1000)
                cursor.execute(
                    """
                    INSERT INTO factchecker_waitlistentry (id, email, first_name, created_at) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (unique_id, email, first_name, datetime.now().isoformat())
                )
                
                conn.commit()
                logger.info(f"Added user to waitlist: {email} with ID: {unique_id}")
                
                return https_fn.Response(
                    json.dumps({
                        "status": "success",
                        "message": "Successfully added to waitlist",
                        "id": unique_id
                    }),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            conn.rollback()
            raise
        finally:
            # Return connection to the pool instead of closing it
            pool.putconn(conn)
    except Exception as e:
        logger.error(f"Error registering for waitlist: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Failed to register: {str(e)}"}),
            status=500,
            headers={"Content-Type": "application/json"}
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
        # Test the low-level database connection first
        conn = get_db_connection()
        
        # Execute a simple query
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 as connection_test")
            psycopg_result = cursor.fetchone()
        
        conn.close()
        
        # Now test Django's connection
        from django.db import connection
        from django.conf import settings
        
        # Get current Django database settings
        db_settings = settings.DATABASES['default']
        connection_type = "Unix Socket" if '/cloudsql' in str(db_settings.get('HOST', '')) else "TCP/IP"
        is_emulator = os.getenv('FUNCTIONS_EMULATOR') == 'true'
        
        # Execute a query using Django's connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 as django_test")
            django_result = cursor.fetchone()[0]
        
        return https_fn.Response(
            json.dumps({
                "status": "success",
                "message": "Database connection successful",
                "direct_connection": {
                    "result": psycopg_result
                },
                "django_connection": {
                    "result": django_result,
                    "connection_type": connection_type,
                    "environment": "emulator" if is_emulator else "production",
                    "engine": db_settings.get('ENGINE'),
                    "host": db_settings.get('HOST')
                }
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({
                "status": "error",
                "message": f"Database connection failed: {str(e)}",
                "traceback": traceback.format_exc(),
                "environment": "emulator" if os.getenv('FUNCTIONS_EMULATOR') == 'true' else "production"
            }),
            status=500,
            headers={"Content-Type": "application/json"}
        )
    

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"],
    ),
    memory=options.MemoryOption.GB_4
)
def stream_analyze(request):
    """HTTP Cloud Function that streams dataset analysis results."""

    # Initialize db
    db = firestore.client()
    
    # Parse request data
    request_json = request.get_json(silent=True)
    
    if not request_json:
        return https_fn.Response(
            json.dumps({"error": "No JSON data provided"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Handle warming requests quickly
    if request_json.get('warming'):
        logger.info("Warming request received for stream_analyze")
        return https_fn.Response(
            json.dumps({"status": "warmed"}),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    # Get the required parameters
    dataset_ids = request_json.get('dataset_ids', [])
    # For backward compatibility, check for single dataset_id as well
    dataset_id = request_json.get('dataset_id', '')
    if dataset_id and not dataset_ids:
        dataset_ids = [dataset_id]
    
    query = request_json.get('query', '')
    
    # Optional file path parameter
    file_path = request_json.get('file_path', None)
    
    # Validate required parameters
    if not dataset_ids:
        return https_fn.Response(
            json.dumps({"error": "At least one dataset ID is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    if not query:
        return https_fn.Response(
            json.dumps({"error": "Query is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    logger.info(f"Streaming analysis parameters: dataset_ids={dataset_ids}, query='{query}'")
    
    # Create a generator function that yields analysis results as they come in
    def generate():
        # Initialize a variable to store the final result
        final_result = None
        
        # Process the streaming analysis
        for chunk in stream_analyze_helper(
            dataset_ids=dataset_ids,
            query=query,
            file_path=file_path
        ):
            # If this is a JSON object and it's the 'complete' type, store it as the final result
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
            except:
                pass
            
            # Yield the chunk in SSE format with "data:" prefix
            yield f"data: {chunk}\n"
        
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Get a reference to the Firestore database
                db = firestore.client()
                
                # Create a document with the analysis results
                analysis_ref = db.collection('analyses').document()
                
                # Add the analysis data
                analysis_ref.set({
                    'dataset_ids': dataset_ids,
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'results': final_result
                })
                
                logger.info(f"Stored analysis results in Firestore with ID: {analysis_ref.id}")
            except Exception as e:
                logger.error(f"Error storing analysis results in Firestore: {e}")
    
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
