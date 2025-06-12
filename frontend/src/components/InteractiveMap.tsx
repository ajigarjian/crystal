"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapSkeleton } from "@/components/MapSkeleton";
import { getPowerInfrastructure, PowerInfrastructureData } from "@/lib/firebase";

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

  React.useEffect(() => {
    async function loadPowerInfrastructure() {
      try {
        const data = await getPowerInfrastructure();
        console.log("Power infrastructure data received:", data);
        console.log("Number of features:", data?.features?.length);
        
        // Debug: Check first few features to see flowgate data
        if (data?.features?.length > 0) {
          console.log("First 5 features:", data.features.slice(0, 5));
          
          // Debug: Extract all unique flowgates to see what we're working with
          const allFlowgates = data.features.map(f => f.properties.flowgate);
          const uniqueFlowgates = Array.from(new Set(allFlowgates));
          console.log("All flowgates found:", uniqueFlowgates);
          console.log("Non-null flowgates:", uniqueFlowgates.filter(fg => fg && fg !== 'null'));
        }
        
        setPowerInfrastructureData(data);
      } catch (error) {
        console.error("Failed to load power infrastructure data:", error);
        setPowerInfrastructureData(null);
      }
    }
    
    loadPowerInfrastructure();
  }, []);

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
        maxZoom={12}
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
        

        {/* Existing dam markers */}
        {showDams && markers.map((marker) => (
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