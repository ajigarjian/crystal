"""
Utility functions for enriching dataset metadata with quality metrics and granularity information.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List
import logging
from factchecker.utils.openai_client import chat_completion
import re # Import re module
import json

# Configure logging
logger = logging.getLogger(__name__)

def calculate_quality_metrics(dataset_content: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate quality metrics for a dataset.
    
    Args:
        dataset_content: Pandas DataFrame containing the dataset
        
    Returns:
        Dictionary with quality metrics including:
        - quality_score: Percentage of non-missing values (0-100)
        - missing_cells: Number of missing cells
        - total_cells: Total number of cells in the DataFrame
        - column_completeness: Per-column completeness percentages
    """
    if not isinstance(dataset_content, pd.DataFrame):
        return {
            "quality_score": 0,
            "error": "Not a valid DataFrame"
        }
    
    try:
        # Calculate total cells and missing cells
        total_cells = dataset_content.size
        missing_cells = dataset_content.isna().sum().sum()
        
        # Calculate quality score as percentage of non-missing values
        quality_score = ((total_cells - missing_cells) / total_cells) * 100 if total_cells > 0 else 0
        
        # Calculate per-column completeness
        column_completeness = {}
        for col in dataset_content.columns:
            col_total = len(dataset_content[col])
            col_missing = dataset_content[col].isna().sum()
            col_completeness = ((col_total - col_missing) / col_total) * 100 if col_total > 0 else 0
            column_completeness[col] = round(col_completeness, 2)
        
        # Detect duplicate rows
        duplicate_rows = dataset_content.duplicated().sum()
        duplicate_percentage = (duplicate_rows / len(dataset_content)) * 100 if len(dataset_content) > 0 else 0
        
        # Detect potentially corrupted data (checking for extreme outliers in numeric columns)
        corrupted_columns = []
        for col in dataset_content.select_dtypes(include=[np.number]).columns:
            try:
                # Check if column has any values more than 10 std devs from mean (potential corruption)
                std = dataset_content[col].std()
                mean = dataset_content[col].mean()
                if std > 0:  # Avoid division by zero
                    extreme_outliers = ((dataset_content[col] - mean).abs() > 10 * std).sum()
                    if extreme_outliers > 0.01 * len(dataset_content):  # More than 1% are extreme outliers
                        corrupted_columns.append(col)
            except:
                # Skip columns that cause errors in calculation
                pass
        
        # Assign a quality label based on score
        if quality_score >= 95:
            quality_label = "high"
        elif quality_score >= 80:
            quality_label = "medium"
        else:
            quality_label = "low"
            
        return {
            "quality_score": round(quality_score, 2),
            "quality_label": quality_label,
            "missing_cells": int(missing_cells),
            "total_cells": int(total_cells),
            "duplicate_rows": int(duplicate_rows),
            "duplicate_percentage": round(duplicate_percentage, 2),
            "column_completeness": column_completeness,
            "potentially_corrupted_columns": corrupted_columns
        }
        
    except Exception as e:
        logger.error(f"Error calculating quality metrics: {str(e)}")
        return {
            "quality_score": 0,
            "error": str(e)
        }

def determine_granularity(dataset_content: pd.DataFrame, query: str, dataset_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determine the granularity of the dataset (what each row represents).
    
    Args:
        dataset_content: Pandas DataFrame containing the dataset
        query: The original user query for context
        dataset_metadata: Dictionary containing dataset title, description, org, etc.
        
    Returns:
        Dictionary with granularity information including:
        - granularity: String describing what each row represents
        - confidence: Confidence level in the determination
        - reasoning: Explanation of how granularity was determined
    """
    if not isinstance(dataset_content, pd.DataFrame):
        return {
            "granularity": "Unknown",
            "confidence": 0,
            "reasoning": "Not a valid DataFrame"
        }
    
    try:
        # Extract additional context from dataset_metadata
        title = dataset_metadata.get('title', 'Unknown Title')
        description = dataset_metadata.get('description', '')
        # Handle organization being a string or dict
        org_data = dataset_metadata.get('organization', {})
        if isinstance(org_data, str):
             organization_name = org_data
        elif isinstance(org_data, dict):
             organization_name = org_data.get('title', org_data.get('name', 'Unknown Organization'))
        else:
             organization_name = 'Unknown Organization'

        # Extract dataset information for the prompt
        column_info = []
        for col in dataset_content.columns:
            dtype = str(dataset_content[col].dtype)
            unique_count = dataset_content[col].nunique()
            unique_ratio = unique_count / len(dataset_content) if len(dataset_content) > 0 else 0
            sample_values = dataset_content[col].dropna().head(3).tolist()
            
            column_info.append({
                "name": col,
                "dtype": dtype,
                "unique_values": unique_count,
                "unique_ratio": round(unique_ratio, 3),
                "sample_values": sample_values
            })
        
        # Identify potential ID columns
        potential_ids = []
        for col in dataset_content.columns:
            if col.lower().endswith('id') or col.lower().endswith('_id') or col.lower() == 'id':
                potential_ids.append(col)
                
        # Identify date columns
        date_columns = []
        for col in dataset_content.columns:
            if pd.api.types.is_datetime64_dtype(dataset_content[col]) or 'date' in col.lower() or 'time' in col.lower():
                date_columns.append(col)
                
        # Identify geographic columns
        geo_columns = []
        geo_terms = ['zip', 'postal', 'city', 'state', 'county', 'country', 'latitude', 'longitude', 'address', 'location']
        for col in dataset_content.columns:
            if any(term in col.lower() for term in geo_terms):
                geo_columns.append(col)
        
        # Format column info for LLM
        column_info_str = "\n".join([
            f"- {col_info['name']} ({col_info['dtype']}): {col_info['unique_values']} unique values, " + 
            f"unique ratio: {col_info['unique_ratio']}, samples: {col_info['sample_values'][:50] if isinstance(col_info['sample_values'], str) else col_info['sample_values']}"
            for col_info in column_info[:20]  # Limit to 20 columns for prompt size
        ])
        
        if len(column_info) > 20:
            column_info_str += f"\n- ... and {len(column_info) - 20} more columns"
        
        # Create prompt for LLM, including the new context
        prompt = f"""Determine the granularity of this dataset (what each row represents).

USER QUERY: "{query}"

DATASET CONTEXT:
Title: {title}
Description: {description}
Organization: {organization_name}

DATASET STRUCTURE:
- Rows: {len(dataset_content)}
- Columns: {len(dataset_content.columns)}

COLUMN INFORMATION:
{column_info_str}

Potential ID columns: {potential_ids}
Date columns: {date_columns}
Geographic columns: {geo_columns}

DATA PREVIEW (first 3 rows):
{dataset_content.head(3).to_string()}

TASK:
Determine what each row in this dataset represents. Consider these granularity types:
1. Individual (person, case, patient, etc.)
2. Transaction (order, payment, etc.)
3. Event (incident, visit, etc.)
4. Time period (daily, monthly, yearly)
5. Geographic unit (zip code, county, state, etc.)
6. Entity (company, organization, etc.)
7. Aggregated data (summary statistics)

In your analysis:
- Use the DATASET CONTEXT (Title, Description, Org) to inform your decision.
- Look for ID columns that might indicate the unit of observation
- Check for date/time columns that might indicate temporal granularity
- Consider geographic columns for spatial granularity
- Examine unique value counts - columns with many unique values are often identifiers
- Look for repetition patterns in the data

Format your response exactly as:
GRANULARITY: [brief 2-5 word description of what each row represents]
CONFIDENCE: [0-100 percentage representing your confidence]
REASONING: [2-3 sentence explanation of your determination]
"""

        # Call the LLM
        system_message = "You are a data analyst specializing in understanding dataset structure and organization. Be concise and precise."
        response = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1
        )
        
        # Parse the response
        import re # Ensure re is imported if not already at top level
        
        granularity_match = re.search(r'GRANULARITY:\s*(.*?)(?:\nCONFIDENCE:|$)', response, re.DOTALL)
        confidence_match = re.search(r'CONFIDENCE:\s*(.*?)(?:\nREASONING:|$)', response, re.DOTALL)
        reasoning_match = re.search(r'REASONING:\s*(.*)', response, re.DOTALL)
        
        granularity = granularity_match.group(1).strip() if granularity_match else "Unknown"
        
        # Parse confidence as a number
        confidence_str = confidence_match.group(1).strip() if confidence_match else "0"
        confidence = 0
        try:
            # Handle percentages like "80%" or numbers like "80"
            confidence_str = confidence_str.rstrip('%')
            confidence = float(confidence_str)
        except:
            confidence = 0
            
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "No explanation provided"
        
        # Return the results
        return {
            "granularity": granularity,
            "confidence": confidence,
            "reasoning": reasoning
        }
        
    except Exception as e:
        logger.error(f"Error determining granularity: {str(e)}")
        return {
            "granularity": "Unknown",
            "confidence": 0,
            "reasoning": f"Error in determination: {str(e)}"
        }

def refine_time_range_with_llm(time_range_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uses an LLM to check if the extracted time range is plausible.
    If min > max or they're obviously out-of-bound, it can try to refine or recommend ignoring them.
    """
    if not time_range_info.get('has_time_data'):
        return time_range_info  # No changes if there's no time data.

    claimed_min = str(time_range_info.get('min', 'N/A'))
    claimed_max = str(time_range_info.get('max', 'N/A'))
    if not claimed_min and not claimed_max:
        return time_range_info  # nothing to refine

    system_message = "You are a helpful assistant that checks for obviously invalid or improbable dates."
    prompt = f"""We have a dataset with a claimed time range from {claimed_min} to {claimed_max}.
    Are these obviously invalid or from a far-future year? If so, propose a corrected time range if possible.
    Otherwise, confirm that the range is plausible.
    Respond with JSON in the format:
    {{\"is_plausible\": true/false, \"min\": <corrected_min_or_original>, \"max\": <corrected_max_or_original>, \"reason\": <short explanation>}}"""

    llm_response = chat_completion(
        prompt=prompt,
        system_message=system_message,
        temperature=0.0
    )

    import json
    try:
        parsed = json.loads(llm_response)
        if not isinstance(parsed, dict) or 'is_plausible' not in parsed:
            return time_range_info  # Malformed LLM reply, fallback.
        is_plausible = parsed.get('is_plausible', True)
        refined_min = str(parsed.get('min', claimed_min)).strip()
        refined_max = str(parsed.get('max', claimed_max)).strip()
        reason = parsed.get('reason', '')

        if not is_plausible:
            # Possibly set has_time_data=False if it's truly invalid, or store the refined times.
            # We'll store the refined anyway, but add a 'note'.
            time_range_info['reason'] = f"LLM flagged as implausible or corrected. {reason}"
        # Merge updated min/max
        time_range_info['min'] = refined_min
        time_range_info['max'] = refined_max
        return time_range_info
    except Exception as e:
        # We just fallback if parse fails.
        return time_range_info

def extract_time_range_llm(dataset_content: pd.DataFrame, dataset_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Called if no explicit date columns or time info is found in the data.
    We'll pass relevant info (e.g. dataset title, shape, first few rows, etc.)
    to an LLM, asking it to guess a time range or declare none.
    Return a structure in the same format: {"has_time_data": bool, "min":..., "max":..., "reason":..., ...}
    """
    system_message = "You are a helpful assistant that determines the approximate time range of a dataset by looking at metadata, columns, and sample rows."

    title = dataset_metadata.get('title', 'No Title')
    description = dataset_metadata.get('description', '')
    org_data = dataset_metadata.get('organization', {})
    if isinstance(org_data, dict):
        org_name = org_data.get('title') or org_data.get('name') or 'Unknown Organization'
    else:
        org_name = str(org_data) if org_data else 'Unknown Organization'

    shape_str = f"{len(dataset_content)} rows, {len(dataset_content.columns)} cols"
    sample_rows = dataset_content.head(3).to_dict(orient='records') if not dataset_content.empty else []
    columns_list = list(dataset_content.columns)

    prompt = f"""We have a dataset with the following metadata:\nTitle: {title}\nDescription: {description}\nOrganization: {org_name}\nShape: {shape_str}\nColumns: {columns_list}\nSample rows (up to 3): {sample_rows}\n\nWe couldn't find any explicit date/datetime columns automatically. Please guess if there's a time range or time period indicated in this data or its metadata.\n\nRespond in valid JSON with the format:\n{{\"has_time_data\": <true or false>, \"min\": <YYYY-MM-DD or empty>, \"max\": <YYYY-MM-DD or empty>, \"reason\": <string explaining your reasoning>}}\n"""

    llm_response = chat_completion(
        prompt=prompt,
        system_message=system_message,
        temperature=0.1,
        max_tokens=300
    )

    import json
    try:
        parsed = json.loads(llm_response)
        if not isinstance(parsed, dict) or 'has_time_data' not in parsed:
            return {
                "has_time_data": False,
                "reason": "LLM response not parseable"
            }
        # We'll trust the keys if present
        return {
            "has_time_data": bool(parsed.get('has_time_data', False)),
            "min": parsed.get('min', None),
            "max": parsed.get('max', None),
            "reason": parsed.get('reason', '')
        }
    except Exception as e:
        return {
            "has_time_data": False,
            "error": f"Error parsing LLM response: {e}"
        }

def extract_time_range(dataset_content: pd.DataFrame, dataset_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Extract the time range from a dataset.
    1) If we find an explicit datetime64 column, we use that.
    2) Otherwise, we do a single LLM call with context to guess if there's a time range.
    """
    if not isinstance(dataset_content, pd.DataFrame):
        return {
            "has_time_data": False,
            "error": "Not a valid DataFrame"
        }
    if dataset_metadata is None:
        dataset_metadata = {}

    try:
        # Step 1: Look for actual datetime columns
        datetime_cols = dataset_content.select_dtypes(include=["datetime64"]).columns.tolist()
        if datetime_cols:
            # Use the first one to get min/max
            col = datetime_cols[0]
            date_series = dataset_content[col]
            if date_series.isna().all():
                # All NaN, fallback
                return extract_time_range_llm(dataset_content, dataset_metadata)
            min_date = date_series.min()
            max_date = date_series.max()
            if pd.isna(min_date) or pd.isna(max_date):
                return extract_time_range_llm(dataset_content, dataset_metadata)
            min_date_str = min_date.strftime('%Y-%m-%d')
            max_date_str = max_date.strftime('%Y-%m-%d')
            return {
                "has_time_data": True,
                "min": min_date_str,
                "max": max_date_str,
                "column": col,
                "reason": "Found explicit datetime column"
            }
        else:
            # Step 2: if no datetime columns, ask LLM
            return extract_time_range_llm(dataset_content, dataset_metadata)

    except Exception as e:
        logger.error(f"Error extracting time range: {str(e)}")
        return {
            "has_time_data": False,
            "error": str(e)
        }

def enrich_dataset_metadata(dataset_content: pd.DataFrame, query: str, dataset_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Comprehensive function to enrich dataset metadata with quality metrics,
    granularity information, and time range.
    
    Args:
        dataset_content: Pandas DataFrame containing the dataset
        query: The original user query for context
        dataset_metadata: Dictionary containing dataset title, description, org, etc.
        
    Returns:
        Dictionary with enriched metadata
    """
    if not isinstance(dataset_content, pd.DataFrame):
        return {
            "enrichment_error": "Not a valid DataFrame"
        }
    
    try:
        # Calculate basic dimensions
        dimensions = {
            "rows": len(dataset_content),
            "columns": len(dataset_content.columns),
            "column_names": list(dataset_content.columns)
        }
        
        # Calculate head preview
        head_preview = None
        has_preview_flag = False
        try:
            # Generate preview only if dataframe is not empty
            if not dataset_content.empty:
                # Use NumpyEncoder compatible format
                head_preview_df = dataset_content.head(5)
                # Convert DataFrame head to list of dicts, handling potential NaN/Inf
                head_preview = json.loads(json.dumps(head_preview_df.to_dict(orient='records'), cls=NumpyEncoder))
                if head_preview: # Ensure preview is not empty
                    has_preview_flag = True
        except Exception as preview_err:
            logger.warning(f"Could not generate head preview: {preview_err}")
            head_preview = None
            has_preview_flag = False

        # Calculate quality metrics
        quality = calculate_quality_metrics(dataset_content)
        
        # Determine granularity - pass dataset_metadata here
        granularity = determine_granularity(dataset_content, query, dataset_metadata)
        
        # Extract time range
        time_range = extract_time_range(dataset_content, dataset_metadata)
        
        # Return the combined enriched metadata, including preview info
        return {
            "dimensions": dimensions,
            "quality": quality,
            "granularity": granularity,
            "time_range": time_range,
            "head_preview": head_preview,
            "has_preview": has_preview_flag,
            "enrichment_timestamp": pd.Timestamp.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error enriching dataset metadata: {str(e)}")
        return {
            "enrichment_error": str(e)
        }


# --- Download and Preview Helper (for search_and_download mode) ---

# def preview_dataset(dataset, start_time):
#     """
#     Downloads, loads, and generates preview messages for a single dataset.
#     Yields JSON string messages.
#     """
#     ds_id = dataset.get('id', 'unknown_preview_' + str(time.time()))
#     title = dataset.get('title', 'Untitled Dataset')
#     resource_url = dataset.get('resource_url') # Assumes assessment added this
#     resources = dataset.get('resources', [])

#     # If resource_url wasn't determined by assessment, try finding the best one now
#     if not resource_url and resources:
#          logger.info(f"No pre-determined resource_url for {ds_id}, finding best resource...")
#          try:
#              # We need the original query to find the best resource if not pre-selected
#              # This is a limitation here; ideally, the query context should be available.
#              # For now, we'll just pick the first resource if URL is missing.
#              # A better approach would be to ensure assessment *always* sets resource_url if relevant.
#              if resources and isinstance(resources, list) and len(resources) > 0:
#                   best_resource = resources[0] # Fallback: use the first resource
#                   resource_url = best_resource.get('url')
#                   logger.warning(f"Falling back to first resource URL for {ds_id}: {resource_url}")
#              else:
#                   logger.error(f"No resources found for dataset {ds_id} to determine download URL.")

#          except Exception as e:
#               logger.error(f"Error getting best resource for {ds_id}: {e}")
#               yield create_error_message(f"Could not determine resource to download for {title}.", start_time=start_time, dataset_id=ds_id)
#               return # Stop processing this dataset

#     if not resource_url:
#         logger.warning(f"No resource URL available for dataset {ds_id} ('{title}'). Cannot download.")
#         yield create_error_message(f'No download URL found for dataset {title}.', start_time=start_time, dataset_id=ds_id)
#         return # Stop processing this dataset

#     # Attempt download
#     yield create_status_message(f'Downloading: {title}...', start_time, dataset_id=ds_id, status='downloading')
#     local_file = None
#     download_dir = '/tmp/dataset_downloads' # Use specific temp subdir
#     os.makedirs(download_dir, exist_ok=True)

#     try:
#         # Construct a filename - use dataset ID and try to get extension
#         file_ext = os.path.splitext(resource_url.split('?')[0])[1] # Basic extension extraction
#         if not file_ext and resources: # Fallback to format if no extension in URL
#              file_ext = "." + resources[0].get('format','').lower() if resources[0].get('format') else ".data"

#         filename = f"{ds_id}{file_ext}"
#         logger.info(f"Attempting download of {resource_url} to {os.path.join(download_dir, filename)}")
#         local_file = download_resource(resource_url, download_dir, filename=filename, max_download_time=30) # Increased timeout

#     except Exception as e:
#         logger.error(f"Download failed for {ds_id} ('{title}') from {resource_url}: {str(e)}")
#         yield create_error_message(f'Download failed for {title}: {str(e)}', start_time=start_time, dataset_id=ds_id)
#         return

#     if not local_file or not os.path.exists(local_file):
#         logger.error(f"Download function returned no valid file path for {ds_id} ('{title}').")
#         yield create_error_message(f'Download did not produce a file for {title}.', start_time=start_time, dataset_id=ds_id)
#         return

#     yield create_status_message(f'Downloaded: {title}. Loading...', start_time, dataset_id=ds_id, status='loading')

#     # Attempt to load via load_datafile
#     df = None
#     load_error = None
#     try:
#         # Determine format if possible (useful for load_datafile)
#         file_format = None
#         if resources and isinstance(resources, list) and len(resources) > 0:
#             file_format = resources[0].get('format') # Use format from metadata if available

#         df = load_datafile(local_file, file_format=file_format) # Pass format hint

#         if df is None:
#              raise ValueError("load_datafile returned None.")

#         # Successfully loaded
#         yield create_status_message(f'Loaded: {title}. Preparing preview...', start_time, dataset_id=ds_id, status='previewing')

#         # Check if it's a DataFrame for shape/head preview
#         if hasattr(df, 'shape') and hasattr(df, 'head'):
#             row_count, col_count = df.shape
#             # Send shape info
#             shape_msg = json.dumps({
#                 'type': 'dataset_download', # Reusing type for simplicity
#                 'data': {
#                     'id': ds_id,
#                     'downloaded': True,
#                     'loaded': True,
#                     'rows': row_count,
#                     'cols': col_count,
#                     'preview_available': True,
#                 },
#                 'timestamp': time.time() - start_time
#             }, cls=NumpyEncoder) + "\n"
#             yield shape_msg

#             # Send first 5 rows preview
#             head_rows = df.head(5) # Keep as DataFrame for NumpyEncoder
#             head_msg = json.dumps({
#                 'type': 'dataset_preview',
#                 'data': {
#                     'id': ds_id,
#                     'head': head_rows # Let NumpyEncoder handle DataFrame serialization
#                 },
#                 'timestamp': time.time() - start_time
#             }, cls=NumpyEncoder) + "\n"
#             yield head_msg
#         else:
#             # Loaded, but not a standard DataFrame (e.g., could be text, JSON dict)
#             yield create_status_message(f'Loaded {title} (non-tabular data).', start_time, dataset_id=ds_id, status='complete')
#             yield json.dumps({
#                 'type': 'dataset_download',
#                 'data': {
#                     'id': ds_id,
#                     'downloaded': True,
#                     'loaded': True,
#                     'message': 'Loaded non-tabular data.',
#                     'preview_available': False
#                  },
#                 'timestamp': time.time() - start_time
#             }, cls=NumpyEncoder) + "\n"

#     except Exception as e:
#         logger.error(f"Error loading or previewing dataset {ds_id} ('{title}') from {local_file}: {str(e)}")
#         logger.error(traceback.format_exc())
#         load_error = str(e)
#         # Send error message related to loading/previewing
#         yield create_error_message(f'Error loading/previewing {title}: {load_error}', start_time=start_time, dataset_id=ds_id)
#         # Send status update that download happened but loading failed
#         yield json.dumps({
#                 'type': 'dataset_download',
#                 'data': {
#                     'id': ds_id,
#                     'downloaded': True,
#                     'loaded': False,
#                     'error': f'Loading/Preview Error: {load_error}',
#                     'preview_available': False
#                  },
#                 'timestamp': time.time() - start_time
#             }, cls=NumpyEncoder) + "\n"

#     finally:
#         # Clean up downloaded file
#         if local_file and os.path.exists(local_file):
#             try:
#                 os.remove(local_file)
#                 logger.info(f"Cleaned up temporary file: {local_file}")
#             except OSError as e:
#                 logger.warning(f"Could not remove temporary file {local_file}: {e}")
