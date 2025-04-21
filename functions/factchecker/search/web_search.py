# web_search.py
import os
import requests
from typing import List, Dict, Any, Optional
import logging
import json
import datetime
import sys
import time # Added for potential timestamping if needed
import re # Ensure re is imported for regex fallback in strip_html

# web_search.py
from dotenv import load_dotenv

# Load .env from two directories up
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(dotenv_path)

# Make sure BeautifulSoup is installed: pip install beautifulsoup4
try:
    from bs4 import BeautifulSoup
except ImportError:
    logging.warning("BeautifulSoup4 not found. HTML stripping will use regex fallback.")
    BeautifulSoup = None # Set to None if not available

logger = logging.getLogger(__name__)

# --- Updated Utility Function for Content Fetching ---
def fetch_and_strip_content(
    url: str,
    timeout: int = 10,
    verify_ssl: bool = False,
    max_content_size: int = 150000 # << INCREASED THRESHOLD
) -> Dict[str, Any]:
    """
    Fetches HTML content from a URL, strips HTML tags, and returns text.
    Handles common request issues and limits *stripped* content size.
    """
    content_result = {
        "plain_text_content": None,
        "content_type": "",
        "html_fetch_error": None,
        "status_code": None
    }
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

        # Simplified handling for special sites, referer added directly
        if "nytimes.com" in url or "sciencedirect.com" in url:
             headers["Referer"] = "https://www.google.com/" # Keep this simple referer

        session = requests.Session()
        response = session.get(url, headers=headers, timeout=timeout, verify=verify_ssl)

        content_result["status_code"] = response.status_code
        content_result["content_type"] = response.headers.get("Content-Type", "")

        # Raise HTTPError for bad responses (4xx or 5xx) AFTER getting status code
        response.raise_for_status()

        # Check content type - only process HTML
        if 'text/html' in content_result["content_type"].lower():
            html_content = response.text

            # --- REMOVED Pre-stripping size check ---
            # if len(response.content) > max_content_size * 1.5: # Estimate threshold buffer for raw HTML
            #     logger.warning(f"Raw content potentially too large for {url} (>{max_content_size * 1.5} bytes raw), proceeding to strip cautiously.")
                # No longer causing an early exit here.

            stripped_text = strip_html(html_content)

            # Check *stripped* content size against the threshold
            if len(stripped_text) > max_content_size:
                 logger.warning(f"Stripped content too large for {url} (>{max_content_size} chars), discarding content.")
                 content_result["html_fetch_error"] = f"Stripped content exceeded size limit ({max_content_size} chars)"
                 content_result["plain_text_content"] = None # Explicitly set to None
            else:
                 content_result["plain_text_content"] = stripped_text
        else:
            logger.warning(f"Skipping content extraction for non-HTML content type: {content_result['content_type']} for URL: {url}")
            content_result["html_fetch_error"] = f"Non-HTML content type: {content_result['content_type']}"

    except requests.exceptions.HTTPError as http_err:
        # Handle HTTP errors specifically (like 403 Forbidden)
        logger.warning(f"HTTP error fetching content for {url}: {http_err}")
        content_result["html_fetch_error"] = str(http_err) # Include status code in error
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request error fetching content for {url}: {e}")
        content_result["html_fetch_error"] = str(e)
    except Exception as e:
        logger.error(f"Unexpected error fetching or stripping content for {url}: {e}", exc_info=True) # Log traceback for unexpected errors
        content_result["html_fetch_error"] = f"Unexpected processing error: {str(e)}"

    return content_result


# --- Modified tavily_web_search to use Google PSE + Content Fetcher ---
def tavily_web_search(
    query: str,
    max_results: int = 10,
    include_content: bool = True,
    api_key: Optional[str] = None, # Unused now, relies on env vars
    search_type: str = "comprehensive",
    timeout: int = 10, # Added for content fetching
    verify_ssl: bool = False, # Added for content fetching
    max_content_size: int = 150000 # << UPDATED DEFAULT
) -> Dict[str, Any]:
    """
    Perform a web search using Google Programmable Search Engine (PSE)
    and optionally fetch and strip content for each result.
    Outputs data in a format compatible with the previous Tavily implementation.

    Args:
        query: The search query string
        max_results: Maximum number of results to request from Google (max 10 per request)
        include_content: Whether to fetch and include stripped page content (default: True)
        api_key: (Unused) Google API Key and CSE ID are expected in environment variables.
        search_type: Type of search ("comprehensive", "news", "academic", "wikipedia")
                     to apply site restrictions.
        timeout: Timeout for fetching content for each URL.
        verify_ssl: Whether to verify SSL for content fetching.
        max_content_size: Max character size for stored stripped content.

    Returns:
        Dictionary containing search results and metadata in Tavily-like format.
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    google_cse_id = os.environ.get("GOOGLE_CSE_ID")

    if not google_api_key:
        logger.warning("Google API key (GOOGLE_API_KEY) not found in environment variables")
        return {
            "error": "Google API key not provided",
            "query": query,
            "results": []
        }
    if not google_cse_id:
        logger.warning("Google CSE ID (GOOGLE_CSE_ID) not found in environment variables")
        return {
            "error": "Google CSE ID not provided",
            "query": query,
            "results": []
        }

    # Google PSE API endpoint
    url = "https://www.googleapis.com/customsearch/v1"

    # Clamp max_results for Google PSE (max 10 per request)
    num_results = min(max_results, 10)
    if max_results > 10:
        logger.warning(f"Google PSE max results per request is 10. Requested {max_results}, using 10.")

    # Prepare request parameters
    params = {
        "key": google_api_key,
        "cx": google_cse_id,
        "q": query,
        "num": num_results,
        # Add other params like 'hl' (language), 'gl' (country) if needed
    }

    # Adjust parameters based on search type using siteSearch
    site_search_filter = None
    # (Site restriction logic remains the same)
    if search_type == "news":
        news_domains = [
            "nytimes.com", "washingtonpost.com", "bbc.com", "cnn.com",
            "reuters.com", "apnews.com", "bloomberg.com", "economist.com",
            "theguardian.com", "wsj.com", "ft.com", "time.com", "npr.org"
        ]
        site_search_filter = " OR ".join([f"site:{domain}" for domain in news_domains])
    elif search_type == "academic":
        academic_domains = [
            "scholar.google.com", "researchgate.net", "academia.edu", "jstor.org",
            "sciencedirect.com", "nature.com", "science.org", "springer.com",
            "ieee.org", "ncbi.nlm.nih.gov", "pubmed.gov", "arxiv.org", "pmc.ncbi.nlm.nih.gov" # Added PMC
        ]
        site_search_filter = " OR ".join([f"site:{domain}" for domain in academic_domains])
    elif search_type == "wikipedia":
        wiki_domains = ["wikipedia.org", "en.wikipedia.org", "wikimedia.org"]
        site_search_filter = " OR ".join([f"site:{domain}" for domain in wiki_domains])

    if site_search_filter:
        params["q"] = f"{query} {site_search_filter}"

    formatted_results = {
        "query": query,
        "results": [],
        "total_results": 0, # Will be updated
        "search_id": f"googlepse_{int(time.time())}", # Generate a pseudo ID
        "timestamp": datetime.datetime.now().isoformat(),
        "search_type": search_type,
        "search_provider": "google_pse" # Add provider info
    }

    try:
        # Make the Google PSE API request
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()  # Raise exception for HTTP errors

        google_data = response.json()
        google_items = google_data.get("items", [])

        formatted_results["total_results"] = len(google_items) # Use actual count returned

        # Process Google results and fetch content if needed
        for i, item in enumerate(google_items):
            result_url = item.get("link")
            if not result_url:
                continue

            result_entry = {
                "title": item.get("title", ""),
                "url": result_url,
                "snippet": item.get("snippet", ""), # Keep snippet from Google
                "score": 1.0 - (i / len(google_items)) if len(google_items) > 0 else 0.5, # Fake score based on rank
                # Initialize content fields
                "raw_content": None, # This will hold the stripped text
                "content": item.get("snippet", ""), # Use snippet as fallback 'content'
                "plain_text_content": None, # Also store here for potential compatibility
                "content_fetch_status": "not_attempted", # Default status
                 "content_fetch_error": None
            }

            if include_content:
                logger.info(f"Fetching content for ({i+1}/{len(google_items)}): {result_url}")
                result_entry["content_fetch_status"] = "fetching" # Update status before fetch
                content_data = fetch_and_strip_content(
                    result_url,
                    timeout=timeout,
                    verify_ssl=verify_ssl,
                    max_content_size=max_content_size # Pass the threshold
                )
                # Populate content fields based on fetch result
                result_entry["plain_text_content"] = content_data["plain_text_content"]
                # IMPORTANT: Populate 'raw_content' with the stripped text
                result_entry["raw_content"] = content_data["plain_text_content"]
                result_entry["content_fetch_error"] = content_data["html_fetch_error"]

                if content_data["plain_text_content"] is not None:
                    result_entry["content_fetch_status"] = "success"
                    # Overwrite 'content' with stripped text if available and not empty
                    if content_data["plain_text_content"].strip():
                       result_entry["content"] = content_data["plain_text_content"]
                    logger.info(f"Successfully fetched and stripped content for {result_url} ({len(result_entry['raw_content'])} chars)")
                elif content_data["html_fetch_error"]:
                    result_entry["content_fetch_status"] = "error"
                    logger.warning(f"Failed to fetch content for {result_url}: {content_data['html_fetch_error']}")
                else:
                    # This case should be less common now unless stripping yields empty string
                     result_entry["content_fetch_status"] = "processed_empty"
                     logger.warning(f"Content processed but resulted in empty string for {result_url}")


            formatted_results["results"].append(result_entry)

        return formatted_results

    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to Google PSE API: {e}")
        return {"error": f"Google PSE API Error: {str(e)}", "query": query, "results": []}
    except Exception as e:
        logger.error(f"Unexpected error during Google PSE search: {e}", exc_info=True) # Log traceback
        return {"error": f"Unexpected Error during search: {str(e)}", "query": query, "results": []}

# --- Modified enhanced_web_search ---
def enhanced_web_search(
    query: str,
    max_results: int = 10,
    api_key: Optional[str] = None, # Unused, pass-through
    timeout: int = 10,
    search_type: str = "comprehensive",
    verify_ssl: bool = False,
    max_content_size: int = 150000 # << UPDATED DEFAULT
) -> Dict[str, Any]:
    """
    Performs web search using Google PSE and ensures content fetching is enabled.
    Uses the updated default max_content_size.
    """
    logger.info(f"Running enhanced search (Google PSE + Content Fetching) for: '{query}'")

    results = tavily_web_search(
        query=query,
        max_results=max_results,
        include_content=True, # Ensure content is fetched
        api_key=api_key,
        search_type=search_type,
        timeout=timeout,
        verify_ssl=verify_ssl,
        max_content_size=max_content_size # Pass threshold
    )
    results["enhanced"] = True
    results["enhancement_method"] = "google_pse_plus_fetch"
    return results


# --- Modified combined_web_search ---
def combined_web_search(
    query: str,
    max_results_per_type: int = 3,
    api_key: Optional[str] = None, # Unused, pass-through
    include_content: bool = True,
    timeout: int = 10,
    verify_ssl: bool = False,
    max_content_size: int = 150000 # << UPDATED DEFAULT
) -> Dict[str, Any]:
    """
    Perform a comprehensive web search combining results from multiple search types
    using Google PSE, optionally fetching stripped text content.
    Uses the updated default max_content_size.
    """
    actual_max_results_per_type = min(max_results_per_type, 10)
    if max_results_per_type > 10:
         logger.warning(f"Google PSE max results per type is 10. Requested {max_results_per_type}, using 10.")

    search_types = ["comprehensive", "news", "academic", "wikipedia"]
    combined_results = {
        "query": query,
        "results": [],
        "total_results": 0,
        "search_types_used": search_types,
        "search_provider": "google_pse_combined"
    }
    processed_urls = set()

    for search_type in search_types:
        logger.info(f"Performing combined search - type: {search_type}")
        try:
            type_results = tavily_web_search(
                query=query,
                max_results=actual_max_results_per_type,
                include_content=include_content,
                api_key=api_key,
                search_type=search_type,
                timeout=timeout,
                verify_ssl=verify_ssl,
                max_content_size=max_content_size # Pass threshold
            )

            if "error" in type_results or not type_results.get("results"):
                logger.warning(f"No results or error for search type '{search_type}': {type_results.get('error', 'No results')}")
                continue

            for result in type_results.get("results", []):
                if result.get("url") and result["url"] not in processed_urls:
                    result["source_type"] = search_type
                    combined_results["results"].append(result)
                    processed_urls.add(result["url"])

        except Exception as e:
            logger.error(f"Exception during combined search for type '{search_type}': {e}", exc_info=True) # Log traceback
            continue

    combined_results["total_results"] = len(combined_results["results"])
    # Optional: Re-rank combined results if needed
    # combined_results["results"].sort(key=lambda x: x.get("score", 0), reverse=True)
    return combined_results


# --- HTML Stripping Function (Ensure BS4 is installed, logic unchanged) ---
def strip_html(html_content: str) -> str:
    """
    Strip HTML tags and formatting from HTML content, replacing with appropriate newlines.
    (Ensure BeautifulSoup4 is installed for best results: pip install beautifulsoup4)
    """
    if not html_content:
        return ""

    try:
        if not BeautifulSoup:
            raise ImportError # Force fallback if BS wasn't imported

        # Use BeautifulSoup for better parsing
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script, style, header, footer, nav elements entirely
        # Added common advertisement/sidebar patterns
        selectors_to_remove = [
            "script", "style", "header", "footer", "nav", "aside", "form",
            "button", "input", "select", "textarea", "figure", "figcaption",
            "[role='banner']", "[role='contentinfo']", "[role='navigation']",
            "[role='complementary']", "[role='search']",
            ".sidebar", "#sidebar", ".ad", "#ad", ".advertisement", "#advertisement",
            ".ads", "#ads", ".banner", "#banner", ".footer", "#footer", ".header", "#header",
            ".nav", "#nav", ".menu", "#menu"
        ]
        for selector in selectors_to_remove:
            for element in soup.select(selector):
                 element.decompose()

        # Replace common block elements with newlines *before* getting text
        # Add more block-level tags if needed
        for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br', 'tr', 'article', 'section', 'blockquote']):
             if tag.name == 'br':
                 tag.replace_with('\n')
             else:
                 # Append newline smartly (basic version: just append)
                 tag.append('\n')


        # Get text and normalize whitespace
        # Using '\n' as separator helps preserve line breaks sometimes lost by get_text
        text = soup.get_text(separator='\n', strip=True)

        # Normalize whitespace: replace multiple newlines with just two, handle spaces around newlines
        text = re.sub(r'[ \t]*\n[ \t]*', '\n', text) # Remove spaces/tabs around newlines
        text = re.sub(r'\n{3,}', '\n\n', text)     # Collapse multiple newlines to max 2
        text = re.sub(r' {2,}', ' ', text)         # Collapse multiple spaces to one (after newline handling)

        return text.strip()

    except ImportError:
        # Fallback to regex-based approach if BeautifulSoup is not available
        logger.warning("Using regex for HTML stripping (BeautifulSoup not found). Results may be less accurate.")

        # Remove script and style elements
        cleaned = re.sub(r'<script.*?>.*?</script>', ' ', html_content, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<style.*?>.*?</style>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        # Remove comments
        cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.DOTALL)
        # Remove header, footer, nav etc. (basic regex attempts)
        cleaned = re.sub(r'<header.*?>.*?</header>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<footer.*?>.*?</footer', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<nav.*?>.*?</nav>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<aside.*?>.*?</aside>', ' ', cleaned, flags=re.DOTALL | re.IGNORECASE)


        # Replace block elements with newlines
        cleaned = re.sub(r'<(p|div|h[1-6]|li|br|tr|article|section)[^>]*>', '\n', cleaned, flags=re.IGNORECASE)
        # Remove closing tags for block elements that were replaced
        cleaned = re.sub(r'</(p|div|h[1-6]|li|tr|article|section)>', ' ', cleaned, flags=re.IGNORECASE)

        # Remove all remaining HTML tags
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)

        # Replace HTML entities
        try:
            import html
            cleaned = html.unescape(cleaned)
        except ImportError:
             cleaned = re.sub(r' ', ' ', cleaned)
             cleaned = re.sub(r'<', '<', cleaned)
             cleaned = re.sub(r'>', '>', cleaned)
             cleaned = re.sub(r'&', '&', cleaned)
             cleaned = re.sub(r'"', '"', cleaned)

        # Normalize whitespace (slightly improved regex)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip() # Collapse all whitespace to single spaces first
        # Re-introduce meaningful newlines (heuristic based on original replacements)
        # This is tricky with regex; BS4 is much better. Basic attempt:
        cleaned = cleaned.replace('\n ', '\n').replace(' \n', '\n') # Tidy spaces around conceptual newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned) # Collapse multiple newlines

        return cleaned.strip()


# --- Test Functions (Unchanged logic, will use new implementations and defaults) ---
def test_web_search(query: str, use_enhanced: bool = True, max_results: int = 5, search_type: str = "comprehensive", verify_ssl: bool = False):
    """
    Test function to demonstrate web search capabilities using the NEW implementation.
    Uses updated default max_content_size.
    """
    print(f"--- Testing Web Search ---")
    print(f"Provider: Google PSE + Custom Content Fetching")
    print(f"Searching for: '{query}'")
    print(f"Using {'enhanced (content guaranteed)' if use_enhanced else 'basic (content optional)'} path")
    print(f"Max results: {min(max_results, 10)}") # Reflect Google's limit
    print(f"Search type: {search_type}")
    print(f"SSL verification for content: {'Enabled' if verify_ssl else 'Disabled'}")

    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("GOOGLE_CSE_ID"):
         print("\n*** WARNING: GOOGLE_API_KEY or GOOGLE_CSE_ID not found in environment. Search will fail. ***\n")

    try:
        if use_enhanced:
            results = enhanced_web_search(
                query=query,
                max_results=max_results,
                search_type=search_type,
                verify_ssl=verify_ssl,
                timeout=15 # Allow slightly longer timeout for testing enhanced
                # Uses default max_content_size=150000
            )
        else:
            # Basic search might not include content unless default include_content=True
            results = tavily_web_search(
                query=query,
                max_results=max_results,
                include_content=False, # Explicitly disable content for basic test path
                search_type=search_type,
                verify_ssl=verify_ssl
                # Uses default max_content_size=150000 if content *were* enabled
            )

        print(f"\nFound {results.get('total_results', 0)} results (fetched from Google PSE)")

        if "error" in results:
            print(f"Error occurred: {results['error']}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_results_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"Full results saved to: {filename}")

        print("\n--- Results Summary ---")
        if results.get("results"):
            for idx, res in enumerate(results["results"]):
                print(f"{idx+1}. {res.get('title')}")
                print(f"   URL: {res.get('url')}")
                print(f"   Snippet: {res.get('snippet')[:100]}...")
                content_status = res.get("content_fetch_status", "unknown")
                details = ""
                if content_status == "success":
                    details = f" ({len(res.get('raw_content', ''))} chars)" if res.get('raw_content') is not None else " (empty)"
                elif content_status == "error":
                     details = f" ({res.get('content_fetch_error')})"
                print(f"   Content Status: {content_status}{details}")

        return results

    except Exception as e:
        print(f"Error during test: {e}")
        logger.error("Error during test_web_search", exc_info=True)
        return {"error": str(e)}

def test_combined_search(query: str, max_results_per_type: int = 3, verify_ssl: bool = False):
    """
    Test function to demonstrate the combined web search capabilities using the NEW implementation.
    Uses updated default max_content_size.
    """
    print(f"\n--- Testing Combined Web Search ---")
    print(f"Provider: Google PSE (Multiple Types) + Custom Content Fetching")
    print(f"Performing combined search for: '{query}'")
    print(f"Max results per type: {min(max_results_per_type, 10)}") # Reflect Google's limit
    print(f"SSL verification for content: {'Enabled' if verify_ssl else 'Disabled'}")

    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("GOOGLE_CSE_ID"):
         print("\n*** WARNING: GOOGLE_API_KEY or GOOGLE_CSE_ID not found in environment. Search will fail. ***\n")

    try:
        results = combined_web_search(
            query=query,
            max_results_per_type=max_results_per_type,
            verify_ssl=verify_ssl,
            include_content=True, # Usually want content for combined
            timeout=15
            # Uses default max_content_size=150000
        )

        print(f"\nFound {results.get('total_results', 0)} unique results across {len(results.get('search_types_used',[]))} types")

        if "error" in results:
            print(f"Error occurred: {results['error']}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"combined_search_results_{timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"Full results saved to: {filename}")

        print("\n--- Combined Results Summary ---")
        if results.get("results"):
            for idx, res in enumerate(results["results"]):
                print(f"{idx+1}. [{res.get('source_type', 'N/A')}] {res.get('title')}")
                print(f"   URL: {res.get('url')}")
                content_status = res.get("content_fetch_status", "unknown")
                details = ""
                if content_status == "success":
                    details = f" ({len(res.get('raw_content', ''))} chars)" if res.get('raw_content') is not None else " (empty)"
                elif content_status == "error":
                     details = f" ({res.get('content_fetch_error')})"
                print(f"   Content Status: {content_status}{details}")

        return results

    except Exception as e:
        print(f"Error during combined test: {e}")
        logger.error("Error during test_combined_search", exc_info=True)
        return {"error": str(e)}

# --- handle_paywalled_sites function (kept for reference, unchanged) ---
def handle_paywalled_sites(url: str, session: requests.Session, headers: Dict[str, str], timeout: int, verify_ssl: bool) -> requests.Response:
    """
    Handle special cases for sites with paywalls or strict bot detection.
    (Note: This function is less critical now as basic handling is in fetch_and_strip_content)
    """
    logger.debug(f"Applying special handling for URL (if applicable): {url}")
    return session.get(url, headers=headers, timeout=timeout, verify_ssl=verify_ssl)


# Example Usage (if run directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.setLevel(logging.INFO) # Ensure logger level is set

    # --- IMPORTANT ---
    # Set your Google API Key and CSE ID as environment variables before running
    # export GOOGLE_API_KEY="YOUR_API_KEY"
    # export GOOGLE_CSE_ID="YOUR_CSE_ID"
    # ---           ---
    if not os.environ.get("GOOGLE_API_KEY") or not os.environ.get("GOOGLE_CSE_ID"):
         print("\n*** WARNING: GOOGLE_API_KEY or GOOGLE_CSE_ID not found in environment. Search will fail. ***\n")
         # sys.exit(1) # Optional: exit if keys are missing


    test_query = "Underground storage tank risks"

    # Test 1: Basic search (content fetch explicitly disabled)
    # print("\n\n===== TEST 1: Basic Search =====")
    # test_web_search(test_query, use_enhanced=False, max_results=3)
    # time.sleep(1) # Small delay between tests

    # Test 2: Enhanced search (content fetch enabled, default settings)
    print("\n\n===== TEST 2: Enhanced Search (Comprehensive) =====")
    test_web_search(test_query, use_enhanced=True, max_results=5, search_type="comprehensive")