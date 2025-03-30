#!/bin/bash

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
  echo "Error: Docker is not running. Please start Docker Desktop or Docker service first."
  exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose > /dev/null 2>&1; then
  echo "Error: docker-compose is not installed or not in PATH."
  exit 1
fi

echo "Setting up development environment..."
echo "Step 1: Starting Cloud SQL proxy..."

# Start the Cloud SQL proxy first
./start-sql-proxy.sh

# If the SQL proxy didn't start, exit
if [ $? -ne 0 ]; then
  echo "Failed to start Cloud SQL proxy. Exiting."
  exit 1
fi

echo -e "\nStep 2: Building and starting Firebase emulator..."
echo "This may take a few minutes on first run while Java and dependencies are installed."

# Stop any existing emulator containers
docker-compose down

# Build and start the container in detached mode
docker-compose up -d --build

# Display initial status
echo "Firebase emulator starting in Docker container..."
echo "Emulator UI will be available at: http://localhost:4000"
echo "Functions endpoint: http://localhost:5001/crystal-2f87e/us-central1/"

# Wait for container to initialize
echo "Waiting for emulator to start (this may take up to a minute)..."
sleep 15

# Show logs to see startup progress
echo "Container logs for Firebase emulator:"
docker-compose logs firebase-emulator | tail -30

# Check if the container is still running
FIREBASE_RUNNING=$(docker-compose ps | grep firebase-emulator | grep -q "Up" && echo "yes" || echo "no")

if [ "$FIREBASE_RUNNING" = "yes" ]; then
  echo -e "\n✅ Development environment is ready!"
  echo "- Firebase emulator is running on http://localhost:4000"
  echo "- Functions are available at http://localhost:5001/crystal-2f87e/us-central1/"
  echo "- Cloud SQL proxy is running on localhost:1234"
  echo ""
  echo "To view Firebase logs in real-time: docker-compose logs -f"
  echo "To view Cloud SQL proxy logs: tail -f /tmp/cloud-sql-proxy.log"
  echo "To stop everything: ./stop-dev.sh"
else
  echo -e "\n❌ Firebase emulator failed to start. See logs above for details."
  echo "Cleaning up..."
  docker-compose down
  
  # Kill the SQL proxy if we need to clean up
  ps aux | grep 'cloud-sql-proxy' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true
  
  exit 1
fi