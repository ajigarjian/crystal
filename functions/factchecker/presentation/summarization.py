import json
import logging
from typing import Dict, List, Any, Optional
import re
import pandas as pd
import numpy as np

from factchecker.utils.openai_client import chat_completion

logger = logging.getLogger(__name__)

def summarize_findings(
    query: str,
    formatted_data_list: List[Dict[str, Any]],
    dataset_analyses: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Summarize findings from multiple datasets into a concise response.
    
    Args:
        query: The original user query
        formatted_data_list: List of dictionaries containing formatted data
        dataset_analyses: List of dataset analysis results
        
    Returns:
        Dictionary containing:
        {
            'key_data_points': List of key data points with sources,
            'summary': Comprehensive summary of findings,
            'sources': List of source information
        }
    """
    # Debug print 
    if not formatted_data_list:
        return {
            'key_data_points': [],
            'summary': "No relevant data was found to answer your query.",
            'sources': []
        }
    
    logger.info(f"Generating summary of findings from {len(formatted_data_list)} datasets")
    
    # Prepare information about each dataset and its extracted data
    dataset_summaries = []
    dataset_ids = []  # Track dataset IDs for the summary
    sources = []  # Create sources list for the frontend
    
    for i, data in enumerate(formatted_data_list):
        # Detailed logging of what's available in each data item
        logger.info(f"Data item #{i+1} keys: {list(data.keys() if isinstance(data, dict) else [])}")
        
        dataset_title = data.get("dataset_title", "Unnamed Dataset")
        dataset_id = data.get("dataset_id", "Unknown ID")
        dataset_ids.append(dataset_id)
        
        # Extract organization info, checking multiple possible locations
        organization = (
            data.get("organization_title") or
            data.get("organization") or
            data.get("dataset_source") or
            data.get("organization_name") or
            "Unknown Source"
        )
        
        # Log organization field values for debugging
        if isinstance(data, dict):
            logger.info(f"Organization fields in data item #{i+1}:")
            logger.info(f"  - organization_title: {data.get('organization_title')}")
            logger.info(f"  - organization: {data.get('organization')}")
            logger.info(f"  - dataset_source: {data.get('dataset_source')}")
            logger.info(f"  - organization_name: {data.get('organization_name')}")
        
        # Log what we found for debugging
        logger.info(f"Source #{i+1}: {dataset_title} (ID: {dataset_id}) - Organization: {organization}")
        
        # Add to sources list for frontend with proper fallbacks
        sources.append({
            "citation_id": dataset_id[:8] if dataset_id and dataset_id != "Unknown ID" else f"DS-{i+1}",
            "title": dataset_title if dataset_title != "Unnamed Dataset" else f"Dataset {i+1}",
            "organization": organization
        })
        
        # Get the summary and aggregations
        summary = data.get("summary", "")
        aggregations = data.get("aggregations", {})
        temporal_scope = data.get("temporal_scope", "Unknown")
        geographic_scope = data.get("geographic_scope", "Unknown")
        limitations = data.get("limitations", "No limitations noted.")
        
        # Format the aggregations as a string
        agg_str = ""
        if isinstance(aggregations, dict):
            for name, agg in aggregations.items():
                if isinstance(agg, dict):
                    agg_str += f"- {name}:\n"
                    for k, v in agg.items():
                        agg_str += f"  - {k}: {v}\n"
                elif isinstance(agg, list):
                    agg_str += f"- {name}:\n"
                    for item in agg:
                        if isinstance(item, dict):
                            agg_str += f"  - "
                            agg_str += ", ".join([f"{k}: {v}" for k, v in item.items()])
                            agg_str += "\n"
                        else:
                            agg_str += f"  - {item}\n"
                else:
                    agg_str += f"- {name}: {agg}\n"
        
        dataset_summaries.append(
            f"Source: {dataset_title} (ID: {dataset_id})\n"
            f"Temporal Scope: {temporal_scope}\n"
            f"Geographic Scope: {geographic_scope}\n"
            f"Summary: {summary}\n"
            f"Aggregations:\n{agg_str}\n"
            f"Limitations: {limitations}"
        )
    
    # Include dataset analyses if provided
    dataset_context = ""
    if dataset_analyses:
        dataset_context = "DATASET CONTEXT:\n"
        for analysis in dataset_analyses:
            # Include basic dataset information
            dataset_context += f"Dataset: {analysis.get('dataset_title', 'Unknown')}\n"
            dataset_context += f"Dataset ID: {analysis.get('dataset_id', 'Unknown ID')}\n"
            
            # Include row and column counts
            if 'row_count' in analysis and 'column_count' in analysis:
                dataset_context += f"Size: {analysis['row_count']} rows, {analysis['column_count']} columns\n"
            
            # Include categorical summaries
            if 'categorical_summaries' in analysis and analysis['categorical_summaries']:
                dataset_context += "Categories: " + "; ".join(analysis['categorical_summaries']) + "\n"
            
            # Include geographic scope
            if 'geographic_scope' in analysis and analysis['geographic_scope']:
                if isinstance(analysis['geographic_scope'], dict):
                    geo_info = [f"{k}: {v}" for k, v in analysis['geographic_scope'].items()]
                    dataset_context += "Geographic scope: " + "; ".join(geo_info) + "\n"
                else:
                    dataset_context += f"Geographic scope: {analysis['geographic_scope']}\n"
            
            # Include analysis if available
            if 'analysis' in analysis:
                dataset_context += f"Analysis: {analysis['analysis']}\n\n"

    # Create prompt for OpenAI
    prompt = f"""
You are analyzing data to answer: "{query}"

{dataset_context}

DATA POINTS:
{chr(10).join(dataset_summaries)}

INSTRUCTIONS:
1. Present the KEY DATA POINTS that directly answer the query - include SPECIFIC NUMBERS and VALUES
2. Be concise but thorough - include all relevant data in your analysis
3. Format as bullet points where appropriate
4. Always cite the source dataset and calculation strategy in brackets [] for each data point
5. If analyzing trends over time, be sure to include the full time range and specific values in your analysis
6. Pay special attention to the most recent data points when analyzing trends
7. Exclude any subset_df data from your analysis

Finally, provide a "SEARCH SUMMARY" section with 2 paragraphs that:
1. Summarizes the overall context of the datasets analyzed (their scope, limitations, quality)
2. Synthesizes the findings in relation to the query [mentioning date context where applicable]

Format your response exactly as:
### Key Data Points

- **Subheading/Category**:
  - Specific finding with numbers and context. [Source: Dataset Name]
  - Another finding with numbers and context. [Source: Dataset Name]

- **Another Subheading**:
  - Specific finding with numbers and context. [Source: Dataset Name]
  - Another finding with numbers and context. [Source: Dataset Name]

---

### Search Summary

Paragraph about the datasets used, their scope, and limitations...

Paragraph directly answering the user's question based on the data analysis...
"""
    
    try:
        response = chat_completion(
            prompt=prompt,
            system_message="You are a data analyst who provides thorough analysis of data, with special attention to recent data points.",
            temperature=0.3,
            model_name="gpt-4o" # Using a more capable model for this task
        )
        
        # Parse the response
        key_findings_match = re.search(r'### Key Data Points(.*?)---', response, re.DOTALL)
        summary_match = re.search(r'### Search Summary(.*)', response, re.DOTALL)
        
        key_findings_text = key_findings_match.group(1).strip() if key_findings_match else "No key findings identified."
        summary = summary_match.group(1).strip() if summary_match else "No findings summary available."
        
        # Extract individual bullet points for the key_data_points array
        key_data_points = []
        
        # Look for bullet points at both levels (main points and sub-points)
        bullet_pattern = r'- \*\*.*?\*\*:(?:\n  - .*?(?:\n|$))+'
        main_points = re.findall(bullet_pattern, key_findings_text, re.DOTALL)
        
        for point in main_points:
            # Add the main category point
            key_data_points.append(point.strip())
        
        # If no structured bullet points were found, use the raw text
        if not key_data_points:
            # Fall back to splitting by newlines for any bullet points
            simple_bullets = [line.strip() for line in key_findings_text.split('\n') 
                             if line.strip().startswith('-')]
            key_data_points = simple_bullets if simple_bullets else [key_findings_text]
        
        # Return the structured summary with sources
        return {
            'key_data_points': key_data_points,
            'summary': summary,
            'sources': sources
        }
        
    except Exception as e:
        logger.error(f"Error generating findings summary: {str(e)}")
        return {
            'key_data_points': ["Error generating key findings."],
            'summary': f"Error generating findings summary: {str(e)}",
            'sources': sources
        }

def format_findings_for_display(findings: Dict[str, Any]) -> str:
    """
    Format the findings dictionary for display to the user.
    
    Args:
        findings: The findings dictionary from summarize_findings
        
    Returns:
        Formatted string with findings for display
    """
    if not findings:
        return "No findings available."
    
    output = []
    
    # Add key findings
    output.append("### Key Data Points")
    
    # If key_data_points exists (new format), use it
    if 'key_data_points' in findings and findings['key_data_points']:
        for point in findings['key_data_points']:
            output.append(point)
    # Otherwise fall back to key_findings (old format)
    elif 'key_findings' in findings:
        output.append(findings['key_findings'])
    else:
        output.append("No key findings identified.")
    
    output.append("\n---\n")
    
    # Add summary
    output.append("### Search Summary")
    output.append(findings.get('summary', "No findings summary available."))
    
    return "\n".join(output)