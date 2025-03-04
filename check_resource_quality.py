import requests
import random
import json
from collections import Counter
import os
import re

def check_resource_name_extensions(api_key, num_datasets=20):
    """
    Check if resource names contain usable file extensions when format is missing.
    """
    base_url = "https://catalog.data.gov/api/3"
    headers = {"Authorization": api_key}
    
    # Get random dataset IDs (simplified for brevity)
    dataset_ids = []
    # Code to get random dataset IDs...
    
    # Same code as before to get dataset IDs
    response = requests.get(
        f"{base_url}/action/package_search", 
        params={"q": "", "rows": 1},
        headers=headers
    )
    total_datasets = response.json()["result"]["count"]
    
    for _ in range(num_datasets):
        random_start = random.randint(0, total_datasets - 1)
        params = {"q": "", "rows": 1, "start": random_start}
        response = requests.get(
            f"{base_url}/action/package_search", 
            params=params,
            headers=headers
        )
        try:
            dataset_id = response.json()["result"]["results"][0]["id"]
            dataset_ids.append(dataset_id)
        except (KeyError, IndexError):
            continue
    
    # Stats to collect
    total_resources = 0
    resources_with_format = 0
    resources_without_format = 0
    resources_with_extension_in_name = 0
    extension_counter = Counter()
    
    # Check each dataset's resources
    print(f"Analyzing resource names for {len(dataset_ids)} datasets...")
    
    for i, dataset_id in enumerate(dataset_ids):
        print(f"Processing dataset {i+1}/{len(dataset_ids)}: {dataset_id}")
        
        try:
            response = requests.get(
                f"{base_url}/action/package_show", 
                params={"id": dataset_id},
                headers=headers
            )
            dataset = response.json()["result"]
            
            resources = dataset.get("resources", [])
            total_resources += len(resources)
            
            for resource in resources:
                name = resource.get("name", "")
                format_value = resource.get("format", "").lower()
                
                # Print the resource name
                print(f"  Processing resource: {name}")
                
                if format_value:
                    resources_with_format += 1
                else:
                    resources_without_format += 1
                    
                    # Check if name contains a file extension
                    extension_match = re.search(r'\.([a-zA-Z0-9]{2,5})$', name)
                    if extension_match:
                        ext = extension_match.group(1).lower()
                        resources_with_extension_in_name += 1
                        extension_counter[ext] += 1
                        print(f"  Resource without format but with extension: {name} (ext: {ext})")
        
        except Exception as e:
            print(f"Error processing dataset {dataset_id}: {e}")
    
    # Calculate percentages
    if resources_without_format > 0:
        extension_pct = (resources_with_extension_in_name / resources_without_format) * 100
    else:
        extension_pct = 0
    
    # Print results
    print("\n=== RESOURCE NAME EXTENSION ANALYSIS ===")
    print(f"Total resources analyzed: {total_resources}")
    print(f"Resources with format field: {resources_with_format}")
    print(f"Resources without format field: {resources_without_format}")
    print(f"Resources without format but with extension in name: {resources_with_extension_in_name} ({extension_pct:.1f}%)")
    
    print("\nTop extensions found in resource names (when format is missing):")
    for ext, count in extension_counter.most_common(10):
        print(f"  .{ext}: {count}")
    
    # Recommendation
    if extension_pct > 50:
        print("\nRECOMMENDATION: Resource names often contain useful file extensions when format is missing.")
        print("Consider extracting format from resource names as a fallback when the format field is empty.")
    else:
        print("\nRECOMMENDATION: Resource names don't reliably contain file extensions when format is missing.")

if __name__ == "__main__":
    api_key = os.environ.get("DATA_GOV_API_KEY")
    if not api_key:
        api_key = input("Enter your Data.gov API key: ")
    
    check_resource_name_extensions(api_key)