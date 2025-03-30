import requests
import json
import time
import sys
import os
import datetime

# URL for the function emulator
# Format: http://localhost:5001/{PROJECT_ID}/{REGION}/{FUNCTION_NAME}
FUNCTION_URL = "http://localhost:5001/crystal-2f87e/us-central1/stream_analyze"

# Test data to send
test_data = {
    "dataset_ids": ["f5899dc6-c712-43ac-a368-f7f4feda20aa"],  # Replace with actual dataset ID
    "query": "Cause of corn emissions?"
}

def process_stream_response(response, query_data):
    """Process a streaming response from the stream_analyze endpoint."""
    try:
        # Tracking variables
        message_count = 0
        status_messages = []
        extracted_data = None
        formatted_data = None
        findings = None
        web_search_results = None
        complete_data = None
        
        # Store the query data for use in saving files
        test_data = query_data
        
        # Process the stream line by line
        for line in response.iter_lines():
            if line:
                # SSE format typically has "data:" prefix
                line = line.decode('utf-8')
                
                # Skip lines that don't contain data
                if not line.startswith('data:'):
                    continue
                
                # Extract the JSON data part
                json_str = line[5:].strip()
                message_count += 1
                
                try:
                    # Parse the data as JSON
                    data = json.loads(json_str)
                    
                    # Process based on type
                    msg_type = data.get('type')
                    
                    if msg_type == 'status':
                        status_messages.append(data.get('message', ''))
                        print(f"Status: {data.get('message', '')}")
                    
                    elif msg_type == 'error':
                        print(f"Error: {data.get('message', '')}")
                        if 'details' in data:
                            print(f"Details: {data.get('details', '')}")
                    
                    elif msg_type == 'web_search_results':
                        web_search_results = data.get('data')
                        print(f"Received web search results with {len(web_search_results.get('results', []))} items")
                    
                    elif msg_type == 'extracted_data':
                        extracted_data = data.get('data')
                        print(f"Received extracted data")
                        # Save extracted data to a JSON file
                        try:
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_dir = "../test_runs"
                            os.makedirs(output_dir, exist_ok=True)
                            
                            # Create a filename based on the query
                            query_slug = '_'.join(test_data.get('query', 'query').lower().split()[:4])
                            filename = f"{output_dir}/extracted_data_{query_slug}_{timestamp}.json"
                            
                            # Save the data to the file
                            with open(filename, 'w', encoding='utf-8') as f:
                                json.dump(extracted_data, f, indent=2, ensure_ascii=False)
                            print(f"Saved extracted data to {filename}")
                        except Exception as e:
                            print(f"Error saving extracted data: {e}")
                    
                    elif msg_type == 'formatted_data':
                        formatted_data = data.get('data')
                        print(f"Received formatted data")
                        # Save formatted data to a JSON file
                        try:
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_dir = "../test_runs"
                            os.makedirs(output_dir, exist_ok=True)
                            
                            # Create a filename based on the query
                            query_slug = '_'.join(test_data.get('query', 'query').lower().split()[:4])
                            filename = f"{output_dir}/formatted_data_{query_slug}_{timestamp}.json"
                            
                            # Save the data to the file
                            with open(filename, 'w', encoding='utf-8') as f:
                                json.dump(formatted_data, f, indent=2, ensure_ascii=False)
                            print(f"Saved formatted data to {filename}")
                        except Exception as e:
                            print(f"Error saving formatted data: {e}")
                    
                    elif msg_type == 'findings':
                        findings = data.get('data')
                        print(f"Received findings summary")
                        # Save findings to a JSON file
                        try:
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            output_dir = "../test_runs"
                            os.makedirs(output_dir, exist_ok=True)
                            
                            # Create a filename based on the query
                            query_slug = '_'.join(test_data.get('query', 'query').lower().split()[:4])
                            filename = f"{output_dir}/findings_{query_slug}_{timestamp}.json"
                            
                            # Save the data to the file
                            with open(filename, 'w', encoding='utf-8') as f:
                                json.dump(findings, f, indent=2, ensure_ascii=False)
                            print(f"Saved findings to {filename}")
                        except Exception as e:
                            print(f"Error saving findings: {e}")
                    
                    elif msg_type == 'complete':
                        complete_data = data.get('data')
                        print(f"Analysis complete in {data.get('message', '')}")
                        
                except json.JSONDecodeError:
                    print(f"Error parsing message: {json_str}")
        
        # Print summary
        print(f"\nReceived {message_count} messages in total")
        
        # Return a summary of the response
        return {
            "message_count": message_count,
            "status_messages": status_messages,
            "has_web_search_results": web_search_results is not None,
            "has_extracted_data": extracted_data is not None,
            "has_formatted_data": formatted_data is not None,
            "has_findings": findings is not None,
            "complete_data": complete_data
        }
        
    except Exception as e:
        print(f"Error processing stream: {e}")
        return None

def test_stream_analyze(data):
    """Test the stream_analyze function with the given data."""
    print(f"Sending request to {FUNCTION_URL} with data: {json.dumps(data, indent=2)}")
    
    start_time = time.time()
    try:
        # Use stream=True to get a streaming response
        response = requests.post(
            FUNCTION_URL,
            json=data,
            headers={"Content-Type": "application/json"},
            stream=True
        )
        
        # Check response status
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            # Process the streaming response
            result = process_stream_response(response, data)
            request_time = time.time() - start_time
            print(f"Total request time: {request_time:.2f} seconds")
            return result
        else:
            # Handle error response
            try:
                error_data = response.json()
                print(f"Error response: {json.dumps(error_data, indent=2)}")
            except json.JSONDecodeError:
                print(f"Error response (not JSON): {response.text}")
            request_time = time.time() - start_time
            print(f"Request time: {request_time:.2f} seconds")
            return None
            
    except Exception as e:
        request_time = time.time() - start_time
        print(f"Exception during request: {e}")
        print(f"Request time: {request_time:.2f} seconds")
        return None

if __name__ == "__main__":
    # Allow test data to be overridden from command line
    if len(sys.argv) > 1:
        query = sys.argv[1]
        test_data["query"] = query
        
    if len(sys.argv) > 2:
        dataset_ids = sys.argv[2].split(',')
        test_data["dataset_ids"] = dataset_ids
    
    print("\n=== Testing stream_analyze ===")
    test_stream_analyze(test_data)
    
    print("\n=== Testing Complete ===")