import requests
import json
import time

# URL for the function emulator
# Format: http://localhost:5001/{PROJECT_ID}/{REGION}/{FUNCTION_NAME}
FUNCTION_URL = "http://localhost:5001/crystal-2f87e/us-central1/stream_search_datasets"

# Test data to send
test_data = {
    "query": "Orange grove emissions factors",
    "similarity_threshold": 0.3,
    "search_method": None,  # Use hybrid search (default)
    "max_results": 20,
    "relevance_threshold": 0.4
}

# Call the function
print(f"Sending request to {FUNCTION_URL} with query: '{test_data['query']}'")
response = requests.post(
    FUNCTION_URL,
    json=test_data,
    headers={"Content-Type": "application/json"},
    stream=True  # Enable streaming response
)

# Check response status
print(f"Status code: {response.status_code}")
if response.status_code != 200:
    print(f"Error: {response.text}")
    exit(1)

# Process the streaming response
print("\nProcessing streaming response:")
print("-" * 50)

# Track metrics
start_time = time.time()
chunk_count = 0
datasets_found = 0
last_timestamp = 0
datasets = {}  # Dictionary to store dataset information

# Process each chunk as it arrives
for chunk in response.iter_lines():
    if chunk:
        chunk_count += 1
        chunk_str = chunk.decode('utf-8')
        
        try:
            # Parse the JSON chunk
            chunk_data = json.loads(chunk_str)
            
            # Update timestamp if available
            if 'timestamp' in chunk_data:
                last_timestamp = chunk_data['timestamp']
            
            # Process different message types
            if chunk_data['type'] == 'status':
                print(f"[STATUS] {chunk_data['message']}")
            
            elif chunk_data['type'] == 'discovery':
                print(f"[DISCOVERY] {chunk_data['message']}")
            
            elif chunk_data['type'] == 'dataset':
                datasets_found += 1
                dataset = chunk_data['data']
                dataset_id = dataset['id']
                datasets[dataset_id] = {
                    'title': dataset['title'],
                    'score': dataset.get('similarity', 'N/A')
                }
                print(f"[DATASET] Found: {dataset['title']} (ID: {dataset_id}, Score: {dataset.get('similarity', 'N/A')})")
            
            elif chunk_data['type'] == 'dataset_update':
                dataset_id = chunk_data['data']['id']
                status = chunk_data['data'].get('status', 'updated')
                print(f"[UPDATE] Dataset {dataset_id}: {status}")
            
            elif chunk_data['type'] == 'phase_complete':
                phase = chunk_data['phase']
                print(f"[PHASE COMPLETE] {phase}: {chunk_data['message']}")
            
            elif chunk_data['type'] == 'complete':
                print(f"[COMPLETE] {chunk_data['message']}")
                print(f"Total execution time: {chunk_data['data']['execution_time']:.2f} seconds")
                print(f"Total datasets found: {chunk_data['data'].get('total_count', 0)}")
            
            elif chunk_data['type'] == 'error':
                print(f"[ERROR] {chunk_data['message']}")
                if 'details' in chunk_data:
                    print(f"Details: {chunk_data['details']}")
            
            else:
                print(f"[UNKNOWN] {chunk_str}")
        
        except json.JSONDecodeError:
            print(f"[INVALID JSON] {chunk_str}")

# Calculate total processing time
total_time = time.time() - start_time

# Define a list of dataset IDs
dataset_ids = []

# Print summary
print("-" * 50)
print(f"Test Summary:")
print(f"- Total chunks received: {chunk_count}")
print(f"- Datasets found: {datasets_found}")
print(f"- Processing time: {total_time:.2f} seconds")
print(f"- Function execution time: {last_timestamp:.2f} seconds")
print("\nDataset Details:")
print("-" * 50)
for dataset_id, info in datasets.items():
    dataset_ids.append(dataset_id)
    print(f"ID: {dataset_id}")
    print(f"Title: {info['title']}")
    print(f"Relevance Score: {info['score']}")
    print("-" * 50)
print(f"Dataset IDs: {dataset_ids}")