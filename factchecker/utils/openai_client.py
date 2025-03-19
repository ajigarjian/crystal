import os
import openai
from typing import Dict, List, Any, Optional

# Try to load Azure OpenAI provider, otherwise fall back to OpenAI
try:
    AZURE_OPENAI_KEY = os.environ["AZURE_OPENAI_API_KEY"]
    AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
    AZURE_OPENAI_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
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
        if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_DEPLOYMENT:
            raise ValueError("Azure endpoint and deployment name are required when using Azure OpenAI")
        
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
        temperature: The temperature to use for generation
        max_tokens: Maximum tokens
        response_format: Optional format specification for the response
        model_name: Optional model name to use (e.g., "gpt-4o", "gpt-4o-mini")
        
    Returns:
        The generated text
    """
    client = get_cached_openai_client()
    
    try:
        # Create API call with or without response_format based on whether it's provided
        if response_format is not None:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
        else:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
        print("Generated response with model:", model_name)
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error calling OpenAI API: {str(e)}")
        return f"Error generating response: {str(e)}" 