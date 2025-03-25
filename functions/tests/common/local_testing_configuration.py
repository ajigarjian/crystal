import sys
import json
import logging
import traceback
from firebase_admin import firestore
import firebase_admin
import os
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set emulator flag for local testing
os.environ["FUNCTIONS_EMULATOR"] = "True"

# Initialize Firebase app if not already initialized
try:
    firebase_admin.get_app()
except ValueError:
    # Turn on emulator if needed
    if os.getenv('FUNCTIONS_EMULATOR'):
        os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"  # adjust port if needed
    firebase_admin.initialize_app()