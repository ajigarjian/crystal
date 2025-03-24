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
import xml.etree.ElementTree as ET
from collections import defaultdict
from pandas import json_normalize

from factchecker.utils.openai_client import chat_completion

"""
This module handles loading and processing datasets for the factchecker application.
It provides utilities for loading datasets from various file formats, assessing their
relevance to user queries, and preparing them for further analysis.
"""

def load_datafile(file_path: str) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Load a data file (CSV, Excel, PDF, XML, or JSON) with appropriate error handling.
    
    Args:
        file_path: Path to the data file
        
    Returns:
        For CSV/Excel/XML/JSON: Pandas DataFrame containing the dataset
        For PDF: Dictionary with extracted text and metadata
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading dataset from {file_path}")
    
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # Handle PDF files
    if file_extension == '.pdf':
        logger.info(f"Detected PDF file: {file_path}")
        return load_pdf_document(file_path)
    
    # Handle XML files
    elif file_extension == '.xml':
        logger.info(f"Detected XML file: {file_path}")
        return load_xml_document(file_path)
    
    # Handle JSON files
    elif file_extension == '.json':
        logger.info(f"Detected JSON file: {file_path}")
        return load_json_document(file_path)
    
    try:
        # Handle Excel files - ENHANCED
        if file_extension in ['.xlsx', '.xls']:
            logger.info(f"Detected Excel file: {file_path}")
            loading_attempts = [
                # Standard loading
                lambda: pd.read_excel(file_path),
                # Try with explicit openpyxl engine
                lambda: pd.read_excel(file_path, engine='openpyxl'),
                # Try with xlrd engine for older .xls files
                lambda: pd.read_excel(file_path, engine='xlrd'),
                # Try with specific sheet (first sheet)
                lambda: pd.read_excel(file_path, sheet_name=0),
                # Try with skiprows to handle headers
                lambda: pd.read_excel(file_path, skiprows=1),
                # Try with skiprows and specific sheet
                lambda: pd.read_excel(file_path, sheet_name=0, skiprows=1),
                # Try with different data_only option for openpyxl
                lambda: pd.read_excel(file_path, engine='openpyxl', storage_options={'data_only': True}),
                # Try with ODF engine for other formats
                lambda: pd.read_excel(file_path, engine='odf') if pd.__version__ >= '1.3.0' else pd.read_excel(file_path),
                # Try with all sheets at once
                lambda: pd.read_excel(file_path, sheet_name=None),
                # Try with lower memory footprint
                lambda: pd.read_excel(file_path, memory_map=True)
            ]
        # Handle CSV files
        else:
            logger.info(f"Detected CSV file: {file_path}")
            loading_attempts = [
                # Standard loading with comma
                lambda: pd.read_csv(file_path, sep=','),
                # Try with tab delimiter
                lambda: pd.read_csv(file_path, sep='\t'),
                # Try with semicolon (common in European files)
                lambda: pd.read_csv(file_path, sep=';'),
                # Try with pipe
                lambda: pd.read_csv(file_path, sep='|'),
                # Try with comma and different encoding
                lambda: pd.read_csv(file_path, sep=',', encoding='latin1'),
                # Try with comma and skip bad lines
                lambda: pd.read_csv(file_path, sep=',', on_bad_lines='skip'),
                # Try with comma, skip bad lines, and different encoding
                lambda: pd.read_csv(file_path, sep=',', on_bad_lines='skip', encoding='latin1'),
                # Try reading the file with explicit delimiter and maximum error tolerance
                lambda: pd.read_csv(file_path, sep=',', on_bad_lines='skip', 
                                  encoding='latin1', quoting=3, error_bad_lines=False),  # QUOTE_NONE
                # Try with skiprows for files with metadata headers (like EPA files)
                lambda: pd.read_csv(file_path, sep=',', skiprows=10, on_bad_lines='skip'),
                # Last resort - read as fixed width
                lambda: pd.read_fwf(file_path, on_bad_lines='skip')
            ]
        
        df = None
        errors = []
        
        for i, attempt in enumerate(loading_attempts):
            try:
                logger.info(f"Attempt {i+1} to load dataset")
                df = attempt()
                
                # Check if we got a valid DataFrame (not empty or too small)
                if isinstance(df, pd.DataFrame) and not df.empty and len(df.columns) > 1:
                    logger.info(f"Successfully loaded dataset with attempt {i+1}")
                    
                    # Log the DataFrame info
                    logger.info(f"DataFrame shape: {df.shape}")
                    logger.info(f"DataFrame columns: {list(df.columns)}")
                    logger.info(f"DataFrame sample:\n{df.head(5).to_string()}")
                    
                    break
                elif isinstance(df, dict) and sheet_name is None:
                    # If we got a dict of DataFrames (multiple sheets)
                    logger.info(f"Got multiple sheets: {list(df.keys())}")
                    # Take the largest sheet
                    largest_sheet = max(df.items(), key=lambda x: (0 if x[1].empty else len(x[1])))[0]
                    logger.info(f"Using largest sheet: {largest_sheet}")
                    df = df[largest_sheet]
                    
                    if not df.empty and len(df.columns) > 1:
                        logger.info(f"Successfully extracted sheet with shape: {df.shape}")
                        break
                    else:
                        logger.warning(f"Largest sheet is empty or has only one column, continuing search")
                        df = None
                else:
                    logger.warning(f"Attempt {i+1} produced invalid DataFrame, continuing search")
                    df = None
                    
            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Attempt {i+1} failed: {str(e)}")
                continue
        
        # If all standard attempts failed, try binary reading approaches for Excel
        if df is None and file_extension in ['.xlsx', '.xls']:
            logger.info("Trying binary Excel reading approaches")
            try:
                # Try using xlrd for .xls with binary mode
                if file_extension == '.xls':
                    import xlrd
                    logger.info("Attempting xlrd with binary mode")
                    wb = xlrd.open_workbook(file_path, logfile=open(os.devnull, 'w'))
                    sheet = wb.sheet_by_index(0)
                    
                    # Extract headers from first row
                    headers = [str(cell.value) for cell in sheet.row(0)]
                    
                    # Extract data from remaining rows
                    data = []
                    for row_idx in range(1, sheet.nrows):
                        row_data = [cell.value for cell in sheet.row(row_idx)]
                        data.append(row_data)
                    
                    # Create DataFrame
                    df = pd.DataFrame(data, columns=headers)
                    logger.info(f"Successfully loaded with binary xlrd: {df.shape}")
                
                # Try using openpyxl for .xlsx with binary mode
                elif file_extension == '.xlsx':
                    import openpyxl
                    logger.info("Attempting openpyxl with binary mode")
                    
                    # Load workbook with minimal features
                    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True, keep_links=False)
                    
                    # Get the first sheet
                    sheet = wb.active
                    
                    # Convert to DataFrame
                    data = []
                    for row in sheet.iter_rows(values_only=True):
                        data.append(row)
                    
                    # Separate headers and data if we have rows
                    if data:
                        headers = data[0]
                        data_rows = data[1:]
                        df = pd.DataFrame(data_rows, columns=headers)
                        logger.info(f"Successfully loaded with binary openpyxl: {df.shape}")
            
            except Exception as e:
                logger.warning(f"Binary Excel reading approach failed: {str(e)}")
        
        # If still no DataFrame, create placeholder
        if df is None:
            logger.warning("All parsing attempts failed, creating placeholder DataFrame")
            try:
                # Create a simple single-row DataFrame with file info
                df = pd.DataFrame({
                    'file_path': [file_path],
                    'parsing_status': ['failed - could not parse file'],
                    'file_name': [os.path.basename(file_path)]
                })
                logger.info("Created placeholder DataFrame for failed file")
                
                # Try to include a sample of the file content if possible
                try:
                    # Use binary mode for reading which works for both text and binary files
                    with open(file_path, 'rb') as f:
                        binary_content = f.read(1000)
                        
                        # Try to decode as text if possible
                        try:
                            sample_content = binary_content.decode('utf-8', errors='replace')
                        except:
                            # If decoding fails completely, provide a hex dump
                            sample_content = f"Binary content (hex): {binary_content.hex()[:100]}..."
                        
                        df['content_sample'] = [sample_content]
                except Exception as e:
                    logger.warning(f"Could not read file content: {str(e)}")
                    df['content_sample'] = ["Could not read file content"]
                
                return df
            except Exception as e:
                logger.error(f"Failed to create placeholder DataFrame: {str(e)}")
                raise ValueError(f"Error loading dataset - please try a different file")
            
        # Handle common issues
        if len(df.columns) == 1 and file_extension not in ['.xlsx', '.xls'] and 'parsing_status' not in df.columns:
            # Only try again if this isn't our placeholder DataFrame
            logger.warning("Only one column detected, trying different delimiter")
            try:
                df = pd.read_csv(file_path, sep=None, engine='python')
            except Exception as e:
                logger.warning(f"Final attempt with auto-delimiter failed: {str(e)}")
                # Don't raise - return what we have
        
        return df
    except Exception as e:
        logger.error(f"Error loading dataset: {str(e)}")
        raise ValueError(f"Error loading dataset: {e}")

def load_pdf_document(file_path: str) -> Dict[str, Any]:
    """
    Extract text and metadata from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        
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
            if os.environ.get("OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY"):
                logger.info("Generating enhanced summary with OpenAI API")
                try:                    
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
                    
                    # Call OpenAI API for summary
                    response = chat_completion(
                    prompt,
                    system_message="You are a document analysis expert.",
                    temperature=0.3,
                    response_format={"type": "json_object"}
                    )
                    
                    summary_content = response
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

def load_xml_document(file_path: str) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Load an XML file and convert it to a pandas DataFrame using ElementTree.
    Uses a multi-strategy approach to handle different XML structures.
    
    Args:
        file_path: Path to the XML file
        
    Returns:
        DataFrame containing the XML data or a dictionary with XML metadata
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading XML file: {file_path}")
    
    try:
        # First try pandas.read_xml with default settings as it's simplest
        try:
            logger.info("Attempting to parse XML with pandas.read_xml")
            df = pd.read_xml(file_path)
            
            # If we got a DataFrame with data, return it
            if not df.empty and len(df.columns) > 1:
                logger.info(f"Successfully parsed XML with pandas.read_xml. Shape: {df.shape}")
                return df
            else:
                logger.info("pandas.read_xml returned empty or single-column DataFrame. Will try ElementTree.")
        except Exception as e:
            logger.warning(f"pandas.read_xml parsing failed: {str(e)}")
        
        # Parse XML using ElementTree
        logger.info("Parsing XML with ElementTree")
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Strategy 1: Look for repeating elements that could form rows
        logger.info("Strategy 1: Looking for repeating elements")
        repeating_elements = find_repeating_elements(root)
        
        if repeating_elements:
            # Get the most common repeating element (likely to be rows)
            most_common_element = max(repeating_elements.items(), key=lambda x: x[1])[0]
            logger.info(f"Found repeating element: {most_common_element}")
            
            # Extract data from repeating elements
            rows = []
            for elem in root.findall(f".//{most_common_element}"):
                row_data = {}
                
                # Extract attributes
                for key, value in elem.attrib.items():
                    row_data[key] = value
                
                # Extract child elements
                for child in elem:
                    # Use tag as column name
                    if child.text and child.text.strip():
                        row_data[child.tag] = child.text.strip()
                    # If child has children, concatenate their text
                    elif len(list(child)) > 0:
                        combined_text = " ".join([subchild.text for subchild in child if subchild.text and subchild.text.strip()])
                        if combined_text:
                            row_data[child.tag] = combined_text
                    # Include attributes if no text
                    elif child.attrib:
                        for attr_key, attr_val in child.attrib.items():
                            row_data[f"{child.tag}_{attr_key}"] = attr_val
                
                if row_data:  # Only add non-empty rows
                    rows.append(row_data)
            
            if rows:
                df = pd.DataFrame(rows)
                logger.info(f"Successfully created DataFrame from repeating elements. Shape: {df.shape}")
                return df
        
        # Strategy 2: Flatten the XML structure
        logger.info("Strategy 2: Flattening XML structure")
        flattened_data = []
        
        # For each direct child of root that might represent a record
        for child in root:
            record = flatten_element(child)
            if record:
                flattened_data.append(record)
        
        if flattened_data:
            df = pd.DataFrame(flattened_data)
            logger.info(f"Successfully created DataFrame from flattened structure. Shape: {df.shape}")
            return df
        
        # Strategy 3: Create a single row with all data (for very flat XMLs)
        logger.info("Strategy 3: Creating single row with all data")
        all_data = flatten_element(root)
        
        if all_data:
            df = pd.DataFrame([all_data])
            logger.info(f"Created single-row DataFrame. Shape: {df.shape}")
            return df
        
        # If all strategies fail, return XML metadata
        logger.warning("All XML parsing strategies failed. Returning XML metadata.")
        
        # Get a sample of the XML content for reference
        with open(file_path, 'r', encoding='utf-8') as f:
            xml_sample = f.read(5000)  # First 5000 chars
        
        return {
            "type": "xml",
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "root_tag": root.tag,
            "xml_sample": xml_sample,
            "parsing_error": "Could not convert XML to DataFrame"
        }
    
    except Exception as e:
        logger.error(f"Error loading XML file: {str(e)}")
        # Return a minimal DataFrame with error information
        return pd.DataFrame({
            "error": [f"Failed to parse XML: {str(e)}"],
            "file_path": [file_path]
        })

def find_repeating_elements(root):
    """
    Find elements that repeat in the XML, which likely represent rows in a table.
    
    Args:
        root: Root element of the XML tree
        
    Returns:
        Dictionary mapping element tags to their frequency
    """
    element_counts = defaultdict(int)
    
    # Count occurrences of each element tag
    for elem in root.iter():
        element_counts[elem.tag] += 1
    
    # Filter to elements that appear multiple times (potential rows)
    repeating_elements = {tag: count for tag, count in element_counts.items() 
                         if count > 1 and tag != root.tag}
    
    return repeating_elements

def flatten_element(element, prefix=''):
    """
    Recursively flatten an XML element and its children into a dictionary.
    
    Args:
        element: XML element to flatten
        prefix: Prefix for nested element names
        
    Returns:
        Dictionary with flattened element data
    """
    result = {}
    
    # Add element attributes
    for key, value in element.attrib.items():
        column_name = f"{prefix}{element.tag}_{key}" if prefix else f"{element.tag}_{key}"
        result[column_name] = value
    
    # Add element text if not empty
    if element.text and element.text.strip():
        column_name = f"{prefix}{element.tag}" if prefix else element.tag
        result[column_name] = element.text.strip()
    
    # Process child elements
    for child in element:
        # Create new prefix for nested elements
        new_prefix = f"{prefix}{element.tag}_" if prefix else f"{element.tag}_"
        
        # Recursively process child element
        child_data = flatten_element(child, new_prefix)
        
        # Add child data to result
        result.update(child_data)
    
    return result

def assess_datafile_relevance(
    df_or_pdf: Union[pd.DataFrame, Dict[str, Any]], 
    query: str, 
    dataset_metadata: Dict[str, Any],
    relevance_threshold: float = 0.7
) -> Tuple[bool, float, str]:
    """
    Assess if a datafile (CSV/Excel) or PDF document is relevant to the user's query using OpenAI.
    
    Args:
        df_or_pdf: The datafile content as a pandas DataFrame or PDF data as a dictionary
        query: The original user query
        dataset_metadata: Metadata about the dataset and datafile
        relevance_threshold: Threshold for considering a datafile relevant (0-1)
        
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


    
    system_message = "You are a data analyst who specializes in evaluating dataset relevance. Be concise and accurate."
    
    response_text = chat_completion(
        prompt=prompt,
        system_message=system_message,
        temperature=0.2
    )
    
    # Parse the response
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

def generate_pdf_summary(pdf_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an enhanced summary of a PDF document using an LLM.
    
    Args:
        pdf_data: Dictionary containing PDF text and metadata
        
    Returns:
        Dictionary with summary, section titles, and key points
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Starting enhanced summary generation for PDF: {pdf_data.get('file_name', 'unknown')}")
    
    # Debug log to confirm we have an API key
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY"):
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

        response = chat_completion(
        prompt,
        system_message="You are a document analysis expert specializing in creating concise, accurate summaries of PDF documents.",
        temperature=0.3
        )
        
        logger.info("Received response from OpenAI API")
        
        # Parse the response
        summary_content = response
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

def load_json_document(file_path: str) -> pd.DataFrame:
    """
    Load a JSON file and convert it to a pandas DataFrame.
    Uses multiple strategies to handle different JSON structures.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        DataFrame containing the JSON data
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading JSON file: {file_path}")
    
    try:
        # Read the JSON file
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Strategy 1: If JSON is already a list of records (most common case)
        if isinstance(json_data, list) and len(json_data) > 0 and isinstance(json_data[0], dict):
            logger.info("JSON is a list of records, converting directly to DataFrame")
            return pd.DataFrame(json_data)
        
        # Strategy 2: If JSON is a dict with a key containing a list of records
        elif isinstance(json_data, dict):
            # Look for array fields that might contain the data
            potential_data_keys = []
            
            for key, value in json_data.items():
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    potential_data_keys.append((key, len(value)))
            
            # If we found potential data arrays, use the largest one
            if potential_data_keys:
                # Sort by array size (descending)
                potential_data_keys.sort(key=lambda x: x[1], reverse=True)
                best_key = potential_data_keys[0][0]
                
                logger.info(f"Using '{best_key}' field which contains a list of {potential_data_keys[0][1]} records")
                return pd.DataFrame(json_data[best_key])
            
            # Strategy 3: If JSON is a nested structure, try to flatten it
            logger.info("Attempting to flatten nested JSON structure")
            try:
                # Use json_normalize to flatten nested structures
                df = json_normalize(json_data)
                
                # If we got a single row with nested data, try to expand it
                if len(df.columns) > 0 and len(df) == 1:
                    for col in df.columns:
                        # If column contains lists of dicts, expand it
                        if isinstance(df[col].iloc[0], list) and len(df[col].iloc[0]) > 0 and isinstance(df[col].iloc[0][0], dict):
                            logger.info(f"Expanding nested array in column '{col}'")
                            nested_df = pd.DataFrame(df[col].iloc[0])
                            # Add any other top-level columns
                            for other_col in df.columns:
                                if other_col != col:
                                    nested_df[other_col] = df[other_col].iloc[0]
                            return nested_df
                
                return df
            except Exception as e:
                logger.warning(f"Error flattening JSON: {e}")
            
            # Strategy 4: If all else fails, convert the dict to a single-row DataFrame
            logger.info("Converting JSON dict to single-row DataFrame")
            # Filter out nested structures that can't be directly converted
            flat_dict = {}
            for key, value in json_data.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    flat_dict[key] = value
                elif isinstance(value, list) and all(isinstance(x, (str, int, float, bool)) for x in value):
                    flat_dict[key] = str(value)  # Convert simple lists to strings
            
            return pd.DataFrame([flat_dict])
        
        # Strategy 5: If JSON is a scalar or empty, create a minimal DataFrame
        else:
            logger.warning("JSON has unexpected structure, creating minimal DataFrame")
            return pd.DataFrame({
                "value": [json_data] if not isinstance(json_data, list) else json_data,
                "file_path": [file_path]
            })
    
    except Exception as e:
        logger.error(f"Error loading JSON file: {str(e)}")
        # Return a minimal DataFrame with error information
        return pd.DataFrame({
            "error": [f"Failed to parse JSON: {str(e)}"],
            "file_path": [file_path]
        })