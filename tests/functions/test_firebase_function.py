import requests
import json

# URL for the function emulator
# Format: http://localhost:5001/{PROJECT_ID}/{REGION}/handle_spotify_auth
FUNCTION_URL = "http://localhost:5001/crystal-2f87e/us-central1/handle_crystal_request"

# Test data to send
test_data = {
    "data": {
        "test_param": "test_value"
    }
}

# Call the function
response = requests.post(
    FUNCTION_URL,
    json=test_data,
    headers={"Content-Type": "application/json"}
)

# Print the response
print(f"Status code: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")