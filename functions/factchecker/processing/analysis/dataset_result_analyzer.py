import json
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
            'resource_format': str or None,
            'resource_reasoning': str
        }
    """
    # Debug print the dataset we're assessing
    dataset_id = dataset_metadata.get('id', 'Unknown ID')
    dataset_title = dataset_metadata.get('title', 'Unknown Title')
    logger.info(f"Starting relevance assessment for dataset: {dataset_id} - {dataset_title}")
    
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
    prompt = f'''Evaluate if this dataset is relevant to the user's query based only on metadata.

USER QUERY: "{query}"

DATASET METADATA:
Title: {title}
Description: {description}
Tags: {tags_str}
Organization: {org_name}
Geographic Scope: {geo_scope}
Temporal Scope: {temp_scope}
Resources: {resources_str if resources_str else "None available"}

EVALUATION CRITERIA:
1. Geographic Match: Query location must match or be within dataset's geographic scope. If scope is "no specifications", consider compatible with any location. Score 0.0 for clear mismatch.

2. Temporal Match: Query time period must be compatible with dataset's temporal scope. If scope is "no specifications", consider compatible with any time period. Score 0.0 for clear mismatch.

3. Subject Match: Dataset's subject matter must align with query. Consider broader datasets that could contain specific query topics as relevant (e.g., "Illinois crime statistics" is relevant for "downtown Chicago crime rates").

4. Resource Selection: For relevant datasets (score ≥ 0.4), recommend the most appropriate resource. Prefer CSV > JSON > XML formats.

SCORING GUIDE:
- 0.00-0.39: Not relevant (including ANY geographic/temporal mismatch)
- 0.40-0.69: Potentially relevant (passes geographic/temporal checks, somewhat relevant subject)
- 0.70-1.00: Highly relevant (passes all criteria easily)

Format your response exactly as:
SCORE: [0.00-1.00]
REASONING: [2-3 sentence explanation]
RESOURCE: [resource number or "none" if score < 0.4 or no resources]
RESOURCE_REASONING: [brief explanation or "not applicable" if score < 0.4]
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

            relevance_dict = {
                'is_relevant': is_relevant,
                'relevance_score': score,
                'reasoning': reasoning,
                'resource_url': resource_url,
                'resource_format': resource_format,
                'resource_reasoning': resource_reasoning
            }
            print("Debug relevance:", relevance_dict)
            return relevance_dict
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

def get_best_resource(
    query: str, 
    dataset_metadata: Dict[str, Any]
) -> Dict[str, Any]:
    
    resources = dataset_metadata.get("resources", [])
    """
    Identify the best resource from a dataset for the user's query.
    
    Args:
        query: The original user query
        dataset_metadata: Metadata about the dataset (title, description, etc.)
        
    Returns:
        Dictionary containing:
        {
            'resource_id': str or None,
            'resource_url': str or None,
            'resource_format': str or None,
            'reasoning': str,
            'dataset_id': str or None  # Added dataset_id for folder creation
        }
    """
    # Get dataset ID for folder creation
    dataset_id = dataset_metadata.get('id') or dataset_metadata.get('dataset_id', 'unknown_dataset')
    
    # First check if any resource is already cached
    for resource in resources:
        if resource.get('is_cached') is True:
            # Get the resource URL, ensuring it's in a format that can be downloaded
            resource_url = resource.get('cache_uri')
            
            # If the URL is a GCS URL (gs://), convert it to an HTTPS URL for direct download
            if resource_url and resource_url.startswith('gs://'):
                # Convert gs:// URL to https://storage.googleapis.com/
                bucket_name = resource_url.split('/')[2]
                object_path = '/'.join(resource_url.split('/')[3:])
                resource_url = f"https://storage.googleapis.com/{bucket_name}/{object_path}"
            
            return {
                'resource_id': resource.get('id') or resource.get('resource_id'),
                'resource_url': resource_url,
                'resource_format': resource.get('format'),
                'reasoning': "Selected already cached resource for faster processing",
                'dataset_id': dataset_id
            }
    
    # If no cached resource found, proceed with the original logic
    # Create prompt for OpenAI
    prompt = f'''Select the most appropriate resource from this dataset for the user's query.

USER QUERY: "{query}"

DATASET METADATA:
{dataset_metadata}

TASK:
1. Analyze which resource would be most useful for answering the user's query
2. Prefer machine-readable formats (CSV > JSON > XML > others)
3. Consider resource names and descriptions for relevance to the query

Format your response exactly as:
RESOURCE: [resource number]
REASONING: [brief explanation of your selection]
'''
    
    system_message = "You are a data analyst who specializes in selecting the most appropriate data resources. Be concise and accurate."
    
    try:
        response_text = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1
        )
        
        # Parse the response
        resource_match = re.search(r'RESOURCE:\s*(.*?)(?:\nREASONING:|$)', response_text, re.DOTALL)
        reasoning_match = re.search(r'REASONING:\s*(.*)', response_text, re.DOTALL)
        
        resource_selection = resource_match.group(1).strip() if resource_match else "1"
        reasoning = reasoning_match.group(1).strip() if reasoning_match else "Default selection"
        
        # Initialize resource information
        resource_id = None
        resource_url = None
        resource_format = None
        
        # Try to find the selected resource
        try:
            # Check if it's a number (Resource 1, Resource 2, etc.)
            if resource_selection.isdigit():
                resource_index = int(resource_selection) - 1
                if 0 <= resource_index < len(resources):
                    selected_resource = resources[resource_index]
                    resource_id = selected_resource.get('id') or selected_resource.get('resource_id')
                    resource_url = selected_resource.get('url')
                    resource_format = selected_resource.get('format')
            # Or it might be "Resource X"
            elif resource_selection.startswith("Resource ") and resource_selection[9:].isdigit():
                resource_index = int(resource_selection[9:]) - 1
                if 0 <= resource_index < len(resources):
                    selected_resource = resources[resource_index]
                    resource_id = selected_resource.get('id') or selected_resource.get('resource_id')
                    resource_url = selected_resource.get('url')
                    resource_format = selected_resource.get('format')
        except (ValueError, IndexError):
            pass
        
        # If we couldn't parse the resource selection, fall back to format preference
        if resource_id is None:
            # First try to find CSV
            for resource in resources:
                if resource.get('format', '').lower() == 'csv':
                    resource_id = resource.get('id') or resource.get('resource_id')
                    resource_url = resource.get('url')
                    resource_format = 'csv'
                    reasoning = "Selected CSV format (most machine-readable)"
                    break
                
            # If no CSV, try JSON
            if resource_id is None:
                for resource in resources:
                    if resource.get('format', '').lower() == 'json':
                        resource_id = resource.get('id') or resource.get('resource_id')
                        resource_url = resource.get('url')
                        resource_format = 'json'
                        reasoning = "Selected JSON format (machine-readable)"
                        break
                    
            # If no JSON, try XML
            if resource_id is None:
                for resource in resources:
                    if resource.get('format', '').lower() == 'xml':
                        resource_id = resource.get('id') or resource.get('resource_id')
                        resource_url = resource.get('url')
                        resource_format = 'xml'
                        reasoning = "Selected XML format (structured data)"
                        break
                    
            # If still no resource found, use the first one if available
            if resource_id is None and resources:
                resource_id = resources[0].get('id') or resources[0].get('resource_id')
                resource_url = resources[0].get('url')
                resource_format = resources[0].get('format')
                reasoning = "Selected first available resource as fallback"
        
        # Return the resource selection results with dataset_id
        return {
            'resource_id': resource_id,
            'resource_url': resource_url,
            'resource_format': resource_format,
            'reasoning': reasoning,
            'dataset_id': dataset_id
        }
    except Exception as e:
        logger.error(f"Error in resource selection: {str(e)}")
        # Fallback to first resource if available
        if resources:
            return {
                'resource_id': resources[0].get('id') or resources[0].get('resource_id'),
                'resource_url': resources[0].get('url'),
                'resource_format': resources[0].get('format'),
                'reasoning': f"Error occurred during selection, defaulted to first resource: {str(e)}",
                'dataset_id': dataset_id
            }
        else:
            return {
                'resource_id': None,
                'resource_url': None,
                'resource_format': None,
                'reasoning': f"Error occurred and no resources available: {str(e)}",
                'dataset_id': dataset_id
            }
    
def format_extracted_data(
    extracted_data: Dict[str, Any],
    analysis_result: Dict[str, Any],
    query: str
) -> Dict[str, Any]:
    """
    Format extracted data into a consistent, user-friendly structure using LLM.
    
    Args:
        extracted_data: The raw extracted data from the dataset
        analysis_result: The dataset overview analysis
        query: The original user query
        
    Returns:
        Dictionary containing formatted data with explanations:
        {
            'formatted_data': {
                'summary': str,
                'subset_explanation': str,
                'temporal_scope': str,
                'geographic_scope': str,
                'aggregations': Dict[str, Dict[str, Any]],
                'visualizations': List[Dict[str, Any]] or None,
                'limitations': str,
                'code_explanation': str
            },
            'raw_data': Dict[str, Any]  # Original extracted data
        }
    """
    if not extracted_data:
        return {
            'formatted_data': {
                'summary': "No relevant data was extracted from this dataset.",
                'subset_explanation': "No data subset was created.",
                'temporal_scope': "Unknown",
                'geographic_scope': "Unknown",
                'aggregations': {},
                'visualizations': None,
                'limitations': "No data was extracted to analyze limitations.",
                'code_explanation': "No code was executed."
            },
            'raw_data': {}
        }
    
    # Get the dataset information
    dataset_title = extracted_data.get('dataset_title', 'Unknown dataset')
    dataset_source = extracted_data.get('dataset_source', 'Unknown source')
    
    # Get the results dictionary which contains the actual data
    results_dict = extracted_data.get('results_dict', {})
    data = results_dict.get('data', {})
    
    # Get the code and printed output
    code = extracted_data.get('code', '')
    printed_output = extracted_data.get('printed_output', '')
    
    # Create a prompt for the LLM
    prompt = f'''Format and explain the extracted data from a dataset in a consistent, user-friendly structure.

USER QUERY: "{query}"

DATASET INFORMATION:
Title: {dataset_title}
Source: {dataset_source}

EXTRACTED DATA:
{data}

CODE USED:
{code}

PRINTED OUTPUT:
{printed_output}

DATASET ANALYSIS:
{analysis_result.get('analysis', 'No analysis available')}

TASK:
Create a structured explanation of the extracted data with the following components:

1. Summary: A 2-3 sentence overview of what data was extracted and how it relates to the user query.

2. Subset Explanation: Explain what subset of the data was selected and why.

3. Temporal Scope: Identify the time period covered by the data.

4. Geographic Scope: Identify the geographic area covered by the data.

5. Aggregations: For each aggregation or calculation in the data, provide:
   - Name: A descriptive name
   - Value: The calculated value
   - Explanation: What this value means in context

6. Limitations: Note any limitations or caveats about the data that the user should be aware of.

7. Code Explanation: A plain language explanation of what the code did to extract and analyze the data.

Format your response exactly as:
SUMMARY: [2-3 sentence overview]
SUBSET_EXPLANATION: [explanation of data subset]
TEMPORAL_SCOPE: [time period or "Unknown"]
GEOGRAPHIC_SCOPE: [geographic area or "Unknown"]
AGGREGATIONS: [JSON object with name, value, and explanation for each aggregation]
LIMITATIONS: [limitations of the data]
CODE_EXPLANATION: [plain language explanation of code]
'''
    
    system_message = "You are a data analyst who specializes in explaining data analysis results clearly and accurately. Be concise and precise."
    
    try:
        response_text = chat_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.1
        )
        
        # Parse the response
        summary_match = re.search(r'SUMMARY:\s*(.*?)(?:\nSUBSET_EXPLANATION:|$)', response_text, re.DOTALL)
        subset_match = re.search(r'SUBSET_EXPLANATION:\s*(.*?)(?:\nTEMPORAL_SCOPE:|$)', response_text, re.DOTALL)
        temporal_match = re.search(r'TEMPORAL_SCOPE:\s*(.*?)(?:\nGEOGRAPHIC_SCOPE:|$)', response_text, re.DOTALL)
        geographic_match = re.search(r'GEOGRAPHIC_SCOPE:\s*(.*?)(?:\nAGGREGATIONS:|$)', response_text, re.DOTALL)
        aggregations_match = re.search(r'AGGREGATIONS:\s*(.*?)(?:\nLIMITATIONS:|$)', response_text, re.DOTALL)
        limitations_match = re.search(r'LIMITATIONS:\s*(.*?)(?:\nCODE_EXPLANATION:|$)', response_text, re.DOTALL)
        code_explanation_match = re.search(r'CODE_EXPLANATION:\s*(.*)', response_text, re.DOTALL)
        
        # Extract the matched content
        summary = summary_match.group(1).strip() if summary_match else "No summary available."
        subset_explanation = subset_match.group(1).strip() if subset_match else "No subset explanation available."
        temporal_scope = temporal_match.group(1).strip() if temporal_match else "Unknown"
        geographic_scope = geographic_match.group(1).strip() if geographic_match else "Unknown"
        
        # Parse aggregations as JSON if possible
        aggregations_text = aggregations_match.group(1).strip() if aggregations_match else "{}"
        try:
            # Try to parse as JSON
            aggregations = json.loads(aggregations_text)
        except json.JSONDecodeError:
            # If not valid JSON, use as text
            aggregations = {"text": aggregations_text}
        
        limitations = limitations_match.group(1).strip() if limitations_match else "No limitations noted."
        code_explanation = code_explanation_match.group(1).strip() if code_explanation_match else "No code explanation available."
        
        # Create the formatted data structure
        formatted_data = {
            'summary': summary,
            'subset_explanation': subset_explanation,
            'temporal_scope': temporal_scope,
            'geographic_scope': geographic_scope,
            'aggregations': aggregations,
            'visualizations': None,  # Could be added in future versions
            'limitations': limitations,
            'code_explanation': code_explanation
        }
        
        return {
            'formatted_data': formatted_data,
            'raw_data': extracted_data
        }
        
    except Exception as e:
        logger.error(f"Error formatting extracted data: {str(e)}")
        return {
            'formatted_data': {
                'summary': f"Error formatting data: {str(e)}",
                'subset_explanation': "Error occurred during formatting.",
                'temporal_scope': "Unknown",
                'geographic_scope': "Unknown",
                'aggregations': {},
                'visualizations': None,
                'limitations': "Error occurred during formatting.",
                'code_explanation': "Error occurred during formatting."
            },
            'raw_data': extracted_data
        }