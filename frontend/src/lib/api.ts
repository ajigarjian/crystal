/**
 * Process a data query using the backend API
 * @param query The natural language query to process
 * @param datasetId Optional dataset ID to analyze specifically
 */
export const processQuery = async (query: string, datasetId?: string): Promise<any> => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000/crystal-2f87e/us-central1';
  
  try {
    // Use the correct endpoint based on whether we have a dataset ID
    const endpoint = datasetId 
      ? `${apiUrl}/stream_analyze?dataset_id=${datasetId}`
      : `${apiUrl}/stream_search_datasets`;
    
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status}`);
    }

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('Error calling API:', error);
    throw error;
  }
};