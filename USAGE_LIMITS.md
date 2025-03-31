# Basic Usage Limits Implementation with Firestore

This feature implements IP-based usage limits for the Crystal API to ensure fair usage during the Alpha phase.

## Features

- Tracks API usage by IP address using Firestore
- Sets different limits for different API endpoints:
  - stream_search_datasets: 25 requests per IP
  - stream_analyze: 10 requests per IP
- Provides friendly error messages when limits are exceeded
- Allows users to request higher limits via feedback

## Implementation Details

### Firestore Data Structure

The implementation stores usage data in Firestore with the following structure:

**Collection**: `usage_limits`

**Document ID**: `{ip_address}_{function_name}`

**Fields**:
- `ip_address`: The client's IP address
- `function_name`: The function being called (stream_search_datasets or stream_analyze)
- `request_count`: Number of requests made
- `first_request_at`: Timestamp of first request
- `last_request_at`: Timestamp of most recent request

### Cloud Functions

Both `stream_search_datasets` and `stream_analyze` functions have been updated to:
1. Extract the client IP address
2. Check if the IP has exceeded its usage limit
3. Return a user-friendly error message if the limit is exceeded

### Frontend

The frontend has been updated to handle and display usage limit errors properly.

## Local Development

The usage limits are automatically bypassed in the following scenarios:
1. When running in the local emulator environment (`FUNCTIONS_EMULATOR` environment variable is set)
2. For localhost IP addresses (`127.0.0.1`, `::1`, and `localhost`)

This ensures a seamless development experience without hitting limits during testing.

## Deployment Instructions

No additional setup is required beyond deploying the updated code. Firestore is already configured in the production environment.

```bash
# Deploy the updated cloud functions
cd functions
gcloud functions deploy stream_search_datasets --entry-point stream_search_datasets
gcloud functions deploy stream_analyze --entry-point stream_analyze
```

## Future Improvements

- Add an admin interface to view and manage usage limits
- Implement time-based reset of limits (e.g., daily or weekly)
- Add whitelisting for specific IP addresses or users
- Integrate with an authentication system when available