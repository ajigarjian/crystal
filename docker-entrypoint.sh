#!/bin/bash
set -e

echo "Firebase authentication status:"
firebase -V
firebase login:list

# Setup Firebase project
echo "Setting up Firebase project..."
firebase use crystal-2f87e --non-interactive || firebase use --add crystal-2f87e --non-interactive

# Enable the webframeworks experiment if needed
firebase experiments:enable webframeworks --non-interactive || true

# Start emulators with debug mode
echo "Starting Firebase emulators..."
exec firebase emulators:start --only functions,firestore --debug --project=crystal-2f87e