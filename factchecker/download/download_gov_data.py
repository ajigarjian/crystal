import requests
import os
from typing import Optional

def download_dataset(api_key: str, dataset_id: str, output_dir: str = "downloads") -> Optional[str]:
    """
    Download a dataset by its ID and save to CSV if possible.
    
    Args:
        api_key: Data.gov API key
        dataset_id: The dataset identifier
        output_dir: Directory to save downloaded files
        
    Returns:
        Path to downloaded file or None if download failed
    """
    base_url = "https://catalog.data.gov/api/3"
    try:
        # Get dataset metadata
        response = requests.get(
            f"{base_url}/action/package_show", 
            params={"id": dataset_id},
            headers={"Authorization": api_key}
        )
        response.raise_for_status()
        dataset = response.json()["result"]
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get dataset title and clean it for use as filename
        dataset_title = dataset.get("title", "dataset")
        # Replace spaces and special characters with underscores
        clean_title = "".join(c if c.isalnum() else "_" for c in dataset_title)
        # Remove multiple consecutive underscores and limit length
        clean_title = "_".join(filter(None, clean_title.split("_")))[:100]
        
        # Look for CSV resources
        for resource in dataset.get("resources", []):
            if resource.get("format", "").lower() == "csv":
                url = resource["url"]
                filename = f"{clean_title}.csv"
                output_path = os.path.join(output_dir, filename)
                
                # Download the CSV file
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return output_path
        
        print(f"No CSV resource found for dataset {dataset_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading dataset: {e}")
        return None