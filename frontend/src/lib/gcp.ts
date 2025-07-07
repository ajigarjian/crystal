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

// Helper to get the correct base URL depending on the environment
function getFunctionsBaseUrl(): string {
  if (typeof process !== 'undefined' && process.env && process.env.NODE_ENV === 'development') {
    return 'http://localhost:8081';
  }
  return 'https://us-central1-crystal-2f87e.cloudfunctions.net';
}

export const streamAgentResponse = async (
  message: string,
  history: HistoryMessage[],
  onChunk: (data: StreamOnChunkData) => void,
  onClose: () => void,
  onError: (error: Error) => void
) => {
  const url = "https://us-central1-crystal-2f87e.cloudfunctions.net/gcp-cli-energy-agent";

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
    capacity_factor: number;
    capacity_factor_timestamp: string | null;
  };
}

export interface PowerInfrastructureData {
  type: "FeatureCollection";
  features: PowerInfrastructureFeature[];
}

/**
 * Fetch BPA power infrastructure data as GeoJSON from the new GCP endpoint
 * @param zoom Optional zoom level for simplification
 */
export const getPowerInfrastructure = async (zoom?: number): Promise<PowerInfrastructureData> => {
  let url = `${getFunctionsBaseUrl()}/gcp-cli-get-power-infrastructure`;
  if (zoom !== undefined) {
    url += `?zoom=${zoom}`;
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
  let url = `${getFunctionsBaseUrl()}/gcp-cli-get-power-generators`;
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
  let url = `${getFunctionsBaseUrl()}/gcp-cli-get-power-plants`;
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