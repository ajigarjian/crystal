#!/bin/bash

# Set environment variables to increase memory limits
export NODE_OPTIONS="--max-old-space-size=8192"
export FIREBASE_DEBUG=true

# Set Python memory environment variables
export PYTHONMALLOC=malloc
export MPLBACKEND=Agg  # Non-interactive matplotlib backend to reduce memory usage

# For Mac, increase the per-process memory limit
ulimit -n 10240  # Increase file descriptor limit
ulimit -v 8589934592  # Set virtual memory limit to 8GB (in bytes)

# Run Firebase emulator with lower concurrency
firebase emulators:start --only functions,firestore --project=crystal-2f87e