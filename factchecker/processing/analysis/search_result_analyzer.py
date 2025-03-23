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
) -> Dict[str, Any]:
    """
    Assess if a dataset is likely to be relevant to the user's query using only metadata,
    before downloading the actual data.
    
    Args:
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description, etc.)
        relevance_threshold: Threshold for considering a dataset relevant (0-1)
        
    Returns:
        Dictionary containing assessment results:
        {
            'is_relevant': bool,
            'relevance_score': float,
            'reasoning': str,
            'resource_url': str or None,
            'resource_format': str or None
        }
    """
    # Debug print the dataset we're assessing
    logger.debug(f"DATASET that we're assessing datafile relevance on: {dataset_metadata}")
    
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
    if isinstance(org, str):
        org_name = org
    
    # Extract geospatial and temporal scopes
    geo_scope, temp_scope = extract_dataset_scopes(title, description, org_name, tags_str)
    
    # Get resources information
    resources = dataset_metadata.get('resources', [])
    resources_str = ""
    for i, resource in enumerate(resources):
        format_type = resource.get('format', 'unknown')
        name = resource.get('name', f'Resource {i+1}')
        resources_str += f"Resource {i+1}: {name} (Format: {format_type})\n"
    
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

AVAILABLE RESOURCES:
{resources_str if resources_str else "No resources available"}

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

4. Resource Selection (Only if dataset is relevant):
 - If the dataset is relevant (score >= 0.4), recommend the most appropriate resource from the available resources.
 - Prefer CSV format for tabular data as it's most accessible, then JSON, then XML.
 - If no clear preference based on format, select the resource that seems most comprehensive or relevant to the query.

Please provide:
1. A relevance score from 0.00 to 1.00, where:
- 0.00: Not relevant (including ANY geographic/temporal mismatch)
- 0.40-0.69: Potentially relevant (only if passes both geographic and temporal checks and subject matter is somewhat relevant)
- 0.70-1.00: Relevant with high confidence (only if passes ALL criteria easily)
2. A brief explanation of your reasoning (2-3 sentences)
3. If score >= 0.4, recommend which resource to use and why

Format your response exactly as follows:
SCORE: [score]
REASONING: [your reasoning]
RESOURCE: [resource number or "none" if score < 0.4 or no resources available]
RESOURCE_REASONING: [why you selected this resource or "not applicable" if score < 0.4 or no resources available]
'''
    
    system_message = "You are a data analyst who specializes in evaluating dataset relevance. Be concise and accurate."
    
    try:
        response_text = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1
        )
        
        # Parse the response
        score_match = re.search(r'SCORE:\s*([\d.]+)', response_text)
        reasoning_match = re.search(r'REASONING:\s*(.*?)(?:\nRESOURCE:|$)', response_text, re.DOTALL)
        resource_match = re.search(r'RESOURCE:\s*(.*?)(?:\nRESOURCE_REASONING:|$)', response_text, re.DOTALL)
        resource_reasoning_match = re.search(r'RESOURCE_REASONING:\s*(.*)', response_text, re.DOTALL)
        
        if score_match and reasoning_match:
            score = float(score_match.group(1))
            reasoning = reasoning_match.group(1).strip()
            is_relevant = score >= relevance_threshold
            
            # Get resource selection if available
            resource_selection = resource_match.group(1).strip() if resource_match else "none"
            resource_reasoning = resource_reasoning_match.group(1).strip() if resource_reasoning_match else "not applicable"
            
            # Initialize resource information
            resource_url = None
            resource_format = None
            
            # If relevant and resources exist, find the selected resource
            if is_relevant and resources and resource_selection != "none":
                try:
                    # Check if it's a number (Resource 1, Resource 2, etc.)
                    if resource_selection.isdigit():
                        resource_index = int(resource_selection) - 1
                        if 0 <= resource_index < len(resources):
                            selected_resource = resources[resource_index]
                            resource_url = selected_resource.get('url')
                            resource_format = selected_resource.get('format')
                    # Or it might be "Resource X"
                    elif resource_selection.startswith("Resource ") and resource_selection[9:].isdigit():
                        resource_index = int(resource_selection[9:]) - 1
                        if 0 <= resource_index < len(resources):
                            selected_resource = resources[resource_index]
                            resource_url = selected_resource.get('url')
                            resource_format = selected_resource.get('format')
                except (ValueError, IndexError):
                    pass
                
                # If we couldn't parse the resource selection, fall back to format preference
                if resource_url is None:
                    # First try to find CSV
                    for resource in resources:
                        if resource.get('format', '').lower() == 'csv':
                            resource_url = resource.get('url')
                            resource_format = 'csv'
                            break
                        
                    # If no CSV, try JSON
                    if resource_url is None:
                        for resource in resources:
                            if resource.get('format', '').lower() == 'json':
                                resource_url = resource.get('url')
                                resource_format = 'json'
                                break
                            
                    # If no JSON, try XML
                    if resource_url is None:
                        for resource in resources:
                            if resource.get('format', '').lower() == 'xml':
                                resource_url = resource.get('url')
                                resource_format = 'xml'
                                break
                            
                    # If still no resource found, use the first one if available
                    if resource_url is None and resources:
                        resource_url = resources[0].get('url')
                        resource_format = resources[0].get('format')
            
            # Return the assessment results as a dictionary
            return {
                'is_relevant': is_relevant,
                'relevance_score': score,
                'reasoning': reasoning,
                'resource_url': resource_url,
                'resource_format': resource_format,
                'resource_reasoning': resource_reasoning
            }
        else:
            logger.warning(f"Failed to parse relevance assessment response: {response_text}")
            return {
                'is_relevant': False,
                'relevance_score': 0.3,
                'reasoning': "Failed to parse relevance assessment, defaulting to not relevant",
                'resource_url': None,
                'resource_format': None,
                'resource_reasoning': "not applicable"
            }
    except Exception as e:
        logger.error(f"Error in pre-download relevance assessment: {str(e)}")
        return {
            'is_relevant': False,
            'relevance_score': 0.3,
            'reasoning': f"Error in assessment: {str(e)}",
            'resource_url': None,
            'resource_format': None,
            'resource_reasoning': "Error occurred during resource selection"
        } 