from .search.web_search import enhanced_web_search

def search_and_analyze(query, max_results=5, search_type="comprehensive", analyze_results=True):
    """
    Search and analyze data based on a given query
    
    Args:
        query (str): The search query
        max_results (int): Maximum number of search results to return
        search_type (str): The type of search to perform (comprehensive, quick, etc.)
        analyze_results (bool): Whether to analyze the search results
        
    Returns:
        dict: A dictionary containing the search results and analysis
    """
    # Perform web search
    search_results = enhanced_web_search(query, max_results)
    
    # Return the results
    return {
        "query": query,
        "search_results": search_results,
        "summary": "Web search results found." if search_results else "No relevant web search results found."
    }