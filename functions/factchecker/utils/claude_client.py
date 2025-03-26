import os
import anthropic
from typing import Dict, List, Any, Optional

def get_claude_client():
    """
    Create and return an Anthropic Claude client.
    
    Returns:
        An Anthropic client
        The model name to use
    """
    CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    
    if not CLAUDE_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")
    
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    return client, "claude-3-7-sonnet-20250219"

def chat_completion_claude(
    prompt: str, 
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 1500,
    response_format: Optional[Dict[str, str]] = None
) -> str:
    """
    Get a chat completion from Claude.
    
    Args:
        prompt: The user prompt
        system_message: The system message to use
        temperature: The temperature to use for generation
        max_tokens: Maximum tokens
        response_format: Optional format specification for the response
        
    Returns:
        The generated text
    """
    client, model = get_claude_client()
    
    # Create API call with or without response_format based on whether it's provided
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system_message,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    # Add response_format if provided
    if response_format is not None and response_format.get("type") == "json_object":
        kwargs["response_format"] = {"type": "json_object"}
    
    response = client.messages.create(**kwargs)
    return response.content[0].text

