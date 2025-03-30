#!/bin/bash

echo "Starting diagnostic check for Firebase emulator..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker Desktop or Docker service first."
  exit 1
fi

# Build the simple container to diagnose the issue
echo "Building simple diagnostic container..."
docker-compose -f docker-compose.simple.yml build --no-cache

# Run the container with full output
echo "Running emulator in diagnostic mode..."
docker-compose -f docker-compose.simple.yml up

# Container will exit, check the logs
echo "Container exited. Checking logs..."
docker-compose -f docker-compose.simple.yml logs

# Clean up
echo "Cleaning up..."
docker-compose -f docker-compose.simple.yml down