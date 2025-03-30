#!/bin/bash

# Check if Cloud SQL Proxy executable exists in scripts/sql
if [ ! -f "scripts/sql/cloud-sql-proxy" ]; then
  echo "Error: Cloud SQL Proxy executable not found in scripts/sql/cloud-sql-proxy"
  exit 1
fi

# Stop any existing proxy
ps aux | grep 'cloud-sql-proxy' | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || true

echo "Starting Cloud SQL Proxy locally..."
echo "Connecting to crystal-2f87e:us-east4:crystal-sql on port 1234"

# Make sure the proxy is executable
chmod +x scripts/sql/cloud-sql-proxy

# Start the proxy in the background
nohup scripts/sql/cloud-sql-proxy --address 0.0.0.0 --port 1234 crystal-2f87e:us-east4:crystal-sql > /tmp/cloud-sql-proxy.log 2>&1 &

# Store the process ID
PROXY_PID=$!
echo "Cloud SQL Proxy started with PID: $PROXY_PID"
echo "The proxy is running on localhost:1234"
echo "To view logs: tail -f /tmp/cloud-sql-proxy.log"
echo "To stop the proxy: kill -9 $PROXY_PID"

# Check if proxy started successfully
sleep 3
if ps -p $PROXY_PID > /dev/null; then
  echo "✅ Cloud SQL Proxy is running successfully"
else
  echo "❌ Cloud SQL Proxy failed to start. Check logs at /tmp/cloud-sql-proxy.log"
  cat /tmp/cloud-sql-proxy.log
  exit 1
fi