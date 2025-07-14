import os
import json
import logging
import traceback
from flask import jsonify, Response
from helpers.db_utils import get_connection_pool, check_usage_limit

def get_wildfires(request):
    """
    GCP Cloud Function endpoint to fetch wildfire perimeter data as GeoJSON.
    Supports zoom-based progressive disclosure and filtering by status/state.
    Includes rate limiting and CORS headers.
    """
    logger = logging.getLogger(__name__)
    logger.info("get_wildfires function initialized successfully.")

    # CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': request.headers.get('Origin', '*'),
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }

    # Handle preflight requests
    if request.method == 'OPTIONS':
        response = Response(status=204)
        response.headers.update(cors_headers)
        return response

    # Rate limiting
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) if hasattr(request, 'headers') else None
    exceeded, error_message = check_usage_limit(ip_address, 'get_wildfires')
    if exceeded:
        response = jsonify({"error": error_message})
        response.status_code = 429
        response.headers.update(cors_headers)
        return response

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_wildfires.")
                response = Response(json.dumps({"status": "warmed"}), status=200, mimetype="application/json")
                response.headers.update(cors_headers)
                return response
        except Exception:
            pass

    # Parse parameters
    zoom_param = request.args.get('zoom', '5') if hasattr(request, 'args') else '5'
    status_filter = request.args.get('status', None) if hasattr(request, 'args') else None
    state_filter = request.args.get('state', None) if hasattr(request, 'args') else None
    active_only = request.args.get('active_only', 'false').lower() == 'true' if hasattr(request, 'args') else False
    
    try:
        zoom_level = float(zoom_param)
    except (ValueError, TypeError):
        zoom_level = 5.0
        logger.warning(f"Invalid zoom parameter: {zoom_param}, defaulting to 5")

    logger.info(f"Processing wildfires request: zoom={zoom_level}, status={status_filter}, state={state_filter}, active_only={active_only}")

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Progressive disclosure based on zoom level
                if zoom_level < 6:
                    # Show only major fires at low zoom levels
                    limit_clause = "LIMIT 50"
                    size_filter = "AND (gis_acres > 1000 OR percent_contained < 100 OR percent_contained IS NULL)"
                elif zoom_level < 8:
                    limit_clause = "LIMIT 200"
                    size_filter = "AND (gis_acres > 100 OR percent_contained < 100 OR percent_contained IS NULL)"
                elif zoom_level < 10:
                    limit_clause = "LIMIT 500"
                    size_filter = ""
                else:
                    limit_clause = "LIMIT 1000"
                    size_filter = ""

                params = []
                base_query = """
                    SELECT jsonb_build_object(
                        'type', 'FeatureCollection',
                        'features', jsonb_agg(feature)
                    )
                    FROM (
                        SELECT jsonb_build_object(
                            'type', 'Feature',
                            'id', w.irwin_id,
                            'geometry', ST_AsGeoJSON(w.geom)::jsonb,
                            'properties', jsonb_build_object(
                                'irwin_id', w.irwin_id,
                                'incident_name', COALESCE(w.incident_name, 'Unnamed Fire'),
                                'gis_acres', w.gis_acres,
                                'reported_acres', w.reported_acres,
                                'percent_contained', w.percent_contained,
                                'status', w.status,
                                'incident_type', w.incident_type,
                                'complexity_level', w.complexity_level,
                                'cause_general', w.cause_general,
                                'state', w.state,
                                'county', w.county,
                                'discovery_time', w.discovery_time,
                                'perimeter_time', w.perimeter_time,
                                'last_update_src', w.last_update_src,
                                'ingestion_timestamp', w.ingestion_timestamp,
                                'geometry_type', ST_GeometryType(w.geom)
                            )
                        ) AS feature
                        FROM fact_wildfire_perimeters w
                        WHERE w.geom IS NOT NULL
                """
                
                # Add size filter for zoom levels
                if size_filter:
                    base_query += f" {size_filter}"

                # Add status filter
                if status_filter:
                    base_query += " AND LOWER(w.status) = LOWER(%s)"
                    params.append(status_filter)

                # Add state filter
                if state_filter:
                    base_query += " AND LOWER(w.state) = LOWER(%s)"
                    params.append(state_filter)

                # Add active only filter (fires that are not 100% contained)
                if active_only:
                    base_query += " AND (w.percent_contained < 100 OR w.percent_contained IS NULL)"

                # Order by most recent and largest fires first
                base_query += """
                        ORDER BY 
                            CASE WHEN w.percent_contained < 100 OR w.percent_contained IS NULL THEN 0 ELSE 1 END,
                            w.last_update_src DESC NULLS LAST,
                            w.gis_acres DESC NULLS LAST
                        {limit_clause}
                    ) AS features;
                """.format(limit_clause=limit_clause)

                cursor.execute(base_query, params)
                result = cursor.fetchone()
                geojson_data = result[0] if result and result[0] else {
                    "type": "FeatureCollection",
                    "features": []
                }

                # Log statistics
                if geojson_data and geojson_data.get("features"):
                    total_features = len(geojson_data["features"])
                    status_counts = {}
                    state_counts = {}
                    active_count = 0
                    
                    for f in geojson_data["features"]:
                        props = f.get("properties", {})
                        status = props.get("status", "Unknown")
                        state = props.get("state", "Unknown")
                        percent_contained = props.get("percent_contained")
                        
                        status_counts[status] = status_counts.get(status, 0) + 1
                        state_counts[state] = state_counts.get(state, 0) + 1
                        if percent_contained is None or percent_contained < 100:
                            active_count += 1
                    
                    logger.info(f"Wildfires response: {total_features} fires, {active_count} active, zoom={zoom_level}")
                    logger.info(f"Status breakdown: {status_counts}")
                    logger.info(f"State breakdown: {state_counts}")

                response = Response(
                    json.dumps(geojson_data),
                    status=200,
                    mimetype="application/json"
                )
                response.headers.update(cors_headers)
                response.headers['Cache-Control'] = 'public, max-age=300'  # 5 minutes cache for live data
                return response

        except Exception as db_error:
            logger.error(f"Database error in get_wildfires: {db_error}")
            logger.error(traceback.format_exc())
            if conn:
                conn.rollback()
            response = Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                mimetype="application/json"
            )
            response.headers.update(cors_headers)
            return response
        finally:
            if conn:
                pool.putconn(conn)

    except Exception as e:
        logger.error(f"General error in get_wildfires: {e}")
        logger.error(traceback.format_exc())
        response = Response(
            json.dumps({"error": "An internal server error occurred.", "details": str(e)}),
            status=500,
            mimetype="application/json"
        )
        response.headers.update(cors_headers)
        return response 