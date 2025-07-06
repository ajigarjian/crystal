import os
import json
import logging
import traceback
from flask import jsonify, Response
from helpers.db_utils import get_connection_pool, check_usage_limit

def get_power_generators(request):
    """
    GCP Cloud Function endpoint to fetch power generator data as GeoJSON.
    Supports zoom-based progressive disclosure. Includes rate limiting and CORS headers.
    """
    logger = logging.getLogger(__name__)
    logger.info("get_power_generators function initialized successfully.")

    # Rate limiting
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) if hasattr(request, 'headers') else None
    exceeded, error_message = check_usage_limit(ip_address, 'get_power_generators')
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
                logger.info("Warming request received for get_power_generators.")
                response = Response(json.dumps({"status": "warmed"}), status=200, mimetype="application/json")
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                return response
        except Exception:
            pass

    # Parse parameters
    zoom_param = request.args.get('zoom', '5') if hasattr(request, 'args') else '5'
    generator_types = request.args.get('types', None) if hasattr(request, 'args') else None
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
                    response = Response(json.dumps({"type": "FeatureCollection", "features": []}), status=200, mimetype="application/json")
                    response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                    response.headers['Cache-Control'] = 'public, max-age=1800'
                    return response
                elif zoom_level < 8:
                    limit_clause = "LIMIT 200"
                elif zoom_level < 10:
                    limit_clause = "LIMIT 500"
                else:
                    limit_clause = "LIMIT 1000"

                params = []
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
                response = Response(
                    json.dumps(geojson_data),
                    status=200,
                    mimetype="application/json"
                )
                response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                response.headers['Cache-Control'] = 'public, max-age=1800'
                return response
        except Exception as db_error:
            logger.error(f"Database error in get_power_generators: {db_error}")
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
        logger.error(f"General error in get_power_generators: {e}")
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