import requests
import os
from typing import Optional, List, Callable, Dict, Any, Tuple
import urllib3
import time
import subprocess

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Common browser headers to mimic a browser
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://catalog.data.gov/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

# Supported file formats
TABULAR_FORMATS = ["csv", "xlsx", "xls", "excel", "xml", "json"]
DOCUMENT_FORMATS = ["pdf"]
ALL_SUPPORTED_FORMATS = TABULAR_FORMATS + DOCUMENT_FORMATS

def get_dataset_metadata(api_key: str, dataset_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata for a dataset from the Data.gov API.
    
    Args:
        api_key: Data.gov API key
        dataset_id: The dataset identifier
        
    Returns:
        Dataset metadata dictionary or None if retrieval failed
    """
    base_url = "https://catalog.data.gov/api/3"
    try:
        response = requests.get(
            f"{base_url}/action/package_show", 
            params={"id": dataset_id},
            headers={"Authorization": api_key}
        )
        response.raise_for_status()
        return response.json()["result"]
    except requests.exceptions.RequestException as e:
        print(f"Error getting dataset metadata: {e}")
        return None

def clean_filename(text: str, max_length: int = 100) -> str:
    """
    Clean text for use as a filename.
    
    Args:
        text: Text to clean
        max_length: Maximum length for the cleaned text
        
    Returns:
        Cleaned text suitable for use as a filename
    """
    # Replace spaces and special characters with underscores
    clean_text = "".join(c if c.isalnum() else "_" for c in text)
    # Remove multiple consecutive underscores and limit length
    return "_".join(filter(None, clean_text.split("_")))[:max_length]

def create_download_attempts(url: str) -> List[Callable]:
    """
    Create a list of download attempt functions for a given URL.
    
    Args:
        url: URL to download from
        
    Returns:
        List of download attempt functions
    """
    return [
        # 1. Standard secure download
        lambda: requests.get(url, stream=True, timeout=15),
        
        # 2. With browser headers
        lambda: requests.get(url, stream=True, timeout=15, headers=BROWSER_HEADERS),
        
        # 3. Insecure download (verify=False)
        lambda: requests.get(url, stream=True, timeout=15, verify=False),
        
        # 4. Insecure with browser headers
        lambda: requests.get(url, stream=True, timeout=15, verify=False, headers=BROWSER_HEADERS),
        
        # 5. Try with http:// if https:// fails
        lambda: requests.get(url.replace('https://', 'http://'), stream=True, timeout=15, headers=BROWSER_HEADERS) 
        if url.startswith('https://') else None,
        
        # 6. Try with https:// if http:// fails
        lambda: requests.get(url.replace('http://', 'https://'), stream=True, timeout=15, headers=BROWSER_HEADERS) 
        if url.startswith('http://') else None,
        
        # 7. Special case for nycgovparks.org
        lambda: requests.get(
            url, 
            stream=True, 
            timeout=15, 
            headers={
                **BROWSER_HEADERS,
                "Referer": "https://www.nycgovparks.org/",
                "Origin": "https://www.nycgovparks.org"
            }
        ) if "nycgovparks.org" in url else None,
    ]

def download_file(url: str, output_path: str, max_download_time: int = 15) -> bool:
    """
    Download a file using multiple fallback methods.
    
    Args:
        url: URL to download from
        output_path: Path to save the downloaded file
        max_download_time: Maximum time in seconds for download
        
    Returns:
        True if download was successful, False otherwise
    """
    if not url:
        return False
        
    # Try different download approaches
    download_attempts = create_download_attempts(url)
    
    for attempt_num, download_attempt in enumerate(download_attempts, 1):
        try:
            # Skip None attempts (when URL doesn't match condition)
            attempt_result = download_attempt()
            if attempt_result is None:
                continue
                
            print(f"Downloading {url} to {output_path} (attempt {attempt_num})")
            response = attempt_result
            response.raise_for_status()
            
            with open(output_path, 'wb') as f:
                # Add timeout check for download
                start_time = time.time()
                for chunk in response.iter_content(chunk_size=8192):
                    # Check if download is taking too long
                    if time.time() - start_time > max_download_time:
                        print(f"Download taking too long, terminating after {max_download_time} seconds")
                        raise TimeoutError("Download timeout exceeded")
                    f.write(chunk)
            
            print(f"Download successful on attempt {attempt_num}")
            return True
            
        except TimeoutError as te:
            print(f"Download attempt {attempt_num} timed out: {te}")
            # Remove partially downloaded file
            if os.path.exists(output_path):
                os.remove(output_path)
            return False  # Don't try other methods if timeout occurred
            
        except Exception as e:
            print(f"Download attempt {attempt_num} failed: {e}")
            # Add a small delay between attempts to avoid rate limiting
            time.sleep(1)
            continue
    
    # If all attempts failed, try curl as a last resort
    try:
        print(f"Trying curl as a last resort for {url}")
        
        # Use curl with user agent and other headers
        curl_command = [
            "curl", 
            "-L",  # Follow redirects
            "-o", output_path,  # Output file
            "-A", BROWSER_HEADERS["User-Agent"],  # User agent
            "-e", BROWSER_HEADERS["Referer"],  # Referer
            "--retry", "1",  # Retry 1 time
            "--max-time", str(max_download_time),  # Set timeout
            url
        ]
        
        result = subprocess.run(curl_command, capture_output=True, text=True)
        
        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Curl download successful for {url}")
            return True
        else:
            print(f"Curl download failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"Curl download attempt failed: {e}")
        return False
    
    return False

def get_resource_extension(resource: Dict[str, Any]) -> str:
    """
    Determine the file extension for a resource based on its format or mimetype.
    
    Args:
        resource: Resource metadata dictionary
        
    Returns:
        File extension string
    """
    resource_format = resource.get("format", "").lower()
    
    if resource_format == "excel":
        # Check mimetype for more specific format
        mimetype = resource.get("mimetype", "")
        if "openxmlformats" in mimetype:
            return "xlsx"
        else:
            return "xls"
    else:
        return resource_format

def find_and_download_resources(
    dataset: Dict[str, Any], 
    output_dir: str, 
    formats: List[str],
    single_resource: bool = False
) -> List[str]:
    """
    Find and download resources of specified formats from a dataset.
    
    Args:
        dataset: Dataset metadata dictionary
        output_dir: Directory to save downloaded files
        formats: List of formats to download
        single_resource: If True, download only the first matching resource
        
    Returns:
        List of paths to downloaded files
    """
    if not dataset:
        return []
        
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get dataset title and clean it for use as filename
    dataset_title = dataset.get("title", "dataset")
    clean_title = clean_filename(dataset_title)
    
    # List to store paths of downloaded files
    downloaded_files = []
    
    for i, resource in enumerate(dataset.get("resources", [])):
        resource_format = resource.get("format", "").lower()
        
        if resource_format in formats:
            resource_url = resource.get("url")
            if not resource_url:
                continue
            
            # Get resource name or use index
            resource_name = resource.get("name", f"resource_{i}")
            clean_resource_name = clean_filename(resource_name, max_length=50)
            
            # Get file extension
            extension = get_resource_extension(resource)
            
            # Create filename with dataset title and resource name
            output_filename = f"{clean_title}_{clean_resource_name}.{extension}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Download the file
            if download_file(resource_url, output_path):
                downloaded_files.append(output_path)
                
                # If we only need one resource, return after the first successful download
                if single_resource:
                    return downloaded_files
    
    return downloaded_files

def download_resource(
    resource_url: str, 
    output_dir: str = "downloads", 
    filename: Optional[str] = None
) -> Optional[str]:
    """
    Download a resource directly from a provided URL.
    
    Args:
        resource_url: Direct URL to the resource to download
        output_dir: Directory to save downloaded file
        filename: Optional filename to use (if None, will extract from URL)
        
    Returns:
        Path to downloaded file or None if download failed
    """
    if not resource_url:
        print("No resource URL provided")
        return None
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, filename)
    
    # Download the file
    if download_file(resource_url, output_path):
        print(f"Successfully downloaded resource to {output_path}")
        return output_path
    
    print(f"Failed to download resource from {resource_url}")
    return None

def download_dataset_resource(api_key: str, dataset_id: str, output_dir: str = "downloads") -> Optional[str]:
    """
    Download one of a dataset's resource by its ID and save to CSV, XLSX, XML, JSON, or PDF if possible.
    
    Args:
        api_key: Data.gov API key
        dataset_id: The dataset identifier
        output_dir: Directory to save downloaded files
        
    Returns:
        Path to downloaded file or None if download failed
    """
    # Get dataset metadata
    dataset = get_dataset_metadata(api_key, dataset_id)
    if not dataset:
        return None
    
    # First try to find and download tabular data formats
    downloaded_files = find_and_download_resources(
        dataset, 
        output_dir, 
        TABULAR_FORMATS,
        single_resource=True
    )
    
    if downloaded_files:
        return downloaded_files[0]
    
    # If no tabular data found, try to find and download PDF
    downloaded_files = find_and_download_resources(
        dataset, 
        output_dir, 
        DOCUMENT_FORMATS,
        single_resource=True
    )
    
    if downloaded_files:
        print(f"Downloaded PDF file: {os.path.basename(downloaded_files[0])} (CSV/Excel/XML/JSON not available)")
        return downloaded_files[0]
    
    print(f"No {', '.join(ALL_SUPPORTED_FORMATS)} resource found for dataset {dataset_id}")
    return None

def download_all_resources(api_key: str, dataset_id: str, output_dir: str = "downloads") -> List[str]:
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
    # Get dataset metadata
    dataset = get_dataset_metadata(api_key, dataset_id)
    if not dataset:
        return []
    
    # First try to find and download tabular data formats
    downloaded_files = find_and_download_resources(
        dataset, 
        output_dir, 
        TABULAR_FORMATS,
        single_resource=False
    )
    
    # If no tabular data found, try to find and download PDF
    if not downloaded_files:
        downloaded_files = find_and_download_resources(
            dataset, 
            output_dir, 
            DOCUMENT_FORMATS,
            single_resource=True  # Just get the first PDF
        )
    
    return downloaded_files