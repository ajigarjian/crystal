import os
import openai
from typing import Dict, List, Any, Optional

# Try to load Azure OpenAI provider, otherwise fall back to OpenAI
try:
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_API_KEY"]
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    provider = "azure"

except KeyError:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    provider = "openai"

def get_openai_client():
    """
    Create and return an OpenAI client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
    """
    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":
        if not AZURE_OPENAI_ENDPOINT:
            raise ValueError("Azure endpoint is required when using Azure OpenAI")
        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-02-01-preview",  # Update this to the version you're using
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client

def get_openai_embeddings_client():
    """
    Create and return an OpenAI embeddings client configured for either OpenAI or Azure OpenAI.
        
    Returns:
        An OpenAI client
    """
    # If the Azure OpenAI key is set, let's default to using that as a preferred OpenAI provider
    if provider == "azure":        
        # Configure for Azure OpenAI
        client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-02-01-preview",  # Hardcoded for text-embedding-3-small model
            azure_endpoint=AZURE_OPENAI_ENDPOINT
        )
        return client
    else:
        # Configure for regular OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client

# Add a cache for the OpenAI client to avoid recreating it for each request
_openai_client_cache = {}
_openai_embeddings_client_cache = {}

def get_cached_openai_client():
    """
    Create and return a cached OpenAI client configured for either OpenAI or Azure OpenAI.
    The client is created only once per process and then reused.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    global _openai_client_cache
    
    if provider not in _openai_client_cache:
        _openai_client_cache[provider] = get_openai_client()
    
    return _openai_client_cache[provider]

def get_cached_openai_embeddings_client():
    """
    Create and return a cached OpenAI embeddings client.
    The client is created only once per process and then reused.
        
    Returns:
        An OpenAI client
        A Deployment Name
    """
    global _openai_embeddings_client_cache
    
    if provider not in _openai_embeddings_client_cache:
        _openai_embeddings_client_cache[provider] = get_openai_embeddings_client()
    
    return _openai_embeddings_client_cache[provider]

def create_embeddings(query):
    """
    Returns a new embeddings output from OpenAI.
    """
    client = get_cached_openai_embeddings_client()

    response = client.embeddings.create(
        input=query,
        model="text-embedding-3-small"
    )

    return response.data[0].embedding

def chat_completion(
    prompt: str, 
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    max_tokens: int = 800,
    response_format: Optional[Dict[str, str]] = None,
    model_name: Optional[str] = "gpt-4o-mini"
) -> str:
    """
    Get a chat completion from OpenAI or Azure OpenAI.
    
    Args:
        prompt: The user prompt
        system_message: The system message to use
        temperature: The temperature to use for generation (not supported by all models)
        max_tokens: Maximum tokens (will be mapped to max_completion_tokens for models that require it)
        response_format: Optional format specification for the response
        model_name: Optional model name to use (e.g., "gpt-4o", "gpt-4o-mini")
        
    Returns:
        The generated text
    """
    client = get_cached_openai_client()
    
    try:
        # Base parameters for the API call
        params = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
        }
        
        # Add temperature for models that support it
        # o3-mini doesn't support temperature parameter
        if not model_name.endswith("o3-mini"):
            params["temperature"] = temperature
        
        # Add response_format if provided
        if response_format is not None:
            params["response_format"] = response_format
            
        # Handle token limit parameter based on model
        if "o3" in model_name or "-o" in model_name:
            # For newer models like GPT-4o and o3 models that use max_completion_tokens
            params["max_completion_tokens"] = max_tokens
        else:
            # For older models that use max_tokens
            params["max_tokens"] = max_tokens
            
        response = client.chat.completions.create(**params)
        
        print("Generated response with model:", model_name)
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return f"Error generating response: {str(e)}" 