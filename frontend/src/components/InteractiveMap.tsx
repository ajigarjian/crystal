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

interface InteractiveMapProps {
  initialLatitude?: number;
  initialLongitude?: number;
  initialZoom?: number;
  markers?: MapMarker[];
  mapboxAccessToken: string; 
  height?: string | number;
  onMarkerClick?: (marker: MapMarker) => void;
  selectedMarkerId?: string | number;
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
  selectedMarkerId,
}: InteractiveMapProps) {
  const [viewport, setViewport] = React.useState({
    latitude: initialLatitude,
    longitude: initialLongitude,
    zoom: initialZoom,
  });
  const [selectedMarker, setSelectedMarker] = React.useState<MapMarker | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isFullScreen, setIsFullScreen] = React.useState(false);
  const [powerInfrastructureData, setPowerInfrastructureData] = React.useState<PowerInfrastructureData | null>(null);

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
    setSelectedMarker(marker);
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
        setPowerInfrastructureData(data);
      } catch (error) {
        console.error("Failed to load power infrastructure data:", error);
        setPowerInfrastructureData(null);
      }
    }
    
    loadPowerInfrastructure();
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
        minZoom={4}
        maxZoom={12}
        style={{
          // filter: 'grayscale(0.6) contrast(0.7) brightness(1.1)',
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
          {/* Water bodies (lakes, rivers, etc.) */}
          <Layer
            id="water-bodies-blue"
            type="fill"
            source-layer="water"
            paint={{
              "fill-color": "#1976d2",
              "fill-opacity": 0.9
            }}
          />
          {/* Waterways (rivers, streams) */}
          <Layer
            id="waterways-blue"
            type="line"
            source-layer="waterway"
            paint={{
              "line-color": "#1565c0",
              "line-width": [
                "interpolate", ["linear"], ["zoom"],
                5, 1,   // At zoom 5, line width is 1
                12, 4  // At zoom 12, line width is 4
              ],
              "line-opacity": 0.9
            }}
          />
        </Source>
        
        {/* Power Infrastructure Layers */}
        {powerInfrastructureData && (
          <Source
            id="power-infrastructure"
            type="geojson"
            data={powerInfrastructureData}
          >
            {/* Power lines (transmission lines) */}
            <Layer
              id="power-lines"
              type="line"
              filter={["==", ["get", "geometry_type"], "ST_LineString"]}
              paint={{
                "line-color": "#666666",
                "line-width": 1.5,
                "line-opacity": 0.8
              }}
              layout={{
                "line-cap": "round",
                "line-join": "round"
              }}
            />

            {/* Power stations and plants (polygons) */}
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

            {/* Power station and plant outlines */}
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

            {/* Power infrastructure points (substations, etc.) */}
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
          </Source>
        )}
        
        {/* Existing dam markers */}
        {markers.map((marker) => (
          <Marker
            key={`marker-${marker.id}`}
            latitude={marker.latitude}
            longitude={marker.longitude}
          >
            <button
              onClick={(e) => {
                e.preventDefault();
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
                    // filter: String(marker.id) === String(selectedMarkerId) 
                    //   ? "drop-shadow(0 3px 6px rgba(33,150,243,0.6))" 
                    //   : "drop-shadow(0 3px 6px rgba(244,67,54,0.4))"
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

        {selectedMarker ? (
          <Popup
            latitude={selectedMarker.latitude}
            longitude={selectedMarker.longitude}
            onClose={() => setSelectedMarker(null)}
            closeButton={true}
            closeOnClick={false}
            style={{ fontFamily: 'var(--font-sans)' }}
          >
            <div style={{ padding: '12px', minWidth: '200px' }}>
              <h3 style={{ 
                margin: '0 0 8px 0', 
                fontSize: '1.1rem', 
                fontWeight: 600, 
                color: '#d32f2f',
                borderBottom: '2px solid #ffebee',
                paddingBottom: '4px'
              }}>
                {selectedMarker.name || 'Dam Location'}
              </h3>
              <div style={{ margin: '8px 0' }}>
                <p style={{ margin: '4px 0', fontSize: '0.875rem', color: '#666' }}>
                  <strong>Basin:</strong> Columbia River System
                </p>
                <p style={{ margin: '4px 0', fontSize: '0.875rem', color: '#666' }}>
                  <strong>Region:</strong> Pacific Northwest
                </p>
                <p style={{ margin: '4px 0', fontSize: '0.875rem', color: '#888' }}>
                  Coordinates: {selectedMarker.latitude.toFixed(3)}°, {selectedMarker.longitude.toFixed(3)}°
                </p>
              </div>
            </div>
          </Popup>
        ) : null}
      </ReactMapGL>
      
      {/* Columbia River System Label Overlay with Full Screen Button */}
      <div 
        className="absolute top-4 left-4 bg-white/95 rounded-lg px-3 py-2 shadow-lg border"
        style={{ zIndex: 400 }}
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
        style={{ zIndex: 400 }}
      >
        <div className="text-xs space-y-2">
          <div className="font-medium text-gray-800 mb-2">Legend</div>
          
          {/* Water and Land */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 rounded bg-blue-600"></div>
              <span className="text-gray-700">Water</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-3 h-3 rounded bg-gray-400"></div>
              <span className="text-gray-700">Land</span>
            </div>
          </div>
          
          {/* Dams */}
          <div className="flex items-center space-x-1">
            <svg height="12" viewBox="0 0 24 24" className="fill-red-500">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
            </svg>
            <span className="text-gray-700">Dams</span>
          </div>
          
          {/* Power Infrastructure */}
          {powerInfrastructureData && (
            <>
              <div className="border-t pt-2">
                <div className="font-medium text-gray-800 mb-1">Power Infrastructure</div>
                <div className="space-y-1">
                  <div className="flex items-center space-x-1">
                    <div className="w-3 h-0.5 bg-red-500"></div>
                    <span className="text-gray-600">500kV Lines</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-3 h-0.5 bg-orange-500"></div>
                    <span className="text-gray-600">230kV Lines</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-3 h-0.5 bg-yellow-500"></div>
                    <span className="text-gray-600">115kV Lines</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                    <span className="text-gray-600">Substations</span>
                  </div>
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 rounded bg-green-500"></div>
                    <span className="text-gray-600">Power Plants</span>
                  </div>
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