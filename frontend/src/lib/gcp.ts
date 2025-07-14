import type * as GeoJSON from 'geojson';

interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

interface ToolCallContent {
  name: string;
  arguments: Record<string, unknown>;
}

interface StreamOnChunkData {
  type: "text" | "tool_code" | "error";
  content: string | ToolCallContent;
}

// Helper to get the correct base URL and function name prefix depending on the environment
function getFunctionsBaseUrl(): { baseUrl: string; prefixFunctionName: (name: string) => string } {
  if (typeof process !== 'undefined' && process.env && process.env.NODE_ENV === 'development') {
    return {
      baseUrl: 'http://localhost:8081',
      prefixFunctionName: (name: string) => name,
    };
  }
  return {
    baseUrl: 'https://us-central1-crystal-2f87e.cloudfunctions.net',
    prefixFunctionName: (name: string) => `gcp-cli-${name}`,
  };
}

export const streamAgentResponse = async (
  message: string,
  history: HistoryMessage[],
  onChunk: (data: StreamOnChunkData) => void,
  onClose: () => void,
  onError: (error: Error) => void
) => {
  const { baseUrl, prefixFunctionName } = getFunctionsBaseUrl();
  const url = `${baseUrl}/${prefixFunctionName('energy-agent')}`;

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message, history }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Response body is empty");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the last partial line in the buffer

      for (const line of lines) {
        if (line.trim()) {
            try {
                const parsed = JSON.parse(line);
                onChunk(parsed);
            } catch (error) {
                console.error("Failed to parse stream chunk:", line, error);
            }
        }
      }
    }
    
    if (buffer.trim()) {
        try {
            const parsed = JSON.parse(buffer);
            onChunk(parsed);
        } catch (error) {
            console.error("Failed to parse final stream chunk:", buffer, error);
        }
    }

  } catch (error) {
    console.error("Streaming failed:", error);
    if (error instanceof Error) {
        onError(error);
    } else {
        onError(new Error("An unknown error occurred during streaming."));
    }
  } finally {
    onClose();
  }
};

// Types for Power Infrastructure
export interface PowerInfrastructureFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.Geometry; // GeoJSON geometry
  properties: {
    gid: number;
    name: string;
    operator: string;
    power_type: string;
    voltage: string;
    geometry_type: string;
    flowgate: string | null;
    is_flowgate_line: boolean;
    capacity_factor?: number; // Optional for single datetime queries
    capacity_factor_timestamp?: string | null; // Optional for single datetime queries
    data_quality?: string | null; // Optional for single datetime queries
    time_series_data?: TimeSeriesDataPoint[] | null; // Optional for date range queries
  };
}

export interface TimeSeriesDataPoint {
  datetime_utc: string;
  capacity_factor: number;
  quality: string; // 'R' for real/historical, 'F' for forecast
}

/**
 * Extract capacity factor data for a specific datetime from time series data
 * @param timeSeriesData Array of time series data points
 * @param targetDateTime Target datetime as Date object
 * @returns Object with capacity_factor, timestamp, and quality, or null if not found
 */
export function extractCapacityFactorForDateTime(
  timeSeriesData: TimeSeriesDataPoint[] | null | undefined,
  targetDateTime: Date
): { capacity_factor: number; capacity_factor_timestamp: string; data_quality: string } | null {
  if (!timeSeriesData || timeSeriesData.length === 0) {
    return null;
  }
  
  // Round target datetime to nearest hour
  const targetHour = new Date(targetDateTime);
  targetHour.setMinutes(0, 0, 0);
  const targetISOString = targetHour.toISOString();
  
  // Find exact match first
  const exactMatch = timeSeriesData.find(point => 
    new Date(point.datetime_utc).toISOString() === targetISOString
  );
  
  if (exactMatch) {
    return {
      capacity_factor: exactMatch.capacity_factor,
      capacity_factor_timestamp: exactMatch.datetime_utc,
      data_quality: exactMatch.quality
    };
  }
  
  // If no exact match, find closest time point
  const closestMatch = timeSeriesData.reduce((closest, current) => {
    const currentTime = new Date(current.datetime_utc).getTime();
    const closestTime = new Date(closest.datetime_utc).getTime();
    const targetTime = targetHour.getTime();
    
    return Math.abs(currentTime - targetTime) < Math.abs(closestTime - targetTime) 
      ? current : closest;
  });
  
  return {
    capacity_factor: closestMatch.capacity_factor,
    capacity_factor_timestamp: closestMatch.datetime_utc,
    data_quality: closestMatch.quality
  };
}

/**
 * Transform time series data to single datetime format for backward compatibility
 * @param powerInfraData Power infrastructure data with time series
 * @param targetDateTime Target datetime to extract
 * @returns Transformed data with single datetime capacity factors
 */
export function transformTimeSeriesForDateTime(
  powerInfraData: PowerInfrastructureData,
  targetDateTime: Date
): PowerInfrastructureData {
  return {
    ...powerInfraData,
    features: powerInfraData.features.map(feature => {
      const capacityFactorData = extractCapacityFactorForDateTime(
        feature.properties.time_series_data,
        targetDateTime
      );
      
      return {
        ...feature,
        properties: {
          ...feature.properties,
          capacity_factor: capacityFactorData?.capacity_factor || 0.0,
          capacity_factor_timestamp: capacityFactorData?.capacity_factor_timestamp || null,
          data_quality: capacityFactorData?.data_quality || null,
          // Remove time_series_data for backward compatibility
          time_series_data: undefined
        }
      };
    })
  };
}

export interface PowerInfrastructureData {
  type: "FeatureCollection";
  features: PowerInfrastructureFeature[];
  time_range?: {
    start_date: string;
    end_date: string;
    weeks: number;
  };
}

/**
 * Fetch BPA power infrastructure data as GeoJSON from the new GCP endpoint
 * @param zoom Optional zoom level for simplification
 * @param datetime Optional datetime in ISO format (YYYY-MM-DDTHH:MM:SSZ) to get capacity factors for specific time
 * @param dateRange Optional date range (e.g., "4w" for 4 weeks of data) to get time series data
 */
export const getPowerInfrastructure = async (zoom?: number, datetime?: string, dateRange?: string): Promise<PowerInfrastructureData> => {
  const { baseUrl, prefixFunctionName } = getFunctionsBaseUrl();
  let url = `${baseUrl}/${prefixFunctionName('get-power-infrastructure')}`;
  
  const params = new URLSearchParams();
  if (zoom !== undefined) {
    params.append('zoom', zoom.toString());
  }
  if (datetime !== undefined) {
    params.append('datetime', datetime);
  }
  if (dateRange !== undefined) {
    params.append('date_range', dateRange);
  }
  
  if (params.toString()) {
    url += `?${params.toString()}`;
  }
  
  console.log("Calling getPowerInfrastructure API at URL:", url);
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    console.log("API response status:", response.status);
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error fetching power infrastructure:', errorText);
      throw new Error(`Failed to fetch power infrastructure: ${response.status}`);
    }
    const data = await response.json();
    console.log("Raw API response data:", data);
    return data;
  } catch (error) {
    console.error('Error in getPowerInfrastructure:', error);
    throw error;
  }
};

export interface GeneratorFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.Geometry;
  properties: {
    id: number;
    name: string;
    operator?: string;
    fuel_type?: string;
    technology?: string;
    capacity_mw?: string;
    status?: string;
    commissioning_date?: string;
    plant_name?: string;
    geometry_type: string;
  };
}

export interface GeneratorData {
  type: "FeatureCollection";
  features: GeneratorFeature[];
}

/**
 * Fetch power generator data as GeoJSON with zoom-based progressive disclosure from the new GCP endpoint
 * @param zoom Zoom level for progressive disclosure
 * @param types Optional comma-separated list of generator types to filter
 */
export const getPowerGenerators = async (
  zoom?: number,
  types?: string
): Promise<GeneratorData> => {
  const { baseUrl, prefixFunctionName } = getFunctionsBaseUrl();
  let url = `${baseUrl}/${prefixFunctionName('get-power-generators')}`;
  const params = new URLSearchParams();
  if (zoom !== undefined) params.append('zoom', zoom.toString());
  if (types) params.append('types', types);
  if (params.toString()) {
    url += `?${params.toString()}`;
  }
  console.log("Calling getPowerGenerators API at URL:", url);
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    console.log("Generators API response status:", response.status);
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error fetching power generators:', errorText);
      throw new Error(`Failed to fetch power generators: ${response.status}`);
    }
    const data = await response.json();
    console.log("Raw generators API response data:", data);
    return data;
  } catch (error) {
    console.error('Error in getPowerGenerators:', error);
    throw error;
  }
};

export interface PowerPlantsFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSON.Geometry;
  properties: {
    id: number;
    name: string;
    operator?: string;
    fuel_type?: string;
    technology?: string;
    capacity_mw?: string;
    status?: string;
    commissioning_date?: string;
    plant_name?: string;
    geometry_type: string;
  };
}

export interface PowerPlantsData {
  type: "FeatureCollection";
  features: PowerPlantsFeature[];
}

/**
 * Fetch power plants data as GeoJSON with zoom-based progressive disclosure from the new GCP endpoint
 * @param zoom Zoom level for progressive disclosure
 * @param types Optional comma-separated list of plant types to filter
 */
export const getPowerPlants = async (
  zoom?: number,
  types?: string
): Promise<PowerPlantsData> => {
  const { baseUrl, prefixFunctionName } = getFunctionsBaseUrl();
  let url = `${baseUrl}/${prefixFunctionName('get-power-plants')}`;
  const params = new URLSearchParams();
  if (zoom !== undefined) params.append('zoom', zoom.toString());
  if (types) params.append('types', types);
  if (params.toString()) {
    url += `?${params.toString()}`;
  }
  console.log("Calling getPowerPlants API at URL:", url);
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    console.log("Plants API response status:", response.status);
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error fetching power plants:', errorText);
      throw new Error(`Failed to fetch power plants: ${response.status}`);
    }
    const data = await response.json();
    console.log("Raw plants API response data:", data);
    return data;
  } catch (error) {
    console.error('Error in getPowerPlants:', error);
    throw error;
  }
}; 

// Types for Wildfire Data
export interface WildfireFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Geometry;
  properties: {
    irwin_id: string;
    incident_name: string;
    gis_acres: number;
    reported_acres: number;
    percent_contained: number;
    status: string;
    incident_type: string;
    complexity_level: string;
    cause_general: string;
    state: string;
    county: string;
    discovery_time: string;
    perimeter_time: string;
    last_update_src: string;
    ingestion_timestamp: string;
    geometry_type: string;
  };
}

export interface WildfireData {
  type: "FeatureCollection";
  features: WildfireFeature[];
}

/**
 * Fetch wildfire perimeter data as GeoJSON with zoom-based progressive disclosure
 * @param zoom Zoom level for progressive disclosure
 * @param status Optional status filter (e.g., 'Active', 'Contained')
 * @param state Optional state filter (e.g., 'CA', 'OR')
 * @param activeOnly Only show fires that are not 100% contained
 */
export const getWildfires = async (
  zoom?: number,
  status?: string,
  state?: string,
  activeOnly?: boolean
): Promise<WildfireData> => {
  const { baseUrl, prefixFunctionName } = getFunctionsBaseUrl();
  let url = `${baseUrl}/${prefixFunctionName('get-wildfires')}`;
  const params = new URLSearchParams();
  
  if (zoom !== undefined) params.append('zoom', zoom.toString());
  if (status) params.append('status', status);
  if (state) params.append('state', state);
  if (activeOnly) params.append('active_only', 'true');
  
  if (params.toString()) {
    url += `?${params.toString()}`;
  }
  
  console.log("Calling getWildfires API at URL:", url);
  
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    console.log("Wildfires API response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Error fetching wildfires:', errorText);
      throw new Error(`Failed to fetch wildfires: ${response.status}`);
    }

    const data = await response.json();
    console.log("Raw wildfires API response data:", data);
    return data;
  } catch (error) {
    console.error('Error in getWildfires:', error);
    throw error;
  }
}; 