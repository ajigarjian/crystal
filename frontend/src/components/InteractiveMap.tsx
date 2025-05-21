"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent } from 'react-map-gl/mapbox';
import { cn } from "@/lib/utils";
import { MapSkeleton } from "@/components/MapSkeleton";

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
  mapStyle?: string;
  mapboxAccessToken: string; 
  height?: string | number;
  onMarkerClick?: (marker: MapMarker) => void;
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
}: InteractiveMapProps) {
  const [viewport, setViewport] = React.useState({
    latitude: initialLatitude,
    longitude: initialLongitude,
    zoom: initialZoom,
  });
  const [selectedMarker, setSelectedMarker] = React.useState<MapMarker | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);

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

  const handleMarkerClick = (marker: MapMarker) => {
    setSelectedMarker(marker);
    if (onMarkerClick) {
      onMarkerClick(marker);
    }
  };

  if (isLoading) {
    return <MapSkeleton style={{ height, width: '100%' }} />;
  }

  return (
    <div 
      style={{ height, width: '100%' }} 
      className="rounded-xl border bg-card text-card-foreground shadow-sm overflow-hidden"
    >
      <ReactMapGL
        {...viewport}
        width="100%"
        height="100%"
        mapboxAccessToken={mapboxAccessToken}
        mapStyle={mapStyle}
        onMove={(evt: ViewStateChangeEvent) => setViewport(evt.viewState)}
        // minZoom={4} // Optional: restrict zoom
        // maxZoom={15} // Optional: restrict zoom
      >
        <NavigationControl position="top-right" />
        {markers.map((marker) => (
          <Marker
            key={`marker-${marker.id}`}
            latitude={marker.latitude}
            longitude={marker.longitude}
            // anchor="bottom" // To make the pin's bottom point at the coordinate
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
              }}
              aria-label={`View details for ${marker.name || 'marker'}`}
            >
              {/* Basic SVG pin - can be customized heavily */}
              <svg 
                height="20" 
                viewBox="0 0 24 24" 
                style={{
                  fill: "hsl(var(--primary))", // Use theme primary color
                  stroke: "hsl(var(--background))", // Use theme background for outline
                  strokeWidth: "1.5",
                  transform: "translateY(-10px)" // Offset to make bottom point at location
                }}
              >
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                <circle cx="12" cy="10" r="3" fill="hsl(var(--primary-foreground))"></circle> 
              </svg>
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
            // anchor="top"
            // offset={10}
            style={{ fontFamily: 'var(--font-sans)' }} // Use theme font
          >
            <div style={{ padding: '4px' }}>
              <h3 style={{ margin: '0 0 4px 0', fontSize: '1rem', fontWeight: 600 }}>
                {selectedMarker.name || 'Location'}
              </h3>
              {/* Add more details here if needed */}
              {/* <p>Lat: {selectedMarker.latitude.toFixed(4)}, Lon: {selectedMarker.longitude.toFixed(4)}</p> */}
            </div>
          </Popup>
        ) : null}
      </ReactMapGL>
    </div>
  );
}

// Remember to set your NEXT_PUBLIC_MAPBOX_TOKEN environment variable! 