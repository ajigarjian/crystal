import requests
import os
from typing import Optional
import urllib3
import time

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def download_resource(api_key: str, dataset_id: str, output_dir: str = "downloads") -> Optional[str]:
    """
    Download one of a dataset's resource by its ID and save to CSV, XLSX, XML, JSON, or PDF if possible.
    
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
        
        # First try to find CSV, Excel, XML, or JSON resources
        for resource in dataset.get("resources", []):
            resource_format = resource.get("format", "").lower()
            if resource_format in ["csv", "xlsx", "xls", "excel", "xml", "json"]:  # Added JSON here
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
        
        # If no CSV, Excel, XML, or JSON found, try to find PDF
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
                
                print(f"Downloaded PDF file: {filename} (CSV/Excel/XML/JSON not available)")
                return output_path
        
        print(f"No CSV, Excel, XML, JSON, or PDF resource found for dataset {dataset_id}")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading dataset: {e}")
        return None

def download_all_resources(api_key: str, dataset_id: str, output_dir: str = "downloads") -> list:
    """
    Download all CSV, XLSX, XLS, XML, and JSON resources from a dataset.
    Handles insecure connections, HTTP/HTTPS issues, and 403 Forbidden errors.
    
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
        
        # First try to find CSV, Excel, XML, or JSON resources
        for i, resource in enumerate(dataset.get("resources", [])):
            resource_format = resource.get("format", "").lower()
            if resource_format in ["csv", "xlsx", "xls", "excel", "xml", "json"]:  # Added JSON here
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
                elif resource_format == "xml":
                    output_filename = f"{clean_title}_{clean_resource_name}.xml"
                elif resource_format == "json":  # Added JSON handling
                    output_filename = f"{clean_title}_{clean_resource_name}.json"
                else:
                    output_filename = f"{clean_title}_{clean_resource_name}"
                
                output_path = os.path.join(output_dir, output_filename)
                
                # Download the file with multiple attempts and fallback options
                download_successful = False
                
                # Common headers to mimic a browser
                browser_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Referer": "https://catalog.data.gov/",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
                
                # Try different download approaches
                download_attempts = [
                    # 1. Standard secure download
                    lambda url: requests.get(url, stream=True, timeout=30),
                    
                    # 2. With browser headers
                    lambda url: requests.get(url, stream=True, timeout=30, headers=browser_headers),
                    
                    # 3. Insecure download (verify=False)
                    lambda url: requests.get(url, stream=True, timeout=30, verify=False),
                    
                    # 4. Insecure with browser headers
                    lambda url: requests.get(url, stream=True, timeout=30, verify=False, headers=browser_headers),
                    
                    # 5. Try with http:// if https:// fails
                    lambda url: requests.get(url.replace('https://', 'http://'), stream=True, timeout=30, headers=browser_headers) 
                    if url.startswith('https://') else None,
                    
                    # 6. Try with https:// if http:// fails
                    lambda url: requests.get(url.replace('http://', 'https://'), stream=True, timeout=30, headers=browser_headers) 
                    if url.startswith('http://') else None,
                    
                    # 7. Special case for nycgovparks.org
                    lambda url: requests.get(
                        url, 
                        stream=True, 
                        timeout=30, 
                        headers={
                            **browser_headers,
                            "Referer": "https://www.nycgovparks.org/",
                            "Origin": "https://www.nycgovparks.org"
                        }
                    ) if "nycgovparks.org" in url else None,
                ]
                
                for attempt_num, download_attempt in enumerate(download_attempts, 1):
                    try:
                        # Skip None attempts (when URL doesn't match condition)
                        if download_attempt(resource_url) is None:
                            continue
                            
                        print(f"Downloading {resource_url} to {output_path} (attempt {attempt_num})")
                        response = download_attempt(resource_url)
                        response.raise_for_status()
                        
                        with open(output_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        downloaded_files.append(output_path)
                        download_successful = True
                        print(f"Download successful on attempt {attempt_num}")
                        break
                        
                    except Exception as e:
                        print(f"Download attempt {attempt_num} failed: {e}")
                        # Add a small delay between attempts to avoid rate limiting
                        time.sleep(1)
                        continue
                
                # If all attempts failed, try to directly download the file using curl
                if not download_successful and resource_url:
                    try:
                        print(f"Trying curl as a last resort for {resource_url}")
                        import subprocess
                        
                        # Use curl with user agent and other headers
                        curl_command = [
                            "curl", 
                            "-L",  # Follow redirects
                            "-o", output_path,  # Output file
                            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",  # User agent
                            "-e", "https://catalog.data.gov/",  # Referer
                            "--retry", "3",  # Retry 3 times
                            resource_url
                        ]
                        
                        result = subprocess.run(curl_command, capture_output=True, text=True)
                        
                        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                            print(f"Curl download successful for {resource_url}")
                            downloaded_files.append(output_path)
                            download_successful = True
                        else:
                            print(f"Curl download failed: {result.stderr}")
                    except Exception as e:
                        print(f"Curl download attempt failed: {e}")
                
                if not download_successful:
                    print(f"All download attempts failed for {resource_url}")
        
        # If no CSV, Excel, XML, or JSON found, try to find PDF with the same approach
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
                    
                    # Download with multiple attempts
                    download_successful = False
                    
                    # Try different download approaches
                    download_attempts = [
                        # 1. Standard secure download
                        lambda url: requests.get(url, stream=True, timeout=30),
                        
                        # 2. Insecure download (verify=False)
                        lambda url: requests.get(url, stream=True, timeout=30, verify=False),
                        
                        # 3. Try with http:// if https:// fails
                        lambda url: requests.get(url.replace('https://', 'http://'), stream=True, timeout=30) 
                        if url.startswith('https://') else None,
                        
                        # 4. Try with https:// if http:// fails
                        lambda url: requests.get(url.replace('http://', 'https://'), stream=True, timeout=30) 
                        if url.startswith('http://') else None,
                        
                        # 5. Insecure http://
                        lambda url: requests.get(url.replace('https://', 'http://'), stream=True, timeout=30, verify=False) 
                        if url.startswith('https://') else None,
                    ]
                    
                    for attempt_num, download_attempt in enumerate(download_attempts, 1):
                        try:
                            # Skip None attempts
                            if download_attempt(resource_url) is None:
                                continue
                                
                            print(f"Downloading {resource_url} to {output_path} (attempt {attempt_num})")
                            response = download_attempt(resource_url)
                            response.raise_for_status()
                            
                            with open(output_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            
                            downloaded_files.append(output_path)
                            download_successful = True
                            print(f"Download successful on attempt {attempt_num}")
                            break
                            
                        except Exception as e:
                            print(f"Download attempt {attempt_num} failed: {e}")
                            continue
                    
                    if download_successful:
                        break  # Just get the first PDF
        
        return downloaded_files
        
    except requests.exceptions.RequestException as e:
        print(f"Error getting dataset metadata: {e}")
        return []