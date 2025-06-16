"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapSkeleton } from "@/components/MapSkeleton";
import { getPowerInfrastructure, PowerInfrastructureData, getPowerGenerators, GeneratorData, getPowerPlants, PlantData } from "@/lib/firebase";

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
  const [plantData, setPlantData] = React.useState<PlantData | null>(null);
  const [showGenerators, setShowGenerators] = React.useState(true);
  const [showPlants, setShowPlants] = React.useState(true);
  
  // Visibility controls for legend items
  const [showDams, setShowDams] = React.useState(true);
  const [showPowerLines, setShowPowerLines] = React.useState(true);
  const [showSubstations, setShowSubstations] = React.useState(false);
  const [showPowerPlants, setShowPowerPlants] = React.useState(true);
  
  // Voltage-specific visibility controls
  const [show500kV, setShow500kV] = React.useState(true);
  const [show230kV, setShow230kV] = React.useState(true);
  const [show115kV, setShow115kV] = React.useState(true);
  const [showOtherVoltages, setShowOtherVoltages] = React.useState(true);

  // Add generator type filters
  const [showNuclear, setShowNuclear] = React.useState(true);
  const [showSolar, setShowSolar] = React.useState(true);
  const [showWind, setShowWind] = React.useState(true);
  const [showHydro, setShowHydro] = React.useState(true);
  const [showGas, setShowGas] = React.useState(true);
  const [showCoal, setShowCoal] = React.useState(true);
  const [showBiomass, setShowBiomass] = React.useState(true);
  const [showGeothermal, setShowGeothermal] = React.useState(true);
  const [showOtherTypes, setShowOtherTypes] = React.useState(true);

  React.useEffect(() => {
    // Simulate map loading delay
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 1500);
    return () => clearTimeout(timer);
  }, []);

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

  // Add this helper function to calculate bounding box
  const calculateBbox = (viewport: any) => {
    // Simple approximation - you might want to use a proper library for more accuracy
    const latDelta = 180 / Math.pow(2, viewport.zoom);
    const lngDelta = 360 / Math.pow(2, viewport.zoom);
    
    const minLng = viewport.longitude - lngDelta;
    const maxLng = viewport.longitude + lngDelta;
    const minLat = viewport.latitude - latDelta;
    const maxLat = viewport.latitude + latDelta;
    
    return `${minLng},${minLat},${maxLng},${maxLat}`;
  };

  // Then modify the loadPowerInfrastructure function:
  React.useEffect(() => {
    async function loadPowerInfrastructure() {
      try {
        // Calculate current viewport bounds
        const bbox = calculateBbox(viewport);
        
        // Load power infrastructure with bbox
        const data = await getPowerInfrastructure(bbox);
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
  }, [viewport.zoom, viewport.latitude, viewport.longitude]);

  // Add new effect for loading generators
  React.useEffect(() => {
    async function loadGenerators() {
      try {
        // Calculate current viewport bounds
        const bbox = calculateBbox(viewport);
        
        // Build filter types based on user selections
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
        
        const typesFilter = enabledTypes.length > 0 ? enabledTypes.join(',') : undefined;
        
        // Load generators with bbox, zoom, and type filters
        const data = await getPowerGenerators(bbox, viewport.zoom, typesFilter);
        console.log("Generator data received:", data);
        setGeneratorData(data);
      } catch (error) {
        console.error("Failed to load generator data:", error);
        setGeneratorData(null);
      }
    }
    
    // Only load generators if they're enabled and at zoom level 6+
    if (showGenerators && viewport.zoom >= 6) {
      const timeoutId = setTimeout(loadGenerators, 300);
      return () => clearTimeout(timeoutId);
    } else {
      setGeneratorData(null);
    }
  }, [viewport.zoom, viewport.latitude, viewport.longitude, showGenerators, showNuclear, showSolar, showWind, showHydro, showGas, showCoal, showBiomass, showGeothermal, showOtherTypes]);

  // Add new effect for loading plants
  React.useEffect(() => {
    async function loadPlants() {
      try {
        // Calculate current viewport bounds
        const bbox = calculateBbox(viewport);
        
        // Build filter types based on user selections
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
        
        const typesFilter = enabledTypes.length > 0 ? enabledTypes.join(',') : undefined;
        
        // Load plants with bbox, zoom, and type filters
        const data = await getPowerPlants(bbox, viewport.zoom, typesFilter);
        console.log("Plant data received:", data);
        setPlantData(data);
      } catch (error) {
        console.error("Failed to load plant data:", error);
        setPlantData(null);
      }
    }
    
    // Only load plants if they're enabled and at zoom level 6+
    if (showPlants && viewport.zoom >= 6) {
      const timeoutId = setTimeout(loadPlants, 300);
      return () => clearTimeout(timeoutId);
    } else {
      setPlantData(null);
    }
  }, [viewport.zoom, viewport.latitude, viewport.longitude, showPlants, showNuclear, showSolar, showWind, showHydro, showGas, showCoal, showBiomass, showGeothermal, showOtherTypes]);

  // Add effect to sync external selectedFlowgate prop with internal state
  React.useEffect(() => {
    setSelectedFlowgateGroup(selectedFlowgate || null);
  }, [selectedFlowgate]);

  // Add effect to sync external selectedPowerLineId with internal state
  React.useEffect(() => {
    setClickedLineId(selectedPowerLineId || null);
  }, [selectedPowerLineId]);

  if (isLoading) {
    return <MapSkeleton style={{ height, width: '100%' }} />;
  }

  const mapComponent = (
    <div className="relative w-full h-full">
      <ReactMapGL
        {...viewport}
        width="100%"
        height="100%"
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
                associatedLines: associatedLines
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
                  associatedLines: associatedLines
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
        scrollZoom={{
          speed: 0.02,
          smooth: true
        }}
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
                    // If this line is part of selected flowgate group, highlight in green
                    [
                      "any",
                      ["==", ["get", "flowgate"], selectedFlowgateGroup || ""],
                      ["==", ["get", "gid"], clickedLineId || -1]
                    ],
                    "#00bcd4", // Green for selected flowgate or clicked line
                    ["has", "voltage"],
                    [
                      "case",
                      ["in", "500", ["to-string", ["get", "voltage"]]],  // String conversion + contains check
                      "#ff4444", // High voltage - red
                      ["in", "230", ["to-string", ["get", "voltage"]]],  // String conversion + contains check
                      "#ff8800", // Medium-high voltage - orange
                      ["in", "115", ["to-string", ["get", "voltage"]]],  // String conversion + contains check
                      "#ffcc00", // Medium voltage - yellow
                      "#666666"  // Unknown/low voltage - gray
                    ],
                    "#666666" // Default gray if no voltage
                  ],
                  "line-opacity": [
                    "case",
                    // Hide lines based on voltage visibility settings
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
                    0.8 // Default opacity
                  ],
                  "line-width": [
                    "case",
                    // If this line is part of selected flowgate group, make it much thicker
                    [
                      "any",
                      ["==", ["get", "flowgate"], selectedFlowgateGroup || ""],
                      ["==", ["get", "gid"], clickedLineId || -1]
                    ],
                    6,
                    // Default width
                    1.5
                  ]
                }}
                layout={{
                  "line-cap": "round",
                  "line-join": "round"
                }}
              />
            )}

            {/* Transmission Line Labels - Show at zoom 8+ */}
            {showPowerLines && (
              <Layer
                id="power-line-labels"
                type="symbol"
                filter={["==", ["get", "geometry_type"], "ST_LineString"]}
                minzoom={8}
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
            {showPowerPlants && (
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
            {showPowerPlants && (
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

        {/* Existing dam markers */}
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
              style={{
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                padding: 0,
                zIndex: 1000,
              }}
              aria-label={`View details for ${marker.name || 'marker'}`}
            >
              {/* Columbia River Basin Dam Marker */}
              <div className="relative">
                <svg 
                  height="28" 
                  viewBox="0 0 24 24" 
                  style={{
                    fill: String(marker.id) === String(selectedMarkerId) ? "#2196f3" : "#f44336",
                    stroke: "#ffffff",
                    strokeWidth: "2.5",
                    transform: "translateY(-14px)",
                  }}
                >
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                  <circle cx="12" cy="10" r="3" fill="#ffffff"></circle> 
                </svg>
                {/* Basin indicator */}
                <div 
                  className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-3 h-3 rounded-full"
                  style={{
                    backgroundColor: String(marker.id) === String(selectedMarkerId) ? "#1976d2" : "#d32f2f",
                    border: "2px solid #ffffff",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.3)"
                  }}
                />
              </div>
            </button>
          </Marker>
        ))}
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
      
      {/* Legend */}
      <div 
        className="absolute bottom-4 right-4 bg-white/95 rounded-lg px-3 py-2 shadow-lg border"
        style={{ zIndex: 40 }}
      >
        <div className="text-xs space-y-2">
          <div className="font-medium text-gray-800 mb-2">Legend</div>
          
          {/* Selected Flowgate Info */}
          {selectedFlowgateGroup && (
            <div className="border-b pb-2 mb-2">
              <div className="font-medium text-red-600 mb-1">Selected Flowgate</div>
              <div className="text-red-700 text-xs font-mono">{selectedFlowgateGroup}</div>
              <button 
                onClick={() => {
                  setSelectedFlowgateGroup(null);
                  setClickedLineId(null);
                }}
                className="text-xs text-gray-500 hover:text-gray-700 mt-1"
              >
                Clear selection
              </button>
            </div>
          )}
          
          {/* Dams */}
          <div className="space-y-1">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={showDams}
                onChange={(e) => setShowDams(e.target.checked)}
                className="w-3 h-3"
              />
              <svg height="12" viewBox="0 0 24 24" className="fill-red-500">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
              </svg>
              <span className="text-gray-700 text-xs">Dams</span>
            </label>
          </div>
          
          
          {/* Power Infrastructure */}
          {powerInfrastructureData && (
            <>
              <div className="border-t pt-2">
                <div className="font-medium text-gray-800 mb-1 text-xs">Power Infrastructure</div>
                <div className="space-y-1">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showPowerLines}
                      onChange={(e) => setShowPowerLines(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <div className="w-3 h-0.5 bg-gray-600"></div>
                    <span className="text-gray-600 text-xs">All Power Lines</span>
                  </label>
                  <div className="ml-5 space-y-1">
                    <div className="flex items-center space-x-1">
                      <div className="w-3 h-0.5 bg-cyan-500"></div>
                      <span className="text-gray-600 text-xs">Selected Flowgate</span>
                    </div>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={show500kV}
                        onChange={(e) => setShow500kV(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-3 h-0.5 bg-red-400"></div>
                      <span className="text-gray-600 text-xs">500kV Lines</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={show230kV}
                        onChange={(e) => setShow230kV(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-3 h-0.5 bg-orange-500"></div>
                      <span className="text-gray-600 text-xs">230kV Lines</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={show115kV}
                        onChange={(e) => setShow115kV(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-3 h-0.5 bg-yellow-500"></div>
                      <span className="text-gray-600 text-xs">115kV Lines</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showOtherVoltages}
                        onChange={(e) => setShowOtherVoltages(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-3 h-0.5 bg-gray-600"></div>
                      <span className="text-gray-600 text-xs">Other Voltages</span>
                    </label>
                  </div>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showSubstations}
                      onChange={(e) => setShowSubstations(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <div className="w-2 h-2 rounded-full bg-gray-500"></div>
                    <span className="text-gray-600 text-xs">Substations</span>
                  </label>
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showPowerPlants}
                      onChange={(e) => setShowPowerPlants(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <div className="w-2 h-2 rounded bg-purple-500"></div>
                    <span className="text-gray-600 text-xs">Power Plants</span>
                  </label>
                </div>
              </div>
            </>
          )}

          {/* Power Generation Controls */}
          {(viewport.zoom >= 6 || showPlants || showGenerators) && (
            <div className="border-t pt-2">
              <div className="font-medium text-gray-800 mb-1 text-xs">Power Generation</div>
              <div className="space-y-1">
                {/* Plants control - show at zoom 6+ */}
                {viewport.zoom >= 6 && (
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showPlants}
                      onChange={(e) => setShowPlants(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <span className="text-gray-600 text-xs">Power Plants</span>
                  </label>
                )}
                
                {/* Generators control - show at zoom 6+ */}
                {viewport.zoom >= 6 && (
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showGenerators}
                      onChange={(e) => setShowGenerators(e.target.checked)}
                      className="w-3 h-3"
                    />
                    <span className="text-gray-600 text-xs">Generators</span>
                  </label>
                )}
                
                {/* Type filters - show when either plants or generators are enabled */}
                {(showPlants || showGenerators) && (
                  <div className="ml-5 space-y-1">
                    <div className="text-xs text-gray-500 mb-1">Filter by Type:</div>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showNuclear}
                        onChange={(e) => setShowNuclear(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-orange-500"></div>
                      <span className="text-gray-600 text-xs">Nuclear</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showSolar}
                        onChange={(e) => setShowSolar(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-yellow-500"></div>
                      <span className="text-gray-600 text-xs">Solar</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showWind}
                        onChange={(e) => setShowWind(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-green-400"></div>
                      <span className="text-gray-600 text-xs">Wind</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showHydro}
                        onChange={(e) => setShowHydro(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                      <span className="text-gray-600 text-xs">Hydro</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showGas}
                        onChange={(e) => setShowGas(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-pink-500"></div>
                      <span className="text-gray-600 text-xs">Natural Gas</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showCoal}
                        onChange={(e) => setShowCoal(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-amber-800"></div>
                      <span className="text-gray-600 text-xs">Coal</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showBiomass}
                        onChange={(e) => setShowBiomass(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-green-600"></div>
                      <span className="text-gray-600 text-xs">Biomass</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showGeothermal}
                        onChange={(e) => setShowGeothermal(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-red-600"></div>
                      <span className="text-gray-600 text-xs">Geothermal</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showOtherTypes}
                        onChange={(e) => setShowOtherTypes(e.target.checked)}
                        className="w-3 h-3"
                      />
                      <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                      <span className="text-gray-600 text-xs">Other</span>
                    </label>
                  </div>
                )}
              </div>
            </div>
          )}
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