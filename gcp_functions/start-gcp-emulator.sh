#!/bin/bash
#
# This script starts a local emulator for Google Cloud Functions
# defined in the 'functions' directory.
#

echo "--- Starting Google Cloud Functions Emulator ---"

# The port to run the emulator on
PORT=8081

# The source file within the 'functions' directory containing the function
SOURCE_FILE="gcp_main.py"

# Navigate to the functions directory
cd "$(dirname "$0")"

# Install/update dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# List all top-level functions in the source file

echo "Loaded functions in '$SOURCE_FILE':"
python3 -c "import ast; print(', '.join([f.name for f in ast.parse(open('$SOURCE_FILE').read()).body if isinstance(f, ast.FunctionDef)]))"

# Start the Functions Framework emulator
echo "Starting emulator for all functions in '$SOURCE_FILE' on port $PORT..."
functions-framework --source "$SOURCE_FILE" --target "main" --port "$PORT" --debug

echo "Emulator stopped." 