import os
import django
from django.conf import settings
import decimal # Add import for decimal
import math

from factchecker.interconnection.icr import compute_diffs, download_icr_excel, fetch_existing_icr, send_email, upload_diff_to_gcs, upsert_icr # Add import for math

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factchecker.settings")

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
from threading import Lock
import random

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
                
                # Note: Don't call django.setup() again here - it's already been called
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
    "Outflow": {"metric_id": 7, "unit": "cfs", "default_trend_desc": "Constant"},
    "Spill %": {"metric_id": 9, "unit": "%", "default_trend_desc": "No change"}, # Changed from Spill to Spill % to match ID
    "Spill": {"metric_id": 8, "unit": "cfs", "default_trend_desc": "None"}, # Changed from Spill % to Spill
    "Gates Open": {"metric_id": 10, "unit": "gates", "default_trend_desc": "Unchanged"},
    "Generation Flow": {"metric_id": 13, "unit": "cfs", "default_trend_desc": "Constant"}
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
        cors_methods=["get", "post", "options"]
    ),
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_ttc_flowgate_data(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch TTC flowgate data for a specific flowgate and date.
    Accepts 'flowgate' and 'date' query parameters.
    """
    logger.info("Received request for TTC flowgate data.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_ttc_flowgate_data.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception:
            pass

    # Parse query params
    flowgate_param = request.args.get('flowgate', '')
    date_param = request.args.get('date', '')
    
    if not flowgate_param:
        logger.warning("Missing flowgate parameter.")
        return https_fn.Response(
            json.dumps({"error": "Flowgate parameter is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    if not date_param:
        logger.warning("Missing date parameter.")
        return https_fn.Response(
            json.dumps({"error": "Date parameter is required (format: YYYY-MM-DD)"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    logger.info(f"Processing TTC request for flowgate: {flowgate_param}, date: {date_param}")

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # First, get the flowgate_id from the flowgate_code
                flowgate_lookup_sql = """
                    SELECT flowgate_id FROM dim_flowgate 
                    WHERE flowgate_code = %s AND is_active = true;
                """
                cursor.execute(flowgate_lookup_sql, (flowgate_param,))
                flowgate_row = cursor.fetchone()
                
                if not flowgate_row:
                    logger.warning(f"Flowgate not found: {flowgate_param}")
                    return https_fn.Response(
                        json.dumps({"error": f"Flowgate '{flowgate_param}' not found"}),
                        status=404,
                        headers={"Content-Type": "application/json"}
                    )
                
                flowgate_id = flowgate_row[0]
                logger.info(f"Found flowgate_id: {flowgate_id} for flowgate: {flowgate_param}")
                
                # Query TTC data for the specific flowgate and date
                # Filter for metric_id = 20 and quality = 'F' (forecast data only)
                query_sql = """
                    SELECT ttc_id, flowgate_id, metric_id, source_id, datetime_utc, 
                           hour_ending, value_mw, quality, ingestion_timestamp
                    FROM fact_ttc_hourly
                    WHERE flowgate_id = %s 
                      AND DATE(datetime_utc) = %s
                      AND metric_id = 20
                      AND quality = 'F'
                    ORDER BY hour_ending ASC;
                """
                
                cursor.execute(query_sql, (flowgate_id, date_param))
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    ttc_id, flowgate_id_val, metric_id, source_id, datetime_utc, hour_ending, value_mw, quality, ingestion_timestamp = row
                    
                    # Format datetime to ISO string
                    datetime_utc_str = datetime_utc.strftime('%Y-%m-%dT%H:%M:%SZ') if datetime_utc else None
                    ingestion_timestamp_str = ingestion_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if ingestion_timestamp else None
                    
                    # Convert value_mw to float if it's a Decimal
                    value_mw_float = None
                    if value_mw is not None:
                        if isinstance(value_mw, decimal.Decimal):
                            value_mw_float = float(value_mw)
                        elif isinstance(value_mw, (int, float)):
                            value_mw_float = float(value_mw)
                        else:
                            try:
                                value_mw_float = float(value_mw)
                            except (ValueError, TypeError):
                                logger.warning(f"Could not convert value_mw {value_mw} to float for ttc_id {ttc_id}")
                                continue
                    
                    if value_mw_float is not None:
                        result.append({
                            "ttc_id": ttc_id,
                            "flowgate_id": flowgate_id_val,
                            "metric_id": metric_id,
                            "source_id": source_id,
                            "datetime_utc": datetime_utc_str,
                            "hour_ending": hour_ending,
                            "value_mw": value_mw_float,
                            "quality": quality,
                            "ingestion_timestamp": ingestion_timestamp_str
                        })
                
                logger.info(f"Returning {len(result)} TTC data points for flowgate {flowgate_param} on {date_param}")
                
                return https_fn.Response(
                    json.dumps(result),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
                
        except Exception as db_error:
            logger.error(f"Database error in get_ttc_flowgate_data: {db_error}")
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
        logger.error(f"General error in get_ttc_flowgate_data: {e}")
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30,
)
def get_power_infrastructure(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch BPA power infrastructure data as GeoJSON.
    Supports zoom-based simplification.
    """
    logger.info("Received request for power infrastructure data.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_power_infrastructure.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception:
            pass

    zoom_str = request.args.get('zoom')
    try:
        zoom = int(zoom_str) if zoom_str else None
    except (ValueError, TypeError):
        zoom = None
    
    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Determine geometry transformation based on zoom level
                if zoom is not None and zoom < 7:
                    # Simplify geometry for lower zoom levels
                    geom_sql = "ST_AsGeoJSON(ST_SimplifyPreserveTopology(pi.geom, 0.01))::jsonb"
                else:
                    # Use full resolution geometry for higher zoom levels
                    geom_sql = "ST_AsGeoJSON(pi.geom)::jsonb"

                # Base query to get power infrastructure as GeoJSON with flowgate data and capacity factors
                query = f"""
                    SELECT jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(feature)
                    )
                    FROM (
                        SELECT DISTINCT ON (pi.gid) jsonb_build_object(
                            'type', 'Feature',
                            'id', pi.gid,
                            'geometry', {geom_sql},
                            'properties', jsonb_build_object(
                                'gid', pi.gid,
                                'name', COALESCE(pi.openinfra_name, 'Unnamed'),
                                'operator', pi.operator,
                                'power_type', pi.power,
                                'voltage', pi.voltage,
                                'geometry_type', ST_GeometryType(pi.geom),
                                'flowgate', pfg.flowgate,
                                'is_flowgate_line', CASE WHEN pfg.flowgate IS NOT NULL THEN true ELSE false END,
                                'capacity_factor', COALESCE(latest_ttc.latest_capacity_factor, 0.0),
                                'capacity_factor_timestamp', latest_ttc.latest_timestamp
                            )
                        ) AS feature
                        FROM power_infra pi
                        LEFT JOIN power_flow_gates pfg ON pi.openinfra_name = pfg.openinfra_name
                        LEFT JOIN (
                            SELECT DISTINCT ON (df.flowgate_code)
                                df.flowgate_code,
                                fth.value_mw as latest_capacity_factor,
                                fth.datetime_utc as latest_timestamp
                            FROM fact_ttc_hourly fth
                            JOIN dim_flowgate df ON fth.flowgate_id = df.flowgate_id
                            WHERE fth.metric_id = 24 -- Capacity Factor metric
                              AND df.is_active = true
                              AND fth.datetime_utc = DATE_TRUNC('hour', NOW() AT TIME ZONE 'UTC')
                            ORDER BY df.flowgate_code, fth.ingestion_timestamp DESC
                        ) AS latest_ttc ON pfg.flowgate = latest_ttc.flowgate_code
                        WHERE pi.geom IS NOT NULL
                        ORDER BY pi.gid, (pfg.flowgate IS NOT NULL) DESC, pfg.flowgate
                    ) AS features;
                """
                
                cursor.execute(query)
                result = cursor.fetchone()
                geojson_data = result[0] if result and result[0] else {
                    "type": "FeatureCollection", 
                    "features": []
                }
                
                # Debug: Log information about flowgates
                if geojson_data and geojson_data.get("features"):
                    total_features = len(geojson_data["features"])
                    flowgate_features = [f for f in geojson_data["features"] if f.get("properties", {}).get("flowgate")]
                    unique_flowgates = set()
                    for f in geojson_data["features"]:
                        fg = f.get("properties", {}).get("flowgate")
                        if fg:
                            unique_flowgates.add(fg)
                    
                    logger.info(f"Power infrastructure debug: {total_features} total features, {len(flowgate_features)} with flowgates, unique flowgates: {sorted(unique_flowgates)}")
                
                return https_fn.Response(
                    json.dumps(geojson_data),
                    status=200,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "public, max-age=3600"  # Cache for 1 hour
                    }
                )
                
        except Exception as db_error:
            logger.error(f"Database error in get_power_infrastructure: {db_error}")
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
        logger.error(f"General error in get_power_infrastructure: {e}")
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
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
                # Enhanced query to get all rich dam metadata from dim_dam
                query_sql = """
                    SELECT 
                        dam_id, 
                        dam_name, 
                        latitude, 
                        longitude,
                        nid_id,
                        federal_id,
                        owner_name,
                        operator_agency,
                        river,
                        city,
                        county,
                        state,
                        structural_height_ft,
                        hydraulic_height_ft,
                        nid_height_ft,
                        dam_length_ft,
                        dam_volume_cy,
                        storage_max_acft,
                        storage_normal_acft,
                        surface_area_acres,
                        drainage_area_sqmi,
                        max_discharge_cfs,
                        capacity_mw,
                        active_storage_acft,
                        gate_count,
                        gate_type,
                        year_completed,
                        year_modified,
                        dam_code
                    FROM dim_dam 
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
                """
                cursor.execute(query_sql)
                rows = cursor.fetchall()
                
                for row_data in rows:
                    dam_id = row_data[0]
                    dam_name_val = row_data[1]
                    lat_val = row_data[2]
                    lon_val = row_data[3]
                    
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
                        # Helper function to safely convert values
                        def safe_convert(value, convert_func=None):
                            if value is None:
                                return None
                            try:
                                return convert_func(value) if convert_func else value
                            except (ValueError, TypeError):
                                return None
                        
                        dam_locations_list.append({
                            "id": dam_id,
                            "name": dam_name_val,
                            "latitude": current_dam_lat,
                            "longitude": current_dam_lon,
                            "nidId": row_data[4],
                            "federalId": row_data[5],
                            "ownerName": row_data[6],
                            "operatorAgency": row_data[7],
                            "river": row_data[8],
                            "city": row_data[9],
                            "county": row_data[10],
                            "state": row_data[11],
                            "structuralHeightFt": safe_convert(row_data[12], float),
                            "hydraulicHeightFt": safe_convert(row_data[13], float),
                            "nidHeightFt": safe_convert(row_data[14], float),
                            "damLengthFt": safe_convert(row_data[15], float),
                            "damVolumeCy": safe_convert(row_data[16], float),
                            "storageMaxAcft": safe_convert(row_data[17], float),
                            "storageNormalAcft": safe_convert(row_data[18], float),
                            "surfaceAreaAcres": safe_convert(row_data[19], float),
                            "drainageAreaSqmi": safe_convert(row_data[20], float),
                            "maxDischargeCfs": safe_convert(row_data[21], float),
                            "capacityMw": safe_convert(row_data[22], float),
                            "activeStorageAcft": safe_convert(row_data[23], float),
                            "gateCount": safe_convert(row_data[24], int),
                            "gateType": row_data[25],
                            "yearCompleted": safe_convert(row_data[26], int),
                            "yearModified": row_data[27],
                            "damCode": row_data[28]
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
        cors_methods=["get", "post", "options"]
    ),
    memory=options.MemoryOption.GB_1,
    timeout_sec=180 # Let's increase timeout here to 3 mins.
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_inflow_timeseries(request: https_fn.Request) -> https_fn.Response:
    """
    Fetch timeseries data for any metric. For inflow (metric_id=6), includes observed, 
    forecast, and forecast error data. For other metrics, returns simple historical data.
    OPTIMIZED: Single query instead of 100+ separate queries.
    """
    # Add performance timing
    start_time = time.time()
    logger.info("Received request for metric timeseries data.")

    # Parse query params
    range_param = request.args.get('range', '7d')
    dam_id_param = request.args.get('dam_id', '1')
    metric_id_param = request.args.get('metric_id', '6')  # Default to inflow
    
    try:
        dam_id_to_query = int(dam_id_param)
        metric_id_to_query = int(metric_id_param)
    except ValueError:
        logger.warning(f"Invalid dam_id or metric_id parameter: '{dam_id_param}', '{metric_id_param}'. Defaulting to dam_id 1, metric_id 6.")
        dam_id_to_query = 1
        metric_id_to_query = 6
    
    logger.info(f"Processing timeseries request for dam_id: {dam_id_to_query}, metric_id: {metric_id_to_query}, range: {range_param}")

    # Calculate date filter for historical data
    now_utc = datetime.utcnow()
    if range_param == "1d":
        start_utc = now_utc - timedelta(days=1)
    elif range_param == "mtd":
        start_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif range_param == "14d":
        start_utc = now_utc - timedelta(days=14)
    else:  # Default to 7d
        start_utc = now_utc - timedelta(days=7)

    try:
        pool = get_connection_pool()
        conn = pool.getconn()

        try:
            with conn.cursor() as cursor:
                # Time the query execution
                query_start = time.time()
                
                if metric_id_to_query == 6:
                    # OPTIMIZED: Single query for inflow with observed, forecast, and forecast errors
                    optimized_inflow_query = """
                    WITH base_data AS (
                        -- Get all data points in the time range
                        SELECT 
                            ts_utc, 
                            value_num, 
                            quality,
                            DATE(ts_utc) as obs_date
                        FROM fact_dam_ops
                        WHERE dam_id = %s AND metric_id = %s 
                          AND ts_utc >= %s AND ts_utc <= %s
                          AND value_num IS NOT NULL
                    ),
                    observed_data AS (
                        -- Observed data points
                        SELECT 
                            ts_utc,
                            value_num,
                            'observed' as data_type,
                            obs_date
                        FROM base_data 
                        WHERE quality = 'R'
                    ),
                    forecast_data AS (
                        -- Current forecast data (future points)
                        SELECT DISTINCT ON (f.ts_utc)
                            f.ts_utc,
                            f.value_num,
                            'forecast' as data_type
                        FROM fact_dam_ops f
                        INNER JOIN (
                            SELECT dam_id, metric_id, MAX(ts_utc) as latest_forecast_time
                            FROM fact_dam_ops
                            WHERE dam_id = %s AND metric_id = %s AND quality = 'F'
                            GROUP BY dam_id, metric_id
                        ) latest ON f.dam_id = latest.dam_id AND f.metric_id = latest.metric_id
                        WHERE f.dam_id = %s AND f.metric_id = %s AND f.quality = 'F'
                          AND f.ts_utc > %s
                        ORDER BY f.ts_utc, f.ts_utc DESC
                    ),
                    forecast_averages AS (
                        -- Pre-calculate average forecasts by date for error calculation
                        SELECT 
                            obs_date,
                            AVG(value_num) as avg_forecast,
                            COUNT(*) as forecast_count
                        FROM base_data 
                        WHERE quality = 'F'
                        GROUP BY obs_date
                    ),
                    forecast_errors AS (
                        -- Calculate forecast errors for observed points
                        SELECT 
                            od.ts_utc,
                            (od.value_num - fa.avg_forecast) as error_value,
                            'forecast_error' as data_type
                        FROM observed_data od
                        INNER JOIN forecast_averages fa ON od.obs_date = fa.obs_date
                        WHERE fa.avg_forecast IS NOT NULL
                    )
                    -- Union all data types
                    SELECT ts_utc, value_num, data_type FROM observed_data
                    UNION ALL
                    SELECT ts_utc, value_num, data_type FROM forecast_data
                    UNION ALL
                    SELECT ts_utc, error_value as value_num, data_type FROM forecast_errors
                    ORDER BY ts_utc ASC
                    LIMIT 5000;
                    """
                    
                    cursor.execute(optimized_inflow_query, (
                        dam_id_to_query, metric_id_to_query, start_utc, now_utc,  # base_data params
                        dam_id_to_query, metric_id_to_query,                      # forecast subquery params
                        dam_id_to_query, metric_id_to_query, now_utc               # forecast_data params
                    ))
                    all_rows = cursor.fetchall()
                    
                else:
                    # OPTIMIZED: Simple query for other metrics
                    simple_query = """
                        SELECT ts_utc, value_num, 'observed' as data_type
                        FROM fact_dam_ops
                        WHERE dam_id = %s AND metric_id = %s 
                          AND ts_utc >= %s AND ts_utc <= %s
                          AND value_num IS NOT NULL
                        ORDER BY ts_utc ASC
                        LIMIT 5000;
                    """
                    
                    cursor.execute(simple_query, (dam_id_to_query, metric_id_to_query, start_utc, now_utc))
                    all_rows = cursor.fetchall()
                
                query_end = time.time()
                logger.info(f"PERFORMANCE: Query executed in {query_end - query_start:.3f} seconds")
                logger.info(f"Retrieved {len(all_rows)} total data points for metric_id {metric_id_to_query}")
                
                # Process results (same logic as before)
                result = []
                for row in all_rows:
                    ts_utc_val_dt = row[0].astimezone(timezone.utc)
                    ts_utc_val = ts_utc_val_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                    data_type = row[2]

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

                total_time = time.time() - start_time
                logger.info(f"PERFORMANCE: Total function execution: {total_time:.3f} seconds")

                return https_fn.Response(
                    json.dumps(result),
                    status=200,
                    headers={
                        "Content-Type": "application/json",
                        "X-Execution-Time": f"{total_time:.3f}s"
                    }
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
        logger.error(f"Unexpected error in get_inflow_timeseries: {e}")
        logger.error(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"error": "An unexpected error occurred.", "details": str(e)}),
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_dashboard_section_cards_data(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch the latest operational data for dashboard section cards.
    Accepts a 'dam_id' query parameter (defaults to 1).
    Optimized version with single query instead of 8 separate queries.
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
        except Exception:
            pass

    # Parse query params for dam_id
    dam_id_param = request.args.get('dam_id', '1')
    try:
        dam_id_to_query = int(dam_id_param)
    except ValueError:
        logger.warning(f"Invalid dam_id parameter for section cards: '{dam_id_param}'. Defaulting to dam_id 1.")
        dam_id_to_query = 1
    
    logger.info(f"Processing section cards request for dam_id: {dam_id_to_query}")

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # OPTIMIZED: Single query to get all metrics at once
                # This replaces the 8 separate queries in the original loop
                optimized_query = """
                WITH metric_list AS (
                    -- All metric IDs from METRICS_CONFIG
                    SELECT unnest(ARRAY[3, 5, 6, 7, 8, 9, 10, 13]) AS metric_id
                ),
                current_data AS (
                    SELECT 
                        f.metric_id,
                        f.ts_utc, 
                        f.value_num,
                        ROW_NUMBER() OVER (PARTITION BY f.metric_id ORDER BY f.ts_utc DESC) as rn
                    FROM fact_dam_ops f
                    INNER JOIN metric_list ml ON f.metric_id = ml.metric_id
                    WHERE f.dam_id = %s 
                      AND (f.quality = 'R' OR f.metric_id != 6)  -- Only inflow (6) needs 'R' quality
                ),
                previous_data AS (
                    SELECT 
                        f.metric_id,
                        f.ts_utc, 
                        f.value_num,
                        ROW_NUMBER() OVER (
                            PARTITION BY f.metric_id 
                            ORDER BY ABS(EXTRACT(EPOCH FROM (f.ts_utc - (CURRENT_TIMESTAMP - INTERVAL '24 hours')))) ASC
                        ) as rn
                    FROM fact_dam_ops f
                    INNER JOIN metric_list ml ON f.metric_id = ml.metric_id
                    WHERE f.dam_id = %s 
                      AND (f.quality = 'R' OR f.metric_id != 6)
                      AND f.ts_utc BETWEEN (CURRENT_TIMESTAMP - INTERVAL '25 hours') 
                                       AND (CURRENT_TIMESTAMP - INTERVAL '23 hours')
                )
                SELECT 
                    c.metric_id,
                    c.ts_utc as current_ts,
                    c.value_num as current_value,
                    p.ts_utc as previous_ts,
                    p.value_num as previous_value
                FROM current_data c
                LEFT JOIN previous_data p ON c.metric_id = p.metric_id AND p.rn = 1
                WHERE c.rn = 1
                ORDER BY c.metric_id;
                """
                
                cursor.execute(optimized_query, (dam_id_to_query, dam_id_to_query))
                all_metric_rows = cursor.fetchall()
                
                # Create a dictionary for quick lookup
                metric_data = {}
                for row in all_metric_rows:
                    metric_id, current_ts, current_value, previous_ts, previous_value = row
                    metric_data[metric_id] = {
                        'current_ts': current_ts,
                        'current_value': current_value,
                        'previous_ts': previous_ts,
                        'previous_value': previous_value
                    }
                
                # Process each metric using the same logic as before
                card_data_list = []
                
                for card_title, config in METRICS_CONFIG.items():
                    metric_id_to_query = config["metric_id"]
                    
                    # Get data from our single query results
                    row_data = metric_data.get(metric_id_to_query)
                    
                    # Initialize defaults (same as original)
                    value_display = f"N/A {config['unit']}"
                    timestamp_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                    trend_val = "neutral"
                    change_24h = None
                    change_24h_percent = None
                    
                    if row_data and row_data['current_ts'] is not None:  # If current data exists
                        current_ts = row_data['current_ts']
                        current_value = row_data['current_value']
                        previous_ts = row_data['previous_ts']
                        previous_value = row_data['previous_value']
                        
                        # Process current timestamp (same as original)
                        if current_ts is not None:
                            if current_ts.tzinfo is None:
                                aware_utc_datetime = current_ts.replace(tzinfo=timezone.utc)
                            else:
                                aware_utc_datetime = current_ts.astimezone(timezone.utc)
                            timestamp_iso = aware_utc_datetime.strftime('%Y-%m-%dT%H:%M:%SZ')
                        
                        # Process current value (same as original)
                        if current_value is not None:
                            numeric_current = None
                            if isinstance(current_value, decimal.Decimal):
                                numeric_current = float(current_value)
                            elif isinstance(current_value, (int, float)):
                                numeric_current = current_value
                            else:
                                try:
                                    numeric_current = float(str(current_value))
                                except (ValueError, TypeError):
                                    logger.warning(f"Could not convert current value for metric_id {metric_id_to_query}")
                            
                            if numeric_current is not None:
                                # Apply special formatting for Reservoir Fill (same as original)
                                display_current = numeric_current
                                if card_title == "Reservoir Fill":
                                    display_current *= 100
                                
                                formatted_num_str = "{:,.1f}".format(display_current)
                                if formatted_num_str.endswith(".0"):
                                    formatted_num_str = formatted_num_str[:-2]
                                value_display = f"{formatted_num_str} {config['unit']}"
                                
                                # Calculate 24-hour change if previous value exists (same as original)
                                if previous_value is not None:
                                    numeric_previous = None
                                    if isinstance(previous_value, decimal.Decimal):
                                        numeric_previous = float(previous_value)
                                    elif isinstance(previous_value, (int, float)):
                                        numeric_previous = previous_value
                                    else:
                                        try:
                                            numeric_previous = float(str(previous_value))
                                        except (ValueError, TypeError):
                                            logger.warning(f"Could not convert previous value for metric_id {metric_id_to_query}")
                                    
                                    if numeric_previous is not None:
                                        # Calculate absolute and percentage change (same as original)
                                        change_24h = numeric_current - numeric_previous
                                        if numeric_previous != 0:
                                            change_24h_percent = (change_24h / abs(numeric_previous)) * 100
                                        else:
                                            change_24h_percent = 0 if change_24h == 0 else float('inf')
                                        
                                        # Determine trend based on change (same as original)
                                        if abs(change_24h) < 0.01:  # Very small change threshold
                                            trend_val = "neutral"
                                        elif change_24h > 0:
                                            trend_val = "up"
                                        else:
                                            trend_val = "down"
                                        
                                        logger.info(f"Metric {card_title}: current={numeric_current}, previous={numeric_previous}, change={change_24h}, trend={trend_val}")
                    
                    # Build response object with 24-hour change data (EXACT same format as original)
                    card_data = {
                        "id": str(metric_id_to_query),
                        "title": card_title,
                        "value": value_display,
                        "timestamp": timestamp_iso,
                        "trend": trend_val,
                        "trendDescription": config["default_trend_desc"],
                        "footerNote": f"Latest reading for {card_title.lower()}",
                        "change24h": change_24h,
                        "change24hPercent": change_24h_percent
                    }
                    
                    card_data_list.append(card_data)

                # Ensure consistent ordering of cards based on METRICS_CONFIG keys (same as original)
                ordered_card_data_list = sorted(card_data_list, key=lambda x: list(METRICS_CONFIG.keys()).index(x["title"]))

                return https_fn.Response(
                    json.dumps(ordered_card_data_list),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )

        except Exception as db_error:
            logger.error(f"Database error in get_dashboard_section_cards_data: {db_error}")
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
        ],
        cors_methods=["get", "post", "options"]
    ),
    memory=options.MemoryOption.MB_512,
    timeout_sec=300,
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_power_generators(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch power generator data as GeoJSON.
    Supports zoom-based progressive disclosure.
    """
    logger.info("Received request for power generators data.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_power_generators.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception:
            pass

    # Parse parameters
    zoom_param = request.args.get('zoom', '5')
    generator_types = request.args.get('types', None)  # Comma-separated list
    
    try:
        zoom_level = float(zoom_param)
    except (ValueError, TypeError):
        zoom_level = 5.0
        logger.warning(f"Invalid zoom parameter: {zoom_param}, defaulting to 5")
    
    logger.info(f"Processing generators request: zoom={zoom_level}, types={generator_types}")
    
    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Progressive disclosure based on zoom level
                if zoom_level < 7:
                    # Don't show generators at low zoom levels to avoid congestion
                    return https_fn.Response(
                        json.dumps({"type": "FeatureCollection", "features": []}),
                        status=200,
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "public, max-age=1800"
                        }
                    )
                elif zoom_level < 8:
                    # Medium zoom - show larger generators first
                    capacity_filter = ""
                    limit_clause = "LIMIT 200"
                elif zoom_level < 10:
                    # Closer zoom - show more generators
                    capacity_filter = ""
                    limit_clause = "LIMIT 500"
                else:
                    # Very close zoom - show all generators
                    capacity_filter = ""
                    limit_clause = "LIMIT 1000"
                
                # Initialize params list
                params = []
                
                # Base query using your actual table schema
                base_query = """
                    SELECT jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(feature)
                    )
                    FROM (
                        SELECT jsonb_build_object(
                            'type', 'Feature',
                            'id', g.generator_id,
                            'geometry', ST_AsGeoJSON(COALESCE(g.geom, p.geom))::jsonb,
                            'properties', jsonb_build_object(
                                'id', g.generator_id,
                                'name', COALESCE(p.name, 'Unnamed Generator'),
                                'plant_name', p.name,
                                'operator', COALESCE(g.operator, p.operator),
                                'fuel_type', COALESCE(g.generator_source, g.generator_type),
                                'generator_method', g.generator_method,
                                'power', COALESCE(g.power, p.power),
                                'size', g.size,
                                'manufacturer', g.manufacturer,
                                'model', g.model,
                                'start_date', COALESCE(g.start_date, p.start_date),
                                'output_electricity', COALESCE(g.output_electricity, p.output_electricity),
                                'geometry_type', ST_GeometryType(COALESCE(g.geom, p.geom))
                            )
                        ) AS feature
                        FROM dim_generators g
                        LEFT JOIN dim_plants p ON g.plant_id = p.plant_id
                        WHERE COALESCE(g.geom, p.geom) IS NOT NULL
                """
                
                # Add capacity filter if needed
                base_query += capacity_filter
                
                # Add generator type filter if specified
                if generator_types:
                    type_list = [t.strip().lower() for t in generator_types.split(',')]
                    type_conditions = []
                    for generator_type in type_list:
                        type_conditions.append("(LOWER(COALESCE(g.generator_source, '')) LIKE %s OR LOWER(COALESCE(g.generator_type, '')) LIKE %s)")
                        params.extend([f'%{generator_type}%', f'%{generator_type}%'])
                    if type_conditions:
                        base_query += f" AND ({' OR '.join(type_conditions)})"
                
                # Add ordering and limit
                base_query += f"""
                        ORDER BY g.generator_id
                        {limit_clause}
                    ) AS features;
                """
                
                cursor.execute(base_query, params)
                result = cursor.fetchone()
                geojson_data = result[0] if result and result[0] else {
                    "type": "FeatureCollection", 
                    "features": []
                }
                
                # Log statistics
                if geojson_data and geojson_data.get("features"):
                    total_features = len(geojson_data["features"])
                    fuel_types = {}
                    for f in geojson_data["features"]:
                        fuel_type = f.get("properties", {}).get("fuel_type", "Unknown")
                        fuel_types[fuel_type] = fuel_types.get(fuel_type, 0) + 1
                    
                    logger.info(f"Generators response: {total_features} generators, zoom={zoom_level}, fuel types: {fuel_types}")
                
                return https_fn.Response(
                    json.dumps(geojson_data),
                    status=200,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "public, max-age=1800"  # Cache for 30 minutes
                    }
                )
                
        except Exception as db_error:
            logger.error(f"Database error in get_power_generators: {db_error}")
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
        logger.error(f"General error in get_power_generators: {e}")
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_power_plants(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch power plant data as GeoJSON.
    Supports zoom-based progressive disclosure.
    """
    logger.info("Received request for power plants data.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_power_plants.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception:
            pass

    # Parse parameters
    zoom_param = request.args.get('zoom', '5')
    plant_types = request.args.get('types', None)  # Comma-separated list
    
    try:
        zoom_level = float(zoom_param)
    except (ValueError, TypeError):
        zoom_level = 5.0
        logger.warning(f"Invalid zoom parameter: {zoom_param}, defaulting to 5")
    
    logger.info(f"Processing plants request: zoom={zoom_level}, types={plant_types}")
    
    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Progressive disclosure based on zoom level
                if zoom_level < 7:
                    # Don't show plants at low zoom levels to avoid congestion
                    return https_fn.Response(
                        json.dumps({"type": "FeatureCollection", "features": []}),
                        status=200,
                        headers={
                            "Content-Type": "application/json",
                            "Cache-Control": "public, max-age=1800"
                        }
                    )
                elif zoom_level < 8:
                    # Medium zoom - show limited plants
                    limit_clause = "LIMIT 100"
                elif zoom_level < 10:
                    # Closer zoom - show more plants
                    limit_clause = "LIMIT 300"
                else:
                    # Very close zoom - show all plants
                    limit_clause = "LIMIT 500"
                
                # Initialize params list
                params = []
                
                # Base query using your actual table schema
                base_query = """
                    SELECT jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(feature)
                    )
                    FROM (
                        SELECT jsonb_build_object(
                            'type', 'Feature',
                            'id', p.plant_id,
                            'geometry', ST_AsGeoJSON(p.geom)::jsonb,
                            'properties', jsonb_build_object(
                                'id', p.plant_id,
                                'name', COALESCE(p.name, 'Unnamed Plant'),
                                'alt_name', p.alt_name,
                                'operator', p.operator,
                                'power', p.power,
                                'plant_source', p.plant_source,
                                'plant_method', p.plant_method,
                                'start_date', p.start_date,
                                'ref_us_eia', p.ref_us_eia,
                                'type', p.type,
                                'output_electricity', p.output_electricity,
                                'geometry_type', ST_GeometryType(p.geom)
                            )
                        ) AS feature
                        FROM dim_plants p
                        WHERE p.geom IS NOT NULL
                """
                
                # Add plant type filter if specified
                if plant_types:
                    type_list = [t.strip().lower() for t in plant_types.split(',')]
                    type_conditions = []
                    for plant_type in type_list:
                        type_conditions.append("(LOWER(COALESCE(p.plant_source, '')) LIKE %s OR LOWER(COALESCE(p.plant_method, '')) LIKE %s OR LOWER(COALESCE(p.type, '')) LIKE %s)")
                        params.extend([f'%{plant_type}%', f'%{plant_type}%', f'%{plant_type}%'])
                    if type_conditions:
                        base_query += f" AND ({' OR '.join(type_conditions)})"
                
                # Add ordering and limit
                base_query += f"""
                        ORDER BY p.plant_id
                        {limit_clause}
                    ) AS features;
                """
                
                cursor.execute(base_query, params)
                result = cursor.fetchone()
                geojson_data = result[0] if result and result[0] else {
                    "type": "FeatureCollection", 
                    "features": []
                }
                
                # Log statistics
                if geojson_data and geojson_data.get("features"):
                    total_features = len(geojson_data["features"])
                    plant_types_found = {}
                    for f in geojson_data["features"]:
                        plant_type = f.get("properties", {}).get("plant_source", "Unknown")
                        plant_types_found[plant_type] = plant_types_found.get(plant_type, 0) + 1
                    
                    logger.info(f"Plants response: {total_features} plants, zoom={zoom_level}, plant types: {plant_types_found}")
                
                return https_fn.Response(
                    json.dumps(geojson_data),
                    status=200,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "public, max-age=1800"  # Cache for 30 minutes
                    }
                )
                
        except Exception as db_error:
            logger.error(f"Database error in get_power_plants: {db_error}")
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
        logger.error(f"General error in get_power_plants: {e}")
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30,
)
def get_snotel_stations(request: https_fn.Request) -> https_fn.Response:
    logger.info("Received request for SNOTEL station locations.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_snotel_stations.")
                return https_fn.Response(json.dumps({"status": "warmed"}), status=200, headers={"Content-Type": "application/json"})
        except Exception:
            pass

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        snotel_stations_list = []
        try:
            with conn.cursor() as cursor:
                # Query to get station metadata, filtering for active stations with valid coordinates
                query_sql = """
                    SELECT station_id, station_triplet, name, latitude, longitude, elevation
                    FROM dim_station 
                    WHERE is_active = true AND latitude IS NOT NULL AND longitude IS NOT NULL;
                """
                cursor.execute(query_sql)
                rows = cursor.fetchall()
                
                for row_data in rows:
                    station_id, station_triplet, name, lat, lon, elevation = row_data
                    
                    try:
                        # Ensure coordinates and elevation are valid floats
                        snotel_stations_list.append({
                            "id": station_id,
                            "triplet": station_triplet,
                            "name": name,
                            "latitude": float(lat),
                            "longitude": float(lon),
                            "elevation": float(elevation) if elevation is not None else None
                        })
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse data for station_id {station_id} (name: {name}). Error: {e}. Skipping this station.")
                        continue
            
            return https_fn.Response(
                json.dumps(snotel_stations_list),
                status=200,
                headers={"Content-Type": "application/json"}
            )
        except Exception as db_error:
            logger.error(f"Database error in get_snotel_stations: {db_error}")
            logger.error(traceback.format_exc())
            if conn: conn.rollback()
            return https_fn.Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                headers={"Content-Type": "application/json"}
            )
        finally:
            if conn:
                pool.putconn(conn)
    except Exception as e:
        logger.error(f"General error in get_snotel_stations: {e}")
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_snotel_station_observations(request: https_fn.Request) -> https_fn.Response:
    """
    HTTP Cloud Function to fetch SNOTEL station observation data.
    Accepts 'station_id', optional 'days', and optional 'metric_id' query parameters.
    If no metric_id is provided, returns all available metrics for the station.
    """
    logger.info("Received request for SNOTEL station observations.")

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_snotel_station_observations.")
                return https_fn.Response(
                    json.dumps({"status": "warmed"}),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
        except Exception:
            pass

    # Parse query params
    station_id_param = request.args.get('station_id', '')
    days_param = request.args.get('days', '30')  # Default to 30 days
    metric_id_param = request.args.get('metric_id', '')  # Optional metric filter
    
    if not station_id_param:
        logger.warning("Missing station_id parameter.")
        return https_fn.Response(
            json.dumps({"error": "station_id parameter is required"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    try:
        station_id = int(station_id_param)
        days = int(days_param)
        days = max(1, min(days, 90))  # Limit between 1 and 90 days
        
        # Parse metric_id if provided
        metric_id = None
        if metric_id_param:
            metric_id = int(metric_id_param)
    except ValueError:
        logger.warning(f"Invalid parameters: station_id={station_id_param}, days={days_param}, metric_id={metric_id_param}")
        return https_fn.Response(
            json.dumps({"error": "station_id, days, and metric_id must be valid integers"}),
            status=400,
            headers={"Content-Type": "application/json"}
        )
    
    logger.info(f"Processing SNOTEL observations request for station_id: {station_id}, days: {days}, metric_id: {metric_id or 'all'}")

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        
        try:
            with conn.cursor() as cursor:
                # Build query based on whether metric_id is specified
                if metric_id:
                    # Query for specific metric
                    query_sql = """
                        SELECT ts_utc, station_id, metric_id, value_num, quality, 
                               source_id, inserted_at, height_depth_in
                        FROM fact_station_observation
                        WHERE station_id = %s 
                          AND metric_id = %s
                          AND ts_utc >= NOW() - INTERVAL '%s days'
                          AND value_num IS NOT NULL
                        ORDER BY ts_utc ASC;
                    """
                    cursor.execute(query_sql, (station_id, metric_id, days))
                else:
                    # Query for all SNOTEL metrics (25-31)
                    query_sql = """
                        SELECT ts_utc, station_id, metric_id, value_num, quality, 
                               source_id, inserted_at, height_depth_in
                        FROM fact_station_observation
                        WHERE station_id = %s 
                          AND metric_id IN (25, 26, 27, 28, 29, 30, 31)
                          AND ts_utc >= NOW() - INTERVAL '%s days'
                          AND value_num IS NOT NULL
                        ORDER BY metric_id, ts_utc ASC;
                    """
                    cursor.execute(query_sql, (station_id, days))
                
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    ts_utc, station_id_val, metric_id, value_num, quality, source_id, inserted_at, height_depth_in = row
                    
                    # Format datetime to ISO string
                    ts_utc_str = ts_utc.strftime('%Y-%m-%dT%H:%M:%SZ') if ts_utc else None
                    inserted_at_str = inserted_at.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if inserted_at else None
                    
                    # Convert value_num to float if it's a Decimal
                    value_num_float = None
                    if value_num is not None:
                        if isinstance(value_num, decimal.Decimal):
                            value_num_float = float(value_num)
                        elif isinstance(value_num, (int, float)):
                            value_num_float = float(value_num)
                        else:
                            try:
                                value_num_float = float(value_num)
                            except (ValueError, TypeError):
                                logger.warning(f"Could not convert value_num {value_num} to float for station_id {station_id}")
                                continue
                    
                    if value_num_float is not None:
                        result.append({
                            "ts_utc": ts_utc_str,
                            "station_id": station_id_val,
                            "metric_id": metric_id,
                            "value_num": value_num_float,
                            "quality": quality,
                            "source_id": source_id,
                            "inserted_at": inserted_at_str,
                            "height_depth_in": height_depth_in
                        })
                
                logger.info(f"Returning {len(result)} SNOTEL observation data points for station_id {station_id}")
                
                return https_fn.Response(
                    json.dumps(result),
                    status=200,
                    headers={"Content-Type": "application/json"}
                )
                
        except Exception as db_error:
            logger.error(f"Database error in get_snotel_station_observations: {db_error}")
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
        logger.error(f"General error in get_snotel_station_observations: {e}")
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
    memory=options.MemoryOption.MB_512
)
def get_bpa_generation_mix(request: https_fn.Request) -> https_fn.Response:
    """Get the latest BPA generation mix data for dashboard display."""
    try:
        # Get the latest timestamp for each metric
        query = """
        WITH latest_data AS (
            SELECT 
                metric_id,
                value_mw,
                timestamp_utc,
                ROW_NUMBER() OVER (PARTITION BY metric_id ORDER BY timestamp_utc DESC) as rn
            FROM fact_bpa_generation 
            WHERE source_id = 6 
              AND metric_id IN (40, 41, 42, 43, 44, 46)
              AND timestamp_utc >= NOW() - INTERVAL '2 hours'
        )
        SELECT 
            metric_id,
            value_mw,
            timestamp_utc
        FROM latest_data 
        WHERE rn = 1
        ORDER BY metric_id
        """
        
        rows = execute_query(query)
        
        # Map metric IDs to readable names
        metric_names = {
            40: "Load",
            41: "VER", 
            42: "Hydro",
            43: "Fossil/Biomass",
            44: "Nuclear",
            46: "Total Generation"
        }
        
        # Process the data
        generation_data = []
        load_value = 0
        total_generation = 0
        latest_timestamp = None
        
        for row in rows:
            metric_id = row['metric_id']        # Changed from row[0]
            value_mw = float(row['value_mw'])   # Changed from row[1]
            timestamp = row['timestamp_utc']    # Changed from row[2]
            
            if latest_timestamp is None:
                latest_timestamp = timestamp
                
            if metric_id == 40:  # Load
                load_value = value_mw
            elif metric_id == 46:  # Total Generation
                total_generation = value_mw
            elif metric_id in [41, 42, 43, 44]:  # Generation sources
                generation_data.append({
                    "type": metric_names[metric_id],
                    "value": value_mw,
                    "metric_id": metric_id
                })
        
        # Calculate net interchange (Generation - Load)
        net_interchange = total_generation - load_value if total_generation and load_value else 0
        
        response_data = {
            "timestamp": latest_timestamp.isoformat() if latest_timestamp else None,
            "load": load_value,
            "total_generation": total_generation,
            "net_interchange": net_interchange,
            "generation_mix": generation_data,
            "summary": {
                "total_mw": total_generation,
                "load_mw": load_value,
                "net_export_mw": net_interchange if net_interchange > 0 else 0,
                "net_import_mw": abs(net_interchange) if net_interchange < 0 else 0
            }
        }
        
        return https_fn.Response(
            json.dumps(response_data),
            status=200,
            headers={"Content-Type": "application/json"}
        )
        
    except Exception as e:
        logger.exception("Error fetching BPA generation mix")
        return https_fn.Response(
            json.dumps({"error": str(e)}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

# Add a new function for BPA time series
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
    memory=options.MemoryOption.MB_512,
    timeout_sec=30
)
def get_bpa_generation_timeseries(request: https_fn.Request) -> https_fn.Response:
    """Get BPA generation mix time series data."""
    try:
        # Get query parameters
        range_param = request.args.get('range', '1d')  # Default to 1 day
        
        # Calculate time range
        now_utc = datetime.now(timezone.utc)
        
        if range_param == '1d':
            start_utc = now_utc - timedelta(days=1)
        elif range_param == '7d':
            start_utc = now_utc - timedelta(days=7)
        elif range_param == '14d':
            start_utc = now_utc - timedelta(days=14)
        elif range_param == 'mtd':
            start_utc = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_utc = now_utc - timedelta(days=1)
        
        # Query for time series data
        query = """
        SELECT 
            timestamp_utc,
            metric_id,
            value_mw
        FROM fact_bpa_generation 
        WHERE source_id = 6 
          AND metric_id IN (40, 41, 42, 43, 44, 46)
          AND timestamp_utc >= %s 
          AND timestamp_utc <= %s
        ORDER BY timestamp_utc ASC, metric_id ASC
        """
        
        rows = execute_query(query, (start_utc, now_utc))
        
        # Map metric IDs to readable names
        metric_names = {
            40: "Load",
            41: "VER", 
            42: "Hydro",
            43: "Fossil/Biomass",
            44: "Nuclear",
            46: "Total Generation"
        }
        
        # Group data by timestamp
        data_by_timestamp = {}
        
        for row in rows:
            timestamp = row['timestamp_utc']
            metric_id = row['metric_id']
            value_mw = float(row['value_mw'])
            
            timestamp_str = timestamp.isoformat()
            
            if timestamp_str not in data_by_timestamp:
                data_by_timestamp[timestamp_str] = {
                    'timestamp': timestamp_str,
                    'Load': 0,
                    'VER': 0,
                    'Hydro': 0,
                    'Fossil/Biomass': 0,
                    'Nuclear': 0,
                    'Total Generation': 0
                }
            
            if metric_id in metric_names:
                data_by_timestamp[timestamp_str][metric_names[metric_id]] = value_mw
        
        # Convert to array and calculate net interchange
        result = []
        for timestamp_str, data in sorted(data_by_timestamp.items()):
            net_interchange = data['Total Generation'] - data['Load']
            
            result.append({
                'timestamp': timestamp_str,
                'Load': data['Load'],
                'VER': data['VER'],
                'Hydro': data['Hydro'],
                'Fossil/Biomass': data['Fossil/Biomass'],
                'Nuclear': data['Nuclear'],
                'Total_Generation': data['Total Generation'],
                'Net_Interchange': net_interchange
            })
        
        return https_fn.Response(
            json.dumps(result),
            status=200,
            headers={"Content-Type": "application/json"}
        )
        
    except Exception as e:
        logger.exception("Error fetching BPA generation time series")
        return https_fn.Response(
            json.dumps({"error": str(e)}),
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
        cors_methods=["get", "post", "options"],
    ),
    memory=options.MemoryOption.MB_512,
    timeout_sec=60,
)
def ingest_bpa_icr(request: https_fn.Request) -> https_fn.Response:
    """
    Ingest BPA ICR Excel, publish diffs, upsert to DB via our Django pool.
    """
    headers = {"Access-Control-Allow-Origin": "*"}

    ICR_URL       = (
        "https://www.bpa.gov/-/media/Aep/transmission-media-documents/"
        "InterconnectionQueueOutput.xlsx"
    )
    
    ICR_DIFF_BUCKET = "crystal-icr-reports"
    # CORS preflight
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        })

    logger.info("Starting BPA ICR ingest")

    # 1) Download & parse latest Excel
    try:
        df_new = download_icr_excel(ICR_URL)
        df_new.set_index("request_number", inplace=True)
    except Exception as e:
        logger.error(f"Failed to download or parse ICR Excel: {e}", exc_info=True)
        return https_fn.Response(
            json.dumps({"status": "error", "message": "Download/parse failed", "details": str(e)}),
            status=500,
            headers=headers
        )

    # 2) Fetch existing state from Django's pool
    pool = get_connection_pool()
    conn = pool.getconn()
    try:
        df_old = fetch_existing_icr(conn)

        # 3) Compute diffs
        df_diff = compute_diffs(df_new, df_old)

        # 4) If any changes, write diff file, publish Pub/Sub, email
        if not df_diff.empty:
            print("There was a change!")
            print(df_diff)
            # diff_uri = upload_diff_to_gcs(df_diff, ICR_DIFF_BUCKET)
            # publish_notification(
            #     os.environ["ICR_PUBSUB_TOPIC"],
            #     {
            #         "event": "icr_diff",
            #         "diff_uri": diff_uri,
            #         "rows_changed": len(df_diff),
            #         "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            #     },
            # )
            # # optional email alert
            # html = (
            #     f"<p>ICR diff detected: {len(df_diff)} changes.</p>"
            #     f"<p>See <a href='{diff_uri}'>{diff_uri}</a></p>"
            # )
            # send_email("BPA ICR Diff Notification", html)

        # 5) Upsert all rows
        affected = upsert_icr(conn, df_new)
        conn.commit()

        msg = {
            "status": "success",
            "message": f"ICR ingest complete – {len(df_diff)} diffs, {affected} upserted."
        }
        logger.info(msg["message"])
        return https_fn.Response(json.dumps(msg), status=200, headers=headers)

    except Exception as err:
        conn.rollback()
        logger.exception("ICR ingest transaction failed")
        return https_fn.Response(
            json.dumps({"status": "error", "message": str(err)}),
            status=500,
            headers=headers
        )
    finally:
        pool.putconn(conn)