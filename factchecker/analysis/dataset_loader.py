import pandas as pd
import os
import openai
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging
import re

"""
This module handles loading and processing datasets for the factchecker application.
It provides utilities for loading datasets from various file formats, assessing their
relevance to user queries, and preparing them for further analysis.
"""

def load_dataset(file_path: str) -> pd.DataFrame:
    """
    Load a dataset (CSV or Excel) with appropriate error handling.
    
    Args:
        file_path: Path to the dataset file
        
    Returns:
        Pandas DataFrame containing the dataset
    """
    logger = logging.getLogger("data_loading")
    logger.info(f"Loading dataset from {file_path}")
    
    file_extension = os.path.splitext(file_path)[1].lower()
    
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

def assess_dataset_relevance(
    df: pd.DataFrame, 
    query: str, 
    dataset_metadata: Dict[str, Any],
    openai_api_key: str,
    relevance_threshold: float = 0.7
) -> Tuple[bool, float, str]:
    """
    Assess if a dataset is relevant to the user's query using OpenAI.
    
    Args:
        df: The dataset as a pandas DataFrame
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
    
    # Get column information
    columns = list(df.columns)
    column_info = []
    for col in columns:
        dtype = str(df[col].dtype)
        sample_values = df[col].dropna().head(3).tolist()
        column_info.append(f"- {col} ({dtype}): {sample_values}")
    
    # Get sample rows
    sample_rows = df.head(5).to_string(index=False)
    
    # Search for key terms from the query in the entire dataset
    # Extract key terms from query
    key_terms = query.lower().split()
    
    # Search for these terms in the dataset
    term_presence = {}
    for term in key_terms:
        if len(term) > 3:  # Only search for meaningful terms (longer than 3 chars)
            # Check if term appears in any string column
            found = False
            for col in df.select_dtypes(include=['object']).columns:
                # Sample a subset of the data to avoid performance issues with large datasets
                sample_size = min(1000, len(df))
                if df[col].sample(sample_size).astype(str).str.contains(term, case=False).any():
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