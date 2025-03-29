/**
 * Process a data query using the backend API
 * @param query The natural language query to process
 * @param datasetIds Optional dataset IDs to analyze specifically
 */
export const processQuery = async (query: string, datasetIds?: string | string[]): Promise<any> => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/crystal-2f87e/us-central1';
  
  try {
    // Check if we have dataset IDs to analyze
    const hasDatasets = !!datasetIds && (
      typeof datasetIds === 'string' ? datasetIds.length > 0 : datasetIds.length > 0
    );
    
    // Use the correct endpoint
    const endpoint = hasDatasets
      ? `${apiUrl}/stream_analyze`
      : `${apiUrl}/stream_search_datasets`;
    
    // Prepare the request body
    const requestBody: Record<string, any> = { query };
    
    // Add dataset_ids to the request if provided
    if (hasDatasets) {
      if (typeof datasetIds === 'string') {
        requestBody.dataset_ids = [datasetIds];
      } else {
        requestBody.dataset_ids = datasetIds;
      }
    }
    
    // Make the request with streaming support
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }
    
    // Check if the response is a stream
    const contentType = response.headers.get('Content-Type');
    if (contentType && contentType.includes('text/event-stream')) {
      // Initialize result object
      const result: any = {
        streaming: true,
        summary: '',
        details: [],
        status: 'processing'
      };
      
      // Set up streaming processor
      const reader = response.body?.getReader();
      if (reader) {
        let buffer = '';
        
        // Process the stream until completion
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          // Decode the chunk and add to buffer
          const chunk = new TextDecoder().decode(value);
          buffer += chunk;
          
          // Process complete SSE messages
          const lines = buffer.split(/\n\n/);
          buffer = lines.pop() || ''; // Keep the last partial chunk in the buffer
          
          for (const line of lines) {
            if (!line.trim()) continue;
            
            // Extract data from SSE format
            const dataMatch = line.match(/data: (.*)/);
            if (dataMatch && dataMatch[1]) {
              try {
                const data = JSON.parse(dataMatch[1]);
                
                // Update the result based on the message type
                if (data.type === 'complete') {
                  result.status = 'complete';
                  result.summary = data.data?.summary || result.summary;
                  result.details = data.data?.details || result.details;
                  result.sources = data.data?.sources || result.sources;
                } else if (data.type === 'update') {
                  result.summary = data.data?.summary || data.message || result.summary;
                  if (data.data?.details) result.details = data.data.details;
                  if (data.data?.sources) result.sources = data.data.sources;
                }
              } catch (e) {
                // Skip parsing errors
              }
            }
          }
        }
        
        return result;
      }
    }

    // For non-streaming responses, just parse the JSON
    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error calling API:', error);
    throw error;
  }
};