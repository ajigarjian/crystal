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
from helpers.stream_analyze import stream_analyze_helper, NumpyEncoder

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
        "https://www.askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"]
    ),
    timeout_sec=10  # Keep timeout short for responsiveness
)
def evaluate_search_query(request):
    """HTTP Cloud Function that evaluates a search query and provides suggestions."""
    
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
        logger.info("Warming request received for evaluate_search_query")
        return https_fn.Response(
            json.dumps({"status": "warmed"}),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    # Get the query parameter
    query = request_json.get('query', '')
    
    if not query:
        return https_fn.Response(
            json.dumps({
                "quality": "typing",
                "rating": 0,
                "message": "Enter a search query",
                "suggestions": []
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    # Get IP-based usage limits
    from helpers.db_utils import check_usage_limit
    
    # Get the client IP address
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = request.remote_addr
    
    # Check if the IP has exceeded the usage limit
    exceeded, error_message = check_usage_limit(ip_address, 'evaluate_search_query')
    if exceeded:
        logger.info(f"Usage limit exceeded for IP {ip_address} on evaluate_search_query")
        return https_fn.Response(
            json.dumps({
                "error": error_message,
                "type": "usage_limit_exceeded",
                "limit_type": "evaluate_search_query"
            }),
            status=429,  # Too Many Requests
            headers={"Content-Type": "application/json"}
        )
    
    # Import the query evaluator
    from factchecker.search.query_processing.query_evaluator import evaluate_query
    
    # Evaluate the query
    start_time = time.time()
    evaluation = evaluate_query(query)
    execution_time = time.time() - start_time
    
    # Add timing information
    evaluation["execution_time"] = execution_time
    
    # Log the response
    logger.info(f"Query evaluation completed in {execution_time:.2f}s for: '{query}'")
    
    return https_fn.Response(
        json.dumps(evaluation),
        status=200,
        headers={"Content-Type": "application/json"}
    )

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://askcrystal.info",
        "https://www.askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post"]
    ),
    memory=options.MemoryOption.GB_2,
    timeout_sec=180, # Let's increase timeout here to 3 mins.
    min_instances=1
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
        
    # Check IP-based usage limits
    from helpers.db_utils import check_usage_limit
    
    # Get the client IP address
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = request.remote_addr
    
    # Check if the IP has exceeded the usage limit
    exceeded, error_message = check_usage_limit(ip_address, 'stream_search_datasets')
    if exceeded:
        logger.info(f"Usage limit exceeded for IP {ip_address} on stream_search_datasets")
        return https_fn.Response(
            json.dumps({
                "error": error_message,
                "type": "usage_limit_exceeded",
                "limit_type": "stream_search_datasets"
            }),
            status=429,  # Too Many Requests
            headers={"Content-Type": "application/json"}
        )
    
    # Get optional parameters with defaults
    similarity_threshold = float(request_json.get('similarity_threshold', 0.3))
    search_method = request_json.get('search_method', None)  # 'vector', 'keyword', or None for hybrid
    max_results = int(request_json.get('max_results', 15))
    census_max_results = int(request_json.get('census_max_results', 5))
    relevance_threshold = float(request_json.get('relevance_threshold', 0.3)) 
    
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
                # Try to parse and handle NaN values properly
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
                    
                # Re-encode with NumpyEncoder to handle NaN values
                chunk = json.dumps(chunk_data, cls=NumpyEncoder)
            except:
                # If parsing fails, leave the chunk as is
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
                
                # Add all search data
                search_data = {
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'search_method': search_method,
                    'similarity_threshold': similarity_threshold,
                    'max_results': max_results,
                    'census_max_results': census_max_results,
                    'relevance_threshold': relevance_threshold,
                    'ip_address': ip_address,
                }
                
                # Add all the result data, not just the metadata
                search_data.update(final_result)
                
                # Save to Firestore
                search_ref.set(search_data)
                
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
            "https://www.askcrystal.info",
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"]
    ),
    memory=options.MemoryOption.MB_512
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
                
                unique_id = int(time.time()) + random.randint(1, 1000)
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
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://www.askcrystal.info",
        "https://askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"],
    ),
    memory=options.MemoryOption.GB_2,
    timeout_sec=300
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
    # Support both formats: dataset_ids array or datasets array of objects
    dataset_ids = []
    
    # If datasets array is provided (array of dataset objects)
    if 'datasets' in request_json:
        datasets = request_json.get('datasets', [])
        logger.info(f"Received {len(datasets)} dataset objects")
        
        # Extract IDs from dataset objects
        dataset_ids = [dataset.get('id') for dataset in datasets if dataset.get('id')]
    else:
        # Get dataset_ids directly if provided in that format
        dataset_ids = request_json.get('dataset_ids', [])
        
    # For backward compatibility, check for single dataset_id as well
    dataset_id = request_json.get('dataset_id', '')
    if dataset_id and not dataset_ids:
        dataset_ids = [dataset_id]
    
    logger.info(f"Processing dataset_ids: {dataset_ids}")
    
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
        
    # Check IP-based usage limits
    from helpers.db_utils import check_usage_limit
    
    # Get the client IP address
    ip_address = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    if not ip_address:
        ip_address = request.remote_addr
    
    # Check if the IP has exceeded the usage limit
    exceeded, error_message = check_usage_limit(ip_address, 'stream_analyze')
    if exceeded:
        logger.info(f"Usage limit exceeded for IP {ip_address} on stream_analyze")
        return https_fn.Response(
            json.dumps({
                "error": error_message,
                "type": "usage_limit_exceeded",
                "limit_type": "stream_analyze"
            }),
            status=429,  # Too Many Requests
            headers={"Content-Type": "application/json"}
        )
    
    logger.info(f"Streaming analysis parameters: dataset_ids={dataset_ids}, query='{query}'")
    
    # Create a generator function that yields analysis results as they come in
    def generate():
        # Initialize a variable to store the final result
        final_result = None
        
        # Initialize tracking stats for datasets
        dataset_stats = {
            "total": len(dataset_ids),
            "queued": 0,
            "downloading": 0,
            "downloaded": 0,
            "loading": 0,
            "loaded": 0,
            "assessing": 0,
            "relevant": 0,
            "not_relevant": 0,
            "extracting": 0,
            "extracted": 0,
            "analyzing": 0,
            "complete": 0,
            "error": 0,
            "dataset_details": {}
        }
        
        # Process the streaming analysis
        for chunk in stream_analyze_helper(
            dataset_ids=dataset_ids,
            query=query,
            file_path=file_path
        ):
            # Track dataset progress through stages
            try:
                chunk_data = json.loads(chunk.strip())
                if chunk_data.get('type') == 'dataset_status':
                    dataset_id = chunk_data.get('dataset_id')
                    status = chunk_data.get('status')
                    
                    # Initialize dataset in tracking if not exists
                    if dataset_id not in dataset_stats["dataset_details"]:
                        dataset_stats["dataset_details"][dataset_id] = {
                            "current_status": None,
                            "statuses_reached": [],
                            "timestamp": chunk_data.get('timestamp', 0)
                        }
                    
                    # Update dataset status in tracking
                    if status:
                        dataset_stats["dataset_details"][dataset_id]["current_status"] = status
                        if status not in dataset_stats["dataset_details"][dataset_id]["statuses_reached"]:
                            dataset_stats["dataset_details"][dataset_id]["statuses_reached"].append(status)
                            dataset_stats[status] = dataset_stats.get(status, 0) + 1
                        dataset_stats["dataset_details"][dataset_id]["timestamp"] = chunk_data.get('timestamp', 0)
                
                # If this is a JSON object and it's the 'complete' type, store it as the final result
                if chunk_data.get('type') == 'complete':
                    final_result = chunk_data.get('data', {})
                    
                    # Add the dataset tracking report
                    dataset_report = create_dataset_progress_report(dataset_stats)
                    tracking_chunk = json.dumps({
                        "type": "dataset_tracking",
                        "data": dataset_stats,
                        "report": dataset_report,
                        "timestamp": chunk_data.get('timestamp', 0)
                    }, cls=NumpyEncoder)
                    yield tracking_chunk + "\n"
                    
                # Re-encode with NumpyEncoder to handle NaN values
                chunk = json.dumps(chunk_data, cls=NumpyEncoder)
            except:
                # If parsing fails, leave the chunk as is
                pass
            
            # Yield the chunk
            yield chunk + "\n"  # Add newline to ensure proper parsing on client side
        
        # If we have a final result, store it in Firestore for later retrieval
        if final_result:
            try:
                # Get a reference to the Firestore database
                db = firestore.client()
                
                # Create a document with the analysis results
                analysis_ref = db.collection('queries').document()
                
                # Add all analysis data
                analysis_data = {
                    'dataset_ids': dataset_ids,
                    'query': query,
                    'timestamp': firestore.SERVER_TIMESTAMP,
                    'file_path': file_path,
                    'ip_address': ip_address,
                    'dataset_stats': dataset_stats
                }
                
                # Add all the result data, not just the metadata
                analysis_data.update(final_result)
                
                # Save to Firestore
                analysis_ref.set(analysis_data)
                
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

def create_dataset_progress_report(dataset_stats):
    """Create a markdown report summarizing the dataset progress through the analysis pipeline."""
    total = dataset_stats["total"]
    
    # Create markdown report
    report = "# Dataset Processing Report\n\n"
    report += f"## Summary\n"
    report += f"Total datasets: {total}\n\n"
    
    # Add stats for each stage
    stages = [
        ("queued", "Datasets queued"),
        ("downloading", "Datasets in downloading state"),
        ("downloaded", "Datasets successfully downloaded"),
        ("loading", "Datasets in loading state"),
        ("loaded", "Datasets successfully loaded"),
        ("assessing", "Datasets in relevance assessment"),
        ("relevant", "Datasets deemed relevant"),
        ("not_relevant", "Datasets deemed not relevant"),
        ("extracting", "Datasets in data extraction"),
        ("extracted", "Datasets with successful extraction"),
        ("analyzing", "Datasets in analysis state"),
        ("complete", "Datasets with completed analysis"),
        ("error", "Datasets with errors")
    ]
    
    report += "## Processing Stages\n"
    for key, label in stages:
        count = dataset_stats.get(key, 0)
        percentage = (count / total * 100) if total > 0 else 0
        report += f"- **{label}**: {count} ({percentage:.1f}%)\n"
    
    # Add details for each dataset
    report += "\n## Dataset Details\n"
    
    # Sort datasets by their progression through the pipeline
    sorted_datasets = sorted(
        dataset_stats["dataset_details"].items(),
        key=lambda x: (
            # First sort by furthest stage reached (using index of status in the stages list)
            max([stage[0] for stage in stages].index(status) if status in [s[0] for s in stages] else -1 
                for status in x[1]["statuses_reached"]),
            # Then by timestamp (most recent first)
            x[1]["timestamp"]
        ),
        reverse=True
    )
    
    for dataset_id, details in sorted_datasets:
        status = details["current_status"] or "unknown"
        statuses = ", ".join(details["statuses_reached"])
        report += f"- **Dataset {dataset_id[:8]}...**: Current status: `{status}`, Stages reached: `{statuses}`\n"
    
    # Add data quality analysis
    report += "\n## Data Flow Analysis\n"
    if dataset_stats.get("downloaded", 0) > 0:
        download_success_rate = (dataset_stats.get("downloaded", 0) / dataset_stats.get("queued", 1)) * 100
        report += f"- **Download success rate**: {download_success_rate:.1f}%\n"
    
    if dataset_stats.get("relevant", 0) + dataset_stats.get("not_relevant", 0) > 0:
        relevance_rate = (dataset_stats.get("relevant", 0) / 
                          (dataset_stats.get("relevant", 0) + dataset_stats.get("not_relevant", 0))) * 100
        report += f"- **Relevance rate**: {relevance_rate:.1f}%\n"
    
    if dataset_stats.get("extracted", 0) > 0 and dataset_stats.get("relevant", 0) > 0:
        extraction_success_rate = (dataset_stats.get("extracted", 0) / dataset_stats.get("relevant", 0)) * 100
        report += f"- **Extraction success rate**: {extraction_success_rate:.1f}%\n"
    
    if dataset_stats.get("complete", 0) > 0 and dataset_stats.get("extracted", 0) > 0:
        analysis_success_rate = (dataset_stats.get("complete", 0) / dataset_stats.get("extracted", 0)) * 100
        report += f"- **Analysis success rate**: {analysis_success_rate:.1f}%\n"
    
    # Calculate overall pipeline efficiency
    if dataset_stats.get("complete", 0) > 0 and total > 0:
        pipeline_efficiency = (dataset_stats.get("complete", 0) / total) * 100
        report += f"- **Overall pipeline efficiency**: {pipeline_efficiency:.1f}%\n"
    
    return report

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://askcrystal.info",
        "https://www.askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"]
    ),
    memory=options.MemoryOption.MB_512
)
def submit_feedback(request):
    """HTTP Cloud Function that submits user feedback to the database using raw SQL."""
    logger.info("Starting submit_feedback function")

    # Parse the request data from bytes to JSON
    try:
        if request.data:
            logger.info(f"Request data: {request.data}")
            data = json.loads(request.data)
        else:
            data = {}
            logger.info("No request data")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON data: {str(e)}")
        return https_fn.Response(
            json.dumps({"error": "Invalid JSON data", "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    # Handle warming requests quickly
    if data.get('warming'):
        logger.info("Warming request received for submit_feedback")
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

    # Extract required fields
    feedback_type = data.get('feedback_type', '')
    title = data.get('title', '')
    description = data.get('description', '')
    
    # Extract optional fields
    email = data.get('email', None)
    page_url = data.get('page_url', '')
    tags = data.get('tags', [])  # Default to empty array
    metadata = data.get('metadata', {})  # Default to empty object
    
    logger.info(f"Received feedback submission: type={feedback_type}, title={title}")

    # Validate required fields
    if not feedback_type or not title or not description:
        error_msg = "Required fields missing: feedback_type, title, and description are required"
        logger.error(error_msg)
        return https_fn.Response(
            json.dumps({"error": error_msg, "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    # Validate feedback type
    valid_types = ['suggestion', 'bug', 'feature_request', 'praise']
    if feedback_type not in valid_types:
        error_msg = f"Invalid feedback type. Must be one of: {', '.join(valid_types)}"
        logger.error(error_msg)
        return https_fn.Response(
            json.dumps({"error": error_msg, "status": "error"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )

    try:
        # Get connection from pool
        logger.info("Getting database connection")
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Modified unique ID generation to stay within PostgreSQL integer range
                unique_id = int(time.time()) + random.randint(1, 1000)
                logger.info(f"Generated unique ID: {unique_id}")
                
                # Convert metadata to JSON string
                metadata_json = json.dumps(metadata)
                
                # Get current timestamp
                current_time = datetime.now().isoformat()
                
                # Log the SQL operation for debugging
                logger.info(f"Inserting feedback record with ID: {unique_id}")
                
                # Execute the raw SQL insert statement
                cursor.execute(
                    """
                    INSERT INTO factchecker_feedback 
                    (id, feedback_type, title, description, email, page_url, tags, metadata, status, created_at, updated_at, upvotes) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        unique_id, 
                        feedback_type,
                        title,
                        description,
                        email,
                        page_url,
                        tags if tags else [], # Ensure empty list, not None
                        metadata_json,
                        'new',  # status
                        current_time,
                        current_time,
                        0  # upvotes
                    )
                )
                
                # Commit the transaction
                conn.commit()
                logger.info(f"Successfully added feedback with ID: {unique_id}")
                
                # Return success response
                return https_fn.Response(
                    json.dumps({
                        "status": "success",
                        "message": "Feedback submitted successfully",
                        "id": unique_id
                    }),
                    status=200, # Use 200 to match register_waitlist
                    headers={"Content-Type": "application/json"}
                )
        except Exception as db_error:
            # Log the database error and roll back any changes
            logger.error(f"Database error in submit_feedback: {db_error}")
            logger.error(traceback.format_exc())
            conn.rollback()
            raise
        finally:
            # Always return the connection to the pool
            pool.putconn(conn)
    except Exception as e:
        # Handle any other exceptions
        logger.error(f"Error submitting feedback: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"status": "error", "message": f"Failed to submit feedback: {str(e)}"}),
            status=500,
            headers={"Content-Type": "application/json"}
        )