import requests
import json
import time

# URL for the function emulator
# Format: http://localhost:5001/{PROJECT_ID}/{REGION}/{FUNCTION_NAME}
FUNCTION_URL = "http://localhost:5001/crystal-2f87e/us-central1/test_db_connection"

# Call the function
print(f"Sending request to {FUNCTION_URL}")
response = requests.post(
    FUNCTION_URL,
    json={},
    headers={"Content-Type": "application/json"}
)

# Check response status
print(f"Status code: {response.status_code}")
if response.status_code != 200:
    print(f"Error: {response.text}")
    exit(1)

# Parse and print the response
try:
    result = response.json()
    print("\nResponse:")
    print("-" * 50)
    print(json.dumps(result, indent=2))
    
    # Check if connection was successful
    if result.get("status") == "success":
        print("\n✅ Database connection successful!")
    else:
        print("\n❌ Database connection failed!")
        print(f"Error: {result.get('message')}")
        
except json.JSONDecodeError:
    print(f"Invalid JSON response: {response.text}")

# Also test the debug_env_vars function to verify environment variables
ENV_VARS_URL = "http://localhost:5001/crystal-2f87e/us-central1/debug_env_vars"

print(f"\nChecking environment variables at {ENV_VARS_URL}")
env_response = requests.post(
    ENV_VARS_URL,
    json={},
    headers={"Content-Type": "application/json"}
)

# Check response status
print(f"Status code: {env_response.status_code}")
if env_response.status_code != 200:
    print(f"Error: {env_response.text}")
    exit(1)

# Parse and print the response
try:
    env_result = env_response.json()
    print("\nEnvironment Variables:")
    print("-" * 50)
    print(json.dumps(env_result, indent=2))
    
    # Check if all required environment variables are set
    required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PORT"]
    missing_vars = [var for var in required_vars if not env_result.get(var)]
    
    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {', '.join(missing_vars)}")
    else:
        print("\n✅ All required environment variables are set!")
        
    if not env_result.get("DB_PASSWORD"):
        print("⚠️ DB_PASSWORD is not set!")
        
except json.JSONDecodeError:
    print(f"Invalid JSON response: {env_response.text}")

# Test a simple query execution
QUERY_TEST_URL = "http://localhost:5001/crystal-2f87e/us-central1/test_db_query"

print(f"\nTesting database query at {QUERY_TEST_URL}")
query_response = requests.post(
    QUERY_TEST_URL,
    json={"query": "SELECT current_timestamp as server_time"},
    headers={"Content-Type": "application/json"}
)

# Check response status
print(f"Status code: {query_response.status_code}")
if query_response.status_code != 200:
    print(f"Error: {query_response.text}")
    exit(1)

# Parse and print the response
try:
    query_result = query_response.json()
    print("\nQuery Result:")
    print("-" * 50)
    print(json.dumps(query_result, indent=2))
    
    if query_result.get("status") == "success":
        print("\n✅ Database query executed successfully!")
    else:
        print("\n❌ Database query failed!")
        print(f"Error: {query_result.get('message')}")
        
except json.JSONDecodeError:
    print(f"Invalid JSON response: {query_response.text}")