#!/bin/bash

echo "Stopping development environment..."

# Stop Firebase emulator
echo "Stopping Firebase emulator..."
docker-compose down

# Kill the Cloud SQL proxy
echo "Stopping Cloud SQL proxy..."
ps aux | grep 'cloud-sql-proxy' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true

echo "✅ Development environment stopped"