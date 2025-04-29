"""
Utility functions for enriching dataset metadata with quality metrics and granularity information.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, List
import logging
from factchecker.utils.openai_client import chat_completion
import re # Import re module

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
            "granularity": "unknown",
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
        
        granularity = granularity_match.group(1).strip() if granularity_match else "unknown"
        
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
            "granularity": "unknown",
            "confidence": 0,
            "reasoning": f"Error in determination: {str(e)}"
        }

def extract_time_range(dataset_content: pd.DataFrame) -> Dict[str, Any]:
    """
    Extract the time range covered by the dataset.
    
    Args:
        dataset_content: Pandas DataFrame containing the dataset
        
    Returns:
        Dictionary with time range information including:
        - min: Minimum date/time value
        - max: Maximum date/time value
        - column: The column used for extraction
        - has_time_data: Boolean indicating if time data was found
    """
    if not isinstance(dataset_content, pd.DataFrame):
        return {
            "has_time_data": False,
            "error": "Not a valid DataFrame"
        }
    
    try:
        # Look for datetime columns first
        datetime_cols = dataset_content.select_dtypes(include=['datetime64']).columns.tolist()
        
        # If no datetime columns, look for columns with date-related names
        if not datetime_cols:
            date_related_terms = ['date', 'time', 'year', 'month', 'day', 'period']
            potential_date_cols = [col for col in dataset_content.columns 
                                if any(term in col.lower() for term in date_related_terms)]
            
            # Try to convert these columns to datetime
            for col in potential_date_cols:
                try:
                    # Skip if column has too many missing values
                    if dataset_content[col].isna().sum() > 0.5 * len(dataset_content):
                        continue
                        
                    # For numeric columns that might be years
                    if pd.api.types.is_numeric_dtype(dataset_content[col]):
                        # Check if values look like years (typically between 1900-2100)
                        min_val = dataset_content[col].min()
                        max_val = dataset_content[col].max()
                        
                        if 1900 <= min_val <= 2100 and 1900 <= max_val <= 2100:
                            return {
                                "has_time_data": True,
                                "min": int(min_val),
                                "max": int(max_val),
                                "column": col,
                                "type": "year"
                            }
                    
                    # Try to parse as datetime for string columns
                    elif pd.api.types.is_string_dtype(dataset_content[col]) or pd.api.types.is_object_dtype(dataset_content[col]):
                        # Sample the column to check if values can be parsed as dates
                        sample = dataset_content[col].dropna().head(100)
                        if len(sample) > 0:
                            pd.to_datetime(sample, errors='raise')
                            datetime_cols.append(col)
                except:
                    pass
        
        # If we found datetime columns, extract the range
        if datetime_cols:
            # Use the first datetime column
            col = datetime_cols[0]
            
            # Convert to datetime if not already
            if not pd.api.types.is_datetime64_dtype(dataset_content[col]):
                try:
                    date_series = pd.to_datetime(dataset_content[col], errors='coerce')
                except:
                    return {
                        "has_time_data": False,
                        "error": f"Failed to convert column {col} to datetime"
                    }
            else:
                date_series = dataset_content[col]
            
            # Get min and max dates
            min_date = date_series.min()
            max_date = date_series.max()
            
            # Check if we got valid dates
            if pd.isna(min_date) or pd.isna(max_date):
                return {
                    "has_time_data": False,
                    "error": "Date values are all NaN"
                }
            
            # Format dates as strings
            min_date_str = min_date.strftime('%Y-%m-%d') if hasattr(min_date, 'strftime') else str(min_date)
            max_date_str = max_date.strftime('%Y-%m-%d') if hasattr(max_date, 'strftime') else str(max_date)
            
            return {
                "has_time_data": True,
                "min": min_date_str,
                "max": max_date_str,
                "column": col,
                "type": "datetime"
            }
        
        # If we got here, we couldn't find time data
        return {
            "has_time_data": False,
            "reason": "No time-related columns identified"
        }
        
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
        
        # Calculate quality metrics
        quality = calculate_quality_metrics(dataset_content)
        
        # Determine granularity - pass dataset_metadata here
        granularity = determine_granularity(dataset_content, query, dataset_metadata)
        
        # Extract time range
        time_range = extract_time_range(dataset_content)
        
        # Return the combined enriched metadata
        return {
            "dimensions": dimensions,
            "quality": quality,
            "granularity": granularity,
            "time_range": time_range,
            "enrichment_timestamp": pd.Timestamp.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error enriching dataset metadata: {str(e)}")
        return {
            "enrichment_error": str(e)
        }
