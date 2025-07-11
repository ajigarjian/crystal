# This is like the old Firebase main.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import django
import json
import asyncio
import traceback
import logging
from flask import Flask, request as flask_request, jsonify, make_response, Response

os.environ["FUNCTIONS_EMULATOR"] = "True" # This file should only be run from the local emulator, never deployed.

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_app.settings")

# Configure Django settings
try:
    django.setup()
except Exception as django_setup_error:
    logger = logging.getLogger(__name__)
    logger.error(f"Error in django.setup(): {django_setup_error}")
    # If running in production and error might be related to database connection
    if not os.getenv('FUNCTIONS_EMULATOR') and 'database' in str(django_setup_error).lower():
        try:
            # Import settings to access the fallback configuration
            from django_app import settings
            # Apply fallback database configuration
            if hasattr(settings, 'DB_FALLBACK'):
                logger.info("Attempting to use fallback database configuration")
                settings.DATABASES = settings.DB_FALLBACK
        except Exception as fallback_error:
            logger.error(f"Fallback configuration also failed: {fallback_error}")
            raise

from helpers.db_utils import check_usage_limit
from energy_agent.energy_agent import energy_agent_stream_generator
# Import power functions
from get_power_generators.get_power_generators import get_power_generators
from get_power_infra.get_power_infra import get_power_infrastructure
from get_power_plants.get_power_plants import get_power_plants

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Allowed origins for CORS
ALLOWED_ORIGINS = [
    "https://crystal-2f87e.web.app",
    "https://askcrystal.info",
    "https://www.askcrystal.info",
    "http://localhost:3000",
    "http://localhost:5173",
]

def _add_cors_headers(response):
    """Adds CORS headers to the response."""
    try:
        origin = flask_request.headers.get('Origin')
        if origin in ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    except Exception:
        pass  # If not running under Flask, skip CORS
    return response

# --- Standalone GCP-compatible functions ---

def energy_agent(request):
    """
    Energy Agent endpoint for GCP Cloud Functions. It delegates the streaming logic
    to a specialized handler.
    """
    from energy_agent.energy_agent import energy_agent as agent_entry
    return agent_entry(request)

def hello_world(request):
    """Dummy Hello World endpoint for testing purposes."""
    logger.info("hello_world function initialized successfully.")
    response = jsonify({"message": "Hello, world!"})
    response.status_code = 200
    return _add_cors_headers(response)

# --- Flask app for local emulation and GCP Function entrypoint ---

app = Flask(__name__)

@app.route('/energy_agent', methods=['GET', 'POST', 'OPTIONS'])
def energy_agent_route():
    if flask_request.method == "OPTIONS":
        return _add_cors_headers(Response(status=204))
    return energy_agent(flask_request)

@app.route('/hello_world', methods=['GET', 'POST', 'OPTIONS'])
def hello_world_route():
    if flask_request.method == "OPTIONS":
        return _add_cors_headers(Response(status=204))
    return hello_world(flask_request)

@app.route('/get-power-generators', methods=['GET', 'POST', 'OPTIONS'])
def get_power_generators_route():
    if flask_request.method == "OPTIONS":
        return _add_cors_headers(Response(status=204))
    return get_power_generators(flask_request)

@app.route('/get-power-infrastructure', methods=['GET', 'POST', 'OPTIONS'])
def get_power_infrastructure_route():
    if flask_request.method == "OPTIONS":
        return _add_cors_headers(Response(status=204))
    return get_power_infrastructure(flask_request)

@app.route('/get-power-plants', methods=['GET', 'POST', 'OPTIONS'])
def get_power_plants_route():
    if flask_request.method == "OPTIONS":
        return _add_cors_headers(Response(status=204))
    return get_power_plants(flask_request)

def main(request):
    """
    Main entry point for GCP Cloud Functions that dispatches requests to the Flask app.
    """
    with app.request_context(request.environ):
        return app.full_dispatch_request()

if __name__ == "__main__":
    EMULATOR_PORT = os.environ.get("PORT", "8081")
    print("\nRegistered HTTP functions in emulator:")
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            print(f" - {rule.endpoint}: http://localhost:{EMULATOR_PORT}{rule.rule}")
    app.run(host="0.0.0.0", port=int(EMULATOR_PORT), debug=True)