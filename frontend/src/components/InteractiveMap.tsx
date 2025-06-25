"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapSkeleton } from "@/components/MapSkeleton";
import { getPowerInfrastructure, PowerInfrastructureData, getPowerGenerators, GeneratorData, getPowerPlants, PowerPlantsData } from "@/lib/firebase";
import { Switch } from "@/components/ui/switch";

interface MapMarker {
  latitude: number;
  longitude: number;
  name?: string; 
  id: string | number;
}

interface PowerLineClickData {
  id: number;
  name: string;
  flowgate?: string | null;
  voltage?: string;
  operator?: string;
  ref?: string;
  associatedLines?: string[];
  capacityFactor: number;
}

interface InteractiveMapProps {
  initialLatitude?: number;
  initialLongitude?: number;
  initialZoom?: number;
  markers?: MapMarker[];
  mapboxAccessToken: string; 
  height?: string | number;
  onMarkerClick?: (marker: MapMarker) => void;
  onPowerLineClick?: (powerLineData: PowerLineClickData) => void;
  onEmptyMapClick?: () => void;
  selectedMarkerId?: string | number;
  selectedPowerLineId?: number | null;
  selectedFlowgate?: string | null;
}

// Focus on Columbia River basin area - covering the basins you mentioned
const DEFAULT_LATITUDE = 47.8; // Columbia River focus
const DEFAULT_LONGITUDE = -119.5; // Columbia River focus  
const DEFAULT_ZOOM = 5.8;

// Use monochrome style as base - everything will be grey
const BASE_STYLE = "mapbox://styles/mapbox/light-v11";

// Add this helper function near the top of the component, after the imports
const formatVoltageToKV = (voltage: string | undefined): string => {
  if (!voltage || voltage === 'Unknown' || voltage === '') {
    return 'Unknown';
  }
  
  // Clean the input string and handle semicolon-separated duplicates
  let cleanVoltage = voltage.trim();
  
  // If there's a semicolon, take only the first value
  if (cleanVoltage.includes(';')) {
    cleanVoltage = cleanVoltage.split(';')[0].trim();
  }
  
  // If it already contains 'kV', check if it's properly formatted
  if (cleanVoltage.toLowerCase().includes('kv')) {
    // Extract the numeric part before 'kV'
    const kvMatch = cleanVoltage.match(/^(\d+(?:\.\d+)?)\s*kv$/i);
    if (kvMatch) {
      // It's already properly formatted, return as is
      const value = parseFloat(kvMatch[1]);
      if (!isNaN(value)) {
        if (value >= 100) {
          return `${Math.round(value)} kV`;
        } else if (value >= 10) {
          return `${value.toFixed(1)} kV`;
        } else {
          return `${value.toFixed(2)} kV`;
        }
      }
    }
    
    // If it contains kV but isn't properly formatted, try to extract just the number
    const numericPart = cleanVoltage.replace(/[^\d.]/g, '');
    const numericValue = parseFloat(numericPart);
    
    if (!isNaN(numericValue)) {
      // If the number is already reasonable for kV (< 1000), use it directly
      if (numericValue < 1000) {
        if (numericValue >= 100) {
          return `${Math.round(numericValue)} kV`;
        } else if (numericValue >= 10) {
          return `${numericValue.toFixed(1)} kV`;
        } else {
          return `${numericValue.toFixed(2)} kV`;
        }
      } else {
        // If it's a large number, convert from V to kV
        const kVValue = numericValue / 1000;
        if (kVValue >= 100) {
          return `${Math.round(kVValue)} kV`;
        } else if (kVValue >= 10) {
          return `${kVValue.toFixed(1)} kV`;
        } else {
          return `${kVValue.toFixed(2)} kV`;
        }
      }
    }
  }
  
  // If it doesn't contain 'kV', assume it's in volts and convert
  const numericValue = parseFloat(cleanVoltage.replace(/[^\d.]/g, ''));
  
  if (isNaN(numericValue)) {
    return cleanVoltage; // Return original if can't parse
  }
  
  // Convert to kV (divide by 1000)
  const kVValue = numericValue / 1000;
  
  // Format with appropriate decimal places
  if (kVValue >= 100) {
    return `${Math.round(kVValue)} kV`;
  } else if (kVValue >= 10) {
    return `${kVValue.toFixed(1)} kV`;
  } else {
    return `${kVValue.toFixed(2)} kV`;
  }
};

export function InteractiveMap({
  initialLatitude = DEFAULT_LATITUDE,
  initialLongitude = DEFAULT_LONGITUDE,
  initialZoom = DEFAULT_ZOOM,
  markers = [],
  mapboxAccessToken,
  height = "300px",
  onMarkerClick,
  onPowerLineClick,
  onEmptyMapClick,
  selectedMarkerId,
  selectedPowerLineId,
  selectedFlowgate,
}: InteractiveMapProps) {
  const [viewport, setViewport] = React.useState({
    latitude: initialLatitude,
    longitude: initialLongitude,
    zoom: initialZoom,
  });
  const [isLoading, setIsLoading] = React.useState(true);
  const [isFullScreen, setIsFullScreen] = React.useState(false);
  const [powerInfrastructureData, setPowerInfrastructureData] = React.useState<PowerInfrastructureData | null>(null);
  const [selectedFlowgateGroup, setSelectedFlowgateGroup] = React.useState<string | null>(null);
  const [clickedLineId, setClickedLineId] = React.useState<number | null>(null);
  const [generatorData, setGeneratorData] = React.useState<GeneratorData | null>(null);
  const [plantData, setPlantData] = React.useState<PowerPlantsData | null>(null);
  
  // Modern organized filter state
  const [filters, setFilters] = React.useState({
    infrastructure: {
      dams: true,
      transmission: {
        enabled: true,
        voltages: {
          '500kV': true,
          '230kV': true,
          '115kV': true,
          'other': true
        }
      },
      substations: false
    },
    generation: {
      plants: true,
      generators: true,
      types: {
        nuclear: true,
        solar: true,
        wind: true,
        hydro: true,
        gas: true,
        coal: true,
        biomass: true,
        geothermal: true,
        other: true
      }
    }
  });

  // Quick access getters for backward compatibility
  const showDams = filters.infrastructure.dams;
  const showPowerLines = filters.infrastructure.transmission.enabled;
  const showSubstations = filters.infrastructure.substations;
  const showPlants = filters.generation.plants;
  const showGenerators = filters.generation.generators;
  const show500kV = filters.infrastructure.transmission.voltages['500kV'];
  const show230kV = filters.infrastructure.transmission.voltages['230kV'];
  const show115kV = filters.infrastructure.transmission.voltages['115kV'];
  const showOtherVoltages = filters.infrastructure.transmission.voltages.other;
  const showNuclear = filters.generation.types.nuclear;
  const showSolar = filters.generation.types.solar;
  const showWind = filters.generation.types.wind;
  const showHydro = filters.generation.types.hydro;
  const showGas = filters.generation.types.gas;
  const showCoal = filters.generation.types.coal;
  const showBiomass = filters.generation.types.biomass;
  const showGeothermal = filters.generation.types.geothermal;
  const showOtherTypes = filters.generation.types.other;

  // Helper function to update filters with proper typing
  const updateFilter = React.useCallback((path: string[], value: boolean | object) => {
    setFilters(prev => {
      const newFilters = { ...prev };
      let current = newFilters as Record<string, any>;
      for (let i = 0; i < path.length - 1; i++) {
        current[path[i]] = { ...current[path[i]] };
        current = current[path[i]];
      }
      current[path[path.length - 1]] = value;
      return newFilters;
    });
  }, []);

  // Add hover state for dam markers
  const [hoveredMarker, setHoveredMarker] = React.useState<MapMarker | null>(null);

  // Add debouncing for hover events to prevent flickering
  const hoverTimeoutRef = React.useRef<NodeJS.Timeout | null>(null);

  const handleMarkerMouseEnter = React.useCallback((marker: MapMarker) => {
    // Clear any existing timeout
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
    }
    // Set the hovered marker immediately
    setHoveredMarker(marker);
  }, []);

  const handleMarkerMouseLeave = React.useCallback(() => {
    // Clear any existing timeout
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
    }
    // Debounce the clearing of hovered marker
    hoverTimeoutRef.current = setTimeout(() => {
      setHoveredMarker(null);
    }, 100); // 100ms delay before clearing
  }, []);

  // Cleanup timeout on unmount
  React.useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
    };
  }, []);

  // Replace the hardcoded timeout effect with data-driven loading
  React.useEffect(() => {
    // Set loading to false once power infrastructure data is loaded (or failed to load)
    if (powerInfrastructureData !== null) {
      setIsLoading(false);
    }
  }, [powerInfrastructureData]);

  React.useEffect(() => {
    // Update viewport if initial props change
    setViewport({
      latitude: initialLatitude,
      longitude: initialLongitude,
      zoom: initialZoom,
    });
  }, [initialLatitude, initialLongitude, initialZoom]);

  const handleMarkerClick = (marker: MapMarker) => {
    setSelectedFlowgateGroup(null);
    setClickedLineId(null);
    if (onMarkerClick) {
      onMarkerClick(marker);
    }
  };

  const toggleFullScreen = () => {
    setIsFullScreen(!isFullScreen);
  };

  const handleEscapeKey = React.useCallback((event: KeyboardEvent) => {
    if (event.key === 'Escape' && isFullScreen) {
      setIsFullScreen(false);
    }
  }, [isFullScreen]);

  React.useEffect(() => {
    if (isFullScreen) {
      document.addEventListener('keydown', handleEscapeKey);
      document.body.style.overflow = 'hidden';
    } else {
      document.removeEventListener('keydown', handleEscapeKey);
      document.body.style.overflow = 'unset';
    }
    
    return () => {
      document.removeEventListener('keydown', handleEscapeKey);
      document.body.style.overflow = 'unset';
    };
  }, [isFullScreen, handleEscapeKey]);

  // Then modify the loadPowerInfrastructure function:
  React.useEffect(() => {
    async function loadPowerInfrastructure() {
      try {
        // Load power infrastructure with zoom level for simplification
        const data = await getPowerInfrastructure(viewport.zoom);
        console.log("Power infrastructure data received:", data);
        
        // Format voltage values in the data
        if (data && data.features) {
          const formattedData = {
            ...data,
            features: data.features.map(feature => ({
              ...feature,
              properties: {
                ...feature.properties,
                voltage_formatted: formatVoltageToKV(feature.properties.voltage)
              }
            }))
          };
          
          // Log capacity factor information
          const flowgateLines = formattedData.features.filter(f => f.properties.is_flowgate_line);
          const capacityFactorStats = flowgateLines.reduce((acc, line) => {
            const cf = line.properties.capacity_factor;
            if (cf < 0.4) acc.green++;
            else if (cf < 0.6) acc.yellow++;
            else if (cf < 0.8) acc.orange++;
            else acc.red++;
            return acc;
          }, { green: 0, yellow: 0, orange: 0, red: 0 });
          
          console.log(`Capacity factor coloring: ${flowgateLines.length} flowgate lines loaded -`, 
                     `Green: ${capacityFactorStats.green}, Yellow: ${capacityFactorStats.yellow}, ` +
                     `Orange: ${capacityFactorStats.orange}, Red: ${capacityFactorStats.red}`);
          
          setPowerInfrastructureData(formattedData);
        } else {
          setPowerInfrastructureData(data);
        }
      } catch (error) {
        console.error("Failed to load power infrastructure data:", error);
        setPowerInfrastructureData(null);
      }
    }
    
    // Debounce the loading to avoid too many requests during pan/zoom
    const timeoutId = setTimeout(loadPowerInfrastructure, 300);
    return () => clearTimeout(timeoutId);
  }, [viewport.zoom]);

  // Optimized generator loading - only load once or when generation is toggled
  const [generatorDataLoaded, setGeneratorDataLoaded] = React.useState(false);
  const [allGeneratorData, setAllGeneratorData] = React.useState<GeneratorData | null>(null);
  
  React.useEffect(() => {
    async function loadAllGenerators() {
      if (generatorDataLoaded || !showGenerators) return;
      
      try {
        // Load all generator data once with all types
        const data = await getPowerGenerators(22); // Get all data without type filter
        console.log("All generator data loaded:", data);
        setAllGeneratorData(data);
        setGeneratorDataLoaded(true);
      } catch (error) {
        console.error("Failed to load generator data:", error);
        setAllGeneratorData(null);
      }
    }
    
    if (showGenerators) {
      loadAllGenerators();
    }
  }, [showGenerators, generatorDataLoaded]);
  
  // Filter generator data based on current type selections
  React.useEffect(() => {
    if (!allGeneratorData || !showGenerators) {
      setGeneratorData(null);
      return;
    }
    
    // Client-side filtering based on enabled types
    const enabledTypes = [];
    if (showNuclear) enabledTypes.push('nuclear');
    if (showSolar) enabledTypes.push('solar', 'photovoltaic');
    if (showWind) enabledTypes.push('wind');
    if (showHydro) enabledTypes.push('hydro', 'water');
    if (showGas) enabledTypes.push('gas', 'natural_gas');
    if (showCoal) enabledTypes.push('coal');
    if (showBiomass) enabledTypes.push('biomass', 'biogas');
    if (showGeothermal) enabledTypes.push('geothermal');
    if (showOtherTypes) enabledTypes.push('oil', 'diesel', 'waste');
    
    if (enabledTypes.length === 0) {
      setGeneratorData({ ...allGeneratorData, features: [] });
      return;
    }
    
    const filteredFeatures = allGeneratorData.features.filter(feature => {
      const fuelType = (feature.properties.fuel_type || '').toLowerCase();
      return enabledTypes.some(type => fuelType.includes(type.toLowerCase()));
    });
    
    setGeneratorData({ ...allGeneratorData, features: filteredFeatures });
  }, [allGeneratorData, showGenerators, showNuclear, showSolar, showWind, showHydro, showGas, showCoal, showBiomass, showGeothermal, showOtherTypes]);

  // Optimized plant loading - only load once or when plants are toggled
  const [plantDataLoaded, setPlantDataLoaded] = React.useState(false);
  const [allPlantData, setAllPlantData] = React.useState<PowerPlantsData | null>(null);
  
  React.useEffect(() => {
    async function loadAllPlants() {
      if (plantDataLoaded || !showPlants) return;
      
      try {
        // Load all plant data once with all types
        const data = await getPowerPlants(22); // Get all data without type filter
        console.log("All plant data loaded:", data);
        setAllPlantData(data);
        setPlantDataLoaded(true);
      } catch (error) {
        console.error("Failed to load plant data:", error);
        setAllPlantData(null);
      }
    }
    
    if (showPlants) {
      loadAllPlants();
    }
  }, [showPlants, plantDataLoaded]);
  
  // Filter plant data based on current type selections
  React.useEffect(() => {
    if (!allPlantData || !showPlants) {
      setPlantData(null);
      return;
    }
    
    // Client-side filtering based on enabled types
    const enabledTypes = [];
    if (showNuclear) enabledTypes.push('nuclear');
    if (showSolar) enabledTypes.push('solar', 'photovoltaic');
    if (showWind) enabledTypes.push('wind');
    if (showHydro) enabledTypes.push('hydro', 'water');
    if (showGas) enabledTypes.push('gas', 'natural_gas');
    if (showCoal) enabledTypes.push('coal');
    if (showBiomass) enabledTypes.push('biomass', 'biogas');
    if (showGeothermal) enabledTypes.push('geothermal');
    if (showOtherTypes) enabledTypes.push('oil', 'diesel', 'waste');
    
    if (enabledTypes.length === 0) {
      setPlantData({ ...allPlantData, features: [] });
      return;
    }
    
    const filteredFeatures = allPlantData.features.filter(feature => {
      const plantSource = (feature.properties.plant_source || '').toLowerCase();
      const plantMethod = (feature.properties.plant_method || '').toLowerCase();
      const type = (feature.properties.type || '').toLowerCase();
      
      return enabledTypes.some(enabledType => 
        plantSource.includes(enabledType.toLowerCase()) ||
        plantMethod.includes(enabledType.toLowerCase()) ||
        type.includes(enabledType.toLowerCase())
      );
    });
    
    setPlantData({ ...allPlantData, features: filteredFeatures });
  }, [allPlantData, showPlants, showNuclear, showSolar, showWind, showHydro, showGas, showCoal, showBiomass, showGeothermal, showOtherTypes]);

  // Add effect to sync external selectedFlowgate prop with internal state
  React.useEffect(() => {
    setSelectedFlowgateGroup(selectedFlowgate || null);
  }, [selectedFlowgate]);

  // Add effect to sync external selectedPowerLineId with internal state
  React.useEffect(() => {
    setClickedLineId(selectedPowerLineId || null);
  }, [selectedPowerLineId]);

  const [pulseOpacity, setPulseOpacity] = React.useState(0.8);

  // Add pulsing animation for flowgate lines
  React.useEffect(() => {
    const interval = setInterval(() => {
      setPulseOpacity(() => {
        // Create a sine wave between 0.6 and 1.0
        const time = Date.now() / 1000; // Convert to seconds
        return 0.6 + 0.2 * (Math.sin(time * 2) + 1); // Oscillates between 0.6 and 1.0
      });
    }, 50); // Update every 50ms for smooth animation

    return () => clearInterval(interval);
  }, []);

  if (isLoading) {
    return <MapSkeleton style={{ height, width: '100%' }} />;
  }

  const mapComponent = (
    <div className="relative w-full h-full">
      <ReactMapGL
        {...viewport}
        mapboxAccessToken={mapboxAccessToken}
        mapStyle={BASE_STYLE}
        onMove={(evt: ViewStateChangeEvent) => setViewport(evt.viewState)}
        onClick={(event) => {
          // Handle click events on power lines
          const features = event.features;
          
          // Check if we clicked on a power line
          if (features && features.length > 0) {
            const powerLineFeature = features.find(f => f.source === 'power-infrastructure' && (f.layer?.id === 'power-lines' || f.layer?.id === 'power-lines-clickable'));
            if (powerLineFeature && powerLineFeature.properties) {
              const lineId = powerLineFeature.properties.gid;
              const flowgate = powerLineFeature.properties.flowgate;
              const lineName = powerLineFeature.properties.name;
              const voltage = powerLineFeature.properties.voltage || 'Unknown';
              const operator = powerLineFeature.properties.operator || 'Unknown';
              const ref = powerLineFeature.properties.ref || '';
              
              // Find all lines in the same flowgate group
              const associatedLines = flowgate && powerInfrastructureData 
                ? powerInfrastructureData.features
                    .filter(f => f.properties.flowgate === flowgate && f.properties.gid !== lineId)
                    .map(f => f.properties.name)
                    .filter(name => name && name !== 'Unnamed')
                : [];
              
              console.log('Clicked power line:', {
                id: lineId,
                name: lineName,
                flowgate: flowgate,
                voltage: voltage,
                operator: operator,
                ref: ref,
                associatedLines: associatedLines,
                capacity_factor: powerLineFeature.properties.capacity_factor,
                capacity_factor_timestamp: powerLineFeature.properties.capacity_factor_timestamp,
                is_flowgate_line: powerLineFeature.properties.is_flowgate_line
              });
              
              setClickedLineId(lineId);
              
              if (flowgate) {
                setSelectedFlowgateGroup(flowgate);
                console.log('Selected flowgate group:', flowgate);
              } else {
                setSelectedFlowgateGroup(null);
                console.log('No flowgate associated with this line');
              }

              // Call parent callback to update dashboard state
              if (onPowerLineClick) {
                onPowerLineClick({
                  id: lineId,
                  name: lineName,
                  flowgate: flowgate,
                  voltage: voltage,
                  operator: operator,
                  ref: ref,
                  associatedLines: associatedLines,
                  capacityFactor: powerLineFeature.properties.capacity_factor || 0
                });
              }
              
              // Don't call empty map click since we clicked a power line
              return;
            }
          }

          // Check if we clicked near a dam marker by checking the click coordinates
          // against marker positions (with some tolerance for the marker size)
          const clickLngLat = event.lngLat;
          const clickedNearMarker = markers.some(marker => {
            const distance = Math.sqrt(
              Math.pow(clickLngLat.lng - marker.longitude, 2) + 
              Math.pow(clickLngLat.lat - marker.latitude, 2)
            );
            // If click is within ~0.1 degrees of a marker, consider it a marker click
            return distance < 0.1;
          });

          // Only call empty map click if we didn't click near any markers
          if (!clickedNearMarker && onEmptyMapClick) {
            onEmptyMapClick();
          }
        }}
        onMouseEnter={(event) => {
          // Check if we're hovering over a power line
          const features = event.target.queryRenderedFeatures(event.point, {
            layers: ['power-lines', 'power-lines-clickable']
          });
          
          if (features.length > 0) {
            event.target.getCanvas().style.cursor = 'pointer';
          }
        }}
        onMouseLeave={(event) => {
          // Reset cursor when leaving power lines
          event.target.getCanvas().style.cursor = '';
        }}
        onMouseMove={(event) => {
          // Update cursor based on what we're hovering over
          const features = event.target.queryRenderedFeatures(event.point, {
            layers: ['power-lines', 'power-lines-clickable']
          });
          
          event.target.getCanvas().style.cursor = features.length > 0 ? 'pointer' : '';
        }}
        interactiveLayerIds={['power-lines', 'power-lines-clickable']}
        minZoom={4}
        maxZoom={22}
        scrollZoom={true}
        style={{
          width: '100%',
          height: '100%',
          transition: 'filter 0.3s ease'
        }}
      >
        <NavigationControl position="top-right" />
        
        {/* Blue water overlay - makes all water features blue */}
        <Source
          id="water-overlay"
          type="vector"
          url="mapbox://mapbox.mapbox-streets-v8"
        >
          {/* Water bodies (lakes, rivers, etc.) - only show large bodies at default zoom */}
          <Layer
            id="water-bodies-blue"
            type="fill"
            source-layer="water"
            paint={{
              "fill-color": "#1976d2",
              "fill-opacity": 0.7
            }}
            filter={[
              "all",
              [">=", ["get", "area"], 100000], // Only show larger water bodies
              ["<=", ["zoom"], 8] // Only show up to zoom level 8
            ]}
            maxzoom={8}
          />
          {/* Waterways (rivers, streams) - only show major waterways at default zoom */}
          <Layer
            id="waterways-blue"
            type="line"
            source-layer="waterway"
            paint={{
              "line-color": "#1565c0",
              "line-width": 1.5,
              "line-opacity": 0.8
            }}
            filter={[
              "all",
              ["in", ["get", "class"], ["literal", ["river", "canal"]]], // Only show major waterways
              ["<=", ["zoom"], 7] // Only show up to zoom level 7
            ]}
            maxzoom={7}
          />
        </Source>
        
        {/* Power Infrastructure Layers */}
        {powerInfrastructureData && (
          <Source
            id="power-infrastructure"
            type="geojson"
            data={powerInfrastructureData}
          >
            {/* Invisible wider power lines for easier clicking */}
            {showPowerLines && (
              <Layer
                id="power-lines-clickable"
                type="line"
                filter={["==", ["get", "geometry_type"], "ST_LineString"]}
                paint={{
                  "line-color": "transparent",
                  "line-width": 8, // Much wider invisible line for easier clicking
                  "line-opacity": 0
                }}
                layout={{
                  "line-cap": "round",
                  "line-join": "round"
                }}
              />
            )}
            
            {/* Visible power lines (transmission lines) */}
            {showPowerLines && (
              <Layer
                id="power-lines"
                type="line"
                filter={["==", ["get", "geometry_type"], "ST_LineString"]}
                paint={{
                  "line-color": [
                    "case",
                    // If this line is part of selected flowgate group, highlight in cyan
                    [
                      "any",
                      ["==", ["get", "flowgate"], selectedFlowgateGroup || ""],
                      ["==", ["get", "gid"], clickedLineId || -1]
                    ],
                    "#00bcd4", // Cyan for selected flowgate or clicked line
                    // Color flowgate lines based on capacity factor (more lenient scale)
                    ["==", ["get", "is_flowgate_line"], true],
                    [
                      "case",
                      // Green for capacity factor < 0.7
                      ["<", ["get", "capacity_factor"], 0.7],
                      "#22c55e", // Green
                      // Yellow for capacity factor 0.7-1.0
                      ["<", ["get", "capacity_factor"], 1.0],
                      "#eab308", // Yellow
                      // Orange for capacity factor 1.0-1.3
                      ["<", ["get", "capacity_factor"], 1.3],
                      "#f97316", // Orange
                      // Red for capacity factor >= 1.3
                      "#ef4444" // Red
                    ],
                    // All other non-flowgate lines are neutral gray
                    "#708090"
                  ],
                  "line-opacity": [
                    "case",
                    // Hide lines based on voltage visibility settings first
                    [
                      "all",
                      ["in", "500", ["to-string", ["get", "voltage"]]],
                      !show500kV
                    ],
                    0, // Hide 500kV lines if disabled
                    [
                      "all", 
                      ["in", "230", ["to-string", ["get", "voltage"]]],
                      !show230kV
                    ],
                    0, // Hide 230kV lines if disabled
                    [
                      "all",
                      ["in", "115", ["to-string", ["get", "voltage"]]],
                      !show115kV
                    ],
                    0, // Hide 115kV lines if disabled
                    [
                      "all",
                      ["!", ["in", "500", ["to-string", ["get", "voltage"]]]],
                      ["!", ["in", "230", ["to-string", ["get", "voltage"]]]],
                      ["!", ["in", "115", ["to-string", ["get", "voltage"]]]],
                      !showOtherVoltages
                    ],
                    0, // Hide other voltage lines if disabled
                    // For visible flowgate lines, use pulsing opacity
                    ["==", ["get", "is_flowgate_line"], true],
                    pulseOpacity, // Animated opacity value
                    // Default opacity for non-flowgate lines
                    0.8
                  ],
                  "line-width": [
                    "case",
                    // If this line is part of selected flowgate group, make it extra thick
                    [
                      "any",
                      ["==", ["get", "flowgate"], selectedFlowgateGroup || ""],
                      ["==", ["get", "gid"], clickedLineId || -1]
                    ],
                    8, // Selected lines get extra thickness
                    
                    // Base width on voltage level - thicker = higher voltage
                    ["in", "500", ["to-string", ["get", "voltage"]]],
                    4, // 500kV lines - thickest (major transmission backbone)
                    ["in", "230", ["to-string", ["get", "voltage"]]],
                    2.5, // 230kV lines - medium-thick (regional transmission)
                    ["in", "115", ["to-string", ["get", "voltage"]]],
                    1.5, // 115kV lines - medium (local transmission)
                    
                    // Default for other/unknown voltages
                    1 // Thinnest for other voltages
                  ]
                }}
                layout={{
                  "line-cap": "round",
                  "line-join": "round"
                }}
              />
            )}

            {/* Transmission Line Labels - Show at zoom 6+ */}
            {showPowerLines && (
              <Layer
                id="power-line-labels"
                type="symbol"
                filter={["==", ["get", "geometry_type"], "ST_LineString"]}
                minzoom={6}
                layout={{
                  "text-field": [
                    "case",
                    // If line has both name and voltage, combine them
                    [
                      "all",
                      ["!=", ["get", "name"], null],
                      ["!=", ["get", "name"], ""],
                      ["!=", ["get", "voltage_formatted"], null],
                      ["!=", ["get", "voltage_formatted"], ""]
                    ],
                    [
                      "concat",
                      ["get", "name"],
                      " - ",
                      ["get", "voltage_formatted"]
                    ],
                    // If line has name but no voltage, use name only
                    [
                      "all",
                      ["!=", ["get", "name"], null],
                      ["!=", ["get", "name"], ""]
                    ],
                    ["get", "name"],
                    // If no name but has voltage, show formatted voltage
                    [
                      "all",
                      ["!=", ["get", "voltage_formatted"], null],
                      ["!=", ["get", "voltage_formatted"], ""]
                    ],
                    ["get", "voltage_formatted"],
                    // If no name or voltage but has operator, show operator
                    ["!=", ["get", "operator"], null],
                    ["get", "operator"],
                    // Default fallback
                    "Transmission Line"
                  ],
                  "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
                  "text-size": [
                    "interpolate",
                    ["linear"],
                    ["zoom"],
                    8, 12,   // At zoom 8, text size 12 (increased from 9)
                    10, 14,  // At zoom 10, text size 14 (increased from 11)
                    12, 16,  // At zoom 12, text size 16 (increased from 12)
                    16, 18   // At zoom 16, text size 18 (increased from 14)
                  ],
                  "symbol-placement": "line",
                  "text-rotation-alignment": "map",
                  "text-pitch-alignment": "viewport",
                  "text-max-angle": 30,
                  "text-padding": 5,
                  "text-allow-overlap": false,
                  "text-ignore-placement": false
                }}
                paint={{
                  "text-color": [
                    "case",
                    // If this line is selected/highlighted, use cyan
                    [
                      "any",
                      ["==", ["get", "flowgate"], selectedFlowgateGroup || ""],
                      ["==", ["get", "gid"], clickedLineId || -1]
                    ],
                    "#00bcd4",
                    // Otherwise use dark color for contrast
                    "#333333"
                  ],
                  "text-halo-color": "#ffffff",
                  "text-halo-width": 2,
                  "text-opacity": [
                    "case",
                    // Hide labels based on voltage visibility settings
                    [
                      "all",
                      ["in", "500", ["to-string", ["get", "voltage"]]],
                      !show500kV
                    ],
                    0, // Hide 500kV labels if disabled
                    [
                      "all", 
                      ["in", "230", ["to-string", ["get", "voltage"]]],
                      !show230kV
                    ],
                    0, // Hide 230kV labels if disabled
                    [
                      "all",
                      ["in", "115", ["to-string", ["get", "voltage"]]],
                      !show115kV
                    ],
                    0, // Hide 115kV labels if disabled
                    [
                      "all",
                      ["!", ["in", "500", ["to-string", ["get", "voltage"]]]],
                      ["!", ["in", "230", ["to-string", ["get", "voltage"]]]],
                      ["!", ["in", "115", ["to-string", ["get", "voltage"]]]],
                      !showOtherVoltages
                    ],
                    0, // Hide other voltage labels if disabled
                    0.9 // Default opacity
                  ]
                }}
              />
            )}

            {/* Power stations and plants (polygons) */}
            {showPlants && (
              <Layer
                id="power-polygons"
                type="fill"
                filter={["in", ["get", "geometry_type"], ["literal", ["ST_Polygon", "ST_MultiPolygon"]]]}
                paint={{
                  "fill-color": "#9C27B0",
                  "fill-opacity": 0.6,
                  "fill-outline-color": "#333333"
                }}
              />
            )}

            {/* Power station and plant outlines */}
            {showPlants && (
              <Layer
                id="power-polygon-outlines"
                type="line"
                filter={["in", ["get", "geometry_type"], ["literal", ["ST_Polygon", "ST_MultiPolygon"]]]}
                paint={{
                  "line-color": "#333333",
                  "line-width": 1,
                  "line-opacity": 0.8
                }}
              />
            )}

            {/* Power infrastructure points (substations, etc.) */}
            {showSubstations && (
              <Layer
                id="power-points"
                type="circle"
                filter={["==", ["get", "geometry_type"], "ST_Point"]}
                paint={{
                  "circle-color": "#757575",
                  "circle-radius": 4,
                  "circle-opacity": 0.8,
                  "circle-stroke-color": "#333333",
                  "circle-stroke-width": 1
                }}
              />
            )}
          </Source>
        )}
        
        {/* Power Plant Layers */}
        {plantData && showPlants && (
          <Source
            id="power-plants"
            type="geojson"
            data={plantData}
          >
            {/* Plant polygons/points */}
            <Layer
              id="plant-points"
              type="circle"
              paint={{
                "circle-color": [
                  "case",
                  // Check plant_source, plant_method, and type fields
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["nuclear"]]],
                  "#ff4500", // Nuclear - orange-red
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["solar", "photovoltaic"]]],
                  "#ffd700", // Solar - gold
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["wind"]]],
                  "#32cd32", // Wind - lime green
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["hydro", "water"]]],
                  "#1e90ff", // Hydro - dodger blue
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["gas", "natural_gas"]]],
                  "#ff69b4", // Gas - hot pink
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["coal"]]],
                  "#8b4513", // Coal - saddle brown
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["biomass", "biogas"]]],
                  "#228b22", // Biomass - forest green
                  ["in", ["downcase", ["coalesce", ["get", "plant_source"], ""]], ["literal", ["geothermal"]]],
                  "#dc143c", // Geothermal - crimson
                  // Check plant_method as fallback
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["nuclear"]]],
                  "#ff4500",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["solar", "photovoltaic"]]],
                  "#ffd700",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["wind"]]],
                  "#32cd32",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["hydro", "water"]]],
                  "#1e90ff",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["gas", "natural_gas"]]],
                  "#ff69b4",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["coal"]]],
                  "#8b4513",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["biomass", "biogas"]]],
                  "#228b22",
                  ["in", ["downcase", ["coalesce", ["get", "plant_method"], ""]], ["literal", ["geothermal"]]],
                  "#dc143c",
                  // Check type as final fallback
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["nuclear"]]],
                  "#ff4500",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["solar", "photovoltaic"]]],
                  "#ffd700",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["wind"]]],
                  "#32cd32",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["hydro", "water"]]],
                  "#1e90ff",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["gas", "natural_gas"]]],
                  "#ff69b4",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["coal"]]],
                  "#8b4513",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["biomass", "biogas"]]],
                  "#228b22",
                  ["in", ["downcase", ["coalesce", ["get", "type"], ""]], ["literal", ["geothermal"]]],
                  "#dc143c",
                  "#9370db" // Other - medium purple (default)
                ],
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  6, 4,
                  10, 8,
                  14, 12
                ],
                "circle-opacity": 0.7,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 2
              }}
            />
            
            {/* Plant labels at high zoom */}
            <Layer
              id="plant-labels"
              type="symbol"
              minzoom={10}
              layout={{
                "text-field": ["get", "name"],
                "text-font": ["Open Sans Bold"],
                "text-size": 11,
                "text-offset": [0, 2],
                "text-anchor": "top"
              }}
              paint={{
                "text-color": "#333333",
                "text-halo-color": "#ffffff",
                "text-halo-width": 2
              }}
            />
          </Source>
        )}
        
        {/* Power Generator Layers */}
        {generatorData && showGenerators && (
          <Source
            id="power-generators"
            type="geojson"
            data={generatorData}
          >
            {/* Generator points */}
            <Layer
              id="generator-points"
              type="circle"
              paint={{
                "circle-color": [
                  "case",
                  // Use fuel_type field (which combines generator_source and generator_type)
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["nuclear"]]],
                  "#ff4500", // Nuclear - orange-red
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["solar", "photovoltaic"]]],
                  "#ffd700", // Solar - gold
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["wind"]]],
                  "#32cd32", // Wind - lime green
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["hydro", "water"]]],
                  "#1e90ff", // Hydro - dodger blue
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["gas", "natural_gas"]]],
                  "#ff69b4", // Gas - hot pink
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["coal"]]],
                  "#8b4513", // Coal - saddle brown
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["biomass", "biogas"]]],
                  "#228b22", // Biomass - forest green
                  ["in", ["downcase", ["coalesce", ["get", "fuel_type"], ""]], ["literal", ["geothermal"]]],
                  "#dc143c", // Geothermal - crimson
                  "#9370db" // Other - medium purple (default)
                ],
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  8, 2,
                  12, 4,
                  16, 6
                ],
                "circle-opacity": 0.8,
                "circle-stroke-color": "#ffffff",
                "circle-stroke-width": 1
              }}
            />
            
            {/* Generator labels at very high zoom */}
            <Layer
              id="generator-labels"
              type="symbol"
              minzoom={14}
              layout={{
                "text-field": ["coalesce", ["get", "name"], ["get", "plant_name"]],
                "text-font": ["Open Sans Regular"],
                "text-size": 9,
                "text-offset": [0, 1.2],
                "text-anchor": "top"
              }}
              paint={{
                "text-color": "#333333",
                "text-halo-color": "#ffffff",
                "text-halo-width": 1
              }}
            />
          </Source>
        )}

        {/* Dam markers with proper dam icons */}
        {showDams && markers && markers.length > 0 && markers.map((marker) => (
          <Marker
            key={`marker-${marker.id}`}
            latitude={marker.latitude}
            longitude={marker.longitude}
          >
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                handleMarkerClick(marker);
              }}
              onMouseEnter={() => handleMarkerMouseEnter(marker)}
              onMouseLeave={handleMarkerMouseLeave}
              style={{
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                padding: 0,
                zIndex: 1000,
              }}
              aria-label={`View details for ${marker.name || 'dam'}`}
            >
              {/* Dam Icon */}
              <div className="relative">
                <svg 
                  width="24" 
                  height="24" 
                  viewBox="0 0 24 24"
                  style={{
                    transform: "translateY(-12px)",
                    filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.3))"
                  }}
                >
                  {/* Dam structure */}
                  <path 
                    d="M2 14h20l-2 6H4l-2-6zm0-2h20V8H2v4zm4-8h12v4H6V4z" 
                    fill={String(marker.id) === String(selectedMarkerId) ? "#2196f3" : "#1976d2"}
                    stroke="#ffffff"
                    strokeWidth="1.5"
                  />
                  {/* Water indicator */}
                  <rect 
                    x="3" 
                    y="15" 
                    width="18" 
                    height="2" 
                    fill={String(marker.id) === String(selectedMarkerId) ? "#64b5f6" : "#42a5f5"}
                    opacity="0.8"
                  />
                </svg>
              </div>
            </button>
          </Marker>
        ))}

        {/* Dam hover popup */}
        {hoveredMarker && (
          <Popup
            latitude={hoveredMarker.latitude}
            longitude={hoveredMarker.longitude}
            closeButton={false}
            closeOnClick={false}
            offset={[0, -20]}
            className="dam-hover-popup"
            style={{ pointerEvents: 'none' }}
          >
            <div style={{ pointerEvents: 'none' }}>
              {hoveredMarker.name || 'Dam'}
            </div>
          </Popup>
        )}
      </ReactMapGL>
      
      {/* Columbia River System Label Overlay with Full Screen Button */}
      <div 
        className="absolute top-4 left-4 bg-white/95 rounded-lg px-3 py-2 shadow-lg border"
        style={{ zIndex: 40 }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-blue-900 mb-1">Columbia River Basin</h4>
            <p className="text-xs text-gray-600">Water Features Highlighted</p>
          </div>
          <button
            onClick={toggleFullScreen}
            className="flex items-center justify-center w-8 h-8 rounded-md bg-blue-100 hover:bg-blue-200 transition-colors"
            aria-label={isFullScreen ? "Exit full screen" : "Enter full screen"}
            title={isFullScreen ? "Exit full screen (ESC)" : "View full screen"}
          >
            {isFullScreen ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-blue-700">
                <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-blue-700">
                <path d="M3 7V5a2 2 0 0 1 2-2h2m10 0h2a2 2 0 0 1 2 2v2m0 10v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/>
              </svg>
            )}
          </button>
        </div>
      </div>
      
      {/* Modern Legend */}
      <div 
        className="absolute bottom-4 right-4 bg-white/95 backdrop-blur-sm rounded-xl shadow-xl border border-gray-200"
        style={{ zIndex: 40, minWidth: '240px', maxWidth: '280px' }}
      >
        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-900 text-sm">Map Layers</h3>
          </div>
          
          {/* Selected Flowgate Info */}
          {selectedFlowgateGroup && (
            <div className="bg-cyan-50 border border-cyan-200 rounded-lg p-3 mb-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-cyan-800 text-xs mb-1">Active Selection</div>
                  <div className="text-cyan-700 text-xs font-mono truncate">{selectedFlowgateGroup}</div>
                </div>
                <button 
                  onClick={() => {
                    setSelectedFlowgateGroup(null);
                    setClickedLineId(null);
                  }}
                  className="text-cyan-600 hover:text-cyan-800 p-1 rounded-full hover:bg-cyan-100 transition-colors"
                  title="Clear selection"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
          
          <div className="space-y-4 text-xs">
            {/* Infrastructure Section */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-gray-800 text-xs uppercase tracking-wider">Infrastructure</h4>
              </div>
              <div className="space-y-2 pl-1">
                {/* Dams */}
                <label className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-1.5 rounded-md transition-colors">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={showDams}
                      onChange={(e) => updateFilter(['infrastructure', 'dams'], e.target.checked)}
                      className="w-4 h-4 text-red-600 border-gray-300 rounded focus:ring-red-500"
                    />
                    <svg className="w-4 h-4 fill-blue-600" viewBox="0 0 24 24">
                      <path d="M2 14h20l-2 6H4l-2-6zm0-2h20V8H2v4zm4-8h12v4H6V4z"/>
                    </svg>
                  </div>
                  <span className="text-gray-700 font-medium">Dams</span>
                </label>
                
                {/* Transmission */}
                <div className="space-y-2">
                  <label className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-1.5 rounded-md transition-colors">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={showPowerLines}
                        onChange={(e) => updateFilter(['infrastructure', 'transmission', 'enabled'], e.target.checked)}
                        className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                      />
                      <div className="w-4 h-1 bg-gray-600 rounded-full"></div>
                    </div>
                    <span className="text-gray-700 font-medium">Transmission Lines</span>
                  </label>
                  
                  {showPowerLines && (
                    <div className="ml-6 space-y-2 border-l-2 border-gray-100 pl-3">
                      <div className="flex items-center gap-2 text-cyan-600 mb-1">
                        <div className="w-3 h-0.5 bg-cyan-500 rounded"></div>
                        <span className="text-xs">Selected lines highlighted</span>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { key: '500kV', label: '500kV', height: '3px', color: 'bg-gray-600' },
                          { key: '230kV', label: '230kV', height: '2px', color: 'bg-gray-600' },
                          { key: '115kV', label: '115kV', height: '1.5px', color: 'bg-gray-600' },
                          { key: 'other', label: 'Other', height: '1px', color: 'bg-gray-600' }
                        ].map(voltage => (
                          <label key={voltage.key} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1 rounded transition-colors">
                            <input
                              type="checkbox"
                              checked={filters.infrastructure.transmission.voltages[voltage.key as keyof typeof filters.infrastructure.transmission.voltages]}
                              onChange={(e) => updateFilter(['infrastructure', 'transmission', 'voltages', voltage.key], e.target.checked)}
                              className="w-3 h-3 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                            />
                            <div className={`w-3 ${voltage.color} rounded`} style={{ height: voltage.height }}></div>
                            <span className="text-xs text-gray-600">{voltage.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Substations */}
                <label className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-1.5 rounded-md transition-colors">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={showSubstations}
                      onChange={(e) => updateFilter(['infrastructure', 'substations'], e.target.checked)}
                      className="w-4 h-4 text-gray-600 border-gray-300 rounded focus:ring-gray-500"
                    />
                    <div className="w-3 h-3 rounded-full bg-gray-500"></div>
                  </div>
                  <span className="text-gray-700 font-medium">Substations</span>
                </label>
              </div>
            </div>

            {/* Generation Section */}
            <div className="border-t border-gray-200 pt-4">
              <div className="flex items-center justify-between mb-2">
                <h4 className="font-medium text-gray-800 text-xs uppercase tracking-wider">Generation</h4>
              </div>
              <div className="space-y-2 pl-1">
                {/* Plants & Generators */}
                <div className="grid grid-cols-2 gap-x-4">
                  <div className="flex items-center justify-between">
                    <label htmlFor="show-plants" className="text-xs text-gray-700 font-medium cursor-pointer">Plants</label>
                    <Switch
                      id="show-plants"
                      checked={showPlants}
                      onCheckedChange={(checked) => updateFilter(['generation', 'plants'], checked)}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <label htmlFor="show-units" className="text-xs text-gray-700 font-medium cursor-pointer">Units</label>
                    <Switch
                      id="show-units"
                      checked={showGenerators}
                      onCheckedChange={(checked) => updateFilter(['generation', 'generators'], checked)}
                    />
                  </div>
                </div>
                
                {/* Generation Types - show when either plants or generators are enabled */}
                {(showPlants || showGenerators) && (
                  <div className="mt-3 border-t border-gray-100 pt-3">
                    <div className="text-xs text-gray-500 mb-2 font-medium">Filter by Type:</div>
                    <div className="grid grid-cols-2 gap-1.5">
                      {[
                        { key: 'nuclear', label: 'Nuclear', color: 'bg-orange-500' },
                        { key: 'solar', label: 'Solar', color: 'bg-yellow-500' },
                        { key: 'wind', label: 'Wind', color: 'bg-green-400' },
                        { key: 'hydro', label: 'Hydro', color: 'bg-blue-500' },
                        { key: 'gas', label: 'Gas', color: 'bg-pink-500' },
                        { key: 'coal', label: 'Coal', color: 'bg-amber-800' },
                        { key: 'biomass', label: 'Biomass', color: 'bg-green-600' },
                        { key: 'geothermal', label: 'Geo', color: 'bg-red-600' },
                        { key: 'other', label: 'Other', color: 'bg-purple-500', span: 'col-span-2' }
                      ].map(type => (
                        <label key={type.key} className={`flex items-center gap-1.5 cursor-pointer hover:bg-gray-50 p-1 rounded transition-colors ${type.span || ''}`}>
                          <input
                            type="checkbox"
                            checked={filters.generation.types[type.key as keyof typeof filters.generation.types]}
                            onChange={(e) => updateFilter(['generation', 'types', type.key], e.target.checked)}
                            className="w-3 h-3 border-gray-300 rounded focus:ring-2"
                            style={{ accentColor: type.color.replace('bg-', '#') }}
                          />
                          <div className={`w-2.5 h-2.5 rounded-full ${type.color}`}></div>
                          <span className="text-xs text-gray-600">{type.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div 
      style={{ height, width: '100%' }} 
      className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden"
    >
      {isFullScreen ? (
        <div 
          className="fixed inset-0 bg-black z-[9999] flex items-center justify-center"
          style={{ height: '100vh', width: '100vw' }}
        >
          <div className="w-full h-full">
            {mapComponent}
          </div>
        </div>
      ) : (
        mapComponent
      )}
    </div>
  );
}

// Remember to set your NEXT_PUBLIC_MAPBOX_TOKEN environment variable! 