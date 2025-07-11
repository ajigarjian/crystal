# GCP Functions - Deployment Guide

This guide covers testing and deploying Python 3.11 Cloud Functions directly to Google Cloud Platform using our automated deployment scripts.

## Prerequisites

1. **Python 3.11** installed on your system
2. **Google Cloud SDK** (`gcloud`) installed and authenticated
3. **pipreqs** installed: `pip install pipreqs`
4. **Java** (for local emulation)

## Initial Setup

1. **Create a virtual environment:**
   ```bash
   cd gcp_functions
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Authenticate with Google Cloud:**
   ```bash
   gcloud auth login
   gcloud config set project crystal-2f87e
   ```

## Creating a New GCP Function

### 1. Create Function Structure
```bash
mkdir your_function_name
cd your_function_name
touch your_function_name.py
```

### 2. Write Your Function Code
Create your function in the Python file. **Important**: Include proper CORS headers to prevent browser errors:

```python
import functions_framework
from flask import jsonify

@functions_framework.http
def your_function_name(request):
    # Set CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization'
    }
    
    # Handle preflight requests
    if request.method == 'OPTIONS':
        return ('', 204, headers)
    
    try:
        # Your function logic here
        result = {"message": "Hello from your function!"}
        return (jsonify(result), 200, headers)
    except Exception as e:
        return (jsonify({"error": str(e)}), 500, headers)
```

### 3. Test Locally
Test your function as a standalone Python script before deploying:
```bash
python your_function_name.py
```

## Local Testing & Emulation

### 1. Add Emulator Route
Add a new Flask route in `gcp_main.py` for local testing:
```python
@app.route('/your-function-name', methods=['GET', 'POST', 'OPTIONS'])
def your_function_name_route():
    from your_function_name.your_function_name import your_function_name
    return your_function_name(request)
```

### 2. Start Local Emulator
```bash
# Start the GCP Functions emulator
./start-gcp-emulator.sh

# If you need database access, also run:
../start-sql-proxy.sh  # From repo root
```

### 3. Test Your Function
Your function will be available at:
```
http://localhost:8080/your-function-name
```

## Deployment

### 1. Configure Deployment
Add your function to the `FUNCTIONS_TO_DEPLOY` list in `deploy-gcp-functions.py`:
```python
FUNCTIONS_TO_DEPLOY = [
    # ... existing functions ...
    ("your_function_name.your_function_name", "your_function_name", "your-function-name", "512MB"),
]
```

Format: `(handler_module, function_name_in_code, deployed_name, memory)`

### 2. Deploy Functions

**Deploy all functions:**
```bash
python deploy-gcp-functions.py
```

**Deploy a specific function:**
```bash
python deploy-gcp-functions.py your-function-name
```

**List available functions:**
```bash
python deploy-gcp-functions.py --list
```

### 3. Currently Available Functions
- `energy-agent`
- `get-power-infrastructure`
- `get-power-generators`
- `get-power-plants`

## Function Configuration

### Memory Options
- `128MB` - Basic functions
- `256MB` - Standard functions
- `512MB` - Functions with moderate processing
- `1GB` - Heavy processing functions

### Deployment Settings
- **Runtime**: Python 3.11
- **Trigger**: HTTP (unauthenticated)
- **Region**: us-central1
- **VPC Connector**: crystal-connector

## Troubleshooting

### Common Issues

1. **CORS Errors**: Ensure your function includes proper CORS headers
2. **Import Errors**: Check that all dependencies are correctly specified
3. **Memory Issues**: Increase memory allocation in `FUNCTIONS_TO_DEPLOY`
4. **Timeout**: Functions have a default timeout - adjust if needed

### Checking Deployment Status
```bash
gcloud functions list --project=crystal-2f87e
```

### View Function Logs
```bash
gcloud functions logs read FUNCTION_NAME --project=crystal-2f87e
```

## Best Practices

1. **Test locally first** using the emulator
2. **Use specific function deployment** during development
3. **Include proper error handling** and logging
4. **Set appropriate memory limits** based on function requirements
5. **Keep functions focused** on single responsibilities

## File Structure
```
gcp_functions/
├── deploy-gcp-functions.py    # Main deployment script
├── gcp_main.py               # Local emulator routes
├── your_function_name/       # Your function directory
│   └── your_function_name.py # Your function code
├── helpers/                  # Shared utilities
└── build_temp/              # Temporary build files (auto-generated)
```