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
    "dataset_ids": [
    "2746fc68-190d-407f-bb86-44c5f42bb6d1",
    "19bb999c-6208-4692-970a-131326d67be3",
    "5f961a68-66f9-4e8d-b3ed-b41cc8e1f9be",
    "7dea0c2b-b84e-48b2-95ad-0867fb14cd89",
    "41cc4071-57bd-452e-af0d-03174f7ade5c",
    "d5fa9b77-6b88-49e3-ba96-445254073d6f",
    "960213c2-effc-4da7-8ccd-375327f6d1e6",
    "e3f73ef6-ca46-4784-9161-c128109163b1",
    "28e0f154-e68b-406a-8871-f9ad62df11b2",
    "01f25998-f9c6-4508-a890-ef53ed596419",
    "044f8ebb-0c54-4f8d-866c-2eb7071817dc",
    "be5795c2-0737-4cad-915a-9a2783d78788",
    "6df5dd5a-f5e5-422a-a069-6d801f3a7208",
    "62915ff9-ca87-4f85-b9e6-6c1793fc4054",
    "bb97ac7a-5cee-4fe5-b0f8-598e46f5d735",
    "5a002f72-8ddb-4bd4-86e2-cdd991b9ad2d",
    "e61357f3-7d69-4067-8b1d-721beafc57ec",
    "9f691d06-ca23-43f7-acc6-90ec2db19dc9",
    "85e95821-1460-4de3-8665-0ade178bb16e",
    "fd699649-d276-43c8-829a-cb4a892cf776"
],
    "query": "Give me trends about underground storage tanks"
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
        web_search_summary = None
        analysis_results = []
        complete_data = None
        
        # Store the query data for use in saving files
        test_data = query_data
        
        print("\nStarting to process streaming response...")
        
        # Process the stream line by line
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
                
            print(f"\nReceived line: {line}")
            
            # SSE format typically has "data:" prefix
            if not line.startswith('data:'):
                print(f"Skipping non-data line: {line}")
                continue
            
            # Extract the JSON data part
            json_str = line[5:].strip()
            message_count += 1
            
            try:
                # Parse the data as JSON
                data = json.loads(json_str)
                print(f"Parsed message type: {data.get('type')}")
                
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
                
                elif msg_type == 'web_search_summary':
                    web_search_summary = data.get('data')
                    print(f"Web search summary: {web_search_summary.get('summary', 'No summary available')}")
                
                elif msg_type == 'analysis_result':
                    dataset_info = data.get('data', {}).get('dataset_info', {})
                    print(f"Dataset: {dataset_info.get('title')}")
                    print(f"Rows: {dataset_info.get('rows')}, Columns: {dataset_info.get('columns')}")
                    analysis_results.append(data.get('data'))
                
                elif msg_type == 'analysis':
                    analysis = data.get('data', 'No analysis available')
                    print(f"Analysis: {analysis}")
                
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
                
                elif msg_type == 'dataset_status':
                    dataset_id = data.get('dataset_id')
                    status = data.get('status')
                    progress = data.get('progress')
                    message = data.get('message', '')
                    print(f"Dataset Status Update: ID={dataset_id}, Status={status}, Progress={progress}, Message='{message}'")

                elif msg_type == 'complete':
                    complete_data = data.get('data')
                    print(f"Analysis complete in {data.get('message', '')}")
                
                else:
                    print(f"Unknown message type: {msg_type}")
                    print(f"Full message: {json.dumps(data, indent=2)}")
                    
            except json.JSONDecodeError as e:
                print(f"Error parsing message: {json_str}")
                print(f"Error details: {str(e)}")
            except Exception as e:
                print(f"Error processing message: {str(e)}")
                print(f"Message content: {json_str}")
        
        # Print summary
        print(f"\nReceived {message_count} messages in total")
        
        # Return a summary of the response
        return {
            "message_count": message_count,
            "status_messages": status_messages,
            "has_web_search_results": web_search_results is not None,
            "has_web_search_summary": web_search_summary is not None,
            "has_analysis_results": len(analysis_results) > 0,
            "has_formatted_data": formatted_data is not None,
            "has_findings": findings is not None,
            "complete_data": complete_data
        }
        
    except Exception as e:
        print(f"Error processing stream: {e}")
        print(f"Error details: {str(e)}")
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
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            stream=True
        )
        
        # Check response status
        print(f"Status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        
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
            
    except requests.exceptions.RequestException as e:
        request_time = time.time() - start_time
        print(f"Request exception: {e}")
        print(f"Request time: {request_time:.2f} seconds")
        return None
    except Exception as e:
        request_time = time.time() - start_time
        print(f"Unexpected exception: {e}")
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