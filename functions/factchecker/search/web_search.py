import os
import requests
from typing import List, Dict, Any, Optional
import logging
import json
import datetime
import sys

logger = logging.getLogger(__name__)

def tavily_web_search(
    query: str,
    max_results: int = 10,
    include_content: bool = True,
    api_key: Optional[str] = None,
    search_type: str = "comprehensive"
) -> Dict[str, Any]:
    """
    Perform a web search using the Tavily API and return top results with full page content.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 10)
        include_content: Whether to include full page content (default: True)
        api_key: Tavily API key (if None, will try to get from environment variable)
        search_type: Type of search to perform ("comprehensive", "news", "academic", or "wikipedia")
        
    Returns:
        Dictionary containing search results and metadata
    """
    # Get API key from environment variable if not provided
    api_key = api_key or os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logger.warning("Tavily API key not provided and not found in environment variables")
        # Return empty results instead of raising an exception
        return {
            "error": "Tavily API key not provided and not found in environment variables",
            "query": query,
            "results": []
        }
    
    # Tavily API endpoint
    url = "https://api.tavily.com/search"
    
    # Prepare request parameters
    params = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "include_domains": [],
        "exclude_domains": [],
        "include_raw_content": include_content,
        "search_depth": "advanced" if include_content else "basic"
    }
    
    # Adjust parameters based on search type
    if search_type == "news":
        # Focus on news sites and recent content
        params["search_depth"] = "advanced"
        params["include_domains"] = [
            "nytimes.com", "washingtonpost.com", "bbc.com", "cnn.com", 
            "reuters.com", "apnews.com", "bloomberg.com", "economist.com",
            "theguardian.com", "wsj.com", "ft.com", "time.com", "npr.org"
        ]
    elif search_type == "academic":
        # Focus on academic and research content
        params["search_depth"] = "advanced"
        params["include_domains"] = [
            "scholar.google.com", "researchgate.net", "academia.edu", "jstor.org",
            "sciencedirect.com", "nature.com", "science.org", "springer.com",
            "ieee.org", "ncbi.nlm.nih.gov", "pubmed.gov", "arxiv.org"
        ]
    elif search_type == "wikipedia":
        # Focus specifically on Wikipedia content
        params["search_depth"] = "advanced"
        params["include_domains"] = [
            "wikipedia.org", "en.wikipedia.org", "wikimedia.org"
        ]
    
    try:
        # Make the API request
        response = requests.post(url, json=params)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        results = response.json()
        
        # Process and format the results
        formatted_results = {
            "query": query,
            "results": results.get("results", []),
            "total_results": len(results.get("results", [])),
            "search_id": results.get("search_id", ""),
            "timestamp": results.get("time", ""),
            "search_type": search_type
        }
        
        # Process each result to ensure raw_content is properly formatted
        for result in formatted_results["results"]:
            # If raw_content is null but content exists, use the content field
            if result.get("raw_content") is None and "content" in result:
                result["raw_content"] = result["content"]
        
        return formatted_results
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to Tavily API: {e}")
        return {"error": str(e), "query": query, "results": []}
    except Exception as e:
        logger.error(f"Unexpected error during Tavily search: {e}")
        return {"error": str(e), "query": query, "results": []}

def enhanced_web_search(
    query: str,
    max_results: int = 10,
    api_key: Optional[str] = None,
    timeout: int = 10,
    search_type: str = "comprehensive",
    verify_ssl: bool = False
) -> Dict[str, Any]:
    """
    Perform a web search using Tavily API and enhance results by fetching the full HTML content
    for each returned URL, but only store the plain-text version.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 10)
        api_key: Tavily API key (if None, will try to get from environment variable)
        timeout: Timeout in seconds for fetching HTML content (default: 10)
        search_type: Type of search to perform ("comprehensive", "news", or "academic")
        verify_ssl: Whether to verify SSL certificates (default: False)
        
    Returns:
        Dictionary containing search results with enhanced full HTML content
    """
    # First get the search results from Tavily
    try:
        search_results = tavily_web_search(
            query=query,
            max_results=max_results,
            include_content=True,
            api_key=api_key,
            search_type=search_type
        )
    except Exception as e:
        logger.error(f"Error in tavily_web_search: {e}")
        return {
            "error": str(e),
            "query": query,
            "results": []
        }
    
    # If there was an error or no results, return early
    if "error" in search_results or not search_results.get("results"):
        return search_results
    
    # Enhance each result with full HTML content (but only save stripped text)
    for result in search_results["results"]:
        url = result.get("url")
        if not url:
            continue
            
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0"
            }
            
            if "nytimes.com" in url or "sciencedirect.com" in url:
                headers["Referer"] = "https://www.google.com/"
                
            session = requests.Session()
            
            if "nytimes.com" in url:
                # First visit the homepage to get cookies
                session.get("https://www.nytimes.com/", headers=headers, timeout=timeout, verify=verify_ssl)
                response = session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
            else:
                response = session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
            
            if response.status_code == 200:
                # Store *only* stripped text
                result["plain_text_content"] = strip_html(response.text)
                result["content_type"] = response.headers.get("Content-Type", "")
            else:
                result["plain_text_content"] = None
                result["html_fetch_error"] = f"HTTP {response.status_code}"
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error fetching HTML content for {url}: {e}")
            result["plain_text_content"] = None
            result["html_fetch_error"] = str(e)
    
    # Add metadata about the enhancement
    search_results["enhanced"] = True
    search_results["enhancement_method"] = "direct_html_fetch"
    
    return search_results

def test_web_search(query: str, use_enhanced: bool = True, max_results: int = 5, search_type: str = "comprehensive", verify_ssl: bool = False):
    """
    Test function to demonstrate web search capabilities.
    
    Args:
        query: The search query to test
        use_enhanced: Whether to use the enhanced search with full HTML (default: True)
        max_results: Maximum number of results to return (default: 5)
        search_type: Type of search to perform ("comprehensive", "news", or "academic")
        verify_ssl: Whether to verify SSL certificates (default: False)
    """
    print(f"Searching for: '{query}'")
    print(f"Using {'enhanced' if use_enhanced else 'basic'} search with max {max_results} results")
    print(f"Search type: {search_type}")
    print(f"SSL verification: {'Enabled' if verify_ssl else 'Disabled'}")
    
    try:
        if use_enhanced:
            results = enhanced_web_search(query=query, max_results=max_results, search_type=search_type, verify_ssl=verify_ssl)
        else:
            results = tavily_web_search(query=query, max_results=max_results, search_type=search_type)
        
        print(f"\nFound {results.get('total_results', 0)} results")
        
        # Save full results to a JSON file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_results_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"Full results saved to: {filename}")
        
        return results
        
    except Exception as e:
        print(f"Error during test: {e}")
        return {"error": str(e)}

def combined_web_search(
    query: str,
    max_results_per_type: int = 3,
    api_key: Optional[str] = None,
    include_content: bool = True,
    timeout: int = 10,
    verify_ssl: bool = False
) -> Dict[str, Any]:
    """
    Perform a comprehensive web search that combines results from multiple search types
    and (optionally) fetches full HTML, but only stores stripped text in results (if not too large).
    """
    THRESHOLD_SIZE = 20000  # same idea as above

    search_types = ["comprehensive", "news", "academic", "wikipedia"]
    
    combined_results = {
        "query": query,
        "results": [],
        "total_results": 0,
        "search_types_used": search_types
    }
    
    # Perform Tavily searches for each type:
    for search_type in search_types:
        try:
            type_results = tavily_web_search(
                query=query,
                max_results=max_results_per_type,
                include_content=include_content,
                api_key=api_key,
                search_type=search_type
            )
            
            # Skip this search type if there was an error
            if "error" in type_results:
                logger.warning(f"Error in {search_type} search: {type_results.get('error')}")
                continue
                
        except Exception as e:
            logger.error(f"Exception in {search_type} search: {e}")
            continue
        
        for result in type_results.get("results", []):
            result["source_type"] = search_type
            
            # If we're including content, fetch HTML but only store stripped text if raw_content is small
            if include_content:
                url = result.get("url")
                if url:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "none",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0"
                    }
                    
                    if "nytimes.com" in url or "sciencedirect.com" in url:
                        headers["Referer"] = "https://www.google.com/"
                    
                    session = requests.Session()
                    
                    try:
                        if "nytimes.com" in url:
                            session.get("https://www.nytimes.com/", headers=headers, timeout=timeout, verify=verify_ssl)
                            response = session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
                        else:
                            response = session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
                        
                        if response.status_code == 200:
                            stripped = strip_html(response.text)
                            result["content_type"] = response.headers.get("Content-Type", "")
                            
                            # If raw_content is huge, skip
                            if len(result.get("raw_content", "")) > THRESHOLD_SIZE:
                                result["plain_text_content"] = None
                            else:
                                result["plain_text_content"] = stripped
                        else:
                            result["plain_text_content"] = None
                            result["html_fetch_error"] = f"HTTP {response.status_code}"
                            
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Error fetching HTML content for {url}: {e}")
                        result["plain_text_content"] = None
                        result["html_fetch_error"] = str(e)
            
            combined_results["results"].append(result)
    
    combined_results["total_results"] = len(combined_results["results"])
    return combined_results

def test_combined_search(query: str, max_results_per_type: int = 3, verify_ssl: bool = False):
    """
    Test function to demonstrate the combined web search capabilities.
    
    Args:
        query: The search query to test
        max_results_per_type: Maximum number of results to return per search type (default: 3)
        verify_ssl: Whether to verify SSL certificates (default: False)
        
    Returns:
        Dictionary containing the combined search results
    """
    print(f"Performing combined search for: '{query}'")
    print(f"Max results per type: {max_results_per_type}")
    print(f"SSL verification: {'Enabled' if verify_ssl else 'Disabled'}")
    
    try:
        results = combined_web_search(query=query, max_results_per_type=max_results_per_type, verify_ssl=verify_ssl)
        
        print(f"\nFound {results.get('total_results', 0)} total results across all sources")
        
        # Save full results to a JSON file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"combined_search_results_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"Full results saved to: {filename}")
        
        return results
        
    except Exception as e:
        print(f"Error during test: {e}")
        return {"error": str(e)}

def strip_html(html_content: str) -> str:
    """
    Strip HTML tags and formatting from HTML content, replacing with appropriate newlines.
    
    Args:
        html_content: The HTML content to strip
        
    Returns:
        Plain text with HTML tags removed and formatting preserved with newlines
    """
    if not html_content:
        return ""
    
    try:
        # Try to use BeautifulSoup if available (provides better HTML parsing)
        from bs4 import BeautifulSoup
        
        # Parse the HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Replace common block elements with newlines
        for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br']):
            tag.append('\n')
        
        # Get text and normalize whitespace
        text = soup.get_text()
        
        # Normalize whitespace: replace multiple newlines with just two
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        return text.strip()
        
    except ImportError:
        # Fallback to regex-based approach if BeautifulSoup is not available
        import re
        
        # Remove script and style elements
        html_content = re.sub(r'<script.*?>.*?</script>', ' ', html_content, flags=re.DOTALL)
        html_content = re.sub(r'<style.*?>.*?</style>', ' ', html_content, flags=re.DOTALL)
        
        # Replace block elements with newlines
        html_content = re.sub(r'<(p|div|h[1-6]|li|br)[^>]*>', '\n', html_content)
        html_content = re.sub(r'</(p|div|h[1-6]|li)>', '\n', html_content)
        
        # Remove all remaining HTML tags
        html_content = re.sub(r'<[^>]*>', ' ', html_content)
        
        # Replace HTML entities
        html_content = re.sub(r'&nbsp;', ' ', html_content)
        html_content = re.sub(r'&lt;', '<', html_content)
        html_content = re.sub(r'&gt;', '>', html_content)
        html_content = re.sub(r'&amp;', '&', html_content)
        html_content = re.sub(r'&quot;', '"', html_content)
        
        # Normalize whitespace
        html_content = re.sub(r'\n{3,}', '\n\n', html_content)
        html_content = re.sub(r' {2,}', ' ', html_content)
        
        return html_content.strip()

def handle_paywalled_sites(url: str, session: requests.Session, headers: Dict[str, str], timeout: int, verify_ssl: bool) -> requests.Response:
    """
    Handle special cases for sites with paywalls or strict bot detection.
    
    Args:
        url: The URL to fetch
        session: The requests session to use
        headers: Headers to use for the request
        timeout: Request timeout in seconds
        verify_ssl: Whether to verify SSL certificates
        
    Returns:
        The response object
    """
    # NYTimes specific handling
    if "nytimes.com" in url:
        # First visit the homepage to get cookies
        session.get("https://www.nytimes.com/", headers=headers, timeout=timeout, verify=verify_ssl)
        # Add specific cookies that might help bypass the paywall
        session.cookies.set("nyt-gdpr", "1", domain=".nytimes.com")
        session.cookies.set("nyt-a", "visitor", domain=".nytimes.com")
        # Then get the actual page
        return session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
    
    # ScienceDirect specific handling
    elif "sciencedirect.com" in url:
        # First visit the homepage to get cookies
        session.get("https://www.sciencedirect.com/", headers=headers, timeout=timeout, verify=verify_ssl)
        # Add specific headers for ScienceDirect
        headers["Origin"] = "https://www.sciencedirect.com"
        headers["Referer"] = "https://www.sciencedirect.com/"
        return session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)
    
    # Default handling for other sites
    else:
        return session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)

