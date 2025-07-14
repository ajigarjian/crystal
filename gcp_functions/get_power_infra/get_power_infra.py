import os
import json
import logging
import traceback
from datetime import datetime, timezone
from flask import jsonify, Response
from helpers.db_utils import get_connection_pool, check_usage_limit

def get_power_infrastructure(request):
    """
    GCP Cloud Function endpoint to fetch BPA power infrastructure data as GeoJSON.
    Supports zoom-based simplification and temporal capacity factor data.
    Includes rate limiting and CORS headers.
    """
    logger = logging.getLogger(__name__)
    logger.info("get_power_infrastructure function initialized successfully.")

    # Rate limiting
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) if hasattr(request, 'headers') else None
    exceeded, error_message = check_usage_limit(ip_address, 'get_power_infrastructure')
    if exceeded:
        response = jsonify({"error": error_message})
        response.status_code = 429
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    # Handle warming requests
    if request.method == 'POST':
        try:
            request_json = request.get_json(silent=True)
            if request_json and request_json.get('warming'):
                logger.info("Warming request received for get_power_infrastructure.")
                response = Response(json.dumps({"status": "warmed"}), status=200, mimetype="application/json")
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                return response
        except Exception:
            pass

    # Parse parameters
    zoom_str = request.args.get('zoom') if hasattr(request, 'args') else None
    datetime_str = request.args.get('datetime') if hasattr(request, 'args') else None
    date_range_str = request.args.get('date_range') if hasattr(request, 'args') else None
    
    try:
        zoom = int(zoom_str) if zoom_str else None
    except (ValueError, TypeError):
        zoom = None
    
    # Parse datetime parameter
    target_datetime = None
    if datetime_str:
        try:
            # Expect ISO format: 2025-01-14T15:00:00Z
            target_datetime = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid datetime parameter: {datetime_str}, error: {e}")
            response = jsonify({"error": f"Invalid datetime format. Expected ISO format: YYYY-MM-DDTHH:MM:SSZ"})
            response.status_code = 400
            response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
    
    # Parse date range parameter (e.g., "4w" for 4 weeks)
    date_range_weeks = None
    if date_range_str:
        try:
            if date_range_str.endswith('w'):
                date_range_weeks = int(date_range_str[:-1])
            else:
                raise ValueError("Date range must end with 'w' for weeks")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid date_range parameter: {date_range_str}, error: {e}")
            response = jsonify({"error": f"Invalid date_range format. Expected format: '4w' for 4 weeks"})
            response.status_code = 400
            response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response

    try:
        pool = get_connection_pool()
        conn = pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Determine geometry transformation based on zoom level
                if zoom is not None and zoom < 7:
                    geom_sql = "ST_AsGeoJSON(ST_SimplifyPreserveTopology(pi.geom, 0.01))::jsonb"
                else:
                    geom_sql = "ST_AsGeoJSON(pi.geom)::jsonb"

                # Build the capacity factor query based on parameters
                if date_range_weeks:
                    # Query for date range - get all capacity factors within the range
                    # Calculate start and end dates (2 weeks before and after current time)
                    from datetime import timedelta
                    now = datetime.now(timezone.utc)
                    half_range_days = (date_range_weeks * 7) // 2
                    start_date = now - timedelta(days=half_range_days)
                    end_date = now + timedelta(days=half_range_days)
                    
                    # Truncate to hour boundaries
                    start_date = start_date.replace(minute=0, second=0, microsecond=0)
                    end_date = end_date.replace(minute=0, second=0, microsecond=0)
                    
                    capacity_factor_subquery = """
                        LEFT JOIN (
                            SELECT 
                                df.flowgate_code,
                                jsonb_agg(
                                    jsonb_build_object(
                                        'datetime_utc', fth.datetime_utc,
                                        'capacity_factor', fth.value_mw,
                                        'quality', fth.quality
                                    ) ORDER BY fth.datetime_utc
                                ) as time_series_data
                            FROM fact_ttc_hourly fth
                            JOIN dim_flowgate df ON fth.flowgate_id = df.flowgate_id
                            WHERE fth.metric_id = 24 -- Capacity Factor metric
                              AND df.is_active = true
                              AND fth.datetime_utc >= %s
                              AND fth.datetime_utc <= %s
                            GROUP BY df.flowgate_code
                        ) AS time_series_ttc ON pfg.flowgate = time_series_ttc.flowgate_code
                    """
                    query_params = [start_date, end_date, date_range_weeks, start_date, end_date]
                    logger.info(f"Querying capacity factors for date range: {start_date} to {end_date} ({date_range_weeks} weeks)")
                    
                elif target_datetime:
                    # Query for specific datetime - check both historical (R) and forecast (F) data
                    capacity_factor_subquery = """
                        LEFT JOIN (
                            SELECT DISTINCT ON (df.flowgate_code)
                                df.flowgate_code,
                                fth.value_mw as latest_capacity_factor,
                                fth.datetime_utc as latest_timestamp,
                                fth.quality as data_quality
                            FROM fact_ttc_hourly fth
                            JOIN dim_flowgate df ON fth.flowgate_id = df.flowgate_id
                            WHERE fth.metric_id = 24 -- Capacity Factor metric
                              AND df.is_active = true
                              AND fth.datetime_utc = DATE_TRUNC('hour', %s AT TIME ZONE 'UTC')
                            ORDER BY df.flowgate_code, fth.ingestion_timestamp DESC
                        ) AS latest_ttc ON pfg.flowgate = latest_ttc.flowgate_code
                    """
                    query_params = [target_datetime]
                    logger.info(f"Querying capacity factors for datetime: {target_datetime}")
                else:
                    # Default behavior - query for current hour
                    capacity_factor_subquery = """
                        LEFT JOIN (
                            SELECT DISTINCT ON (df.flowgate_code)
                                df.flowgate_code,
                                fth.value_mw as latest_capacity_factor,
                                fth.datetime_utc as latest_timestamp,
                                fth.quality as data_quality
                            FROM fact_ttc_hourly fth
                            JOIN dim_flowgate df ON fth.flowgate_id = df.flowgate_id
                            WHERE fth.metric_id = 24 -- Capacity Factor metric
                              AND df.is_active = true
                              AND fth.datetime_utc = DATE_TRUNC('hour', NOW() AT TIME ZONE 'UTC')
                            ORDER BY df.flowgate_code, fth.ingestion_timestamp DESC
                        ) AS latest_ttc ON pfg.flowgate = latest_ttc.flowgate_code
                    """
                    query_params = []
                    logger.info("Querying capacity factors for current hour (default behavior)")

                # Build different query structures for single datetime vs date range
                if date_range_weeks:
                    # For date range queries, include time series data
                    query = f"""
                        SELECT jsonb_build_object(
                            'type', 'FeatureCollection',
                            'features', jsonb_agg(feature),
                            'time_range', jsonb_build_object(
                                'start_date', %s,
                                'end_date', %s,
                                'weeks', %s
                            )
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
                                    'time_series_data', time_series_ttc.time_series_data
                                )
                            ) AS feature
                            FROM power_infra pi
                            LEFT JOIN power_flow_gates pfg ON pi.openinfra_name = pfg.openinfra_name
                            {capacity_factor_subquery}
                            WHERE pi.geom IS NOT NULL
                            ORDER BY pi.gid, (pfg.flowgate IS NOT NULL) DESC, pfg.flowgate
                        ) AS features;
                    """

                else:
                    # For single datetime queries, use the existing structure
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
                                    'capacity_factor_timestamp', latest_ttc.latest_timestamp,
                                    'data_quality', latest_ttc.data_quality
                                )
                            ) AS feature
                            FROM power_infra pi
                            LEFT JOIN power_flow_gates pfg ON pi.openinfra_name = pfg.openinfra_name
                            {capacity_factor_subquery}
                            WHERE pi.geom IS NOT NULL
                            ORDER BY pi.gid, (pfg.flowgate IS NOT NULL) DESC, pfg.flowgate
                        ) AS features;
                    """
                
                cursor.execute(query, query_params)
                result = cursor.fetchone()
                geojson_data = result[0] if result and result[0] else {
                    "type": "FeatureCollection",
                    "features": []
                }

                # Debug: Log information about flowgates and capacity factors
                if geojson_data and geojson_data.get("features"):
                    total_features = len(geojson_data["features"])
                    flowgate_features = [f for f in geojson_data["features"] if f.get("properties", {}).get("flowgate")]
                    unique_flowgates = set()
                    capacity_factor_stats = {"green": 0, "yellow": 0, "orange": 0, "red": 0}
                    quality_stats = {"R": 0, "F": 0, "none": 0}
                    
                    for f in geojson_data["features"]:
                        fg = f.get("properties", {}).get("flowgate")
                        if fg:
                            unique_flowgates.add(fg)
                            cf = f.get("properties", {}).get("capacity_factor", 0)
                            if cf < 0.5:
                                capacity_factor_stats["red"] += 1
                            elif cf < 0.8:
                                capacity_factor_stats["orange"] += 1
                            elif cf < 1.0:
                                capacity_factor_stats["yellow"] += 1
                            else:
                                capacity_factor_stats["green"] += 1
                                
                            # Track data quality
                            quality = f.get("properties", {}).get("data_quality")
                            if quality == "R":
                                quality_stats["R"] += 1
                            elif quality == "F":
                                quality_stats["F"] += 1
                            else:
                                quality_stats["none"] += 1
                    
                    logger.info(f"Power infrastructure debug: {total_features} total features, {len(flowgate_features)} with flowgates")
                    logger.info(f"Unique flowgates: {sorted(unique_flowgates)}")
                    logger.info(f"Capacity factor distribution: {capacity_factor_stats}")
                    logger.info(f"Data quality distribution: {quality_stats}")

                response = Response(
                    json.dumps(geojson_data),
                    status=200,
                    mimetype="application/json"
                )
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                
                # Adjust cache control based on whether we're showing current or historical data
                if target_datetime:
                    # Historical/specific time data can be cached longer
                    response.headers['Cache-Control'] = 'public, max-age=1800'  # 30 minutes
                else:
                    # Current time data should be cached for shorter duration
                    response.headers['Cache-Control'] = 'public, max-age=300'   # 5 minutes
                
                return response
        except Exception as db_error:
            logger.error(f"Database error in get_power_infrastructure: {db_error}")
            logger.error(traceback.format_exc())
            if conn:
                conn.rollback()
            response = Response(
                json.dumps({"error": "A database error occurred.", "details": str(db_error)}),
                status=500,
                mimetype="application/json"
            )
            response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            return response
        finally:
            if conn:
                pool.putconn(conn)
    except Exception as e:
        logger.error(f"General error in get_power_infrastructure: {e}")
        logger.error(traceback.format_exc())
        response = Response(
            json.dumps({"error": "An internal server error occurred.", "details": str(e)}),
            status=500,
            mimetype="application/json"
        )
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
