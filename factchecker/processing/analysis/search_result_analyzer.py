from typing import Dict, Tuple, Any
import logging
import re

from factchecker.utils.openai_client import chat_completion

logger = logging.getLogger(__name__)

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
    
    # Create prompt for OpenAI
    prompt = f"""
You are assessing whether a dataset is likely to be relevant to a user's query based only on metadata.

USER QUERY: "{query}"

DATASET METADATA:
Title: {title}
Description: {description}
Tags: {tags_str}
Organization: {org_name}

ASSESSMENT GUIDELINES:
1. PRIORITIZE the dataset's title and description when determining relevance
2. Consider that you don't have access to the actual data yet
3. If the metadata suggests the dataset could plausibly contain information related to the query, consider it potentially relevant
4. Be more lenient since this is a pre-download assessment

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
            # Fallback if parsing fails
            logger.warning(f"Failed to parse relevance assessment response: {response_text}")
            return (False, 0.3, "Failed to parse relevance assessment, defaulting to not relevant")
    except Exception as e:
        logger.error(f"Error in pre-download relevance assessment: {str(e)}")
        # Default to False in case of error to avoid downloading potentially irrelevant datasets
        return (False, 0.3, f"Error in assessment: {str(e)}") 