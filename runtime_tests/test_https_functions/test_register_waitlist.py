import requests
import json
import time

# URL for the function emulator
# Format: http://localhost:5001/{PROJECT_ID}/{REGION}/{FUNCTION_NAME}
FUNCTION_URL = "http://localhost:5001/crystal-2f87e/us-central1/register_waitlist"

# Test data to send
test_data = {
    "email": "test@example.com",
    "first_name": "Test User"
}

# Function to test registration with given data
def test_registration(data):
    print(f"Sending request to {FUNCTION_URL} with data: {data}")
    
    start_time = time.time()
    response = requests.post(
        FUNCTION_URL,
        json=data,
        headers={"Content-Type": "application/json"}
    )
    request_time = time.time() - start_time
    
    # Check response status
    print(f"Status code: {response.status_code}")
    print(f"Response time: {request_time:.2f} seconds")
    
    # Parse and print response
    try:
        response_data = response.json()
        print(f"Response: {json.dumps(response_data, indent=2)}")
        return response_data
    except json.JSONDecodeError:
        print(f"Error parsing response: {response.text}")
        return None

# Test 1: Valid registration
print("\n=== Test 1: Valid Registration ===")
test_registration(test_data)

# Test 2: Missing email (should fail)
print("\n=== Test 2: Missing Email ===")
test_registration({
    "first_name": "Test User"
})

# Test 3: Duplicate registration (should fail)
print("\n=== Test 3: Duplicate Registration ===")
test_registration(test_data)  # Same email as Test 1

# Test 4: Different user
print("\n=== Test 4: Different User ===")
test_registration({
    "email": "another@example.com",
    "first_name": "Another User"
})

# Test 5: Special characters in name
print("\n=== Test 5: Special Characters ===")
test_registration({
    "email": "special@example.com",
    "first_name": "O'Connor-Smith"
})

print("\n=== Testing Complete ===")