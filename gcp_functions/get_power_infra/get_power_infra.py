import os
import json
import logging
import traceback
from flask import jsonify, Response
from helpers.db_utils import get_connection_pool, check_usage_limit

def get_power_infrastructure(request):
    """
    GCP Cloud Function endpoint to fetch BPA power infrastructure data as GeoJSON.
    Supports zoom-based simplification. Includes rate limiting and CORS headers.
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

    zoom_str = request.args.get('zoom') if hasattr(request, 'args') else None
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
                    geom_sql = "ST_AsGeoJSON(ST_SimplifyPreserveTopology(pi.geom, 0.01))::jsonb"
                else:
                    geom_sql = "ST_AsGeoJSON(pi.geom)::jsonb"

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

                response = Response(
                    json.dumps(geojson_data),
                    status=200,
                    mimetype="application/json"
                )
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                response.headers['Cache-Control'] = 'public, max-age=3600'
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
