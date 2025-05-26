"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapSkeleton } from "@/components/MapSkeleton";
import { Dam } from "lucide-react";

interface MapMarker {
  latitude: number;
  longitude: number;
  name?: string; 
  id: string | number;
  owner_name?: string;
  operator_agency?: string;
  river?: string;
  city?: string;
  county?: string;
  state?: string;
  structural_height_ft?: number;
  hydraulic_height_ft?: number;
  dam_length_ft?: number;
  storage_max_acft?: number;
  capacity_mw?: number;
  year_completed?: number;
  gate_count?: number;
  gate_type?: string;
}

interface InteractiveMapProps {
  initialLatitude?: number;
  initialLongitude?: number;
  initialZoom?: number;
  markers?: MapMarker[];
  mapStyle?: string;
  mapboxAccessToken: string; 
  height?: string | number;
  onMarkerClick?: (marker: MapMarker) => void;
  onGoToDam?: (damId: string | number) => void;
}

const DEFAULT_LATITUDE = 47.0; // Centered more on Washington/Oregon
const DEFAULT_LONGITUDE = -120.5; // Centered more on Washington/Oregon
const DEFAULT_ZOOM = 5.5;

export function InteractiveMap({
  initialLatitude = DEFAULT_LATITUDE,
  initialLongitude = DEFAULT_LONGITUDE,
  initialZoom = DEFAULT_ZOOM,
  markers = [],
  mapStyle = "mapbox://styles/mapbox/outdoors-v12",
  mapboxAccessToken,
  height = "300px", // Default height, can be overridden by props
  onMarkerClick,
  onGoToDam,
}: InteractiveMapProps) {
  const [viewport, setViewport] = React.useState({
    latitude: initialLatitude,
    longitude: initialLongitude,
    zoom: initialZoom,
  });
  const [selectedMarker, setSelectedMarker] = React.useState<MapMarker | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [isFullscreen, setIsFullscreen] = React.useState(false);

  React.useEffect(() => {
    // Simulate map loading delay
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 1500); // Adjust delay as needed
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

  // Handle ESC key to exit fullscreen
  React.useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };

    if (isFullscreen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when fullscreen
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isFullscreen]);

  const handleMarkerClick = (marker: MapMarker, e: React.MouseEvent) => {
    // Prevent the click from bubbling up to the map
    e.preventDefault();
    e.stopPropagation();
    
    setSelectedMarker(marker);
    if (onMarkerClick) {
      onMarkerClick(marker);
    }
  };

  // Handle map click to close popup when clicking outside
  const handleMapClick = () => {
    if (selectedMarker) {
      setSelectedMarker(null);
    }
  };

  // Handle "Go to Dam" button click
  const handleGoToDam = (damId: string | number) => {
    if (onGoToDam) {
      onGoToDam(damId);
      setSelectedMarker(null); // Close popup after navigating
    }
  };

  // Toggle fullscreen mode
  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
    // Close any open popups when toggling fullscreen
    setSelectedMarker(null);
  };

  // Helper function to format numbers with commas
  const formatNumber = (num?: number) => {
    if (num == null) return 'N/A';
    return num.toLocaleString();
  };

  // Helper function to determine marker size based on dam height
  const getMarkerSize = (marker: MapMarker) => {
    const height = marker.structural_height_ft;
    
    if (!height) {
      return {
        containerSize: 'w-4 h-4', // Small default
        iconSize: 10,
        tailSize: 'border-l-[1px] border-r-[1px] border-t-2'
      };
    }
    
    if (height >= 300) { // Very large dams (like Grand Coulee at 550ft)
      return {
        containerSize: 'w-6 h-6',
        iconSize: 14,
        tailSize: 'border-l-[1.5px] border-r-[1.5px] border-t-3'
      };
    } else if (height >= 200) { // Large dams
      return {
        containerSize: 'w-5 h-5',
        iconSize: 12,
        tailSize: 'border-l-[1px] border-r-[1px] border-t-2'
      };
    } else if (height >= 100) { // Medium dams
      return {
        containerSize: 'w-5 h-5',
        iconSize: 12,
        tailSize: 'border-l-[1px] border-r-[1px] border-t-2'
      };
    } else if (height >= 50) { // Small-medium dams
      return {
        containerSize: 'w-4 h-4',
        iconSize: 10,
        tailSize: 'border-l-[1px] border-r-[1px] border-t-2'
      };
    } else { // Small dams
      return {
        containerSize: 'w-4 h-4',
        iconSize: 10,
        tailSize: 'border-l-[1px] border-r-[1px] border-t-2'
      };
    }
  };

  // Helper function to get marker color based on capacity or height
  const getMarkerColor = (marker: MapMarker) => {
    const height = marker.structural_height_ft;
    const capacity = marker.capacity_mw;
    
    // Prioritize capacity if available, then fall back to height
    if (capacity) {
      if (capacity >= 1000) return 'bg-red-600'; // Major hydroelectric
      if (capacity >= 500) return 'bg-orange-600'; // Large hydroelectric
      if (capacity >= 100) return 'bg-yellow-600'; // Medium hydroelectric
      return 'bg-green-600'; // Small hydroelectric
    }
    
    if (height) {
      if (height >= 300) return 'bg-red-600'; // Massive dams
      if (height >= 200) return 'bg-orange-600'; // Large dams
      if (height >= 100) return 'bg-blue-600'; // Medium dams
      return 'bg-blue-500'; // Smaller dams
    }
    
    return 'bg-gray-600'; // Unknown/no data
  };

  if (isLoading) {
    return <MapSkeleton style={{ height, width: '100%' }} />;
  }

  const mapContent = (
    <div 
      style={{ 
        height: isFullscreen ? '100vh' : height, 
        width: isFullscreen ? '100vw' : '100%' 
      }} 
      className={cn(
        "rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden",
        isFullscreen && "fixed inset-0 z-50 rounded-none"
      )}
    >
      <ReactMapGL
        {...viewport}
        mapboxAccessToken={mapboxAccessToken}
        mapStyle={mapStyle}
        onMove={(evt: ViewStateChangeEvent) => setViewport(evt.viewState)}
        onClick={handleMapClick}
      >
        <NavigationControl position="top-right" />
        
        {/* Fullscreen Toggle Button */}
        <div className="absolute top-4 left-4 z-10">
          <button
            onClick={toggleFullscreen}
            className="w-8 h-8 bg-white rounded-md shadow-md border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition-colors duration-150 flex items-center justify-center"
            aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            {isFullscreen ? (
              // Minimize icon
              <svg 
                width="16" 
                height="16" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="currentColor" 
                strokeWidth="2" 
                strokeLinecap="round" 
                strokeLinejoin="round"
                className="text-gray-600"
              >
                <path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3" />
              </svg>
            ) : (
              // Expand icon
              <svg 
                width="16" 
                height="16" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="currentColor" 
                strokeWidth="2" 
                strokeLinecap="round" 
                strokeLinejoin="round"
                className="text-gray-600"
              >
                <path d="M3 8V6a2 2 0 0 1 2-2h2M21 8V6a2 2 0 0 0-2-2h-2M3 16v2a2 2 0 0 0 2 2h2M21 16v2a2 2 0 0 1-2 2h-2" />
              </svg>
            )}
          </button>
        </div>

        {markers.map((marker) => {
          const markerSize = getMarkerSize(marker);
          const markerColor = getMarkerColor(marker);
          
          return (
            <Marker
              key={`marker-${marker.id}`}
              latitude={marker.latitude}
              longitude={marker.longitude}
            >
              <button
                onClick={(e) => handleMarkerClick(marker, e)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  padding: 0,
                }}
                aria-label={`View details for ${marker.name || 'marker'}`}
              >
                {/* Size and color-based Dam Icon */}
                <div className="relative">
                  <div className={cn(
                    markerSize.containerSize,
                    markerColor,
                    "rounded-full shadow-lg border-2 border-white flex items-center justify-center hover:scale-110 transition-transform duration-150"
                  )}>
                    <svg 
                      width={markerSize.iconSize} 
                      height={markerSize.iconSize} 
                      viewBox="0 0 24 24" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="2" 
                      strokeLinecap="round" 
                      strokeLinejoin="round"
                      className="text-white"
                    >
                      <path d="M11 11.31c1.17.56 1.54 1.69 3.5 1.69 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>
                      <path d="M11.75 18c.35.5 1.45 1 2.75 1 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>
                      <path d="M2 10h4"/>
                      <path d="M2 14h4"/>
                      <path d="M2 18h4"/>
                      <path d="M2 6h4"/>
                      <path d="M7 3a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1L10 4a1 1 0 0 0-1-1z"/>
                    </svg>
                  </div>
                  {/* Proportional pointer tail */}
                  <div className={cn(
                    "absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-0 h-0 border-transparent",
                    markerSize.tailSize,
                    markerColor.replace('bg-', 'border-t-')
                  )}></div>
                </div>
              </button>
            </Marker>
          );
        })}

        {selectedMarker ? (
          <Popup
            latitude={selectedMarker.latitude}
            longitude={selectedMarker.longitude}
            onClose={() => setSelectedMarker(null)}
            closeButton={false}
            closeOnClick={false}
            anchor="top"
            offset={10}
            style={{ fontFamily: 'var(--font-sans)' }} // Use theme font
            maxWidth="300px" // Slightly smaller max width
          >
            {/* Container with fixed height and scroll */}
            <div 
              className="w-[280px] max-h-[200px] overflow-y-auto"
              onClick={(e) => e.stopPropagation()} // Prevent popup clicks from closing the popup
            >
              <div className="p-3">
                {/* Header - Always visible with close button */}
                <div className="border-b border-gray-200 pb-2 mb-3 sticky top-0 bg-white z-10 relative">
                  {/* Custom Close Button - now inside sticky header */}
                  <button
                    onClick={() => setSelectedMarker(null)}
                    className="absolute top-0 right-0 w-8 h-8 bg-white rounded-full shadow-md border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition-colors duration-150 flex items-center justify-center"
                    aria-label="Close popup"
                  >
                    <svg 
                      width="16" 
                      height="16" 
                      viewBox="0 0 24 24" 
                      fill="none" 
                      stroke="currentColor" 
                      strokeWidth="2" 
                      strokeLinecap="round" 
                      strokeLinejoin="round"
                      className="text-gray-600 hover:text-gray-800"
                    >
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                  </button>

                  {/* View Dashboard Button - positioned next to title */}
                  {onGoToDam && (
                    <button
                      onClick={() => handleGoToDam(selectedMarker.id)}
                      className="absolute top-0 right-10 w-8 h-8 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-md border border-blue-600 hover:border-blue-700 transition-colors duration-150 flex items-center justify-center"
                      aria-label={`Go to ${selectedMarker.name || 'dam'} dashboard`}
                    >
                      <svg 
                        width="14" 
                        height="14" 
                        viewBox="0 0 24 24" 
                        fill="none" 
                        stroke="currentColor" 
                        strokeWidth="2" 
                        strokeLinecap="round" 
                        strokeLinejoin="round"
                      >
                        <path d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </button>
                  )}

                  {/* Header content with right padding to avoid buttons */}
                  <div className={`${onGoToDam ? 'pr-20' : 'pr-10'}`}>
                    <h3 className="text-lg font-bold text-gray-900 mb-1 leading-tight">
                      {selectedMarker.name || 'Dam'}
                    </h3>
                    {selectedMarker.river && (
                      <p className="text-sm text-gray-600">
                        📍 {selectedMarker.river}
                      </p>
                    )}
                    {(selectedMarker.city || selectedMarker.county || selectedMarker.state) && (
                      <p className="text-xs text-gray-500">
                        {[selectedMarker.city, selectedMarker.county, selectedMarker.state]
                          .filter(Boolean)
                          .join(', ')}
                      </p>
                    )}
                  </div>
                </div>

                {/* Scrollable content area */}
                <div className="space-y-3">
                  {/* Key Statistics */}
                  <div className="space-y-2">
                    <h4 className="font-semibold text-sm text-gray-700 border-b border-gray-100 pb-1">
                      Key Statistics
                    </h4>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {selectedMarker.structural_height_ft && (
                        <div>
                          <span className="text-gray-500 block">Height:</span>
                          <div className="font-medium">{formatNumber(selectedMarker.structural_height_ft)} ft</div>
                        </div>
                      )}
                      {selectedMarker.capacity_mw && (
                        <div>
                          <span className="text-gray-500 block">Capacity:</span>
                          <div className="font-medium">{formatNumber(selectedMarker.capacity_mw)} MW</div>
                        </div>
                      )}
                      {selectedMarker.storage_max_acft && (
                        <div className="col-span-2">
                          <span className="text-gray-500 block">Max Storage:</span>
                          <div className="font-medium">{formatNumber(selectedMarker.storage_max_acft)} ac-ft</div>
                        </div>
                      )}
                      {selectedMarker.dam_length_ft && (
                        <div className="col-span-2">
                          <span className="text-gray-500 block">Length:</span>
                          <div className="font-medium">{formatNumber(selectedMarker.dam_length_ft)} ft</div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Operations Info */}
                  {(selectedMarker.gate_count || selectedMarker.gate_type || selectedMarker.year_completed) && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 border-b border-gray-100 pb-1">
                        Operations
                      </h4>
                      <div className="text-xs space-y-1">
                        {selectedMarker.gate_count && selectedMarker.gate_type && (
                          <div className="flex justify-between">
                            <span className="text-gray-500">Gates:</span>
                            <span className="font-medium">
                              {selectedMarker.gate_count} {selectedMarker.gate_type}
                            </span>
                          </div>
                        )}
                        {selectedMarker.year_completed && (
                          <div className="flex justify-between">
                            <span className="text-gray-500">Completed:</span>
                            <span className="font-medium">{selectedMarker.year_completed}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Management */}
                  {(selectedMarker.owner_name || selectedMarker.operator_agency) && (
                    <div className="space-y-2">
                      <h4 className="font-semibold text-sm text-gray-700 border-b border-gray-100 pb-1">
                        Management
                      </h4>
                      <div className="text-xs space-y-2">
                        {selectedMarker.owner_name && (
                          <div>
                            <span className="text-gray-500 block">Owner:</span>
                            <div className="font-medium text-wrap break-words">{selectedMarker.owner_name}</div>
                          </div>
                        )}
                        {selectedMarker.operator_agency && selectedMarker.operator_agency !== selectedMarker.owner_name && (
                          <div>
                            <span className="text-gray-500 block">Operator:</span>
                            <div className="font-medium text-wrap break-words">{selectedMarker.operator_agency}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Scroll indicator at bottom */}
                <div className="mt-2 text-center">
                  <div className="text-xs text-gray-400">
                    {/* Small scroll indicator */}
                    <div className="w-8 h-1 bg-gray-200 rounded-full mx-auto"></div>
                  </div>
                </div>
              </div>
            </div>
          </Popup>
        ) : null}
      </ReactMapGL>
    </div>
  );

  // Render fullscreen in a portal-like way, or normally
  if (isFullscreen) {
    return (
      <>
        {/* Backdrop */}
        <div className="fixed inset-0 bg-black/50 z-40" />
        {mapContent}
      </>
    );
  }

  return mapContent;
}

// Remember to set your NEXT_PUBLIC_MAPBOX_TOKEN environment variable! 