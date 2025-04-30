import traceback
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
import mimetypes
from collections import defaultdict
from pandas import json_normalize
import zipfile
import tarfile
import gzip
import bz2
import io # For handling in-memory streams
import tempfile # For temporary extraction if needed
import zipfile
import tarfile
import gzip
import bz2
import io # For handling in-memory streams
import tempfile # For temporary extraction if needed

logger = logging.getLogger("data_loading")

# Import magic library, handling potential ImportError
try:
    import magic
    magic_available = True
    # Create one instance for reuse if available
    magic_checker = magic.Magic(mime=True, uncompress=False) # mime=True gets MIME type, uncompress=False prevents magic from decompressing internally
    logger.info("python-magic library found and initialized.")
except ImportError:
    magic = None
    magic_available = False
    magic_checker = None
    logger.warning("python-magic library not found. Archive type detection will rely on standard library trials.")
except Exception as magic_init_e: # Catch other potential init errors
    magic = None
    magic_available = False
    magic_checker = None
    logger.error(f"Failed to initialize python-magic: {magic_init_e}. Archive type detection will rely on standard library trials.")

from factchecker.utils.openai_client import chat_completion

"""
This module handles loading and processing datasets for the factchecker application.
It provides utilities for loading datasets from various file formats, assessing their
relevance to user queries, and preparing them for further analysis.
"""


# --- Archive Handling Helper Functions ---

SUPPORTED_DATA_EXTENSIONS = ['.csv', '.xlsx', '.xls', '.json', '.xml']

def _find_first_data_file_in_archive(member_list: List[str]) -> Optional[str]:
    """Finds the first file in a list of archive members with a supported data extension."""
    for member_name in member_list:
        # Ignore directory entries and hidden files/metadata (simple heuristic)
        if not member_name.endswith('/') and not os.path.basename(member_name).startswith('.'):
            ext = os.path.splitext(member_name)[1].lower()
            if ext in SUPPORTED_DATA_EXTENSIONS:
                logger.info(f"Found potential data file in archive: {member_name}")
                return member_name
    logger.info("No file with a directly supported data extension found in archive member list.")
    return None

def _load_archived_file(
    archive_type: str,
    file_path: str,
    member_to_extract: Optional[str] = None
) -> Union[pd.DataFrame, Dict[str, Any], None]:
    """
    Loads data from a specific member within an archive (ZIP, TAR)
    or decompresses a single file archive (GZIP, BZ2) and attempts to load it.

    Args:
        archive_type: 'zip', 'tar', 'gzip', 'bz2'
        file_path: Path to the original archive file.
        member_to_extract: Name of the member file inside ZIP/TAR to load (optional).
                           If None for GZIP/BZ2, assumes the whole decompressed stream is the data.

    Returns: Loaded DataFrame/Dict or None if loading fails.
    """
    logger.info(f"Handling archive type '{archive_type}' for file: {file_path}")
    temp_dir = None
    extracted_path = None
    content_stream = None

    try:
        if archive_type == 'zip':
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                members = zip_ref.namelist()
                if member_to_extract is None:
                    member_to_extract = _find_first_data_file_in_archive(members)

                if member_to_extract:
                    logger.info(f"Attempting to load member '{member_to_extract}' from ZIP.")
                    # Extract to memory or temp file (using stream is often better)
                    with zip_ref.open(member_to_extract, 'r') as member_file:
                        # We need load_datafile to handle streams, or save temporarily
                        # Option 1: Save to temp file (simpler integration for now)
                        temp_dir = tempfile.TemporaryDirectory()
                        extracted_path = os.path.join(temp_dir.name, os.path.basename(member_to_extract))
                        with open(extracted_path, 'wb') as temp_f:
                            temp_f.write(member_file.read())
                        logger.info(f"Extracted ZIP member to temporary file: {extracted_path}")
                        # Recursively call load_datafile on the extracted file
                        return load_datafile(extracted_path)
                else:
                    logger.warning(f"Could not find a supported data file within ZIP: {file_path}")
                    return None

        elif archive_type == 'tar':
             # TarFile needs careful handling (e.g., tar bombs). Only extract known good extensions.
             # Determine compression type (gz, bz2, xz, or none)
             try:
                  tar_mode = 'r:*' # Auto-detect compression
                  with tarfile.open(file_path, mode=tar_mode) as tar_ref:
                       members = tar_ref.getnames()
                       if member_to_extract is None:
                           member_to_extract = _find_first_data_file_in_archive(members)

                       if member_to_extract:
                           logger.info(f"Attempting to load member '{member_to_extract}' from TAR.")
                           member_info = tar_ref.getmember(member_to_extract)
                           if member_info.isfile(): # Ensure it's a file
                                extracted_fileobj = tar_ref.extractfile(member_to_extract)
                                if extracted_fileobj:
                                     # Option 1: Save to temp file
                                     temp_dir = tempfile.TemporaryDirectory()
                                     extracted_path = os.path.join(temp_dir.name, os.path.basename(member_to_extract))
                                     with open(extracted_path, 'wb') as temp_f:
                                         temp_f.write(extracted_fileobj.read())
                                     logger.info(f"Extracted TAR member to temporary file: {extracted_path}")
                                     return load_datafile(extracted_path)
                                else:
                                     logger.error(f"Could not extract file object for member '{member_to_extract}' from TAR.")
                                     return None
                           else:
                                logger.warning(f"Selected member '{member_to_extract}' in TAR is not a file.")
                                return None
                       else:
                           logger.warning(f"Could not find a supported data file within TAR: {file_path}")
                           return None
             except tarfile.ReadError as tar_err:
                  logger.error(f"Failed to read TAR file {file_path}: {tar_err}")
                  return None

        elif archive_type in ['gzip', 'bz2']:
            open_func = gzip.open if archive_type == 'gzip' else bz2.open
            # Assume the decompressed stream *is* the data file. Need to guess its type.
            # Best guess is often based on the original filename before compression (if available).
            # Let's try saving to a temp file *without* the compression extension.
            original_filename_base = os.path.splitext(os.path.basename(file_path))[0] # e.g., 'data.csv' from 'data.csv.gz'
            # Ensure the base doesn't still end in .gz or .bz2 if double compressed? Maybe not needed.
            temp_dir = tempfile.TemporaryDirectory()
            # Use the base name for the temp file to help load_datafile infer type
            extracted_path = os.path.join(temp_dir.name, original_filename_base)

            logger.info(f"Decompressing {archive_type} file to temporary path: {extracted_path}")
            try:
                with open_func(file_path, 'rb') as compressed_file, open(extracted_path, 'wb') as temp_f:
                    # Read and write in chunks for large files
                    chunk_size = 8192
                    while True:
                        chunk = compressed_file.read(chunk_size)
                        if not chunk:
                            break
                        temp_f.write(chunk)

                # Now load the decompressed temp file
                logger.info(f"Attempting to load decompressed temporary file: {extracted_path}")
                return load_datafile(extracted_path) # Recursive call

            except (gzip.BadGzipFile, EOFError, OSError) as decomp_err: # Add relevant errors for bz2?
                 logger.error(f"Failed to decompress {archive_type} file {file_path}: {decomp_err}")
                 return None

        else:
            logger.error(f"Unsupported archive type '{archive_type}' passed to _load_archived_file.")
            return None

    except Exception as e:
        logger.error(f"Error handling archive '{file_path}' (type: {archive_type}): {str(e)}")
        logger.error(traceback.format_exc()) # Log full traceback for archive errors
        return None
    finally:
        # Clean up temporary directory if created
        if temp_dir:
            try:
                temp_dir.cleanup()
                logger.debug(f"Cleaned up temporary directory: {temp_dir.name}")
            except Exception as cleanup_e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir.name}: {cleanup_e}")


# --- Helper Functions for Loading Specific File Types ---

def _load_csv(file_path: str) -> pd.DataFrame:
    """Load a CSV file with robust encoding and delimiter detection."""
    logger.info(f"Attempting to load CSV file: {file_path}")
    
    encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
    delimiters = [',', '\t', ';', '|']
    errors = []
    df = None

    # Try common encodings and delimiters
    for enc in encodings:
        for delim in delimiters:
            try:
                logger.info(f"Trying encoding: {enc}, delimiter: '{delim}'")
                df = pd.read_csv(file_path, sep=delim, encoding=enc, on_bad_lines='warn', low_memory=False)
                if df is not None and len(df.columns) > 1:
                    logger.info(f"Successfully loaded CSV with encoding={enc}, delimiter='{delim}'. Shape: {df.shape}")
                    return df
                else:
                    logger.warning(f"Loaded CSV with encoding={enc}, delimiter='{delim}', but result is invalid (single column or empty).")
                    df = None # Reset df to continue trying other options
            except UnicodeDecodeError:
                logger.debug(f"Encoding {enc} failed for {file_path}")
                errors.append(f"Encoding {enc} failed.")
            except pd.errors.ParserError as e:
                 logger.warning(f"Parser error with encoding={enc}, delimiter='{delim}': {str(e)}")
                 errors.append(f"Parser error with encoding={enc}, delimiter='{delim}': {str(e)}")
            except Exception as e:
                errors.append(f"Unexpected error with encoding={enc}, delimiter='{delim}': {str(e)}")
                logger.warning(f"Unexpected error loading CSV with encoding={enc}, delimiter='{delim}': {str(e)}")

    # Fallback attempts if standard methods fail
    logger.info("Standard CSV loading failed, trying fallback methods.")
    fallback_attempts = [
        lambda: pd.read_csv(file_path, sep=None, engine='python', on_bad_lines='skip'), # Auto-detect delimiter
        lambda: pd.read_csv(file_path, sep=',', encoding='latin1', on_bad_lines='skip', quoting=3), # QUOTE_NONE, latin1
        lambda: pd.read_csv(file_path, sep=',', skiprows=10, on_bad_lines='skip'), # Skip potential headers
        lambda: pd.read_fwf(file_path, on_bad_lines='skip') # Fixed-width as last resort
    ]

    for i, attempt in enumerate(fallback_attempts):
        try:
            logger.info(f"Fallback attempt {i+1}")
            df = attempt()
            if df is not None and not df.empty:
                 # Check if it's likely just a single column misinterpreted
                 if len(df.columns) == 1 and df.iloc[:, 0].str.contains(r'[,;\t|]').any():
                     logger.warning("Fallback resulted in single column, likely delimiter issue remains.")
                     # Potentially could try splitting the single column here, but might get complex.
                     # For now, we accept it but log a warning.
                 else:
                    logger.info(f"Successfully loaded CSV with fallback attempt {i+1}. Shape: {df.shape}")
                    return df
            df = None # Reset if attempt resulted in empty df
        except Exception as e:
            errors.append(f"Fallback attempt {i+1} failed: {str(e)}")
            logger.warning(f"Fallback attempt {i+1} failed: {str(e)}")
            continue

    logger.error(f"All CSV loading attempts failed for {file_path}. Errors: {errors}")
    raise ValueError(f"Could not parse CSV file {os.path.basename(file_path)} after multiple attempts.")


def _load_excel(file_path: str) -> pd.DataFrame:
    """Load an Excel file, attempting to find the best sheet and header."""
    logger.info(f"Attempting to load Excel file: {file_path}")
    errors = []
    df = None
    
    # Try different engines first, as sheet/header logic depends on successful opening
    engines = ['openpyxl', 'xlrd', None] # None lets pandas choose
    
    for engine in engines:
        logger.info(f"Trying Excel engine: {engine if engine else 'default'}")
        try:
            excel_file = pd.ExcelFile(file_path, engine=engine)
            sheet_names = excel_file.sheet_names
            logger.info(f"Found sheets: {sheet_names} using engine: {engine}")

            best_sheet_name = None
            potential_sheets = []

            # Heuristic to find the best sheet: prioritize common names, then size
            common_data_names = ['data', 'sheet1', 'results', 'summary']
            
            # 1. Check for common names and basic structure
            for sheet_name in sheet_names:
                 try:
                     # Read a few rows to check for content
                     sample_df = pd.read_excel(excel_file, sheet_name=sheet_name, nrows=5, header=None)
                     if not sample_df.empty and sample_df.shape[1] > 1: # Has multiple columns
                        has_common_name = any(common_name in sheet_name.lower() for common_name in common_data_names)
                        potential_sheets.append({'name': sheet_name, 'common': has_common_name, 'rows': sample_df.shape[0], 'cols': sample_df.shape[1]})
                 except Exception as e:
                     logger.warning(f"Could not sample sheet '{sheet_name}' with engine {engine}: {e}")
            
            if not potential_sheets:
                 logger.warning(f"No valid sheets found with data samples using engine {engine}.")
                 continue # Try next engine

            # Select the best candidate sheet
            # Prioritize sheets with common names, then largest number of columns in sample, then first sheet
            potential_sheets.sort(key=lambda x: (x['common'], x['cols'], -sheet_names.index(x['name'])), reverse=True)
            best_sheet_name = potential_sheets[0]['name']
            logger.info(f"Selected sheet '{best_sheet_name}' based on heuristics.")

            # Heuristic to detect header row
            header_row = 0
            try:
                # Read first few rows without assuming header
                inspect_df = pd.read_excel(excel_file, sheet_name=best_sheet_name, nrows=10, header=None)
                # Simple heuristic: if row 0 looks like headers (mostly strings, few NaNs compared to row 1)
                # More sophisticated logic could be added here (e.g., checking for merged cells, specific keywords)
                if len(inspect_df) > 1:
                     row0_is_str = inspect_df.iloc[0].apply(lambda x: isinstance(x, str)).mean() > 0.6
                     row1_is_str = inspect_df.iloc[1].apply(lambda x: isinstance(x, str)).mean() > 0.6
                     if row0_is_str and not row1_is_str: # If row 0 looks like text headers and row 1 less so
                         logger.info(f"Detected potential header in row 0 for sheet '{best_sheet_name}'.")
                         header_row = 0 # Standard header=0 is default anyway
                     else:
                         # Look for the first row with a decent number of non-null values as potential header
                         for i in range(min(5, len(inspect_df))):
                             if inspect_df.iloc[i].notna().sum() / inspect_df.shape[1] > 0.5:
                                 logger.info(f"Potential header found at row {i} for sheet '{best_sheet_name}'. Setting header={i}.")
                                 header_row = i
                                 break
                         else:
                             logger.info(f"No clear header detected in first 10 rows for sheet '{best_sheet_name}'. Assuming header=0.")
                             header_row = 0

            except Exception as e:
                logger.warning(f"Error during header detection for sheet '{best_sheet_name}': {e}. Assuming header=0.")
                header_row = 0

            # Attempt to load the selected sheet with detected header
            try:
                df = pd.read_excel(excel_file, sheet_name=best_sheet_name, header=header_row)
                if df is not None and not df.empty:
                    logger.info(f"Successfully loaded Excel sheet '{best_sheet_name}' with header={header_row}, engine={engine}. Shape: {df.shape}")
                    return df
                else:
                     logger.warning(f"Loaded sheet '{best_sheet_name}' (header={header_row}, engine={engine}) but it's empty.")
                     df = None # Reset df
            except Exception as e:
                 logger.warning(f"Failed to load sheet '{best_sheet_name}' (header={header_row}, engine={engine}): {e}")
                 errors.append(f"Engine {engine}, Sheet '{best_sheet_name}', Header {header_row}: {e}")
                 df = None # Ensure df is None if load fails

        except Exception as e:
            errors.append(f"Failed to open/process Excel file with engine {engine}: {str(e)}")
            logger.warning(f"Failed to open/process Excel file with engine {engine}: {str(e)}")
            # Continue to next engine

    # If all engines/sheets failed
    logger.error(f"All Excel loading attempts failed for {file_path}. Errors: {errors}")
    raise ValueError(f"Could not parse Excel file {os.path.basename(file_path)} after trying engines and sheets.")

# --- Existing PDF, XML, JSON Loaders (moved to helpers, kept internal logic mostly as is) ---

def _load_pdf(file_path: str) -> Dict[str, Any]:
    """Extract text and metadata from a PDF file, including enhanced summary."""
    logger = logging.getLogger("data_loading.pdf") # Specific logger
    logger.info(f"Extracting content from PDF: {file_path}")
    
    try:
        # Extract text from PDF
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Get basic metadata
            num_pages = len(pdf_reader.pages)
            logger.info(f"PDF has {num_pages} pages.")
            
            # Extract text from all pages (with page limits for very large PDFs)
            # Consider making max_pages configurable or removing limit if performance allows
            max_pages_to_extract = min(50, num_pages)
            if num_pages > max_pages_to_extract:
                 logger.warning(f"PDF has {num_pages} pages. Limiting text extraction to first {max_pages_to_extract} pages.")

            # Extract text from each page
            full_text = ""
            extracted_pages = []
            
            for i in range(max_pages_to_extract):
                try:
                    page = pdf_reader.pages[i]
                    page_text = page.extract_text()
                    if page_text:
                        extracted_pages.append(page_text)
                        full_text += page_text + "\n\n" # Add separator between pages
                except Exception as page_e:
                    logger.warning(f"Could not extract text from page {i+1}: {page_e}")
            
            logger.info(f"Extracted ~{len(full_text)} characters of text from {len(extracted_pages)} out of {max_pages_to_extract} attempted pages.")
            
            # Create a structured representation
            pdf_data = {
                "type": "pdf",
                "num_pages": num_pages,
                "pages_extracted": len(extracted_pages),
                "pages_attempted": max_pages_to_extract,
                "full_text": full_text,
                "page_texts": extracted_pages, # List of text per page
                "file_path": file_path,
                "file_name": os.path.basename(file_path)
            }
            
            # Extract standard PDF metadata if available
            try:
                if hasattr(pdf_reader, 'metadata') and pdf_reader.metadata:
                    metadata = pdf_reader.metadata
                    # Normalize metadata keys (remove leading '/') and handle potential None values
                    pdf_data["metadata"] = {k.lstrip('/'): v for k, v in metadata.items() if v is not None}
                    pdf_data["title"] = metadata.get('/Title', '')
                    pdf_data["author"] = metadata.get('/Author', '')
                    # Add more common fields if needed
            except Exception as meta_e:
                 logger.warning(f"Could not extract standard PDF metadata: {meta_e}")

            # Create a basic text sample (used for relevance if enhancement fails)
            text_sample = full_text[:10000]
            pdf_data["text_sample"] = text_sample
            
            # Create a simple dataframe view (optional, but useful for consistency)
            if extracted_pages:
                 text_df = pd.DataFrame({
                     "page_number": range(1, len(extracted_pages) + 1),
                     "text": extracted_pages
                 })
                 pdf_data["dataframe"] = text_df
            else:
                 pdf_data["dataframe"] = pd.DataFrame(columns=["page_number", "text"]) # Empty DF


            # ----- START: Existing PDF Summary Generation (Kept as per request) -----
            if os.environ.get("OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY"):
                logger.info("Attempting to generate enhanced summary with OpenAI API")
                try:
                    # Use the specific generate_pdf_summary function if defined later,
                    # or keep the inline logic here. Assuming inline for now.
                    # Simplified prompt from original code for context:
                    prompt = f"""
Create a summary of this PDF document:
Title: {pdf_data.get('title', pdf_data.get('file_name', 'Unknown'))}
Pages: {num_pages}

Text sample (first 5000 chars):
{full_text[:5000]}

Please provide:
1. A concise summary (3-5 sentences)
2. 3-5 key points from the document

Format as JSON with fields: "summary" and "key_points" (array)
"""
                    
                    response = chat_completion(
                        prompt,
                        system_message="You are a document analysis expert.",
                        temperature=0.3,
                        response_format={"type": "json_object"}
                    )
                    
                    summary_content = response
                    summary_data = json.loads(summary_content)
                    
                    pdf_data["enhanced_summary"] = summary_data.get("summary", "")
                    pdf_data["key_points"] = summary_data.get("key_points", [])
                    
                    enhanced_text_sample = f"""
SUMMARY: {summary_data.get('summary', '')}

KEY POINTS:
{chr(10).join(['- ' + point for point in summary_data.get('key_points', [])])}
"""
                    pdf_data["enhanced_text_sample"] = enhanced_text_sample
                    logger.info("Successfully generated enhanced summary")
                    
                except Exception as e:
                    logger.error(f"Error generating PDF summary via OpenAI: {str(e)}")
                    pdf_data["enhanced_summary"] = f"Summary generation failed: {str(e)}"
                    # Fallback: enhanced sample is just the normal sample
                    pdf_data["enhanced_text_sample"] = text_sample
            else:
                 logger.warning("No OpenAI API key found. Skipping enhanced PDF summary generation.")
                 # Ensure keys exist even if summary not generated
                 pdf_data["enhanced_summary"] = "Not Generated (No API Key)"
                 pdf_data["key_points"] = []
                 pdf_data["enhanced_text_sample"] = text_sample

            # ----- END: Existing PDF Summary Generation -----

            logger.info(f"Successfully extracted content from PDF: {file_path}")
            return pdf_data
            
    except PyPDF2.errors.PdfReadError as pdf_err:
         logger.error(f"Invalid or corrupted PDF file: {file_path}. Error: {pdf_err}")
         raise ValueError(f"Cannot read PDF file '{os.path.basename(file_path)}'. It might be corrupted or password-protected.")
    except Exception as e:
        logger.error(f"Error extracting PDF content from {file_path}: {str(e)}")
        raise ValueError(f"Error processing PDF file {os.path.basename(file_path)}: {e}")


def _load_xml(file_path: str) -> Union[pd.DataFrame, Dict[str, Any]]:
    """Load an XML file into a DataFrame using multiple strategies."""
    logger = logging.getLogger("data_loading.xml")
    logger.info(f"Loading XML file: {file_path}")
    
    # Strategy 1: Try pandas.read_xml (often works for table-like XML)
    try:
        logger.info("Attempting to parse XML with pandas.read_xml")
        # Consider adding xpath or other args if common structures are known
        df = pd.read_xml(file_path, parse_dates=False) # parse_dates can be slow/error-prone
        
        # Check if the result is reasonable
        if not df.empty and df.shape[1] > 0:
             # Simple check: if only one column named 'Body' or similar, it might be nested wrongly
             if df.shape[1] == 1 and df.columns[0].lower() in ['body', 'root', 'data']:
                  logger.warning("pandas.read_xml resulted in a single generic column. Might be nested. Will try ElementTree.")
             else:
                logger.info(f"Successfully parsed XML with pandas.read_xml. Shape: {df.shape}")
                return df
        else:
            logger.info("pandas.read_xml returned empty or unusable DataFrame. Trying ElementTree.")
    except ValueError as ve:
         # ValueError often means structure not suitable for read_xml's assumptions
         logger.warning(f"pandas.read_xml failed (likely unsuitable XML structure): {ve}")
    except Exception as e:
        logger.warning(f"pandas.read_xml parsing failed: {str(e)}")

    # Strategy 2: Use ElementTree for more complex structures
    try:
        logger.info("Parsing XML with ElementTree")
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Strategy 2a: Look for repeating elements (potential rows)
        logger.info("ElementTree Strategy: Looking for repeating elements")
        repeating_elements = find_repeating_elements(root) # Assumes find_repeating_elements is defined below

        if repeating_elements:
            # Select the most frequent repeating tag (heuristic for row tag)
            # Exclude root tag itself from candidates
            candidates = {tag: count for tag, count in repeating_elements.items() if tag != root.tag}
            if candidates:
                most_common_element_tag = max(candidates.items(), key=lambda x: x[1])[0]
                logger.info(f"Found most common repeating element: <{most_common_element_tag}> ({candidates[most_common_element_tag]} times)")
                
                rows = []
                # Find all instances of this element anywhere in the tree
                for elem in root.findall(f".//{most_common_element_tag}"):
                    # Use flatten_element helper to get data from this element and its children
                    row_data = flatten_element(elem) # Assumes flatten_element defined below
                    if row_data:
                        rows.append(row_data)
                
                if rows:
                    df = pd.DataFrame(rows)
                    # Post-processing: Handle potential list columns if flatten_element doesn't fully flatten
                    # df = df.applymap(lambda x: str(x) if isinstance(x, list) else x)
                    logger.info(f"Created DataFrame from repeating element <{most_common_element_tag}>. Shape: {df.shape}")
                    return df
                else:
                     logger.info(f"Found repeating element <{most_common_element_tag}> but could not extract rows.")
            else:
                logger.info("Found repeating elements, but none suitable as row indicators besides root.")


        # Strategy 2b: Flatten the entire XML structure from root (if no clear repeating element)
        logger.info("ElementTree Strategy: Flattening entire XML structure")
        # This might result in a single row DataFrame if the XML is not list-like
        all_data = flatten_element(root)
        if all_data:
            # Try creating a DataFrame. If it's complex, json_normalize might work better.
            try:
                 df = pd.DataFrame([all_data]) # Wrap in list for single row
                 logger.info(f"Created single-row DataFrame by flattening root. Shape: {df.shape}")
                 # Check if any column contains complex objects (dicts/lists) suggesting further normalization needed
                 if any(isinstance(df[col].iloc[0], (dict, list)) for col in df.columns):
                      logger.info("Flattened structure seems nested. Trying json_normalize.")
                      try:
                           # Normalize the flattened dictionary
                           df_normalized = json_normalize(all_data)
                           if not df_normalized.empty:
                                logger.info(f"Successfully normalized flattened structure. Shape: {df_normalized.shape}")
                                return df_normalized
                           else:
                                logger.warning("json_normalize on flattened data yielded empty result.")
                                return df # Return the less normalized version
                      except Exception as norm_e:
                           logger.warning(f"json_normalize failed on flattened data: {norm_e}. Returning previous flattened DataFrame.")
                           return df
                 else:
                      return df # Return the simple flattened DataFrame
            except Exception as df_e:
                 logger.warning(f"Could not create DataFrame directly from flattened root data: {df_e}")

        # Strategy 3: Fallback - Return metadata if DataFrame creation failed
        logger.warning("All XML parsing strategies failed to produce a DataFrame. Returning XML metadata.")
        xml_sample = ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f: # Try reading sample
                xml_sample = f.read(5000)
        except Exception as sample_e:
             logger.warning(f"Could not read XML sample: {sample_e}")

        return {
            "type": "xml_meta", # Indicate it's not a DataFrame
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "root_tag": root.tag if 'root' in locals() else 'Unknown',
            "xml_sample": xml_sample,
            "parsing_status": "Failed to convert XML to DataFrame"
        }

    except ET.ParseError as pe:
         logger.error(f"Invalid XML structure in file {file_path}: {pe}")
         raise ValueError(f"Cannot parse XML file '{os.path.basename(file_path)}'. Invalid structure.")
    except Exception as e:
        logger.error(f"Error loading XML file {file_path} with ElementTree: {str(e)}")
        # Reraise or return error structure? Reraise for now.
        raise ValueError(f"Error processing XML file {os.path.basename(file_path)}: {e}")


def _load_json(file_path: str) -> pd.DataFrame:
    """Load a JSON file into a DataFrame using multiple strategies."""
    logger = logging.getLogger("data_loading.json")
    logger.info(f"Loading JSON file: {file_path}")
    
    try:
        # Read the JSON file first
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                 json_data = json.load(f)
            except json.JSONDecodeError as json_err:
                 logger.error(f"Invalid JSON format in {file_path}: {json_err}")
                 # Try reading line-delimited JSON (common variant)
                 logger.info("Trying to read as line-delimited JSON (.jsonl)")
                 try:
                     with open(file_path, 'r', encoding='utf-8') as f_lines:
                         lines = f_lines.readlines()
                         records = [json.loads(line) for line in lines if line.strip()]
                     if records:
                           logger.info(f"Successfully read {len(records)} records as line-delimited JSON.")
                           # Try to normalize in case records are nested
                           try:
                               df = json_normalize(records)
                               logger.info(f"Normalized line-delimited JSON. Shape: {df.shape}")
                               return df
                           except Exception as norm_e:
                               logger.warning(f"Could not normalize line-delimited JSON records ({norm_e}), creating DataFrame directly.")
                               return pd.DataFrame(records)
                     else:
                          raise ValueError(f"Invalid JSON format in {os.path.basename(file_path)}.")
                 except Exception as e:
                      logger.error(f"Failed to read as line-delimited JSON: {e}")
                      raise ValueError(f"Invalid JSON format in {os.path.basename(file_path)}.")
        
        df = None

        # Strategy 1: Use pandas.read_json (handles common structures)
        try:
            logger.info("Attempting to load JSON with pandas.read_json")
            # Try different orientations, 'records' is common for lists of dicts
            orientations_to_try = ['records', 'columns', 'index', 'split', 'values']
            for orient in orientations_to_try:
                 try:
                      df = pd.read_json(file_path, orient=orient, lines=False) # lines=False assumes standard JSON object/array
                      if not df.empty:
                           logger.info(f"Successfully loaded JSON with pandas.read_json(orient='{orient}'). Shape: {df.shape}")
                           return df
                      df = None # Reset if empty
                 except ValueError: # ValueError often means wrong orientation
                      continue # Try next orientation
                 except Exception as pd_e: # Other errors during read_json
                      logger.debug(f"pandas.read_json(orient='{orient}') failed: {pd_e}")
                      break # Stop trying orientations if a fundamental error occurs

            # Try reading as line-delimited with read_json
            if df is None:
                 logger.info("Trying pandas.read_json with lines=True")
                 try:
                      df = pd.read_json(file_path, lines=True)
                      if not df.empty:
                           logger.info("Successfully loaded JSON with pandas.read_json(lines=True). Shape: {df.shape}")
                           return df
                      df = None
                 except Exception as pd_lines_e:
                      logger.warning(f"pandas.read_json(lines=True) failed: {pd_lines_e}")

        except Exception as e:
            logger.warning(f"Initial pandas.read_json attempts failed: {str(e)}")
        
        # Strategy 2: Use json_normalize if read_json failed or if data is nested dict
        if df is None:
             logger.info("Attempting to load JSON using json.load and json_normalize")
             if isinstance(json_data, list):
                 # Common case: list of records
                 logger.info("JSON is a list, applying json_normalize.")
                 try:
                      df = json_normalize(json_data)
                      if not df.empty:
                           logger.info(f"Successfully loaded list JSON with json_normalize. Shape: {df.shape}")
                           return df
                      else: logger.warning("json_normalize on list resulted in empty DataFrame.")
                 except Exception as e:
                      logger.warning(f"json_normalize failed on list: {e}")
             
             elif isinstance(json_data, dict):
                 # Try normalizing the whole dict, or look for lists within it
                 logger.info("JSON is a dictionary, attempting json_normalize.")
                 try:
                      # First, try normalizing the entire dict
                      df = json_normalize(json_data)
                      if not df.empty:
                           logger.info(f"Successfully loaded dict JSON with json_normalize. Shape: {df.shape}")
                           return df
                      else:
                           logger.warning("json_normalize on dict resulted in empty DataFrame. Looking for nested lists.")
                           # Look for the largest list inside the dict to normalize
                           largest_list_key = None
                           max_len = 0
                           for key, value in json_data.items():
                                if isinstance(value, list) and len(value) > max_len:
                                     # Check if list contains dicts suitable for normalization
                                     if value and isinstance(value[0], dict):
                                          max_len = len(value)
                                          largest_list_key = key
                           
                           if largest_list_key:
                                logger.info(f"Found potential data in nested list under key '{largest_list_key}'. Normalizing this list.")
                                try:
                                     df = json_normalize(json_data[largest_list_key])
                                     if not df.empty:
                                          logger.info(f"Successfully normalized nested list '{largest_list_key}'. Shape: {df.shape}")
                                          # Optionally add other top-level keys as columns
                                          for top_key, top_value in json_data.items():
                                               if top_key != largest_list_key and not isinstance(top_value, (dict, list)):
                                                    if top_key not in df.columns:
                                                         df[top_key] = top_value
                                                    else: # Avoid overwriting normalized columns
                                                         df[f"meta_{top_key}"] = top_value
                                          return df
                                     else:
                                        logger.warning(f"json_normalize on nested list '{largest_list_key}' was empty.")
                                except Exception as e:
                                    logger.warning(f"Failed to normalize nested list '{largest_list_key}': {e}")
                           else:
                                logger.info("No suitable nested list found in dict for normalization.")

                 except Exception as e:
                     logger.warning(f"json_normalize failed on dict: {e}")

        # Strategy 3: Fallback - Create DataFrame from top-level keys if still no df
        if df is None and isinstance(json_data, dict):
            logger.info("Falling back to creating DataFrame from top-level dictionary keys.")
            try:
                # Filter out complex values if direct conversion fails
                simple_data = {k: v for k, v in json_data.items() if not isinstance(v, (dict, list))}
                if simple_data:
                    df = pd.DataFrame([simple_data])
                    logger.info(f"Created single-row DataFrame from simple top-level keys. Shape: {df.shape}")
                    return df
                else:
                     logger.warning("No simple key-value pairs found at top level of JSON dict.")
            except Exception as e:
                 logger.warning(f"Failed to create DataFrame from simple top-level keys: {e}")


        # If all strategies failed
        if df is None or df.empty:
             logger.error(f"All JSON loading strategies failed for {file_path}.")
             raise ValueError(f"Could not parse JSON file {os.path.basename(file_path)} into a usable DataFrame.")
        
        # Should have returned df by now if successful
        return df # Should technically not be reached if logic is correct

    except FileNotFoundError:
         logger.error(f"JSON file not found: {file_path}")
         raise
    except Exception as e:
        logger.error(f"Error loading JSON file {file_path}: {str(e)}")
        raise ValueError(f"Error processing JSON file {os.path.basename(file_path)}: {e}")

# --- Main Loading Function ---
def load_datafile(file_path: str, file_format: Optional[str] = None) -> Union[pd.DataFrame, Dict[str, Any]]:
    """
    Load a data file (CSV, Excel, PDF, XML, JSON, or supported archives)
    using appropriate helpers. Prioritizes explicit format, then extension,
    then content-based type detection (magic or trial-and-error for archives).

    Returns a DataFrame for tabular data or a Dict for PDF/unparseable XML.

    Raises FileNotFoundError if file doesn't exist, or ValueError/other exceptions on loading errors.
    """
    logger.info(f"Initiating loading for: {file_path}. Explicit format provided: {file_format}")

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        raise FileNotFoundError(f"The specified file does not exist: {file_path}")

    result: Union[pd.DataFrame, Dict[str, Any]] = None
    final_log_type = None # To store the type used for final logging
    loading_attempted = False # Track if any specific loading function was called
    load_error_message = None # Store specific load error

    try:
        # 1. Prioritize explicit format if provided
        if file_format:
            format_lower = file_format.lower().strip()
            logger.info(f"Attempting to load using explicit format: '{format_lower}'")
            load_function = None
            archive_type = None

            if format_lower == 'csv':
                load_function = _load_csv
                final_log_type = 'CSV (explicit)'
            elif format_lower in ['xlsx', 'xls']:
                load_function = _load_excel
                final_log_type = 'Excel (explicit)'
            elif format_lower == 'pdf':
                load_function = _load_pdf # Returns Dict
                final_log_type = 'PDF (explicit)'
            elif format_lower == 'xml':
                load_function = _load_xml # Returns DataFrame or Dict
                final_log_type = 'XML (explicit)'
            elif format_lower == 'json':
                load_function = _load_json
                final_log_type = 'JSON (explicit)'
            elif format_lower == 'html':
                # Explicitly handle HTML - currently unsupported for tabular data
                loading_attempted = True # Mark as attempted
                final_log_type = 'HTML (explicit)'
                logger.warning("Explicit format 'HTML' provided. HTML table parsing is not yet supported. Treating as non-tabular.")
                # We might load basic text later if needed, but not a DataFrame here.
                # For now, let it proceed to the final error if no other loader works.
                load_error_message = "HTML format specified, but tabular data extraction from HTML is not supported."
                # Do not set load_function, let it potentially fall through or error out cleanly.
            elif format_lower == 'zip':
                 archive_type = 'zip'
                 final_log_type = 'ZIP Archive (explicit)'
            elif format_lower == 'tar':
                 archive_type = 'tar'
                 final_log_type = 'TAR Archive (explicit)'
            elif format_lower == 'gzip':
                 archive_type = 'gzip'
                 final_log_type = 'GZIP Archive (explicit)'
            elif format_lower == 'bz2':
                 archive_type = 'bz2'
                 final_log_type = 'BZ2 Archive (explicit)'
            else:
                logger.warning(f"Explicit format '{file_format}' provided but not recognized or supported. Falling back to extension/inference.")

            if load_function:
                try:
                    result = load_function(file_path)
                    loading_attempted = True
                    logger.info(f"Successfully loaded using explicit format '{file_format}'.")
                except Exception as e:
                    loading_attempted = True # Mark attempt even on failure
                    load_error_message = f"Error loading file using explicit format '{file_format}': {e}"
                    logger.error(f"{load_error_message}. Falling back.")
                    result = None
                    final_log_type = None # Reset log type for fallback
            elif archive_type:
                 try:
                     result = _load_archived_file(archive_type, file_path)
                     loading_attempted = True
                     # _load_archived_file logs success/failure internally
                 except Exception as e:
                     loading_attempted = True
                     load_error_message = f"Error handling archive using explicit format '{file_format}': {e}"
                     logger.error(f"{load_error_message}. Falling back.")
                     result = None
                     final_log_type = None


        # 2. If explicit format wasn't provided, failed, or wasn't recognized, use extension
        if result is None and not loading_attempted:
            logger.info("Using file extension for loading.")
            file_extension = os.path.splitext(file_path)[1].lower()
            load_function = None
            archive_type = None

            if file_extension == '.csv':
                load_function = _load_csv
                final_log_type = 'CSV (extension)'
            elif file_extension in ['.xlsx', '.xls']:
                load_function = _load_excel
                final_log_type = 'Excel (extension)'
            elif file_extension == '.pdf':
                load_function = _load_pdf # Returns Dict
                final_log_type = 'PDF (extension)'
            elif file_extension == '.xml':
                load_function = _load_xml # Returns DataFrame or Dict
                final_log_type = 'XML (extension)'
            elif file_extension == '.json':
                 load_function = _load_json
                 final_log_type = 'JSON (extension)'
            elif file_extension == '.html':
                 loading_attempted = True # Mark as attempted
                 final_log_type = 'HTML (extension)'
                 logger.warning("Detected '.html' extension. HTML table parsing is not yet supported. Treating as non-tabular.")
                 load_error_message = "Detected HTML extension, but tabular data extraction from HTML is not supported."
                 # Do not set load_function
            elif file_extension == '.zip':
                archive_type = 'zip'
                final_log_type = 'ZIP Archive (extension)'
            elif file_extension in ['.tar', '.tgz', '.tar.gz', '.tar.bz2', '.tar.xz']: # More TAR extensions
                archive_type = 'tar'
                final_log_type = 'TAR Archive (extension)'
            elif file_extension == '.gz':
                 archive_type = 'gzip'
                 final_log_type = 'GZIP Archive (extension)'
            elif file_extension == '.bz2':
                 archive_type = 'bz2'
                 final_log_type = 'BZ2 Archive (extension)'
            # else: Fall through to content detection if extension is unknown/unsupported

            if load_function:
                try:
                    result = load_function(file_path)
                    loading_attempted = True
                    logger.info(f"Successfully loaded using extension '{file_extension}'.")
                except Exception as e:
                    loading_attempted = True
                    load_error_message = f"Error loading file using extension '{file_extension}': {e}"
                    logger.error(f"{load_error_message}. Proceeding to content detection.")
                    result = None
                    final_log_type = None
            elif archive_type:
                try:
                    result = _load_archived_file(archive_type, file_path)
                    loading_attempted = True
                    # Internal logging in helper
                except Exception as e:
                     loading_attempted = True
                     load_error_message = f"Error handling archive using extension '{file_extension}': {e}"
                     logger.error(f"{load_error_message}. Proceeding to content detection.")
                     result = None
                     final_log_type = None


        # 3. If result is still None, try content-based detection (Magic or Trial-and-Error)
        if result is None and not loading_attempted:
            logger.info("Using content-based type detection.")
            detected_archive_type = None
            load_function = None
            final_log_type_base = "inferred" # Base for logging type
            mime_type = "unknown" # Default

            # Strategy 3a: Use python-magic if available
            if magic_available and magic_checker:
                try:
                    mime_type = magic_checker.from_file(file_path)
                    logger.info(f"Detected MIME type using libmagic: {mime_type}")

                    # Map MIME type to loader or archive handler
                    # PRIORITIZE specific known types over generic text/html
                    if 'zip' in mime_type: detected_archive_type = 'zip'
                    elif 'tar' in mime_type: detected_archive_type = 'tar'
                    elif 'gzip' in mime_type: detected_archive_type = 'gzip'
                    elif 'bzip2' in mime_type: detected_archive_type = 'bz2'
                    elif 'csv' in mime_type: # Explicit CSV type
                         load_function = _load_csv
                         final_log_type_base = "CSV"
                    elif 'excel' in mime_type or 'spreadsheet' in mime_type or 'ms-excel' in mime_type or 'openxmlformats-officedocument.spreadsheetml.sheet' in mime_type:
                         load_function = _load_excel
                         final_log_type_base = "Excel"
                    elif 'pdf' in mime_type:
                         load_function = _load_pdf
                         final_log_type_base = "PDF"
                    elif 'xml' in mime_type and 'html' not in mime_type: # Make sure it's not XHTML identified as XML
                         load_function = _load_xml
                         final_log_type_base = "XML"
                    elif 'json' in mime_type:
                         load_function = _load_json
                         final_log_type_base = "JSON"
                    elif 'html' in mime_type:
                         # *** Explicitly handle HTML detected by magic ***
                         loading_attempted = True # Mark as attempted
                         final_log_type = 'HTML (magic inferred)'
                         logger.warning("Detected 'text/html' via magic. HTML table parsing is not yet supported. Treating as non-tabular.")
                         load_error_message = "Detected HTML content, but tabular data extraction from HTML is not supported."
                         # Do not set load_function or detected_archive_type
                    elif 'text/plain' in mime_type:
                        # Treat plain text cautiously - might be CSV, might be something else.
                        # Allow fallback CSV attempt but log warning.
                        logger.warning("Detected 'text/plain' via magic. Will attempt CSV loading, but format may not be suitable.")
                        load_function = _load_csv
                        final_log_type_base = "CSV (from text/plain)"
                    else:
                         logger.warning(f"Unsupported MIME type detected by libmagic: {mime_type}")

                    # Update final_log_type based on detection
                    if final_log_type is None: # Avoid overwriting if already set (e.g., by HTML check)
                        if detected_archive_type:
                             final_log_type = f"{detected_archive_type.upper()} Archive (magic inferred)"
                        elif load_function:
                             final_log_type = f"{final_log_type_base.upper()} (magic inferred)"
                        else:
                             final_log_type = f"Unknown ({mime_type} via magic)"


                except Exception as magic_e:
                    logger.error(f"python-magic failed to analyze file {file_path}: {magic_e}. Falling back to trial-and-error if applicable.")
                    final_log_type = None # Reset log type

            # Strategy 3b: Trial-and-error archive loading (if magic unavailable or failed AND not identified as loadable type yet)
            if detected_archive_type is None and load_function is None and final_log_type != 'HTML (magic inferred)':
                 # (Keep existing trial-and-error logic for zip, tar, gzip, bz2) ...
                logger.info("Attempting trial-and-error archive loading.")
                # Tentative log type, might be overwritten if specific type found
                final_log_type = "Archive (trial inferred)"
                archive_handlers = [
                    ('zip', zipfile.is_zipfile),
                    ('tar', tarfile.is_tarfile),
                ]
                for arc_type, check_func in archive_handlers:
                    try:
                        if check_func(file_path):
                            logger.info(f"Trial-and-error: Detected possible '{arc_type}' archive.")
                            detected_archive_type = arc_type
                            final_log_type = f"{arc_type.upper()} Archive (trial inferred)" # More specific
                            break
                    except Exception as check_e:
                         logger.debug(f"Trial-and-error check for {arc_type} failed: {check_e}")

                if detected_archive_type is None:
                     try:
                          with gzip.open(file_path, 'rb') as f_gz: f_gz.read(1)
                          logger.info("Trial-and-error: Detected possible 'gzip' archive.")
                          detected_archive_type = 'gzip'
                          final_log_type = "GZIP Archive (trial inferred)"
                     except (gzip.BadGzipFile, EOFError, OSError):
                          try:
                               with bz2.open(file_path, 'rb') as f_bz2: f_bz2.read(1)
                               logger.info("Trial-and-error: Detected possible 'bz2' archive.")
                               detected_archive_type = 'bz2'
                               final_log_type = "BZ2 Archive (trial inferred)"
                          except (EOFError, OSError) as bz_err:
                               logger.info(f"Trial-and-error: File does not appear to be Gzip or Bzip2. Final check error: {bz_err}")
                               if final_log_type == "Archive (trial inferred)": final_log_type = "Unknown (trial failed)" # Update log type if no archive found
                          except Exception as gz_bz_e:
                               logger.warning(f"Unexpected error during Gzip/Bz2 trial open: {gz_bz_e}")
                               if final_log_type == "Archive (trial inferred)": final_log_type = "Unknown (trial error)"
                     except Exception as gz_bz_e:
                          logger.warning(f"Unexpected error during Gzip trial open: {gz_bz_e}")
                          if final_log_type == "Archive (trial inferred)": final_log_type = "Unknown (trial error)"


            # --- Execute loading based on content detection ---
            # This part runs if Step 1/2 failed OR if Step 3 detected something loadable
            if detected_archive_type:
                try:
                    result = _load_archived_file(detected_archive_type, file_path)
                    loading_attempted = True
                except Exception as e:
                     loading_attempted = True
                     load_error_message = f"Error handling detected archive type '{detected_archive_type}': {e}"
                     logger.error(load_error_message)
                     result = None
                     # Keep final_log_type as detected archive type for error reporting
            elif load_function:
                 try:
                      result = load_function(file_path)
                      loading_attempted = True
                 except Exception as e:
                      loading_attempted = True
                      load_error_message = f"Error loading file using inferred type '{final_log_type_base}': {e}"
                      logger.error(load_error_message)
                      result = None
                      # Keep final_log_type as inferred type for error reporting


        # 4. Final check and error raising
        if result is None:
            final_error_message = f"Failed to load file {os.path.basename(file_path)} after all attempts."
            if final_log_type:
                final_error_message += f" Last detected/attempted type: {final_log_type}."
            if load_error_message:
                 final_error_message += f" Specific load error: {load_error_message}"
            else:
                 # If loading_attempted is False here, it means no format/extension/type matched anything known
                 if not loading_attempted:
                      final_error_message = f"Could not determine loadable file type for {os.path.basename(file_path)}. Extension: {file_extension}, Detected MIME: {mime_type}."
                 else:
                      # A loader was attempted but returned None without raising, or was skipped (like HTML)
                      final_error_message += " Loading function failed or format is unsupported for tabular data."

            logger.error(final_error_message)
            # Raise a specific error type
            raise ValueError(final_error_message)


        # Log success and return result
        log_type_str = final_log_type or "UnknownType"
        if isinstance(result, pd.DataFrame):
            logger.info(f"Successfully loaded {log_type_str} into DataFrame. Shape: {result.shape}")
        elif isinstance(result, dict):
             # ... (existing dict logging) ...
             data_type = result.get('type', 'dictionary')
             if data_type == 'pdf':
                 logger.info(f"Successfully processed PDF ({log_type_str}). Pages: {result.get('num_pages', 0)}")
             elif data_type == 'xml_meta':
                 logger.warning(f"XML loading ({log_type_str}) resulted in metadata dictionary, not DataFrame. Root tag: {result.get('root_tag')}")
             else:
                  logger.info(f"Successfully loaded data as dictionary ({log_type_str}). Keys: {list(result.keys())}")
        else:
             logger.info(f"Successfully loaded data ({log_type_str}). Type: {type(result).__name__}")

        return result

    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError, RuntimeError, Exception) as e:
        # Log the final error before re-raising
        # Adding traceback here can be helpful for debugging loading errors
        logger.error(f"Failed to load file {file_path}. Final Error: {type(e).__name__} - {str(e)}")
        logger.debug(traceback.format_exc()) # Add traceback to debug log
        raise # Re-raise the exception

# --- Make sure helper XML functions exist ---
# Add these if they weren't included in the original code block

def find_repeating_elements(root: ET.Element) -> Dict[str, int]:
    """
    Find elements that repeat within the XML tree (excluding root).
    Args: root: Root element of the XML tree
    Returns: Dictionary mapping element tags to their frequency
    """
    element_counts = defaultdict(int)
    for elem in root.iter():
        if elem != root: # Don't count the root itself
             element_counts[elem.tag] += 1
    # Filter to elements that appear more than once
    return {tag: count for tag, count in element_counts.items() if count > 1}

def flatten_element(element: ET.Element, prefix: str = '') -> Dict[str, Any]:
    """
    Recursively flatten an XML element into a dictionary.
    Handles attributes, text, and nested children.
    Args: element: XML element to flatten, prefix: Prefix for nested keys
    Returns: Dictionary with flattened data
    """
    result = {}
    # Use regex to remove potential namespace like {http://some.namespace/blah}tagname -> tagname
    element_tag_match = re.match(r'(\{.*\})?(.*)', element.tag)
    element_tag = element_tag_match.group(2) if element_tag_match else element.tag # Fallback if regex fails

    current_prefix = f"{prefix}{element_tag}_" if prefix else f"{element_tag}_"

    # Add attributes with prefix
    for key, value in element.attrib.items():
        attr_key_match = re.match(r'(\{.*\})?(.*)', key) # Remove namespace from attribute key too
        attr_key_base = attr_key_match.group(2) if attr_key_match else key
        attr_key = f"{current_prefix}attr_{attr_key_base}"
        result[attr_key] = value

    # Add text content if present
    if element.text and element.text.strip():
        text_key = f"{prefix}{element_tag}" if prefix else element_tag
        # If key already exists (e.g., from attribute), append '_text'
        # Avoid appending _text if the element only has text and no attributes/children
        has_attrs_or_children = bool(element.attrib or list(element))
        if text_key in result and has_attrs_or_children:
             text_key += "_text"
        elif text_key in result and not has_attrs_or_children:
             # If key exists and no attrs/children, likely a simple repeated tag handled below
             pass # Let list handling take care of it
        else:
             result[text_key] = element.text.strip()

    # Recursively process child elements, grouping tags
    child_data_grouped = defaultdict(list)
    for child in element:
        child_tag_match = re.match(r'(\{.*\})?(.*)', child.tag)
        child_tag = child_tag_match.group(2) if child_tag_match else child.tag
        flattened_child = flatten_element(child) # Flatten child without prefix initially

        # If the flattened child is just simple text (a single key matching its tag)
        if len(flattened_child) == 1 and list(flattened_child.keys())[0] == child_tag:
            child_data_grouped[child_tag].append(list(flattened_child.values())[0])
        else:
            child_data_grouped[child_tag].append(flattened_child)

    # Merge grouped child data into the main result
    for tag, data_list in child_data_grouped.items():
        key = f"{prefix}{element_tag}_{tag}" if prefix else f"{element_tag}_{tag}"
        if len(data_list) == 1:
            # If only one child with this tag, merge its content or assign directly
            if isinstance(data_list[0], dict):
                 # Prefix keys from the child dict before merging to avoid collisions
                 prefixed_child_data = {f"{key}_{sub_key}": val for sub_key, val in data_list[0].items()}
                 result.update(prefixed_child_data)
            else:
                 result[key] = data_list[0] # Assign simple value directly
        else:
            # If multiple children with the same tag, keep as a list
            result[key] = data_list

    return result


# ... rest of dataset_loader.py (assess_datafile_relevance, etc.) ...


# --- Helper functions for XML/JSON parsing (used by _load_xml, _load_json) ---

def find_repeating_elements(root: ET.Element) -> Dict[str, int]:
    """
    Find elements that repeat within the XML tree (excluding root).
    Args: root: Root element of the XML tree
    Returns: Dictionary mapping element tags to their frequency
    """
    element_counts = defaultdict(int)
    for elem in root.iter():
        if elem != root: # Don't count the root itself
             element_counts[elem.tag] += 1
    # Filter to elements that appear more than once
    return {tag: count for tag, count in element_counts.items() if count > 1}


# --- Existing Relevance Assessment Function (Kept as per request) ---

def assess_datafile_relevance(
    df_or_pdf: Union[pd.DataFrame, Dict[str, Any]], 
    query: str, 
    dataset_metadata: Dict[str, Any],
    relevance_threshold: float = 0.7
) -> Tuple[bool, float, str]:
    """
    Assess if a datafile (CSV/Excel/etc.) or PDF document is relevant to the user's query using OpenAI.
    
    Args:
        df_or_pdf: The loaded data (DataFrame) or PDF info (Dict)
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description)
        relevance_threshold: Threshold for considering a datafile relevant (0-1)
        
    Returns:
        Tuple of (is_relevant, relevance_score, reasoning)
    """
    logger_relevance = logging.getLogger("relevance_assessment")
    logger_relevance.info(f"Assessing relevance for query: '{query}'")

    # Get dataset information
    title = dataset_metadata.get('title', 'Unknown Dataset')
    description = dataset_metadata.get('description', 'No description provided.')
    
    # Check if we're dealing with a PDF dict or a placeholder failure dict
    is_pdf = isinstance(df_or_pdf, dict) and df_or_pdf.get('type') == 'pdf'
    # Check if it's a placeholder indicating loading failed
    is_placeholder_df = isinstance(df_or_pdf, pd.DataFrame) and 'parsing_status' in df_or_pdf.columns and 'Failed' in df_or_pdf['parsing_status'].iloc[0]
    is_xml_meta = isinstance(df_or_pdf, dict) and df_or_pdf.get('type') == 'xml_meta'

    if is_placeholder_df or is_xml_meta:
         logger_relevance.warning("Assessing relevance on a placeholder DataFrame or XML metadata due to loading failure.")
         # Provide minimal info for assessment based on filename and sample (if available)
         file_name = df_or_pdf['file_name'].iloc[0] if is_placeholder_df else df_or_pdf.get('file_name', 'Unknown')
         content_sample = df_or_pdf['content_sample'].iloc[0] if is_placeholder_df and 'content_sample' in df_or_pdf.columns else df_or_pdf.get('xml_sample', '')
         content_sample = content_sample[:1000] # Limit sample size

         prompt = f"""
You are assessing whether a file, which COULD NOT BE FULLY PARSED, might be relevant to a user's query based only on metadata and a small content sample.

USER QUERY: "{query}"

FILE INFORMATION:
Original Filename: {file_name}
Dataset Title: {title}
Dataset Description: {description}
Parsing Status: {'Failed to parse' if is_placeholder_df else 'Could not convert XML to table'}

CONTENT SAMPLE (first 1000 chars, may be inaccurate):
{content_sample if content_sample else 'No content sample available.'}

ASSESSMENT GUIDELINES:
1. Relevance is UNCERTAIN due to parsing failure.
2. Base your judgment PRIMARILY on the filename, dataset title, and description.
3. Use the content sample cautiously, as it might be misleading or incomplete.
4. Assign a LOWER score than you would if the file parsed correctly, reflecting the uncertainty.
5. If title/description/filename strongly suggest relevance, assign a moderate score (e.g., 0.5-0.7). If they seem unrelated, assign a low score (0.0-0.3).

Please provide:
1. A relevance score from 0.0 to 1.0.
2. A brief explanation acknowledging the parsing failure and justifying the score based on available info.

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
"""

    elif is_pdf:
        # Handle PDF document assessment (using existing logic structure)
        pdf_data = df_or_pdf
        logger_relevance.info(f"Assessing relevance for PDF: {pdf_data.get('file_name', 'Unknown')}")
        
        num_pages = pdf_data.get('num_pages', 0)
        pdf_title_meta = pdf_data.get('metadata', {}).get('Title', '') # From PDF metadata
        pdf_title_file = pdf_data.get('title', '') # From generate_pdf_summary if run
        
        # Use the most descriptive title available
        doc_title = pdf_title_meta or pdf_title_file or pdf_data.get('file_name', 'Unknown PDF')
        
        # Use enhanced summary/sample if available, otherwise fall back
        text_for_analysis = pdf_data.get('enhanced_text_sample', pdf_data.get('text_sample', ''))
        text_for_analysis = text_for_analysis[:4000] # Limit prompt size

        # Key term search (optional but kept from original)
        key_terms = [term for term in query.lower().split() if len(term) > 3]
        term_presence_summary = "Term search not performed."
        if key_terms and 'full_text' in pdf_data:
            full_text_lower = pdf_data['full_text'].lower()
            term_presence = {term: (term in full_text_lower) for term in key_terms}
            term_presence_summary = f"Key term search results in full text: {chr(10)}" + \
                                    f"{chr(10).join([f'- "{term}": {"Found" if found else "Not found"}' for term, found in term_presence.items()])}"

        prompt = f"""
You are assessing whether a PDF document is relevant to a user's query.

USER QUERY: "{query}"

DOCUMENT INFORMATION:
Document Title: {doc_title}
Dataset Title (if different): {title}
Dataset Description: {description}
Number of Pages: {num_pages}

DOCUMENT CONTENT SUMMARY / SAMPLE (up to 4000 chars):
{text_for_analysis if text_for_analysis else 'No text summary available.'}

{term_presence_summary}

ASSESSMENT GUIDELINES:
1. PRIORITIZE the document's title, dataset context (title/description), and content summary/sample.
2. Consider that the summary/sample may not represent all content.
3. If the document plausibly relates to the query based on available information, lean towards relevance.

Please provide:
1. A relevance score from 0.0 to 1.0 (0.0-0.3: Not relevant, 0.4-0.6: Potentially relevant, 0.7-1.0: Highly relevant).
2. A brief explanation of your reasoning (2-3 sentences).

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
"""
    
    else: # Handle DataFrame assessment (original logic structure)
        df = df_or_pdf # Assume it's a DataFrame
        logger_relevance.info(f"Assessing relevance for DataFrame. Shape: {df.shape}")

        # Get column information
        columns = list(df.columns)
        column_info = []
        num_cols_to_sample = min(len(columns), 30) # Limit column details in prompt
        for i, col in enumerate(columns[:num_cols_to_sample]):
            try:
                dtype = str(df[col].dtype)
                # Sample non-NA values, convert to string safely
                sample_values_raw = df[col].dropna().head(3).tolist()
                sample_values = [str(v)[:50] for v in sample_values_raw] # Truncate long values
                column_info.append(f"- {col} ({dtype}): {sample_values}")
            except Exception as col_e:
                 column_info.append(f"- {col}: Error sampling values ({col_e})")
        if len(columns) > num_cols_to_sample:
             column_info.append(f"... and {len(columns) - num_cols_to_sample} more columns.")
        
        # Get sample rows (limit width)
        sample_rows = df.head(5).to_string(index=False, max_colwidth=80)
        sample_rows = sample_rows[:3000] # Limit sample size in prompt

        # Key term search (optional, kept from original, simplified for performance)
        key_terms = [term for term in query.lower().split() if len(term) > 3]
        term_presence_summary = "Term search not performed."
        if key_terms:
             term_presence = {}
             # Search only in object columns (potential text) and sample data
             search_cols = df.select_dtypes(include=['object']).columns
             sample_df_search = df.head(100) # Search only in head
             for term in key_terms:
                 found = False
                 for col in search_cols:
                     try:
                          # Use vectorized contains, handle NA
                          if sample_df_search[col].astype(str).str.contains(term, case=False, na=False).any():
                               found = True
                               break
                     except Exception: pass # Ignore errors during search
                 term_presence[term] = found
             term_presence_summary = f"Key term search results (in sample text columns): {chr(10)}" + \
                                     f"{chr(10).join([f'- "{term}": {"Found" if found else "Not found"}' for term, found in term_presence.items()])}"


        prompt = f"""
You are assessing whether a dataset loaded into a DataFrame is relevant to a user's query.

USER QUERY: "{query}"

DATASET CONTEXT:
Dataset Title: {title}
Dataset Description: {description}

DATAFRAME STRUCTURE:
Columns ({len(columns)} total): {', '.join(columns[:num_cols_to_sample])}{'...' if len(columns) > num_cols_to_sample else ''}

Column Details (Sample):
{chr(10).join(column_info)}

Sample Data (first 5 rows, truncated):
{sample_rows}

{term_presence_summary}

ASSESSMENT GUIDELINES:
1. PRIORITIZE dataset context (title, description) and DataFrame structure (column names, types).
2. Use sample data and term search results as supporting evidence.
3. If the structure/context suggests the data *could* contain relevant info, lean towards relevance.

Please provide:
1. A relevance score from 0.0 to 1.0 (0.0-0.3: Not relevant, 0.4-0.6: Potentially relevant, 0.7-1.0: Highly relevant).
2. A brief explanation of your reasoning (2-3 sentences).

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
"""

    # Call OpenAI API (Common logic for all cases)
    system_message = "You are a data analyst expert at evaluating data relevance for user queries. Provide concise, accurate assessments based *only* on the provided information."
    
    try:
        response_text = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1 # Lower temperature for more deterministic scoring
        )
        
        # Parse the response
        score_match = re.search(r'SCORE:\s*([\d.]+)', response_text)
        # Make reasoning regex less greedy and handle multiline better
        reasoning_match = re.search(r'REASONING:\s*(.*?)(?:\n\n|\Z)', response_text, re.DOTALL | re.IGNORECASE)
        
        if score_match and reasoning_match:
            try:
                score = float(score_match.group(1))
                # Clamp score between 0.0 and 1.0
                score = max(0.0, min(1.0, score))
                reasoning = reasoning_match.group(1).strip()
                is_relevant = score >= relevance_threshold
                logger_relevance.info(f"Relevance assessment complete. Score: {score:.2f}, Relevant: {is_relevant}, Reasoning: {reasoning}")
                return (is_relevant, score, reasoning)
            except ValueError:
                 logger_relevance.error(f"Could not parse score as float: {score_match.group(1)}")
                 return (False, 0.0, f"Failed to parse relevance score. Raw response: {response_text[:200]}")
        else:
            logger_relevance.error(f"Failed to parse SCORE/REASONING from LLM response: {response_text[:500]}")
            # Fallback if parsing fails
            return (False, 0.0, f"Failed to parse relevance assessment response. Response snippet: {response_text[:200]}")

    except Exception as e:
        logger_relevance.error(f"Error during relevance assessment API call: {str(e)}")
        return (False, 0.0, f"Error during relevance assessment: {str(e)}")


# --- PDF Summary Generation Function (Kept as per request, called by _load_pdf) ---
# Note: This function was previously defined inside load_pdf_document.
# It's kept separate here for clarity but is still tightly coupled to _load_pdf.
# Consider moving this out entirely in a future refactor.

def generate_pdf_summary(pdf_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an enhanced summary of a PDF document using an LLM.
    (Note: This is called internally by _load_pdf if API keys are present)
    
    Args:
        pdf_data: Dictionary containing PDF text and metadata (modified in-place)
        
    Returns:
        The modified pdf_data dictionary
    """
    logger_summary = logging.getLogger("pdf_summary") # Specific logger
    logger_summary.info(f"Starting enhanced summary generation for PDF: {pdf_data.get('file_name', 'unknown')}")
    
    # Check for API key (redundant if check is already in _load_pdf, but safe)
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("AZURE_OPENAI_API_KEY")):
        logger_summary.warning("No OpenAI API key provided. Skipping enhanced summary generation.")
        pdf_data["enhanced_summary"] = "Not Generated (No API Key)"
        pdf_data["section_titles"] = []
        pdf_data["key_points"] = []
        pdf_data["notable_elements"] = []
        pdf_data["enhanced_text_sample"] = pdf_data.get("text_sample", "") # Fallback sample
        return pdf_data

    # Get text for analysis, sampling if very long
    full_text = pdf_data.get('full_text', '')
    max_len_for_prompt = 15000 # Max chars to send to LLM
    
    if len(full_text) > max_len_for_prompt:
        # Simple truncation for now, could be smarter (start/middle/end)
        analysis_text = full_text[:max_len_for_prompt]
        logger_summary.info(f"PDF text length ({len(full_text)}) > {max_len_for_prompt}. Using truncated text for analysis.")
    else:
        analysis_text = full_text
        logger_summary.info(f"Using full text ({len(full_text)} chars) for analysis.")
    
    # Create prompt (more detailed than the relevance one)
    prompt = f"""
Analyze the following text extracted from a PDF document and provide a structured summary.

DOCUMENT TITLE (from metadata/filename): {pdf_data.get('title', pdf_data.get('file_name', 'Unknown'))}
DOCUMENT PAGE COUNT: {pdf_data.get('num_pages', 'Unknown')}

DOCUMENT TEXT SAMPLE (up to {max_len_for_prompt} chars):
{analysis_text}
{'[... Text Truncated ...]' if len(full_text) > max_len_for_prompt else ''}

TASK:
Generate a JSON object containing:
1.  "summary": A concise summary (3-5 sentences) of the document's main purpose and findings.
2.  "section_titles": A list of apparent major section titles or topics covered (up to 10). If none are clear, provide an empty list.
3.  "key_points": A list of the 5-7 most important points, conclusions, or findings mentioned.
4.  "notable_elements": A list of any specific dates, statistics, key figures, or named entities that seem important (up to 7).

Ensure the output is a single, valid JSON object.

JSON OUTPUT:
"""

    try:
        logger_summary.info("Calling OpenAI API for enhanced summary generation.")
        response = chat_completion(
            prompt,
            system_message="You are a document analysis expert skilled at creating structured summaries from text.",
            temperature=0.2,
            response_format={"type": "json_object"} # Request JSON directly
        )
        
        logger_summary.info("Received response from OpenAI API.")
        
        # Parse the JSON response
        summary_data = json.loads(response) # Assumes response IS the JSON string
        logger_summary.info("Successfully parsed JSON response.")
            
        # Add the summary data to the PDF data dictionary
        pdf_data["enhanced_summary"] = summary_data.get("summary", "Summary not found in response")
        pdf_data["section_titles"] = summary_data.get("section_titles", [])
        pdf_data["key_points"] = summary_data.get("key_points", [])
        pdf_data["notable_elements"] = summary_data.get("notable_elements", [])
        
        # Create a combined text sample for easier downstream use (like relevance assessment)
        enhanced_text_sample_parts = [
            f"SUMMARY: {pdf_data['enhanced_summary']}"
        ]
        if pdf_data["section_titles"]:
            enhanced_text_sample_parts.append(f"SECTIONS/TOPICS: {', '.join(pdf_data['section_titles'][:5])}{'...' if len(pdf_data['section_titles']) > 5 else ''}")
        if pdf_data["key_points"]:
            enhanced_text_sample_parts.append(f"KEY POINTS:\n" + "\n".join([f"- {p}" for p in pdf_data["key_points"][:5]]))
        if pdf_data["notable_elements"]:
             enhanced_text_sample_parts.append(f"NOTABLE ELEMENTS:\n" + "\n".join([f"- {e}" for e in pdf_data["notable_elements"][:5]]))
        
        pdf_data["enhanced_text_sample"] = "\n\n".join(enhanced_text_sample_parts)
            
        logger_summary.info("Successfully generated and stored enhanced summary for PDF.")
        
    except json.JSONDecodeError as e:
        logger_summary.error(f"Failed to parse JSON response from LLM: {e}")
        logger_summary.error(f"LLM Response Snippet: {response[:500]}...")
        pdf_data["enhanced_summary"] = "Summary Generation Failed (JSON Parsing Error)"
        pdf_data["enhanced_text_sample"] = pdf_data.get("text_sample", "") # Fallback
    except Exception as e:
        logger_summary.error(f"Error during enhanced PDF summary generation: {str(e)}")
        pdf_data["enhanced_summary"] = f"Summary Generation Failed ({type(e).__name__})"
        pdf_data["enhanced_text_sample"] = pdf_data.get("text_sample", "") # Fallback

    return pdf_data # Return the modified dict