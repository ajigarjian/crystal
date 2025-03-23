# PDF Analysis Module for Factchecker
import logging
import json
from typing import Dict, List, Any, Union

from factchecker.utils.openai_client import chat_completion

def analyze_and_extract_pdf_data(
    pdf_data: Dict[str, Any],
    query: str,
    dataset_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Analyze the entire PDF content and extract all relevant data based on the query.
    
    Args:
        pdf_data: The PDF data dictionary from load_pdf_document
        query: The user query
        dataset_metadata: Metadata about the dataset
        
    Returns:
        Dictionary with extracted data in the same format as tabular extraction
    """
    logger = logging.getLogger("pdf_analysis")
    logger.info(f"Analyzing PDF for query: {query}")
    
    # Initialize the result structure
    result = {
        "dataset_id": dataset_metadata.get("id", ""),
        "dataset_title": dataset_metadata.get("title", pdf_data.get("file_name", "")),
        "file_path": pdf_data.get("file_path", ""),
        "results_dict": {},
        "printed_output": "",
        "extraction_strategy": "Comprehensive PDF content extraction",
        "explanation": "Extracted all relevant content from PDF based on query",
        "code": "",
        "error": None
    }
    
    try:
        # Get the full text and page texts
        full_text = pdf_data.get("full_text", "")
        page_texts = pdf_data.get("page_texts", [])
        total_pages = len(page_texts)
        
        # Create a structured representation with page numbers
        formatted_pages = []
        for i, page_text in enumerate(page_texts):
            page_num = i + 1  # 1-indexed page numbers
            formatted_pages.append(f"PAGE {page_num}:\n{page_text}")
        
        all_pages_text = "\n\n".join(formatted_pages)
        
        # Create prompt for the entire document
        prompt = f"""
You are analyzing a PDF document to find ALL content relevant to a user query.

USER QUERY: "{query}"

PDF DOCUMENT:
Title: {pdf_data.get('title', pdf_data.get('file_name', 'Unknown'))}
Total Pages: {total_pages}

For each page that contains information relevant to the query, identify ALL specific text sections and their relevance.
Do not limit yourself to a specific number of sections - extract ALL relevant content.

{all_pages_text}

Your analysis should include:
1. All text sections that are relevant to the query, including their page numbers
2. Key findings that directly address the query based on the document content

Return your analysis as JSON with these fields:
- relevant_sections: Array of {{"text": "extracted text", "page_number": number, "relevance": "brief explanation of relevance"}}
- key_findings: Array of strings with key information related to the query

If a page has no relevant content, don't include it in the results.
"""
        
        response = chat_completion(
            prompt,
            system_message="You are a document analysis expert. Extract ALL relevant content, not just a limited number of sections.",
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # Parse the response
        analysis_results = json.loads(response)
        
        # Format the final results
        result["results_dict"] = {
            "relevant_text_sections": analysis_results.get("relevant_sections", []),
            "key_findings": analysis_results.get("key_findings", [])
        }
        
        # Generate a summary of what was extracted
        num_sections = len(result["results_dict"]["relevant_text_sections"])
        num_findings = len(result["results_dict"]["key_findings"])
        result["printed_output"] = f"Extracted {num_sections} relevant text sections and {num_findings} key findings from PDF."
        
        logger.info(f"Completed PDF analysis. Found {num_sections} relevant sections and {num_findings} key findings.")
        return result
        
    except Exception as e:
        logger.error(f"Error analyzing and extracting PDF data: {str(e)}")
        result["error"] = str(e)
        return result