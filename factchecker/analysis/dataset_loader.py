import pandas as pd
import os
import openai
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import logging
import re
import PyPDF2
from io import StringIO
import json

"""
This module handles loading and processing datasets for the factchecker application.
It provides utilities for loading datasets from various file formats, assessing their
relevance to user queries, and preparing them for further analysis.
"""

def load_dataset(file_path: str, openai_api_key: str = None) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Load a dataset (CSV, Excel, or PDF) with appropriate error handling.
    
    Args:
        file_path: Path to the dataset file
        openai_api_key: Optional OpenAI API key for enhanced PDF summary
        
    Returns:
        For CSV/Excel: Pandas DataFrame containing the dataset
        For PDF: Dictionary with extracted text and metadata
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading dataset from {file_path}")
    
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # Handle PDF files
    if file_extension == '.pdf':
        logger.info(f"Detected PDF file: {file_path}")
        return load_pdf_document(file_path, openai_api_key)
    
    try:
        # Handle Excel files
        if file_extension in ['.xlsx', '.xls']:
            logger.info(f"Detected Excel file: {file_path}")
            loading_attempts = [
                # Standard loading
                lambda: pd.read_excel(file_path),
                # Try with explicit engine
                lambda: pd.read_excel(file_path, engine='openpyxl'),
                # Try with xlrd engine for older .xls files
                lambda: pd.read_excel(file_path, engine='xlrd')
            ]
        # Handle CSV files
        else:
            logger.info(f"Detected CSV file: {file_path}")
            loading_attempts = [
                # Standard loading
                lambda: pd.read_csv(file_path),
                # Try with Latin-1 encoding
                lambda: pd.read_csv(file_path, encoding='latin1'),
                # Try with explicit quoting
                lambda: pd.read_csv(file_path, quoting=pd.io.common.csv.QUOTE_NONNUMERIC),
                # Try with different engine
                lambda: pd.read_csv(file_path, engine='python'),
                # Try with auto delimiter detection
                lambda: pd.read_csv(file_path, sep=None, engine='python')
            ]
        
        df = None
        errors = []
        
        for i, attempt in enumerate(loading_attempts):
            try:
                logger.info(f"Attempt {i+1} to load dataset")
                df = attempt()
                # If we got here, loading succeeded
                logger.info(f"Successfully loaded dataset with attempt {i+1}")
                
                # Log the DataFrame info
                logger.info(f"DataFrame shape: {df.shape}")
                logger.info(f"DataFrame columns: {list(df.columns)}")
                logger.info(f"DataFrame sample:\n{df.head(5).to_string()}")
                
                break
            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Attempt {i+1} failed: {str(e)}")
                continue
        
        if df is None:
            raise ValueError(f"All loading attempts failed: {errors}")
            
        # Handle common issues
        if len(df.columns) == 1 and file_extension not in ['.xlsx', '.xls']:
            # Try different delimiter if only one column detected (for CSV only)
            logger.warning("Only one column detected, trying different delimiter")
            df = pd.read_csv(file_path, sep=None, engine='python')
            
        return df
    except Exception as e:
        logger.error(f"Error loading dataset: {str(e)}")
        raise ValueError(f"Error loading dataset: {e}")

def load_pdf_document(file_path: str, openai_api_key: str = None) -> Dict[str, Any]:
    """
    Extract text and metadata from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        openai_api_key: Optional OpenAI API key for enhanced summary generation
        
    Returns:
        Dictionary containing extracted text and metadata
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Extracting content from PDF: {file_path}")
    
    try:
        # Extract text from PDF
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Get basic metadata
            num_pages = len(pdf_reader.pages)
            
            # Extract text from all pages (with page limits for very large PDFs)
            max_pages_to_extract = min(50, num_pages)  # Limit to first 50 pages for very large PDFs
            
            # Extract text from each page
            full_text = ""
            extracted_pages = []
            
            for i in range(max_pages_to_extract):
                page = pdf_reader.pages[i]
                page_text = page.extract_text()
                if page_text:
                    extracted_pages.append(page_text)
                    full_text += page_text + "\n\n"
            
            logger.info(f"Extracted {len(full_text)} characters of text from {max_pages_to_extract} pages")
            
            # Create a structured representation
            pdf_data = {
                "type": "pdf",
                "num_pages": num_pages,
                "pages_extracted": max_pages_to_extract,
                "full_text": full_text,
                "page_texts": extracted_pages,
                "file_path": file_path,
                "file_name": os.path.basename(file_path)
            }
            
            # If the PDF has metadata, extract it
            if hasattr(pdf_reader, 'metadata') and pdf_reader.metadata:
                metadata = pdf_reader.metadata
                pdf_data["title"] = metadata.get('/Title', '')
                pdf_data["author"] = metadata.get('/Author', '')
                pdf_data["subject"] = metadata.get('/Subject', '')
                pdf_data["creator"] = metadata.get('/Creator', '')
            
            # Create a basic text sample (will be used as fallback)
            text_sample = full_text[:10000]  # First 10K characters
            pdf_data["text_sample"] = text_sample
            
            # Create a simple dataframe with the text for compatibility
            text_df = pd.DataFrame({
                "page_number": range(1, len(extracted_pages) + 1),
                "text": extracted_pages
            })
            pdf_data["dataframe"] = text_df
            
            # Generate enhanced summary if OpenAI API key is provided
            if openai_api_key:
                logger.info("Generating enhanced summary with OpenAI API")
                try:
                    # Direct implementation of summary generation
                    client = openai.OpenAI(api_key=openai_api_key)
                    
                    # Create a simplified prompt for testing
                    prompt = f"""
Create a summary of this PDF document:
Title: {pdf_data.get('title', pdf_data.get('file_name', 'Unknown'))}
Pages: {num_pages}

Text sample:
{full_text[:5000]}

Please provide:
1. A concise summary (3-5 sentences)
2. 3-5 key points from the document

Format as JSON with fields: "summary" and "key_points" (array)
"""
                    
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are a document analysis expert."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.3
                    )
                    
                    summary_content = response.choices[0].message.content
                    summary_data = json.loads(summary_content)
                    
                    # Add the summary data to the PDF data
                    pdf_data["enhanced_summary"] = summary_data.get("summary", "")
                    pdf_data["key_points"] = summary_data.get("key_points", [])
                    
                    # Create a simplified enhanced text sample
                    enhanced_text_sample = f"""
SUMMARY: {summary_data.get('summary', '')}

KEY POINTS:
{chr(10).join(['- ' + point for point in summary_data.get('key_points', [])])}
"""
                    pdf_data["enhanced_text_sample"] = enhanced_text_sample
                    logger.info("Successfully generated enhanced summary")
                    
                except Exception as e:
                    logger.error(f"Error in OpenAI API call: {str(e)}")
                    # If there's an error, we'll still have the original text sample
                    pdf_data["enhanced_summary"] = f"Summary generation failed: {str(e)}"
            
            logger.info(f"Successfully extracted content from PDF")
            return pdf_data
            
    except Exception as e:
        logger.error(f"Error extracting PDF content: {str(e)}")
        raise ValueError(f"Error extracting PDF content: {e}")

def assess_dataset_relevance(
    df_or_pdf: Union[pd.DataFrame, Dict[str, Any]], 
    query: str, 
    dataset_metadata: Dict[str, Any],
    openai_api_key: str,
    relevance_threshold: float = 0.7
) -> Tuple[bool, float, str]:
    """
    Assess if a dataset or PDF document is relevant to the user's query using OpenAI.
    
    Args:
        df_or_pdf: The dataset as a pandas DataFrame or PDF data as a dictionary
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description, etc.)
        openai_api_key: OpenAI API key
        relevance_threshold: Threshold for considering a dataset relevant (0-1)
        
    Returns:
        Tuple of (is_relevant, relevance_score, reasoning)
    """
    # Get dataset information
    title = dataset_metadata.get('title', 'Unknown')
    description = dataset_metadata.get('description', '')
    
    # Check if we're dealing with a PDF
    is_pdf = isinstance(df_or_pdf, dict) and df_or_pdf.get('type') == 'pdf'
    
    if is_pdf:
        # Handle PDF document
        pdf_data = df_or_pdf
        
        # Get PDF metadata
        num_pages = pdf_data.get('num_pages', 0)
        pdf_title = pdf_data.get('title', '')
        if pdf_title and pdf_title != title:
            title = f"{title} (PDF title: {pdf_title})"
        
        # Use enhanced summary if available, otherwise fall back to text sample
        if "enhanced_text_sample" in pdf_data:
            text_for_analysis = pdf_data.get('enhanced_text_sample')
        else:
            text_for_analysis = pdf_data.get('text_sample', '')[:2000]  # Limit to 2000 chars for the prompt
        
        # Search for key terms from the query in the PDF text
        key_terms = query.lower().split()
        term_presence = {}
        
        for term in key_terms:
            if len(term) > 3:  # Only search for meaningful terms
                found = term.lower() in pdf_data.get('full_text', '').lower()
                term_presence[term] = found
        
        # Create prompt for OpenAI
        prompt = f"""
You are assessing whether a PDF document is relevant to a user's query.

USER QUERY: "{query}"

DOCUMENT INFORMATION:
Title: {title}
Description: {description}
Number of Pages: {num_pages}

DOCUMENT CONTENT SUMMARY:
{text_for_analysis}

KEY TERM SEARCH RESULTS:
The following key terms from the query were searched in the document:
{chr(10).join([f"- '{term}': {'Found' if found else 'Not found'}" for term, found in term_presence.items()])}

ASSESSMENT GUIDELINES:
1. PRIORITIZE the document's title, description, and content when determining relevance
2. Consider that the summary may not represent all content in the document
3. If the document contains information that could plausibly relate to the query, consider it potentially relevant
4. Consider that specific categories or terms might be present in the full document even if not in the summary

Please provide:
1. A relevance score from 0.0 to 1.0, where:
   - 0.0-0.3: Not relevant
   - 0.4-0.6: Somewhat relevant
   - 0.7-1.0: Highly relevant
2. A brief explanation of your reasoning (2-3 sentences)

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
"""
    else:
        # Original code for DataFrame handling
        # Get column information
        columns = list(df_or_pdf.columns)
        column_info = []
        for col in columns:
            dtype = str(df_or_pdf[col].dtype)
            sample_values = df_or_pdf[col].dropna().head(3).tolist()
            column_info.append(f"- {col} ({dtype}): {sample_values}")
        
        # Get sample rows
        sample_rows = df_or_pdf.head(5).to_string(index=False)
        
        # Search for key terms from the query in the entire dataset
        # Extract key terms from query
        key_terms = query.lower().split()
        
        # Search for these terms in the dataset
        term_presence = {}
        for term in key_terms:
            if len(term) > 3:  # Only search for meaningful terms (longer than 3 chars)
                # Check if term appears in any string column
                found = False
                for col in df_or_pdf.select_dtypes(include=['object']).columns:
                    # Sample a subset of the data to avoid performance issues with large datasets
                    sample_size = min(1000, len(df_or_pdf))
                    if df_or_pdf[col].sample(sample_size).astype(str).str.contains(term, case=False).any():
                        found = True
                        break
                term_presence[term] = found
        
        # Create prompt for OpenAI
        prompt = f"""
You are assessing whether a dataset is relevant to a user's query.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {title}
Description: {description}

DATASET STRUCTURE:
Columns: {', '.join(columns)}

Column Details:
{chr(10).join(column_info)}

Sample Data (first 5 rows):
{sample_rows}

KEY TERM SEARCH RESULTS:
The following key terms from the query were searched in the dataset:
{chr(10).join([f"- '{term}': {'Found' if found else 'Not found'}" for term, found in term_presence.items()])}

ASSESSMENT GUIDELINES:
1. PRIORITIZE the dataset's title, description, and column names when determining relevance
2. Consider that the sample rows may not represent all data in the dataset
3. If the dataset contains columns that could plausibly contain information related to the query, consider it potentially relevant
4. Consider that specific categories or terms might be present in the full dataset even if not in the sample

Please provide:
1. A relevance score from 0.0 to 1.0, where:
   - 0.0-0.3: Not relevant
   - 0.4-0.6: Somewhat relevant
   - 0.7-1.0: Highly relevant
2. A brief explanation of your reasoning (2-3 sentences)

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
"""

    # Call OpenAI API
    client = openai.OpenAI(api_key=openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a data analyst who specializes in evaluating dataset relevance. Be concise and accurate."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    
    # Parse the response
    response_text = response.choices[0].message.content
    
    # Extract score and reasoning
    score_match = re.search(r'SCORE:\s*([\d.]+)', response_text)
    reasoning_match = re.search(r'REASONING:\s*(.*)', response_text, re.DOTALL)
    
    if score_match and reasoning_match:
        score = float(score_match.group(1))
        reasoning = reasoning_match.group(1).strip()
        is_relevant = score >= relevance_threshold
        return (is_relevant, score, reasoning)
    else:
        # Fallback if parsing fails
        return (False, 0.0, "Failed to parse relevance assessment")

def generate_pdf_summary(pdf_data: Dict[str, Any], openai_api_key: str) -> Dict[str, Any]:
    """
    Generate an enhanced summary of a PDF document using an LLM.
    
    Args:
        pdf_data: Dictionary containing PDF text and metadata
        openai_api_key: OpenAI API key
        
    Returns:
        Dictionary with summary, section titles, and key points
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Starting enhanced summary generation for PDF: {pdf_data.get('file_name', 'unknown')}")
    
    # Debug log to confirm we have an API key
    if openai_api_key:
        logger.info("OpenAI API key is provided")
    else:
        logger.warning("No OpenAI API key provided for summary generation")
        return pdf_data
    
    # Get the full text or a substantial portion for analysis
    full_text = pdf_data.get('full_text', '')
    logger.info(f"PDF text length: {len(full_text)} characters")
    
    # If the PDF is very large, use a representative sample
    # We'll take the beginning, some from the middle, and the end
    if len(full_text) > 15000:
        text_beginning = full_text[:5000]
        middle_start = max(5000, len(full_text) // 2 - 2500)
        text_middle = full_text[middle_start:middle_start + 5000]
        text_end = full_text[-5000:] if len(full_text) > 5000 else ""
        analysis_text = f"{text_beginning}\n\n[...]\n\n{text_middle}\n\n[...]\n\n{text_end}"
        logger.info("Using sampled text from beginning, middle, and end for analysis")
    else:
        analysis_text = full_text
        logger.info("Using full text for analysis")
    
    # Create prompt for OpenAI
    prompt = f"""
You are analyzing a PDF document to create an enhanced summary. The document may be truncated.

DOCUMENT TITLE: {pdf_data.get('title', pdf_data.get('file_name', 'Unknown'))}
DOCUMENT LENGTH: {pdf_data.get('num_pages', 0)} pages

DOCUMENT TEXT SAMPLE:
{analysis_text}

Please provide:
1. A concise summary (3-5 sentences) of the document's main content
2. A list of apparent section titles or major topics covered
3. 5-7 key points or findings from the document
4. Any notable dates, statistics, or entities mentioned

Format your response as JSON with the following structure:
{{
  "summary": "Concise summary here",
  "section_titles": ["Section 1", "Section 2", ...],
  "key_points": ["Key point 1", "Key point 2", ...],
  "notable_elements": ["Notable date/statistic/entity 1", ...]
}}
"""

    try:
        logger.info("Calling OpenAI API for summary generation")
        # Call OpenAI API
        client = openai.OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a document analysis expert specializing in creating concise, accurate summaries of PDF documents."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        logger.info("Received response from OpenAI API")
        
        # Parse the response
        summary_content = response.choices[0].message.content
        logger.info(f"Response content length: {len(summary_content)} characters")
        
        try:
            summary_data = json.loads(summary_content)
            logger.info("Successfully parsed JSON response")
            
            # Add the summary data to the PDF data
            pdf_data["enhanced_summary"] = summary_data.get("summary", "")
            pdf_data["section_titles"] = summary_data.get("section_titles", [])
            pdf_data["key_points"] = summary_data.get("key_points", [])
            pdf_data["notable_elements"] = summary_data.get("notable_elements", [])
            
            # Create a more informative text sample that combines the summary and key points
            enhanced_text_sample = f"""
SUMMARY: {summary_data.get('summary', '')}

SECTIONS: {', '.join(summary_data.get('section_titles', [])[:10])}

KEY POINTS:
{chr(10).join(['- ' + point for point in summary_data.get('key_points', [])[:5]])}

NOTABLE ELEMENTS:
{chr(10).join(['- ' + element for element in summary_data.get('notable_elements', [])[:5]])}
"""
            pdf_data["enhanced_text_sample"] = enhanced_text_sample
            
            logger.info("Successfully generated enhanced summary for PDF")
            return pdf_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response content: {summary_content[:500]}...")
            # If JSON parsing fails, we'll still have the original text sample
            pdf_data["enhanced_summary"] = "Summary generation failed - JSON parsing error"
            pdf_data["enhanced_text_sample"] = pdf_data.get("text_sample", "")
            return pdf_data
        
    except Exception as e:
        logger.error(f"Error generating enhanced PDF summary: {str(e)}")
        # If the summary generation fails, we'll still have the original text sample
        pdf_data["enhanced_summary"] = f"Summary generation failed: {str(e)}"
        pdf_data["enhanced_text_sample"] = pdf_data.get("text_sample", "")
        return pdf_data