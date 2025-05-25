import os
import django
from django.conf import settings
import decimal # Add import for decimal
import math # Add import for math

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factchecker.settings")

# Initialize Django
django.setup()

from firebase_functions import https_fn, options
from firebase_admin import initialize_app, firestore
import requests
from datetime import datetime, timedelta, timezone
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
from helpers.db_utils import execute_query, get_connection_pool, check_usage_limit
from helpers.stream_search_datasets import stream_search_datasets_helper
from helpers.stream_analyze import stream_analyze_helper, NumpyEncoder
# Import the query evaluator at the top level
from factchecker.search.query_processing.query_evaluator import evaluate_query

# Import the new helper modules for the inflow forecast
from helpers.forecast_db_utils import write_run_header, write_forecast_rows
from helpers.inflow_model_v0 import run_inflow_forecast as run_inflow_forecast_v0


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase app
firebase_admin.initialize_app()

# Metric configuration for the dashboard cards
# Maps card titles to their corresponding metric_id in the fact_dam_ops table
# and a default unit/trend description.
METRICS_CONFIG = {
    "Headroom": {"metric_id": 3, "unit": "ft", "default_trend_desc": "Stable"},
    "Reservoir Fill": {"metric_id": 5, "unit": "%", "default_trend_desc": "Steady"},
    "Inflow": {"metric_id": 6, "unit": "cfs", "default_trend_desc": "Constant"},
    "Spill %": {"metric_id": 9, "unit": "%", "default_trend_desc": "No change"}, # Changed from Spill to Spill % to match ID
    "Spill": {"metric_id": 8, "unit": "cfs", "default_trend_desc": "None"}, # Changed from Spill % to Spill
    "Gates Open": {"metric_id": 10, "unit": "gates", "default_trend_desc": "Unchanged"}
}

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
            "https://crystal-2f87e.web.app",
            "https://askcrystal.info",
            "https://www.askcrystal.info",
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        cors_methods=["get", "options"] # Primarily a GET request
    ),
    timeout_sec=30,
    memory=options.MemoryOption.MB_512
)
def get_dam_locations(request: https_fn.Request) -> https_fn.Response:
    logger.info("Received request for dam locations.")

    # Handle warming requests (optional but good practice)
    if request.method == 'POST': # Warming often sent as POST
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_dam_locations.")
                return https_fn.Response(json.dumps({"status": "warmed"}), status=200, headers={"Content-Type": "application/json"})
        except Exception:
             # If JSON parsing fails or not a warming request, proceed normally
            pass

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        dam_locations_list = []
        try:
            with conn.cursor() as cursor:
                # Query to get dam_id, dam_name, latitude, and longitude from dim_dam
                # Filters out rows where latitude or longitude is NULL
                query_sql = """
                    SELECT dam_id, dam_name, latitude, longitude 
                    FROM dim_dam 
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
                """
                cursor.execute(query_sql)
                rows = cursor.fetchall()
                
                for row_data in rows:
                    dam_id, dam_name_val, lat_val, lon_val = row_data
                    
                    current_dam_lat = None
                    current_dam_lon = None
                    
                    try:
                        # Ensure latitude and longitude are converted to float
                        if lat_val is not None:
                            current_dam_lat = float(lat_val)
                        if lon_val is not None:
                            current_dam_lon = float(lon_val)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not convert lat/lon for dam_id {dam_id} (name: {dam_name_val}). Error: {e}. Skipping this dam.")
                        continue # Skip this dam if coordinates are invalid
                    
                    # Only add if both latitude and longitude are valid numbers
                    if current_dam_lat is not None and current_dam_lon is not None:
                        dam_locations_list.append({
                            "id": dam_id,
                            "name": dam_name_val,
                            "latitude": current_dam_lat,
                            "longitude": current_dam_lon
                        })
            
            return https_fn.Response(
                json.dumps(dam_locations_list),
                status=200,
                headers={"Content-Type": "application/json"}
            )
        except Exception as db_error:
            logger.error(f"Database error in get_dam_locations: {db_error}")
            logger.error(traceback.format_exc())
            if conn: conn.rollback() # Rollback in case of error during transaction
            return https_fn.Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                headers={"Content-Type": "application/json"}
            )
        finally:
            if conn:
                pool.putconn(conn) # Return connection to the pool
    except Exception as e:
        logger.error(f"General error in get_dam_locations: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"error": "An internal server error occurred.", "details": str(e)}),
            status=500,
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
        cors_methods=["get", "post", "options"]
    ),
    timeout_sec=20,  # Keep timeout short for responsiveness
    min_instances=1,
    memory=options.MemoryOption.MB_512 # Increase memory
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
    
    # Return early for very short queries
    MIN_QUERY_LENGTH = 3
    if len(query) < MIN_QUERY_LENGTH:
        return https_fn.Response(
            json.dumps({
                "quality": "typing",
                "rating": 0,
                "message": f"Keep typing...", # Suggest continuing typing
                "suggestions": []
            }),
            status=200,
            headers={"Content-Type": "application/json"}
        )
    
    # Get IP-based usage limits
    # from helpers.db_utils import check_usage_limit # Moved to top
    
    # Get the client IP address, prioritizing Cloudflare header
    cf_ip = request.headers.get('cf-connecting-ip')
    if cf_ip:
        ip_address = cf_ip
    else:
        # Fallback to X-Forwarded-For, taking the first IP if multiple exist
        xff = request.headers.get('x-forwarded-for')
        if xff:
            ip_address = xff.split(',')[0].strip()
        else:
            # Fallback to remote_addr if no proxy headers are present
            ip_address = request.remote_addr
    
    # Ensure ip_address is not None before logging or using it
    if not ip_address:
        ip_address = "unknown" # Or handle error appropriately
        logger.warning("Could not determine client IP address for evaluate_search_query.")
    
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
    
    # Import the query evaluator # Moved to top
    # from factchecker.search.query_processing.query_evaluator import evaluate_query
    
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
    memory=options.MemoryOption.GB_1,
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
    
    # Get the client IP address, prioritizing Cloudflare header
    cf_ip = request.headers.get('cf-connecting-ip')
    if cf_ip:
        ip_address = cf_ip
    else:
        # Fallback to X-Forwarded-For, taking the first IP if multiple exist
        xff = request.headers.get('x-forwarded-for')
        if xff:
            ip_address = xff.split(',')[0].strip()
        else:
            # Fallback to remote_addr if no proxy headers are present
            ip_address = request.remote_addr
    
    # Ensure ip_address is not None before logging or using it
    if not ip_address:
        ip_address = "unknown" # Or handle error appropriately
        logger.warning("Could not determine client IP address for stream_search_datasets.")
    
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
        "https://askcrystal.info",
        "https://www.askcrystal.info",
        "http://localhost:3000",
        "http://localhost:5173",
        ],
        cors_methods=["get", "post", "options"]
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
    
    # Get the client IP address, prioritizing Cloudflare header
    cf_ip = request.headers.get('cf-connecting-ip')
    if cf_ip:
        ip_address = cf_ip
    else:
        # Fallback to X-Forwarded-For, taking the first IP if multiple exist
        xff = request.headers.get('x-forwarded-for')
        if xff:
            ip_address = xff.split(',')[0].strip()
        else:
            # Fallback to remote_addr if no proxy headers are present
            ip_address = request.remote_addr
    
    # Ensure ip_address is not None before logging or using it
    if not ip_address:
        ip_address = "unknown" # Or handle error appropriately
        logger.warning("Could not determine client IP address for stream_analyze.")
    
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
    timeout_sec=30,
    memory=options.MemoryOption.MB_512
)
def get_inflow_timeseries(request: https_fn.Request) -> https_fn.Response:
    """
    Fetch inflow timeseries combining observed (quality='R') and forecast (quality='F') data.
    Returns observed data up to current time and forecast data from current time forward.
    """
    logger.info("Received request for inflow timeseries data.")

    # Parse query params
    range_param = request.args.get('range', '7d')
    dam_id_param = request.args.get('dam_id', '1')
    try:
        dam_id_to_query = int(dam_id_param)
    except ValueError:
        logger.warning(f"Invalid dam_id parameter: '{dam_id_param}'. Defaulting to dam_id 1.")
        dam_id_to_query = 1
    
    logger.info(f"Processing inflow request for dam_id: {dam_id_to_query}, range: {range_param}")

    # Calculate date filter for historical data
    now_utc = datetime.utcnow()
    if range_param == 'mtd':
        start_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    elif range_param == '14d':
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_of_today_utc - timedelta(days=14)
    elif range_param == '7d':
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_of_today_utc - timedelta(days=7)
    else:
        logger.warning(f"Unexpected range_param: {range_param}, defaulting to 7d logic.")
        start_of_today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_of_today_utc - timedelta(days=7)

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Combined query for both observed and forecast data
                query_sql = """
                    -- Get observed data (quality = 'R') up to current time
                    SELECT ts_utc, value_num, 'observed' as data_type
                    FROM fact_dam_ops
                    WHERE dam_id = %s AND metric_id = %s AND quality = 'R' 
                      AND ts_utc >= %s AND ts_utc <= %s
                    
                    UNION ALL
                    
                    -- Get most recent forecast data (quality = 'F') from current time forward
                    SELECT f.ts_utc, f.value_num, 'forecast' as data_type
                    FROM fact_dam_ops f
                    INNER JOIN (
                        -- Get the most recent forecast run for this dam
                        SELECT dam_id, metric_id, MAX(ts_utc) as latest_forecast_time
                        FROM fact_dam_ops
                        WHERE dam_id = %s AND metric_id = %s AND quality = 'F'
                        GROUP BY dam_id, metric_id
                    ) latest ON f.dam_id = latest.dam_id 
                              AND f.metric_id = latest.metric_id
                    WHERE f.dam_id = %s AND f.metric_id = %s AND f.quality = 'F'
                      AND f.ts_utc > %s
                    
                    ORDER BY ts_utc ASC;
                """
                
                cursor.execute(query_sql, (
                    dam_id_to_query, 6, start_utc, now_utc,  # observed data params
                    dam_id_to_query, 6,                       # latest forecast subquery params
                    dam_id_to_query, 6, now_utc              # forecast data params
                ))
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    ts_utc_val_dt = row[0].astimezone(timezone.utc)
                    ts_utc_val = ts_utc_val_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                    data_type = row[2]  # 'observed' or 'forecast'

                    value_num_val = None
                    if row[1] is not None:
                        if isinstance(row[1], decimal.Decimal):
                            value_num_val = float(row[1])
                        elif isinstance(row[1], (int, float)):
                            value_num_val = row[1]
                        else:
                            try:
                                value_num_val = float(row[1])
                            except (ValueError, TypeError):
                                logger.error(f"Could not convert value_num {row[1]} to float.")
                                continue
                    
                    if value_num_val is not None:
                        result.append({
                            "ts_utc": ts_utc_val, 
                            "value_num": value_num_val,
                            "data_type": data_type
                        })

                return https_fn.Response(
                    json.dumps(result),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception as db_error:
            logger.error(f"Database error in get_inflow_timeseries: {db_error}")
            logger.error(traceback.format_exc())
            if conn:
                conn.rollback()
            return https_fn.Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                headers={"Content-Type": "application/json"}
            )
        finally:
            if conn:
                pool.putconn(conn)
    except Exception as e:
        logger.error(f"General error in get_inflow_timeseries: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"error": "An internal server error occurred.", "details": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

@https_fn.on_request(
    cors=options.CorsOptions(
        cors_origins=[
        "https://crystal-2f87e.web.app",
        "https://askcrystal.info",
        "https://www.askcrystal.info",
        "http://localhost:3000",  # For Next.js local dev
        "http://localhost:5173",  # For Vite local dev (if used)
        ],
        cors_methods=["get", "post", "options"]
    ),
    timeout_sec=60, # Standard timeout
    memory=options.MemoryOption.MB_512, # Standard memory
    min_instances=0 # Allow scale to zero for cost-effectiveness
)

def get_dashboard_section_cards_data(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch the latest operational data for dashboard section cards.
    Accepts a 'dam_id' query parameter (defaults to 1).
    Queries the 'fact_dam_ops' table for the given dam_id and specific metric_ids.
    """
    logger.info("Received request for dashboard section cards data.")

    # Handle warming requests if sent via POST with a specific body
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_dashboard_section_cards_data.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception: # pylint: disable=broad-except
            # If JSON parsing fails for a POST, it's not a valid warming request, proceed
            pass
    
    # For actual data fetching, typically a GET request is used.
    # No specific request body is expected for this data retrieval.

    # Parse query params for dam_id
    dam_id_param = request.args.get('dam_id', '1')  # Default to '1' (Grand Coulee Dam)
    try:
        dam_id_to_query = int(dam_id_param)
    except ValueError:
        logger.warning(f"Invalid dam_id parameter for section cards: '{dam_id_param}'. Defaulting to dam_id 1.")
        dam_id_to_query = 1
    
    logger.info(f"Processing section cards request for dam_id: {dam_id_to_query}")

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        card_data_list = []
        
        # Dam ID is now dynamically set from the request parameter
        # dam_id_to_query = 1 # This line is replaced by the parsing logic above

        try:
            with conn.cursor() as cursor:
                for card_title, config in METRICS_CONFIG.items():
                    metric_id_to_query = config["metric_id"]
                    
                    # Special handling for Inflow metric to get only observed data (quality = 'R')
                    if metric_id_to_query == 6:  # Inflow metric
                        query_sql = """
                            SELECT f.ts_utc, f.value_num
                            FROM fact_dam_ops f
                            INNER JOIN (
                                SELECT metric_id, MAX(ts_utc) as max_ts_utc
                                FROM fact_dam_ops
                                WHERE dam_id = %s AND metric_id = %s AND quality = 'R'
                                GROUP BY metric_id
                            ) latest_f ON f.metric_id = latest_f.metric_id AND f.ts_utc = latest_f.max_ts_utc
                            WHERE f.dam_id = %s AND f.metric_id = %s AND f.quality = 'R';
                        """
                    else:
                        # Default query for other metrics (no quality filter)
                        query_sql = """
                            SELECT f.ts_utc, f.value_num
                            FROM fact_dam_ops f
                            INNER JOIN (
                                SELECT metric_id, MAX(ts_utc) as max_ts_utc
                                FROM fact_dam_ops
                                WHERE dam_id = %s AND metric_id = %s
                                GROUP BY metric_id
                            ) latest_f ON f.metric_id = latest_f.metric_id AND f.ts_utc = latest_f.max_ts_utc
                            WHERE f.dam_id = %s AND f.metric_id = %s;
                        """
                    
                    cursor.execute(query_sql, (dam_id_to_query, metric_id_to_query, dam_id_to_query, metric_id_to_query))
                    row = cursor.fetchone()
                    
                    # Initialize defaults
                    value_display = f"N/A {config['unit']}" 
                    timestamp_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') 
                    trend_val = "neutral" 
                    
                    if row: # If a record was found
                        db_ts_utc, db_value_num = row[0], row[1]

                        if db_ts_utc is not None:
                            # Ensure the database timestamp is UTC and correctly formatted
                            if db_ts_utc.tzinfo is None:
                                # If naive, assume it's UTC and make it aware
                                aware_utc_datetime = db_ts_utc.replace(tzinfo=timezone.utc)
                            else:
                                # If already aware, convert to UTC to be certain
                                aware_utc_datetime = db_ts_utc.astimezone(timezone.utc)
                            # Ensure Z (Zulu) suffix for UTC timestamps
                            timestamp_iso = aware_utc_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
                        # If db_ts_utc is None, timestamp_iso remains the current UTC time default (already formatted with Z)

                        if db_value_num is not None:
                            numeric_value_for_processing = None
                            if isinstance(db_value_num, decimal.Decimal):
                                numeric_value_for_processing = float(db_value_num)
                            elif isinstance(db_value_num, (int, float)):
                                numeric_value_for_processing = db_value_num
                            else:
                                try:
                                    numeric_value_for_processing = float(str(db_value_num))
                                    logger.info(f"Successfully converted db_value_num '{db_value_num}' (type {type(db_value_num)}) to float for metric_id {metric_id_to_query}.")
                                except (ValueError, TypeError):
                                    logger.warning(f"Value for metric_id {metric_id_to_query} ('{db_value_num}' type: {type(db_value_num)}) is not a recognized number and could not be converted. Defaulting to N/A.")
                                    # value_display will use the default "N/A {config['unit']}"

                            if numeric_value_for_processing is not None:
                                temp_value = numeric_value_for_processing

                                if card_title == "Reservoir Fill":
                                    temp_value *= 100
                                
                                formatted_num_str = "{:,.1f}".format(temp_value)
                                if formatted_num_str.endswith(".0"):
                                    formatted_num_str = formatted_num_str[:-2]
                                value_display = f"{formatted_num_str} {config['unit']}"
                            # If conversion failed or numeric_value_for_processing is None,
                            # value_display retains its default "N/A {config['unit']}"
                        # else (if db_value_num is None), value_display remains "N/A {config['unit']}"
                    # else (if row is None), defaults for value_display and timestamp_iso are used.

                    logger.info(f"DEBUG: Card: {card_title}, Formatted Timestamp: {timestamp_iso}") # <--- ADD THIS

                    card_data_list.append({
                        "id": str(metric_id_to_query), # Use metric_id as a unique ID for the card
                        "title": card_title,
                        "value": value_display,
                        "timestamp": timestamp_iso,
                        "trend": trend_val, # Placeholder
                        "trendDescription": config["default_trend_desc"], # Placeholder
                        "footerNote": f"Latest reading for {card_title.lower()}"
                    })

            # Ensure consistent ordering of cards based on METRICS_CONFIG keys
            ordered_card_data_list = sorted(card_data_list, key=lambda x: list(METRICS_CONFIG.keys()).index(x["title"]))

            return https_fn.Response(
                json.dumps(ordered_card_data_list), # Use default=str for datetime if not already string
                status=200,
                headers={"Content-Type": "application/json"}
            )

        except Exception as db_error: # pylint: disable=broad-except
            logger.error(f"Database error in get_dashboard_section_cards_data: {db_error}")
            logger.error(traceback.format_exc())
            if conn: # conn might not be None if getconn() succeeded but cursor failed
                conn.rollback()
            return https_fn.Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                headers={"Content-Type": "application/json"}
            )
        finally:
            if conn: # conn should exist if pool.getconn() was successful
                pool.putconn(conn)

    except Exception as e: # pylint: disable=broad-except
        logger.error(f"General error in get_dashboard_section_cards_data: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"error": "An internal server error occurred.", "details": str(e)}),
            status=500,
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
            # Add any other origins if needed, e.g., for Cloud Scheduler if invoked via authenticated HTTP
        ],
        cors_methods=["get", "post", "options"] # Allow POST if scheduler uses it
    ),
    timeout_sec=540,  # 9 minutes, as per ChatGPT's gcloud example
    memory=options.MemoryOption.GB_1, # 1GiB, as per ChatGPT's gcloud example
    min_instances=0 # Can scale to zero
)

def generate_inflow_forecast_v0(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP-triggered Cloud Function to generate a deterministic inflow forecast.
    Writes results to fact_forecast_run and fact_dam_forecast.
    
    Query Parameters:
        dam_id (int, optional): The ID of the dam. Defaults to 1 (Grand Coulee).
                                Note: V0 model is hardcoded for Grand Coulee.
        model_id (int, optional): The ID of the model. Defaults to 1.
        metric_id (int, optional): The ID of the metric. Defaults to 6 (inflow).
        horizon_hours (int, optional): Forecast horizon in hours. Defaults to 120.
    """
    logger.info("Received request for generate_inflow_forecast_v0.")

    # Handle warming requests
    if request.method == 'POST': # Warming often sent as POST
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for generate_inflow_forecast_v0.")
                return https_fn.Response(json.dumps({"status": "warmed"}), status=200, headers={"Content-Type": "application/json"})
        except Exception:
             # If JSON parsing fails or not a warming request, proceed normally
            pass

    try:
        # --- Configuration ---
        # dam_id: For V0, the model internally uses Grand Coulee data.
        # The parameter is here for future expansion.
        dam_id_to_process = int(request.args.get('dam_id', '1'))
        
        # model_id: As per your plan, placeholder for V0.
        # This should correspond to an entry in dim_model.
        model_id_to_use = int(request.args.get('model_id', '1'))
        
        # metric_id for inflow
        metric_id_for_forecast = int(request.args.get('metric_id', '6')) # 6 for inflow
        
        # Forecast horizon
        forecast_horizon_hours = int(request.args.get('horizon_hours', '120'))

        # Ensemble member: -1 for deterministic forecasts
        ensemble_member = -1

        logger.info(f"Starting inflow forecast generation for dam_id: {dam_id_to_process}, model_id: {model_id_to_use}, horizon: {forecast_horizon_hours}h")

        # 0. Bookkeeping - Get current time as issue time
        # Ensure it's timezone-aware UTC
        run_issued_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

        # 1. Run the inflow model
        # The model will return a list of {'valid_utc': datetime, 'value_cfs': float}
        # `run_inflow_forecast_v0` expects `current_utc_time` to be the issue time.
        forecast_data = run_inflow_forecast_v0(
            dam_id=dam_id_to_process, # Passed to model, though V0 is hardcoded
            current_utc_time=run_issued_utc,
            forecast_horizon_hours=forecast_horizon_hours
        )

        if not forecast_data:
            logger.warning("Inflow model returned no forecast data.")
            return https_fn.Response(
                json.dumps({"status": "error", "message": "Inflow model returned no data."}),
                status=500,
                headers={"Content-Type": "application/json"}
            )

        # 2. Write header row to fact_forecast_run
        # Determine forecast_start_utc and forecast_end_utc from the data
        # Ensure these are also timezone-aware UTC
        forecast_start_utc = forecast_data[0]['valid_utc']
        forecast_end_utc = forecast_data[-1]['valid_utc']
        
        if forecast_start_utc.tzinfo is None: # Ensure UTC
             forecast_start_utc = forecast_start_utc.replace(tzinfo=timezone.utc)
        if forecast_end_utc.tzinfo is None: # Ensure UTC
            forecast_end_utc = forecast_end_utc.replace(tzinfo=timezone.utc)

        # Calculate actual horizon and lead time from data and issue time
        # Horizon is duration from first forecast point to last.
        actual_horizon_duration = forecast_end_utc - forecast_start_utc
        # Add 1 because if start and end are 1 hour apart, it's 2 data points covering 1 full hour interval + start point.
        # Or, more simply, it's the number of forecast points if they are contiguous hourly.
        # Let's use the number of points if they are hourly.
        # A more robust way for horizon: ((forecast_end_utc - forecast_start_utc).total_seconds() / 3600) + 1
        actual_horizon_hours = math.ceil(actual_horizon_duration.total_seconds() / 3600) + 1
        
        # Lead time is duration from issue to first forecast point.
        lead_time_duration = forecast_start_utc - run_issued_utc
        actual_lead_time_hours = lead_time_duration.total_seconds() / 3600

        # Construct a simple string for the note
        run_note = f"Source: generate_inflow_forecast_v0_cloud_function, Dam ID processed: {dam_id_to_process}, Horizon: {forecast_horizon_hours}h"

        run_id = write_run_header(
            model_id=model_id_to_use,
            run_issued_utc=run_issued_utc,
            forecast_start_utc=forecast_start_utc,
            forecast_end_utc=forecast_end_utc,
            horizon_hours=actual_horizon_hours, # Use calculated horizon
            lead_time_hours=actual_lead_time_hours, # Use calculated lead time
            note=run_note # Pass the simple string here
        )

        if run_id is None:
            logger.error("Failed to write forecast run header. Aborting.")
            return https_fn.Response(
                json.dumps({"status": "error", "message": "Failed to write forecast run header."}),
                status=500,
                headers={"Content-Type": "application/json"}
            )

        # 3. Write the forecast value rows to fact_dam_forecast
        write_forecast_rows(
            run_id=run_id,
            dam_id=dam_id_to_process,
            ensemble_member=ensemble_member,
            forecast_data=forecast_data
        )

        success_message = f"Successfully generated and stored inflow forecast. run_id: {run_id}, rows: {len(forecast_data)}"
        logger.info(success_message)
        return https_fn.Response(
            json.dumps({"status": "success", "message": success_message, "run_id": run_id, "rows_written": len(forecast_data)}),
            status=200,
            headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        logger.error(f"Error in generate_inflow_forecast_v0: {e}", exc_info=True)
        # Consider if traceback.format_exc() is too verbose for client
        return https_fn.Response(
            json.dumps({"status": "error", "message": "An internal server error occurred.", "details": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )