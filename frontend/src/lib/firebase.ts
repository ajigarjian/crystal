import { initializeApp } from "firebase/app";
import { getFunctions, httpsCallable, connectFunctionsEmulator } from "firebase/functions";
import { getFirestore, connectFirestoreEmulator } from "firebase/firestore";
import { getAnalytics, logEvent } from "firebase/analytics";

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
    apiKey: "AIzaSyC3KIK0ol5TquNaz6-DyVoxzijDNySgrq4",
    authDomain: "crystal-2f87e.firebaseapp.com",
    projectId: "crystal-2f87e",
    storageBucket: "crystal-2f87e.firebasestorage.app",
    messagingSenderId: "422374862387",
    appId: "1:422374862387:web:1a11af2b205c777173bd46",
    measurementId: "G-1CFM4WMH4B"
  };

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Cloud Firestore and get a reference to the service
export const db = getFirestore(app);

// Initialize Cloud Functions
export const functions = getFunctions(app);

// Initialize Analytics (in browser environment)
export const getFirebaseAnalytics = () => {
  if (typeof window !== 'undefined' && process.env.NODE_ENV !== 'development') {
    return getAnalytics(app);
  }
  return null;
};

export const trackDwellTimeStart = (pageName: string) => {
  const analytics = getFirebaseAnalytics();
  if (analytics) {
    console.log(`Tracking dwell time start for: ${pageName}`);
    logEvent(analytics, 'dwell_time_start', { 
      page_name: pageName,
      start_time: new Date().toISOString()
    });
    console.log('Dwell time start event logged');
    
    // Log a page_view event too (standard event)
    logEvent(analytics, 'page_view', {
      page_title: pageName,
      page_location: window.location.href
    });
    console.log('Page view event logged');
  } else {
    console.error('Analytics not available for trackDwellTimeStart');
  }
};

export const trackDwellTimeEnd = (pageName: string, startTime: Date) => {
  const analytics = getFirebaseAnalytics();
  if (analytics) {
    const endTime = new Date();
    const durationSeconds = Math.floor((endTime.getTime() - startTime.getTime()) / 1000);
    logEvent(analytics, 'dwell_time_end', { 
      page_name: pageName,
      duration_seconds: durationSeconds
    });
  }
};

// Set up emulator if in development
if (process.env.NODE_ENV === 'development') {
  console.log(`Using Firebase Functions emulator...`);
  connectFunctionsEmulator(functions, 'localhost', 5001);
  connectFirestoreEmulator(db, 'localhost', 8080);
}

// Export a helper for calling the waitlist registration function
export const registerWaitlist = async (data: { email: string, first_name: string }) => {
  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    // Use production URL in production
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/register_waitlist`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to register');
    }
    
    const result = await response.json();
    return { data: result };
  } catch (error: any) {
    console.error('Error calling register_waitlist:', error);
    throw new Error(error.message || 'Failed to register');
  }
};

// Export a helper for calling the stream search datasets function
export const streamSearchDatasets = async (
  data: {
    query: string;
    search_method: string | null;
    similarity_threshold: number;
    max_results?: number;
    census_max_results?: number;
    relevance_threshold?: number;
  },
  onChunk?: (chunk: any) => void, // Callback for processing chunks
  signal?: AbortSignal // New parameter for AbortController signal
) => {
  // Create a default onChunk function if none is provided
  const processChunk = typeof onChunk === 'function' 
    ? onChunk 
    : (chunk: any) => {
        //console.log('Received chunk:', chunk);
        // Default implementation just logs the chunk
      };

  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    // Use production URL in production
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/stream_search_datasets`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify(data),
      signal // Pass the abort signal to fetch
    });
    
    if (!response.ok) {
      let errorText = await response.text();
      console.error('Error response:', errorText);
      
      // Try to parse JSON error message for usage limits
      try {
        const errorData = JSON.parse(errorText);
        if (errorData.type === 'usage_limit_exceeded') {
          // This is a usage limit error - use the provided message
          throw new Error(errorData.error || `Usage limit exceeded for ${errorData.limit_type}`);
        }
      } catch (parseError) {
        // If parsing fails, continue with the text error
      }
      
      throw new Error(errorText || 'Failed to search datasets');
    }
    
    // For streaming responses, we need to process the response as a stream
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Stream reader not available');
    }
    
    // Process the stream and parse each chunk as JSON
    const decoder = new TextDecoder();
    let buffer = '';
    const chunks = []; // Store processed chunks to return
    
    while (true) {
      // Check for abort before each read
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted', 'AbortError');
      }
      
      const { done, value } = await reader.read();
      if (done) break;
      
      // Decode the chunk and add it to our buffer
      buffer += decoder.decode(value, { stream: true });
      
      // Split the buffer by newlines to get individual JSON objects
      const lines = buffer.split('\n');
      
      // Process all complete lines
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line) {
          try {
            // Extract the JSON part if the line starts with 'data:'
            const jsonStr = line.startsWith('data:') 
              ? line.substring(5).trim() 
              : line;
            
            // Replace NaN with null before parsing
            const sanitizedJsonStr = jsonStr.replace(/:\s*NaN\s*([,}])/g, ': null$1');
            const data = JSON.parse(sanitizedJsonStr);
            // Call the callback with each chunk of data
            processChunk(data);
            chunks.push(data);
          } catch (e) {
            console.error('Error parsing JSON:', e, 'Line:', line);
          }
        }
      }
      
      // Keep the last (potentially incomplete) line in the buffer
      buffer = lines[lines.length - 1];
    }
    
    // Process any remaining data in the buffer
    if (buffer.trim()) {
      try {
        // Extract the JSON part if the line starts with 'data:'
        const jsonStr = buffer.trim().startsWith('data:') 
          ? buffer.trim().substring(5).trim() 
          : buffer.trim();
        
        // Replace NaN with null before parsing
        const sanitizedJsonStr = jsonStr.replace(/:\s*NaN\s*([,}])/g, ': null$1');
        const data = JSON.parse(sanitizedJsonStr);
        processChunk(data);
        chunks.push(data);
      } catch (e) {
        console.error('Error parsing final JSON:', e);
      }
    }
    
    return chunks; // Return all processed chunks
  } catch (error: any) {
    // Check if this is an abort error
    if (error.name === 'AbortError') {
      console.log('Search was aborted by user');
      throw error; // Re-throw the abort error to be caught by the caller
    }
    
    console.error('Error calling stream_search_datasets:', error);
    throw new Error(error.message || 'Failed to search datasets');
  }
};

// Add a helper function to process dataset chunks for UI display
export const processDatasetChunks = (chunks: any[]) => {
  // Extract all datasets, including non-relevant ones
  const datasets = chunks
    .filter(chunk => chunk.type === 'dataset' || 
                    (chunk.type === 'dataset_update' && chunk.data))
    .map(chunk => {
      // For dataset_update chunks, use the updated data which includes relevance score
      if (chunk.type === 'dataset_update') {
        return {
          ...chunk.data,
          timestamp: chunk.timestamp
        };
      }
      // For initial dataset chunks
      return {
        ...chunk.data,
        timestamp: chunk.timestamp
      };
    });
  
  // Get the final status from the complete chunk
  const completeChunk = chunks.find(chunk => chunk.type === 'complete');
  const finalStatus = completeChunk ? completeChunk.message : '';
  
  // Get all status messages for progress display
  const statusMessages = chunks
    .filter(chunk => chunk.type === 'status' || 
                    chunk.type === 'discovery' || 
                    chunk.type === 'phase_complete' ||
                    chunk.type === 'complete')
    .map(chunk => ({
      message: chunk.message,
      timestamp: chunk.timestamp,
      type: chunk.type
    }));
  
  return {
    datasets,
    finalStatus,
    statusMessages
  };
};

// Add this function after your other export functions
export const submitFeedback = async (data: {
  feedback_type: string;
  title: string;
  description: string;
  email?: string;
  page_url: string;
  tags?: string[];
  metadata?: any;
}) => {
  console.log("Starting submitFeedback with data:", data);
  
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
    console.log("Using development URL:", baseUrl);
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
    console.log("Using production URL:", baseUrl);
  }
  
  const url = `${baseUrl}/submit_feedback`;
  console.log("Full request URL:", url);
  
  try {
    console.log("Making fetch request...");
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify(data),
    });
    
    console.log("Fetch response received. Status:", response.status);
    
    let responseText;
    try {
      responseText = await response.text();
      console.log("Response text:", responseText);
    } catch (textError) {
      console.error("Error reading response text:", textError);
      responseText = "Unable to read response";
    }
    
    if (!response.ok) {
      let errorData;
      try {
        errorData = JSON.parse(responseText);
      } catch (jsonError) {
        console.error("Error parsing JSON response:", jsonError);
        errorData = { error: responseText || "Unknown error" };
      }
      throw new Error(errorData.error || 'Failed to submit feedback');
    }
    
    let result;
    try {
      result = JSON.parse(responseText);
    } catch (jsonError) {
      console.error("Error parsing success response:", jsonError);
      throw new Error("Invalid response format");
    }
    
    console.log("Submission successful:", result);
    return { data: result };
  } catch (error: any) {
    console.error('Error submitting feedback:', error);
    throw new Error(error.message || 'Failed to submit feedback');
  }
};

// Add this new function for evaluating search queries
export const evaluateSearchQuery = async (query: string) => {
  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    // Use emulator URL in development
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    // Use production URL in production
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/evaluate_search_query`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify({ query }),
    });
    
    if (!response.ok) {
      let errorText = await response.text();
      
      // Try to parse JSON error message for usage limits
      try {
        const errorData = JSON.parse(errorText);
        if (errorData.type === 'usage_limit_exceeded') {
          // This is a usage limit error - use the provided message
          throw new Error(errorData.error || `Usage limit exceeded for query evaluation`);
        }
      } catch (parseError) {
        // If parsing fails, continue with the text error
      }
      
      throw new Error(errorText || 'Failed to evaluate query');
    }
    
    const result = await response.json();
    return result;
  } catch (error: any) {
    console.error('Error evaluating search query:', error);
    // Return a default response instead of throwing, to make error handling cleaner in UI
    return {
      quality: "error",
      rating: 0,
      message: "Unable to evaluate query",
      suggestions: []
    };
  }
};

// Also update warmFunctions to include the new function
export const warmFunctions = async () => {
  if (process.env.NODE_ENV === 'development') {
    console.log('Skipping function warming in development mode');
    return;
  }
  
  try {
    // Get the region and project ID
    const region = functions.region || 'us-central1';
    const projectId = firebaseConfig.projectId;
    const baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
    
    // List of functions to warm
    const functionsToWarm = [
      'register_waitlist',
      'stream_search_datasets',
      'stream_analyze',
      'submit_feedback',
      'evaluate_search_query', // Add the new function
      'get_dashboard_section_cards_data', // Added new function here
      'get_inflow_timeseries' // Add new inflow timeseries function
    ];
    
    // Warm each function with a minimal payload
    functionsToWarm.forEach(async (functionName) => {
      const url = `${baseUrl}/${functionName}`;
      
      try {
        await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
          },
          body: JSON.stringify({ warming: true }),
        });
        console.log(`Warmed function: ${functionName}`);
      } catch (e) {
        // Silently ignore errors during warming
      }
    });
  } catch (error) {
    // Don't let warming errors affect the user experience
    console.log('Function warming failed silently');
  }
};

// Export a helper for calling the stream analyze datasets function
export const streamAnalyzeDatasets = async (
  data: {
    query: string;
    datasets?: any[];     // Support datasets array - Using any[] to resolve linter error
    dataset_ids?: string[];   // Support dataset_ids array
  },
  onChunk?: (chunk: any) => void
) => {
  // Create a default onChunk function if none is provided
  const processChunk = typeof onChunk === 'function' 
    ? onChunk 
    : (chunk: any) => {
        console.log('Received analysis chunk:', chunk);
      };

  // Get the region and project ID from the functions instance
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  
  // Construct the URL for the HTTP function
  let baseUrl = '';
  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }
  
  const url = `${baseUrl}/stream_analyze`;

  // Use dataset_ids if provided, otherwise pass datasets
  const payload = {
    query: data.query,
    datasets: data.datasets,    // Pass datasets if provided
    dataset_ids: data.dataset_ids  // Pass dataset_ids if provided
  };
  
  console.log('Sending analysis request with payload:', payload);
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify(payload),
    });
    
    if (!response.ok) {
      let errorText = await response.text();
      console.error('Error response:', errorText);
      
      // Try to parse JSON error message for usage limits
      try {
        const errorData = JSON.parse(errorText);
        if (errorData.type === 'usage_limit_exceeded') {
          // This is a usage limit error - use the provided message
          throw new Error(errorData.error || `Usage limit exceeded for ${errorData.limit_type}`);
        }
      } catch (parseError) {
        // If parsing fails, continue with the text error
      }
      
      throw new Error(errorText || 'Failed to analyze datasets');
    }
    
    // For streaming responses, read as a stream
    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Stream reader not available');
    }
    
    const decoder = new TextDecoder();
    let buffer = '';
    const chunks = [];
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line) {
          try {
            // Extract the JSON part if the line starts with 'data:'
            const jsonStr = line.startsWith('data:') 
              ? line.substring(5).trim() 
              : line;
            
            // Replace NaN with null before parsing
            const sanitizedJsonStr = jsonStr.replace(/:\s*NaN\s*([,}])/g, ': null$1');
            const parsed = JSON.parse(sanitizedJsonStr);
            processChunk(parsed);
            chunks.push(parsed);
          } catch (e) {
            console.error('Error parsing JSON:', e, 'Line:', line);
          }
        }
      }
      buffer = lines[lines.length - 1];
    }
    
    if (buffer.trim()) {
      try {
        // Extract the JSON part if the line starts with 'data:'
        const jsonStr = buffer.trim().startsWith('data:') 
          ? buffer.trim().substring(5).trim() 
          : buffer.trim();
        
        // Replace NaN with null before parsing
        const sanitizedJsonStr = jsonStr.replace(/:\s*NaN\s*([,}])/g, ': null$1');
        const parsed = JSON.parse(sanitizedJsonStr);
        processChunk(parsed);
        chunks.push(parsed);
      } catch (e) {
        console.error('Error parsing final JSON:', e);
      }
    }
    
    return chunks;
  } catch (error: any) {
    console.error('Error calling stream_analyze:', error);
    throw new Error(error.message || 'Failed to analyze datasets');
  }
};

// Define the expected structure of a single card's data from the backend
export interface SectionCardData {
  id: string; // metric_id will be used as id
  title: string;
  value: string; // e.g., "123.45 ft" or "N/A %"
  timestamp: string; // ISO string format from the backend
  trend: 'up' | 'down' | 'neutral'; // Current placeholder, will be 'neutral'
  trendDescription: string; // Default description from backend config
  footerNote: string;
}

// Export a helper for calling the new dashboard card data function
export const getDashboardSectionCards = async (damId: number): Promise<SectionCardData[]> => {
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  let baseUrl = '';

  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }

  // The name of the new Python Cloud Function
  const url = `${baseUrl}/get_dashboard_section_cards_data?dam_id=${damId}`;

  try {
    // This is a GET request to fetch data
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      let errorData = { error: "Failed to fetch section card data" };
      try {
        errorData = await response.json();
      } catch (e) {
        // If parsing error response fails, use the default error
        console.error("Failed to parse error response from getDashboardSectionCards: ", e);
      }
      console.error('Error fetching section card data:', response.status, errorData);
      throw new Error(errorData.error || `Failed to fetch section card data. Status: ${response.status}`);
    }

    const data = await response.json();
    return data as SectionCardData[];
  } catch (error: any) {
    console.error('Error calling getDashboardSectionCards function:', error);
    // Return an empty array in case of error so the UI can handle it gracefully
    // Or re-throw if you have a higher-level error boundary in Next.js
    return []; 
    // throw new Error(error.message || 'Failed to fetch section card data');
  }
};

// Define the expected structure for a single data point from the inflow timeseries
export interface InflowDataPoint {
  ts_utc: string; // ISO string from backend
  value_num: number;
}

// Define the new time range options type here as well to be used by the function
export type TimeRangeOption = "mtd" | "14d" | "7d";

// Export a helper for calling the new inflow timeseries data function
// Updated to accept new TimeRangeOption types and damId
export const getInflowTimeseries = async (range: TimeRangeOption, damId: number): Promise<InflowDataPoint[]> => {
  const region = functions.region || 'us-central1';
  const projectId = firebaseConfig.projectId;
  let baseUrl = '';

  if (process.env.NODE_ENV === 'development') {
    baseUrl = `http://localhost:5001/${projectId}/${region}`;
  } else {
    baseUrl = `https://${region}-${projectId}.cloudfunctions.net`;
  }

  // The name of the new Python Cloud Function
  // Append dam_id to the query parameters
  const url = `${baseUrl}/get_inflow_timeseries?range=${range}&dam_id=${damId}`;

  try {
    // This is a GET request to fetch data
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      let errorData = { error: "Failed to fetch inflow timeseries data" };
      try {
        errorData = await response.json();
      } catch (e) {
        console.error("Failed to parse error response from getInflowTimeseries: ", e);
      }
      console.error('Error fetching inflow timeseries data:', response.status, errorData);
      throw new Error(errorData.error || `Failed to fetch inflow timeseries data. Status: ${response.status}`);
    }

    const data = await response.json();
    return data as InflowDataPoint[];
  } catch (error: any) {
    console.error('Error calling getInflowTimeseries function:', error);
    return []; 
  }
}; 