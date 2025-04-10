#!/bin/bash

# Set the project root directory
PROJECT_ROOT="/Users/cedricfitzgerald/Documents/Startup/crystal"

# Change to the functions directory
cd "$PROJECT_ROOT/functions"

# Add the functions directory to PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT/functions:$PYTHONPATH"

# Skip makemigrations to avoid generating migration 16
# python factchecker/manage.py makemigrations

# Run migrations for Django models in factchecker
python factchecker/manage.py migrate

# Run the extraction command to extract JSON data into structured fields
echo "Running extraction command..."
python factchecker/manage.py add_linkrot_tracking

echo "Migration completed."