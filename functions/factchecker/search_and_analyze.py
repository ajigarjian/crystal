import datetime
import json
import sys
import os
from typing import Any, Dict, Optional

# Add the project root to Python's path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if project_root not in sys.path:
    sys.path.append(project_root)

from functions.factchecker.search.web_search import enhanced_web_search
from functions.factchecker.processing.analysis.web_search_result_analyzer import analyze_search_results, summarize_search_analysis


def search_and_analyze(
    query: str,
    max_results: int = 10,
    search_type: str = "comprehensive",
    api_key: Optional[str] = None,
    include_content: bool = True,
    analyze_results: bool = True,
    strip_plain_text: bool = True
) -> Dict[str, Any]:
    """
    Perform a web search and analyze the results for relevance to the query.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return and analyze
        search_type: Type of search to perform ("comprehensive", "news", "academic", or "wikipedia")
        api_key: Tavily API key (if None, will try to get from environment variable)
        include_content: Whether to include full page content
        analyze_results: Whether to analyze the results for relevance
        strip_plain_text: Whether to remove plain_text_content from results to reduce payload size
        
    Returns:
        Dictionary containing search results and analysis
    """
    # First perform the search
    search_results = enhanced_web_search(
        query=query,
        max_results=max_results,
        api_key=api_key,
        search_type=search_type
    )
    
    # If analysis is not requested or there was an error, return just the search results
    if not analyze_results or "error" in search_results:
        if strip_plain_text:
            search_results = _strip_plain_text_content(search_results)
        return search_results
    
    # Analyze the search results
    analysis_results = analyze_search_results(
        query=query,
        search_results=search_results,
        max_results=max_results
    )
    
    # Create a summary of the analysis
    summary = summarize_search_analysis(
        query=query,
        analysis_results=analysis_results
    )
    
    # Return the combined results, optionally stripping plain_text_content
    if strip_plain_text:
        search_results = _strip_plain_text_content(search_results)
    
    return {
        "search_results": search_results,
        "analysis": analysis_results,
        "summary": summary
    }

def _strip_plain_text_content(search_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove plain_text_content, content, and raw_content from search results to reduce payload size.
    
    Args:
        search_results: The search results dictionary
        
    Returns:
        Search results with plain_text_content, content, and raw_content removed
    """
    if not isinstance(search_results, dict):
        return search_results
    
    # Create a copy to avoid modifying the original
    results_copy = search_results.copy()
    
    # Remove plain_text_content, content, and raw_content from each result
    if "results" in results_copy and isinstance(results_copy["results"], list):
        for result in results_copy["results"]:
            # Remove plain_text_content if present
            if "plain_text_content" in result:
                result["plain_text_content_stripped"] = True
                del result["plain_text_content"]
            
            # Remove content if present
            if "content" in result:
                result["content_stripped"] = True
                del result["content"]
                
            # Remove raw_content if present
            if "raw_content" in result:
                result["raw_content_stripped"] = True
                del result["raw_content"]
    
    return results_copy

def test_search_and_analyze(
    query: str,
    max_results: int = 5,
    search_type: str = "comprehensive",
    verify_ssl: bool = False,
    strip_plain_text: bool = True
):
    """
    Test function to demonstrate web search and analysis capabilities.
    
    Args:
        query: The search query to test
        max_results: Maximum number of results to return and analyze
        search_type: Type of search to perform
        verify_ssl: Whether to verify SSL certificates
        strip_plain_text: Whether to remove plain_text_content from results
    """
    print(f"Searching and analyzing: '{query}'")
    print(f"Max results: {max_results}")
    print(f"Search type: {search_type}")
    print(f"SSL verification: {'Enabled' if verify_ssl else 'Disabled'}")
    print(f"Strip plain text: {'Enabled' if strip_plain_text else 'Disabled'}")
    
    try:
        results = search_and_analyze(
            query=query,
            max_results=max_results,
            search_type=search_type,
            strip_plain_text=strip_plain_text
        )
        
        # Get summary information
        summary = results.get("summary", {})
        has_relevant_results = summary.get("has_relevant_results", False)
        summary_text = summary.get("summary", "No summary available")
        
        print(f"\nAnalysis complete. Found relevant results: {has_relevant_results}")
        print(f"Summary: {summary_text}")
        
        # Save full results to a JSON file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_analysis_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"Full results saved to: {filename}")
        
        return results
        
    except Exception as e:
        print(f"Error during test: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Example usage
    test_query = "what is the percentage of Americans who abstain from alcohol?"
    
    # Test search and analysis
    test_search_and_analyze(test_query, max_results=5, search_type="comprehensive")
    
    # Uncomment to test individual search types
    # test_web_search(test_query, max_results=8, verify_ssl=False)
    # test_web_search(test_query, search_type="news", max_results=8, verify_ssl=False)
    # test_web_search(test_query, search_type="academic", max_results=8, verify_ssl=False)
    # test_web_search(test_query, search_type="wikipedia", max_results=8, verify_ssl=False)
