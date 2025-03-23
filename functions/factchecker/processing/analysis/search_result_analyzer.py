from typing import Dict, Tuple, Any
import logging
import re
from datetime import datetime

from factchecker.utils.openai_client import chat_completion

logger = logging.getLogger(__name__)

def extract_dataset_scopes(title: str, description: str, org_name: str, tags: str) -> Tuple[str, str]:
    """
    Extract the geospatial and temporal scopes from dataset metadata.
    
    Args:
        title: Dataset title
        description: Dataset description
        org_name: Organization name
        tags: Dataset tags as string
        
    Returns:
        Tuple of (geospatial_scope, temporal_scope) where each is a string describing the scope
        or "no specifications" if not found
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_year = datetime.now().year

    prompt = f'''Extract the geographic and temporal scope from this dataset metadata.
Today's date is {current_date} for reference when interpreting temporal information.

DATASET METADATA:
Title: {title}
Description: {description}
Organization: {org_name}
Tags: {tags}

TASK:
1. Identify the geographic scope (e.g., "San Francisco", "California", "United States", etc.), heavily weighing the organization name ({org_name}) and title ({title})
   - PAY SPECIAL ATTENTION to organization names - they often indicate geographic scope, e.g. "City of Philadelphia", "NYC Department"
   - City/State/County departments (e.g., "City of Philadelphia", "NYC Department") indicate specific geographic bounds
   - If organization name contains a location, this is a STRONG indicator of geographic scope
   - Regional authorities (e.g., "Bay Area Transit Authority") define their geographic scope
   - If no geographic information exists, use "no specifications" (not "unknown")

2. Identify the temporal scope (e.g., "2015-2019", "2020", "current", etc.)
   - When dataset mentions "current" or "present", interpret as {current_year}
   - For relative time references, calculate based on current year {current_year}
   - If no temporal information exists, use "no specifications" (not "unknown")

Format your response exactly as:
GEOGRAPHIC: [scope or "no specifications"]
TEMPORAL: [scope or "no specifications"]

Examples:
- If title is "Air Quality Data" and org is "City of Philadelphia", return "GEOGRAPHIC: Philadelphia"
- If org is "NYC Department of Health" but no dates, return "GEOGRAPHIC: New York City\nTEMPORAL: no specifications"
- If org is "California State Water Board" and title is "National Water Quality", return "GEOGRAPHIC: California"
- If description mentions "nationwide statistics" but org is "Boston Public Health", return "GEOGRAPHIC: Boston"
- If org contains no location and no other geographic indicators exist, return "GEOGRAPHIC: no specifications"
- If description says "last 5 years", return temporal as "{current_year-5}-{current_year}"
- If description says "current data", return temporal as "{current_year}"
'''

    try:
        response = chat_completion(
            prompt=prompt,
            system_message="You are a data analyst who extracts geographic and temporal information from dataset metadata. Be precise and concise.",
            temperature=0.1
        )
        
        geo_match = re.search(r'GEOGRAPHIC:\s*(.*)', response)
        temp_match = re.search(r'TEMPORAL:\s*(.*)', response)
        
        geo_scope = geo_match.group(1).strip() if geo_match else "no specifications"
        temp_scope = temp_match.group(1).strip() if temp_match else "no specifications"
        
        return (geo_scope, temp_scope)
    except Exception as e:
        logger.error(f"Error extracting scopes: {str(e)}")
        return ("no specifications", "no specifications")

def assess_datafile_relevance_predownload(
    query: str, 
    dataset_metadata: Dict[str, Any],
    relevance_threshold: float = 0.4
) -> Tuple[bool, float, str]:
    """
    Assess if a dataset is likely to be relevant to the user's query using only metadata,
    before downloading the actual data.
    
    Args:
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description, etc.)
        relevance_threshold: Threshold for considering a dataset relevant (0-1)
        
    Returns:
        Tuple of (is_relevant, relevance_score, reasoning)
    """
    # Get dataset information
    title = dataset_metadata.get('title', 'Unknown')
    description = dataset_metadata.get('description', '')
    
    # Extract any additional metadata that might be useful
    tags = dataset_metadata.get('tags', [])
    if isinstance(tags, list):
        tags_str = ", ".join([str(tag) for tag in tags])
    else:
        tags_str = str(tags)
    
    # Get organization info if available
    org = dataset_metadata.get('organization', {})
    org_name = org.get('name', '') if isinstance(org, dict) else ''
    
    # Extract geospatial and temporal scopes
    geo_scope, temp_scope = extract_dataset_scopes(title, description, org_name, tags_str)
    
    # Create prompt for OpenAI
    prompt = f'''You are assessing whether a dataset is likely to be relevant to a user's query based ONLY on the metadata given.

USER QUERY: "{query}"

DATASET METADATA:
Title: {title}
Description: {description}
Tags: {tags_str}
Organization: {org_name}
Geographic Scope: {geo_scope}
Temporal Scope: {temp_scope}

ASSESSMENT FLOW:

1. Geographic Match (Hard Requirement):
- Check if query's location matches or is contained within dataset's Geographic Scope: {geo_scope}
- If the scope is "no specifications", consider it compatible with any location in the query
- If there is a clear mismatch, score 0.0 and stop
- Example: Query "San Francisco air quality" fails for scope "New York" but passes for "California", "United States", or "no specifications"

2. Temporal Match (Hard Requirement):
- Check if query's time period is compatible with dataset's Temporal Scope: {temp_scope}
- If the scope is "no specifications", consider it compatible with any time period in the query
- If there is a clear mismatch, score 0.0 and stop
- Example: Query "homelessness 2013" fails for scope "2015-2019" but passes for "2010-2015" or "no specifications"

3. Subject Match (Only if above checks pass): 
 - Determine if the dataset's subject matter (from the title, description, tags, or organization focus) aligns with the user's query. 
 - Consider only the information explicitly provided in the metadata. Avoid assuming that data exists if not mentioned. 
 - If the query has specific topics that appear to be a subset of the dataset's broader topic, treat it as potentially relevant (e.g., "orange grove emissions factors" could be covered by a dataset on "emissions factors for agriculture", "downtown Chicago crime rates" would be relevant for "Illinois crime statistics", "elementary school test scores in Boston" would be relevant for "Massachusetts education performance data", "solar panel efficiency in desert conditions" would be relevant for "renewable energy performance metrics").
 - If the dataset's subject matter clearly does not match the query, score 0.0.

Please provide:
1. A relevance score from 0.00 to 1.00, where:
- 0.00: Not relevant (including ANY geographic/temporal mismatch)
- 0.40-0.69: Potentially relevant (only if passes both geographic and temporal checks and subject matter is somewhat relevant)
- 0.70-1.00: Relevant with high confidence (only if passes ALL criteria easily)
2. A brief explanation of your reasoning (2-3 sentences)

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
'''
    
    system_message = "You are a data analyst who specializes in evaluating dataset relevance. Be concise and accurate."
    
    try:
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
            logger.warning(f"Failed to parse relevance assessment response: {response_text}")
            return (False, 0.3, "Failed to parse relevance assessment, defaulting to not relevant")
    except Exception as e:
        logger.error(f"Error in pre-download relevance assessment: {str(e)}")
        return (False, 0.3, f"Error in assessment: {str(e)}") 