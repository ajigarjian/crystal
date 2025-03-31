import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple

from factchecker.utils.openai_client import chat_completion

logger = logging.getLogger(__name__)

def extract_relevant_content(
    query: str,
    search_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract relevant parts of the search result content that address the user's query.
    
    Args:
        query: The user's original query
        search_result: A single search result dictionary containing content
        
    Returns:
        Dictionary containing:
        {
            'is_relevant': bool,
            'relevance_level': int (0-5),
            'summary': str,
            'content_source': str,
            'temporal_context': str,
            'scope': str
        }
    """
    # Get the content from the search result
    title = search_result.get('title', '')
    url = search_result.get('url', '')
    snippet = search_result.get('snippet', '')
    
    # Try to get the full content in order of preference
    content = None
    content_source = None
    
    if search_result.get('plain_text_content'):
        content = search_result.get('plain_text_content')
        content_source = 'plain_text_content'
    elif search_result.get('raw_content'):
        content = search_result.get('raw_content')
        content_source = 'raw_content'
    elif search_result.get('content'):
        content = search_result.get('content')
        content_source = 'content'
    else:
        content = snippet
        content_source = 'snippet'
    
    # If content is too large, truncate it
    max_content_length = 15000  # Limit to avoid token limits in LLM
    if content and len(content) > max_content_length:
        content = content[:max_content_length] + "... [content truncated]"
    
    # Create prompt for OpenAI
    prompt = f'''Determine the relevance of this web search result to the user's query and provide a summary.

USER QUERY: "{query}"

WEB SEARCH RESULT:
Title: {title}
URL: {url}
Content:
{content}

CURRENT YEAR: 2025

TASK:
1. Determine if this search result contains information relevant to the user's query.
2. If relevant, provide a summary (1-2 paragraphs) of the content that addresses the query.
3. Note any temporal information (dates, timeframes) in the content.
4. Consider the scope of the information (e.g., global, national, specific demographic).
5. Assign a relevance level from 0-5:
   - 0: Not relevant at all
   - 1: Minimally relevant
   - 2: Somewhat relevant
   - 3: Moderately relevant
   - 4: Highly relevant
   - 5: Extremely relevant

Format your response exactly as:
RELEVANT: [Yes/No]
RELEVANCE_LEVEL: [0-5]
SUMMARY: [Summary of the content or "None" if not relevant]
TEMPORAL_CONTEXT: [Any dates or time periods mentioned]
SCOPE: [Geographic or demographic scope of the information]
'''

    system_message = "You are a research assistant who extracts relevant information from web search results. Be precise and only extract exact quotes that directly address the query. Pay special attention to when the information was published or the time period it refers to."
    
    try:
        response = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1
        )
        
        # Parse the response
        relevant_match = re.search(r'RELEVANT:\s*(Yes|No)', response, re.IGNORECASE)
        level_match = re.search(r'RELEVANCE_LEVEL:\s*(\d)', response)
        summary_match = re.search(r'SUMMARY:\s*(.*?)(?:\n\w+:|$)', response, re.DOTALL)
        temporal_match = re.search(r'TEMPORAL_CONTEXT:\s*(.*?)(?:\n\w+:|$)', response, re.DOTALL)
        scope_match = re.search(r'SCOPE:\s*(.*?)(?:\n\w+:|$)', response, re.DOTALL)
        
        is_relevant = False
        if relevant_match:
            is_relevant = relevant_match.group(1).lower() == 'yes'
        
        relevance_level = 0
        if level_match:
            relevance_level = int(level_match.group(1))
        
        summary = "No summary provided"
        if summary_match:
            summary = summary_match.group(1).strip()
        
        temporal_context = ""
        if temporal_match:
            temporal_context = temporal_match.group(1).strip()
        
        scope = ""
        if scope_match:
            scope = scope_match.group(1).strip()
        
        return {
            'is_relevant': is_relevant,
            'relevance_level': relevance_level,
            'summary': summary,
            'content_source': content_source,
            'temporal_context': temporal_context,
            'scope': scope
        }
    
    except Exception as e:
        logger.error(f"Error extracting relevant content: {str(e)}")
        return {
            'is_relevant': False,
            'relevance_level': 0,
            'summary': f"Error during extraction: {str(e)}",
            'content_source': content_source,
            'temporal_context': "",
            'scope': ""
        }

def validate_extraction(
    query: str,
    search_result: Dict[str, Any],
    extraction_result: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Validate the relevance and summary of the extracted content.
    
    Args:
        query: The user's original query
        search_result: The original search result
        extraction_result: The result from extract_relevant_content
        
    Returns:
        Tuple of (is_valid, reason)
    """
    # If not relevant, nothing to validate
    if not extraction_result.get('is_relevant', False):
        return True, "Not relevant, no validation needed"
    
    # Validate relevance level
    relevance_level = extraction_result.get('relevance_level', 0)
    summary = extraction_result.get('summary', '')
    
    if relevance_level > 0 and not summary:
        return False, "Relevance level > 0 but no summary provided"
    
    return True, "Validation successful"

def analyze_search_result(
    query: str,
    search_result: Dict[str, Any],
    max_retries: int = 1
) -> Optional[Dict[str, Any]]:
    """
    Analyze a single search result to extract relevant content and validate the extraction.
    
    Args:
        query: The user's original query
        search_result: A single search result dictionary
        max_retries: Maximum number of retries for extraction
        
    Returns:
        Dictionary containing the analysis result or None if validation fails
    """
    retry_count = 0
    
    while retry_count <= max_retries:
        # Extract relevant content
        extraction_result = extract_relevant_content(query, search_result)
        
        # Validate the extraction
        is_valid, validation_reason = validate_extraction(query, search_result, extraction_result)
        
        if is_valid:
            # Return the result with metadata
            return {
                'title': search_result.get('title', 'Unknown'),
                'url': search_result.get('url', ''),
                'source_type': search_result.get('source_type', 'web'),
                'is_relevant': extraction_result.get('is_relevant', False),
                'relevance_level': extraction_result.get('relevance_level', 0),
                'summary': extraction_result.get('summary', ''),
                'temporal_context': extraction_result.get('temporal_context', ''),
                'scope': extraction_result.get('scope', ''),
                'validation': {
                    'is_valid': is_valid,
                    'reason': validation_reason
                }
            }
        
        # If validation failed and we have retries left, try again
        retry_count += 1
        logger.warning(f"Validation failed: {validation_reason}. Retrying ({retry_count}/{max_retries})...")
    
    # If we've exhausted retries and still failed validation, return None
    logger.error(f"Failed to validate extraction after {max_retries} retries")
    return {
        'title': search_result.get('title', 'Unknown'),
        'url': search_result.get('url', ''),
        'source_type': search_result.get('source_type', 'web'),
        'is_relevant': extraction_result.get('is_relevant', False),
        'relevance_level': 0,
        'summary': extraction_result.get('summary', ''),
        'temporal_context': extraction_result.get('temporal_context', ''),
        'scope': extraction_result.get('scope', ''),
        'validation': {
            'is_valid': False,
            'reason': validation_reason
        }
    }

def analyze_search_results(
    query: str,
    search_results: Dict[str, Any],
    max_results: int = 10
) -> Dict[str, Any]:
    """
    Analyze web search results to extract relevant content from each result.
    
    Args:
        query: The user's original query
        search_results: Dictionary containing search results from web_search.py
        max_results: Maximum number of results to analyze
        
    Returns:
        Dictionary containing analysis of each result
    """
    results = search_results.get('results', [])
    
    # Limit the number of results to analyze
    results = results[:max_results]
    
    analyzed_results = []
    
    for result in results:
        analysis = analyze_search_result(query, result)
        if analysis:
            analyzed_results.append(analysis)
    
    # Sort results by relevance level (descending)
    analyzed_results.sort(key=lambda x: x.get('relevance_level', 0), reverse=True)
    
    analysis_result = {
        'query': query,
        'total_results_analyzed': len(analyzed_results),
        'relevant_results': sum(1 for r in analyzed_results if r.get('is_relevant', False)),
        'analyzed_results': analyzed_results,
        'search_metadata': {
            'search_id': search_results.get('search_id', ''),
            'timestamp': search_results.get('timestamp', ''),
            'search_type': search_results.get('search_type', 'comprehensive')
        }
    }
    
    # Print sources information to stdout
    print(f"Analysis complete. Found relevant results: {analysis_result['relevant_results'] > 0}")
    
    return analysis_result

def summarize_search_analysis(
    query: str,
    analysis_results: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create a summary of the search analysis results.
    
    Args:
        query: The user's original query
        analysis_results: The results from analyze_search_results
        
    Returns:
        Dictionary containing a summary of the analysis
    """
    analyzed_results = analysis_results.get('analyzed_results', [])
    relevant_results = [r for r in analyzed_results if r.get('is_relevant', False)]
    
    # If no relevant results, return a simple summary
    if not relevant_results:
        return {
            'query': query,
            'has_relevant_results': False,
            'summary': "No relevant information found in the search results.",
            'top_sources': [],
            'sources': {}  # Empty sources dictionary
        }
    
    # Create a prompt for the LLM to summarize the relevant results
    relevant_content = []
    
    # Track URLs to avoid duplicates
    seen_urls = set()
    unique_relevant_results = []
    
    # Filter out duplicate sources based on URL
    for result in relevant_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_relevant_results.append(result)
    
    # Use only unique results (up to 5)
    for i, result in enumerate(unique_relevant_results[:5]):
        source_name = f"{result.get('title', 'Unknown')}"
        temporal_info = f" ({result.get('temporal_context', 'No date information')})" if result.get('temporal_context') else ""
        scope_info = f" - Scope: {result.get('scope', 'Not specified')}" if result.get('scope') else ""
        
        relevant_content.append(
            f"Source {i+1}: {source_name}{temporal_info}\n"
            f"URL: {result.get('url', '')}{scope_info}\n"
            f"Summary: {result.get('summary', 'No summary available')}"
        )
    
    all_content = "\n\n".join(relevant_content)
    
    prompt = f'''Summarize the relevant information to directly answer the user's query.

USER QUERY: "{query}"

RELEVANT SEARCH RESULTS:
{all_content}

CURRENT YEAR: 2025

TASK:
1. Focus primarily on directly answering the user's query with clarity and accuracy
2. Create a comprehensive but concise summary (2-3 paragraphs) that emphasizes key information relevant to the query
3. Still cite sources using numbered citation format [1], [2], etc. but keep citations brief and unobtrusive
4. Include temporal context when available and relevant to interpreting the answer
5. Only note scope information (global, national, demographic-specific) when it affects the interpretation of results
6. Identify consensus or contradictions between sources only when relevant to the user's understanding
7. Keep your language clear, direct, and focused on providing the most useful answer

Format your response exactly as:
SUMMARY: [2-3 paragraph summary that directly answers the query, with unobtrusive numbered citations [1], [2], etc.]
'''

    system_message = "You are a research assistant who directly answers user questions from multiple sources. Focus on providing clear, accurate answers with minimal focus on the sources themselves. Be concise, emphasize insights relevant to the query, and use citations only when needed for credibility."
    
    try:
        response = chat_completion(
            prompt=prompt,
            system_message=system_message,
            model_name="o3-mini",
            temperature=0.1
        )
        
        # Parse the response
        summary_match = re.search(r'SUMMARY:\s*(.*)', response, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else "No summary generated."
        
        # Get top sources (up to 5) - use the unique results
        top_sources = []
        sources_dict = {}
        for i, result in enumerate(unique_relevant_results[:5]):
            source_num = i + 1
            top_sources.append({
                'title': result.get('title', 'Unknown'),
                'url': result.get('url', ''),
                'relevance_level': result.get('relevance_level', 0),
                'source_type': result.get('source_type', 'web')
            })
            
            # Add to sources dictionary with numeric keys
            sources_dict[str(source_num)] = {
                'title': result.get('title', 'Unknown'),
                'url': result.get('url', ''),
                'publisher': result.get('publisher', 'Unknown')
            }
        
        # Create separate objects for summary and sources
        summary_result = {
            'query': query,
            'has_relevant_results': True,
            'summary': summary,
            'total_relevant_sources': len(relevant_results),
            'source_citations': True
        }
        
        # Sources information in a separate object
        sources_info = {
            'top_sources': top_sources,
            'sources': sources_dict
        }
        
        # Print summary and sources to stdout
        print(f"Summary: {summary}")
        print(f"Sources: {json.dumps(sources_dict, indent=2)}")
        
        # Return combined result
        return {**summary_result, **sources_info}
        
    except Exception as e:
        logger.error(f"Error creating summary: {str(e)}")
        return {
            'query': query,
            'has_relevant_results': True,
            'summary': f"Error creating summary: {str(e)}",
            'top_sources': [{'title': r.get('title', 'Unknown'), 'url': r.get('url', '')} for r in relevant_results[:5]],
            'sources': {},  # Empty sources dictionary
            'total_relevant_sources': len(relevant_results)
        }
