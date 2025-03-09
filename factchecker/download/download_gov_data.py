import requests
import os
from typing import Optional

def download_resource(api_key: str, dataset_id: str, output_dir: str = "downloads") -> Optional[str]:
    """
    Download one of a dataset's resource by its ID and save to CSV, XLSX, or PDF if possible.
    
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
        
        # First try to find CSV or Excel resources
        for resource in dataset.get("resources", []):
            resource_format = resource.get("format", "").lower()
            if resource_format in ["csv", "xlsx", "xls", "excel"]:
                url = resource["url"]
                # Determine file extension based on format or mimetype
                if resource_format == "excel":
                    # Check mimetype for more specific format
                    mimetype = resource.get("mimetype", "")
                    if "openxmlformats" in mimetype:
                        extension = "xlsx"
                    else:
                        extension = "xls"
                else:
                    extension = resource_format
                    
                filename = f"{clean_title}.{extension}"
                output_path = os.path.join(output_dir, filename)
                
                # Download the file
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return output_path
        
        # If no CSV or Excel found, try to find PDF
        for resource in dataset.get("resources", []):
            resource_format = resource.get("format", "").lower()
            if resource_format == "pdf":
                url = resource["url"]
                filename = f"{clean_title}.pdf"
                output_path = os.path.join(output_dir, filename)
                
                # Download the PDF file
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"Downloaded PDF file: {filename} (CSV/Excel not available)")
                return output_path
        
        print(f"No CSV, Excel, or PDF resource found for dataset {dataset_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading dataset: {e}")
        return None

def download_all_resources(api_key: str, dataset_id: str, output_dir: str = "downloads") -> list:
    """
    Download all CSV, XLSX, and XLS resources from a dataset.
    
    Args:
        api_key: Data.gov API key
        dataset_id: The dataset identifier
        output_dir: Directory to save downloaded files
        
    Returns:
        List of paths to downloaded files or empty list if download failed
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
        
        # List to store paths of downloaded files
        downloaded_files = []
        
        # First try to find CSV or Excel resources
        for i, resource in enumerate(dataset.get("resources", [])):
            resource_format = resource.get("format", "").lower()
            if resource_format in ["csv", "xlsx", "xls", "excel"]:
                resource_url = resource.get("url")
                if not resource_url:
                    continue
                
                # Get resource name or use index
                resource_name = resource.get("name", f"resource_{i}")
                clean_resource_name = "".join(c if c.isalnum() else "_" for c in resource_name)
                clean_resource_name = "_".join(filter(None, clean_resource_name.split("_")))[:50]
                
                # Create filename with dataset title and resource name
                if resource_format == "csv":
                    output_filename = f"{clean_title}_{clean_resource_name}.csv"
                elif resource_format in ["xlsx", "xls", "excel"]:
                    output_filename = f"{clean_title}_{clean_resource_name}.xlsx"
                else:
                    output_filename = f"{clean_title}_{clean_resource_name}"
                
                output_path = os.path.join(output_dir, output_filename)
                
                # Download the file
                try:
                    print(f"Downloading {resource_url} to {output_path}")
                    response = requests.get(resource_url, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    downloaded_files.append(output_path)
                except Exception as e:
                    print(f"Error downloading resource: {e}")
                    continue
        
        # If no CSV or Excel found, try to find PDF
        if not downloaded_files:
            for i, resource in enumerate(dataset.get("resources", [])):
                resource_format = resource.get("format", "").lower()
                if resource_format == "pdf":
                    resource_url = resource.get("url")
                    if not resource_url:
                        continue
                    
                    # Get resource name or use index
                    resource_name = resource.get("name", f"resource_{i}")
                    clean_resource_name = "".join(c if c.isalnum() else "_" for c in resource_name)
                    clean_resource_name = "_".join(filter(None, clean_resource_name.split("_")))[:50]
                    
                    output_filename = f"{clean_title}_{clean_resource_name}.pdf"
                    output_path = os.path.join(output_dir, output_filename)
                    
                    # Download the file
                    try:
                        print(f"Downloading {resource_url} to {output_path}")
                        response = requests.get(resource_url, stream=True, timeout=30)
                        response.raise_for_status()
                        
                        with open(output_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        downloaded_files.append(output_path)
                        break  # Just get the first PDF
                    except Exception as e:
                        print(f"Error downloading resource: {e}")
                        continue
        
        return downloaded_files
        
    except requests.exceptions.RequestException as e:
        print(f"Error getting dataset metadata: {e}")
        return []