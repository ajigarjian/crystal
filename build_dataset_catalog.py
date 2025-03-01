#!/usr/bin/env python3
import requests
import json
import os
import time
import argparse
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

def init_api_key(api_key: Optional[str] = None) -> str:
    """Initialize the Data.gov API key."""
    data_gov_key = api_key or os.environ.get("DATA_GOV_API_KEY")
    
    if not data_gov_key:
        raise ValueError("Data.gov API key is required. Set DATA_GOV_API_KEY environment variable or pass it directly.")
    
    return data_gov_key

def fetch_with_retry(url: str, params: Dict, headers: Dict, max_retries: int = 3) -> Dict:
    """Fetch data with retry logic."""
    retries = 0
    backoff_factor = 1.5
    
    while retries <= max_retries:
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            retries += 1
            if retries > max_retries:
                raise
            
            # Exponential backoff with jitter
            wait_time = (backoff_factor ** retries) * (0.5 + random.random())
            print(f"Request failed: {e}. Retrying in {wait_time:.1f} seconds...")
            time.sleep(wait_time)
    
    # This should never happen due to the raise in the except block
    raise RuntimeError("Failed to fetch data after retries")

def download_dataset_catalog(
    api_key: str, 
    output_file: str = "data_gov_catalog.json", 
    batch_size: int = 500,  # Reduced from 1000
    include_resources: bool = False,
    include_tags: bool = True,
    limit: Optional[int] = None,
    resume_from: int = 0,
    save_interval: int = 5000
) -> Dict:
    """
    Download metadata for Data.gov datasets and save as a JSON catalog.
    
    Args:
        api_key: Data.gov API key
        output_file: File to save the catalog to
        batch_size: Number of datasets to retrieve in each request
        include_resources: Whether to include resource (file) information
        include_tags: Whether to include dataset tags
        limit: Optional limit on total number of datasets to fetch (for testing)
        resume_from: Index to resume downloading from (default: 0)
        save_interval: Save progress after processing this many datasets
        
    Returns:
        Dictionary with dataset information and stats
    """
    base_url = "https://catalog.data.gov/api/3"
    headers = {"Authorization": api_key}
    
    # Load existing data if resuming and file exists
    all_datasets = []
    if resume_from > 0 and os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                all_datasets = existing_data.get("datasets", [])
                print(f"Loaded {len(all_datasets)} existing datasets from {output_file}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load existing data from {output_file}: {e}")
            resume_from = 0
    
    # Get total count first
    params = {
        "q": "",  # Empty query to match all datasets
        "rows": 1  # Just need to get the total count
    }
    
    try:
        print("Retrieving dataset count...")
        data = fetch_with_retry(f"{base_url}/action/package_search", params, headers)
        
        total_datasets = data["result"]["count"]
        
        # If limit is set, cap the total
        if limit and limit < total_datasets:
            total_datasets = limit
            
        print(f"Found {total_datasets} total datasets" + 
              (f" (limited to {limit})" if limit else ""))
        
        if resume_from > 0:
            print(f"Resuming from dataset {resume_from}")
        
        start = resume_from
        last_save = start
        
        while start < total_datasets:
            end_point = min(start + batch_size, total_datasets)
            print(f"Downloading metadata for datasets {start+1} to {end_point} of {total_datasets}...")
            
            params = {
                "q": "",
                "rows": min(batch_size, total_datasets - start),
                "start": start
            }
            
            batch_data = fetch_with_retry(f"{base_url}/action/package_search", params, headers)
            
            # Extract simplified dataset info
            for dataset in batch_data["result"]["results"]:
                simplified = {
                    "id": dataset.get("id"),
                    "title": dataset.get("title"),
                    "description": dataset.get("notes", "")
                }
                
                # Add organization if available
                if dataset.get("organization"):
                    simplified["organization"] = {
                        "name": dataset.get("organization", {}).get("name"),
                        "title": dataset.get("organization", {}).get("title")
                    }
                
                # Add tags if requested
                if include_tags and dataset.get("tags"):
                    simplified["tags"] = [tag.get("name") for tag in dataset.get("tags", [])]
                
                # Add resource info if requested
                if include_resources and dataset.get("resources"):
                    simplified["resources"] = [
                        {
                            "id": r.get("id"),
                            "name": r.get("name"),
                            "format": r.get("format", "").lower(),
                            "size": r.get("size")
                        }
                        for r in dataset.get("resources", [])
                    ]
                
                all_datasets.append(simplified)
            
            # Move to next batch
            start += batch_size
            
            # Save progress periodically
            if start - last_save >= save_interval:
                save_progress(output_file, all_datasets)
                last_save = start
                print(f"Progress saved: {len(all_datasets)} datasets processed so far")
            
            # Add a small delay to avoid rate limits
            time.sleep(1.0)  # Increased from 0.5
        
        # Final save
        save_progress(output_file, all_datasets)
        print(f"Catalog with {len(all_datasets)} datasets saved to {output_file}")
        print(f"File size: {os.path.getsize(output_file) / (1024*1024):.2f} MB")
        
        return {
            "last_updated": datetime.now().isoformat(),
            "total_count": len(all_datasets),
            "datasets": all_datasets
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading dataset catalog: {e}")
        # Save what we have so far
        if all_datasets:
            save_progress(output_file, all_datasets)
            print(f"Partial catalog with {len(all_datasets)} datasets saved to {output_file}")
            print(f"To resume, run: python {os.path.basename(__file__)} --resume-from {start}")
        return {"error": str(e), "last_processed_index": start}

def save_progress(output_file: str, datasets: List[Dict]) -> None:
    """Save current progress to file."""
    catalog = {
        "last_updated": datetime.now().isoformat(),
        "total_count": len(datasets),
        "datasets": datasets
    }
    
    # Save to file with a temporary name first to avoid corruption
    temp_file = output_file + ".tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    # Rename to final filename
    if os.path.exists(output_file):
        os.replace(temp_file, output_file)
    else:
        os.rename(temp_file, output_file)

def main():
    parser = argparse.ArgumentParser(description="Download a complete catalog of Data.gov datasets")
    parser.add_argument("--output", default="data_gov_catalog.json", help="Output JSON file path")
    parser.add_argument("--batch-size", type=int, default=500, help="Number of datasets per request")
    parser.add_argument("--limit", type=int, help="Limit the total number of datasets (for testing)")
    parser.add_argument("--include-resources", action="store_true", help="Include resource/file information")
    parser.add_argument("--include-tags", action="store_true", help="Include dataset tags")
    parser.add_argument("--api-key", help="Data.gov API key (will check DATA_GOV_API_KEY env var if not provided)")
    parser.add_argument("--resume-from", type=int, default=0, help="Resume downloading from a specific index")
    parser.add_argument("--save-interval", type=int, default=5000, help="Save progress after this many datasets")
    
    args = parser.parse_args()
    
    try:
        api_key = init_api_key(args.api_key)
        download_dataset_catalog(
            api_key=api_key,
            output_file=args.output,
            batch_size=args.batch_size,
            include_resources=args.include_resources,
            include_tags=args.include_tags,
            limit=args.limit,
            resume_from=args.resume_from,
            save_interval=args.save_interval
        )
    except ValueError as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user. You can resume later with --resume-from")

if __name__ == "__main__":
    main() 