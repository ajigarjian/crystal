"use client";

import * as React from 'react';
import ReactMapGL, { Marker, Popup, NavigationControl, ViewStateChangeEvent, Source, Layer } from 'react-map-gl/mapbox';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MapSkeleton } from "@/components/MapSkeleton";
import { getPowerInfrastructure, PowerInfrastructureData, getPowerGenerators, GeneratorData, getPowerPlants, PowerPlantsData, getWildfires, WildfireData, transformTimeSeriesForDateTime } from "@/lib/gcp";
import { Switch } from "@/components/ui/switch";
import { TemporalControl } from "./TemporalControl";


interface PointGeometry {
  type: 'Point';
  coordinates: [number, number];
}

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

interface GenerationClickData {
  id: number;
  name: string;
  type: 'plant' | 'generator';
  fuelType?: string;
  capacity?: string;
  operator?: string;
  status?: string;
  commissioningDate?: string;
  plantName?: string;
  technology?: string;
}

interface WildfireClickData {
  irwinId: string;
  incidentName: string;
  gisAcres: number;
  reportedAcres: number;
  percentContained: number;
  status: string;
  incidentType: string;
  complexityLevel: string;
  causeGeneral: string;
  state: string;
  county: string;
  discoveryTime: string;
  perimeterTime: string;
  lastUpdateSrc: string;
  ingestionTimestamp: string;
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
  onGenerationClick?: (generationData: GenerationClickData) => void;
  onWildfireClick?: (wildfireData: WildfireClickData) => void;
  onEmptyMapClick?: () => void;
  selectedMarkerId?: string | number;
  selectedPowerLineId?: number | null;
  selectedFlowgate?: string | null;
  snotelStations?: SnotelStationInfo[];
  onSnotelStationClick?: (stationData: SnotelStationInfo) => void;
  selectedSnotelStationId?: number | null;
  selectedGeneration?: { id: number; type: 'plant' | 'generator' } | null;
}

interface SnotelStationInfo {
  id: number;
  name: string;
  triplet: string;
  latitude: number;
  longitude: number;
  elevation: number | null;
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
  onGenerationClick,
  onWildfireClick,
  onEmptyMapClick,
  selectedMarkerId,
  selectedPowerLineId,
  selectedFlowgate,
  snotelStations = [],
  onSnotelStationClick,
  selectedSnotelStationId,
  selectedGeneration,
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
  const [wildfireData, setWildfireData] = React.useState<WildfireData | null>(null);
  const [isLegendVisible, setIsLegendVisible] = React.useState(false);
  const [isMobileModalOpen, setIsMobileModalOpen] = React.useState(false);
  const [isMobile, setIsMobile] = React.useState(false);
  const [isTemporalControlCollapsed, setIsTemporalControlCollapsed] = React.useState(false);
  
  // Temporal control state
  const [selectedDateTime, setSelectedDateTime] = React.useState<Date>(() => {
    const now = new Date();
    now.setMinutes(0, 0, 0); // Round to nearest hour
    return now;
  });
  const [isTemporalDataLoading, setIsTemporalDataLoading] = React.useState(false);
  
  // Caching state for time series data
  const [cachedTimeSeriesData, setCachedTimeSeriesData] = React.useState<PowerInfrastructureData | null>(null);
  const [cacheLoadTime, setCacheLoadTime] = React.useState<Date | null>(null);
  const [isCacheLoading, setIsCacheLoading] = React.useState(false);
  
  const selectedGenId = selectedGeneration?.id ?? -1;
  const selectedGenType = selectedGeneration?.type ?? '';

  const snotelGeoJsonData = React.useMemo(() => {
    if (!snotelStations || snotelStations.length === 0) {
      return null;
    }
    return {
      type: 'FeatureCollection' as const,
      features: snotelStations.map(station => ({
        type: 'Feature' as const,
        geometry: {
          type: 'Point' as const,
          coordinates: [station.longitude, station.latitude],
        },
        properties: station,
      })),
    };
  }, [snotelStations]);
  
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
      substations: false,
      snotelStations: true
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
    },
    environmental: {
      wildfires: true,
      activeOnly: true
    }
  });

  // Quick access getters for backward compatibility
  const showDams = filters.infrastructure.dams;
  const showPowerLines = filters.infrastructure.transmission.enabled;
  const showSubstations = filters.infrastructure.substations;
  const showSnotelStations = filters.infrastructure.snotelStations;
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
  const showWildfires = filters.environmental.wildfires;
  const showActiveWildfiresOnly = filters.environmental.activeOnly;

  // Mobile detection
  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768); // Tailwind md breakpoint
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Helper function to update filters with proper typing
  const updateFilter = React.useCallback((path: string[], value: boolean | object) => {
    setFilters(prev => {
      const newFilters = { ...prev };
      let current = newFilters as Record<string, any>;
      for (let i = 0; i < path.length - 1; i++) {
        const key = path[i];
        const nextNode = current[key];
        if (typeof nextNode === 'object' && nextNode !== null) {
          current[key] = { ...nextNode };
        } else {
          current[key] = {};
        }
        current = current[key];
      }
      current[path[path.length - 1]] = value;
      return newFilters;
    });
  }, []);

  // Handle legend/modal toggle
  const handleLegendToggle = React.useCallback(() => {
    if (isMobile && !isFullScreen) {
      setIsMobileModalOpen(true);
    } else {
      setIsLegendVisible(!isLegendVisible);
    }
  }, [isMobile, isFullScreen, isLegendVisible]);

  const queryableLayers = React.useMemo(() => {
    const layers = ['power-lines', 'power-lines-clickable'];
    if (showPlants && plantData) layers.push('plant-points');
    if (showGenerators && generatorData) layers.push('generator-points');
    if (showSnotelStations && snotelGeoJsonData && viewport.zoom >= 5.8) {
        layers.push('snotel-points');
    }
    if (showWildfires && wildfireData) {
      layers.push('wildfire-fills', 'wildfire-outlines');
    }
    return layers;
  }, [showPlants, showGenerators, showSnotelStations, showWildfires, viewport.zoom, plantData, generatorData, snotelGeoJsonData, wildfireData]);

  // Add hover state for dam markers
  const [hoveredMarker, setHoveredMarker] = React.useState<MapMarker | null>(null);
  
  // Add hover state for generation markers
  const [hoveredGeneration, setHoveredGeneration] = React.useState<{id: number, name: string, type: string, operator?: string, longitude: number, latitude: number} | null>(null);

  // Add hover state for SNOTEL stations
  const [hoveredSnotelStation, setHoveredSnotelStation] = React.useState<SnotelStationInfo | null>(null);

  // Add hover state for power lines
  const [hoveredPowerLine, setHoveredPowerLine] = React.useState<{ name: string; voltage: string; longitude: number; latitude: number; flowgate?: string | null; capacityFactor?: number; } | null>(null);

  // Add hover state for wildfires
  const [hoveredWildfire, setHoveredWildfire] = React.useState<{ name: string; acres: number; percentContained: number; status: string; state: string; county: string; longitude: number; latitude: number; } | null>(null);

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
    // and the cache is either loaded or failed to load
    if (powerInfrastructureData !== null && !isCacheLoading && !isTemporalDataLoading) {
      setIsLoading(false);
    }
  }, [powerInfrastructureData, isCacheLoading, isTemporalDataLoading]);

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

  const handleSnotelStationClick = (station: SnotelStationInfo) => {
    setSelectedFlowgateGroup(null);
    setClickedLineId(null);
    if (onSnotelStationClick) {
      onSnotelStationClick(station);
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

  // Load initial 4-week time series data cache
  React.useEffect(() => {
    async function loadInitialTimeSeriesCache() {
      try {
        setIsCacheLoading(true);
        
        // Load 4 weeks of time series data
        const data = await getPowerInfrastructure(undefined, undefined, '4w');
        
        console.log("Time series cache loaded:", data);
        console.log("Time range:", data.time_range);
        
        setCachedTimeSeriesData(data);
        setCacheLoadTime(new Date());
      } catch (error) {
        console.error("Failed to load time series cache:", error);
        setCachedTimeSeriesData(null);
      } finally {
        setIsCacheLoading(false);
      }
    }
    
    // Only load cache once on component mount
    if (!cachedTimeSeriesData && !isCacheLoading) {
      loadInitialTimeSeriesCache();
    }
  }, []); // Empty dependency array - only run once
  
  // Transform cached data for selected datetime (instant, no loading needed)
  React.useEffect(() => {
    if (cachedTimeSeriesData) {
      try {
        // Transform the cached time series data for the selected datetime (synchronous)
        const transformedData = transformTimeSeriesForDateTime(cachedTimeSeriesData, selectedDateTime);
        
        // Format voltage values in the data
        const formattedData = {
          ...transformedData,
          features: transformedData.features.map(feature => ({
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
          const cf = line.properties.capacity_factor || 0;
          if (cf < 0.5) acc.red++;
          else if (cf < 0.8) acc.orange++;
          else if (cf < 1.0) acc.yellow++;
          else acc.green++;
          return acc;
        }, { green: 0, yellow: 0, orange: 0, red: 0 });
        
        const qualityStats = flowgateLines.reduce((acc, line) => {
          const quality = line.properties.data_quality;
          if (quality === 'R') acc.historical++;
          else if (quality === 'F') acc.forecast++;
          else acc.unknown++;
          return acc;
        }, { historical: 0, forecast: 0, unknown: 0 });
        
        console.log(`Capacity factor coloring for ${selectedDateTime.toISOString()}: ${flowgateLines.length} flowgate lines -`, 
                   `Green: ${capacityFactorStats.green}, Yellow: ${capacityFactorStats.yellow}, ` +
                   `Orange: ${capacityFactorStats.orange}, Red: ${capacityFactorStats.red}`);
        console.log(`Data quality distribution: Historical: ${qualityStats.historical}, ` +
                   `Forecast: ${qualityStats.forecast}, Unknown: ${qualityStats.unknown}`);
        
        setPowerInfrastructureData(formattedData);
      } catch (error) {
        console.error("Failed to transform cached data:", error);
        setPowerInfrastructureData(null);
      }
    } else if (!isCacheLoading) {
      // If no cache and not loading, fall back to single datetime API call
      async function loadSingleDatetimeData() {
        try {
          setIsTemporalDataLoading(true);
          
          const data = await getPowerInfrastructure(undefined, selectedDateTime.toISOString());
          
          console.log("Single datetime data loaded:", data);
          console.log("Selected datetime:", selectedDateTime.toISOString());
          
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
          console.error("Failed to load single datetime data:", error);
          setPowerInfrastructureData(null);
        } finally {
          setIsTemporalDataLoading(false);
        }
      }
      
      loadSingleDatetimeData();
    }
  }, [selectedDateTime, cachedTimeSeriesData, isCacheLoading]); // Reload when selectedDateTime or cache changes

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
    const enabledTypes: string[] = [];
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
    const enabledTypes: string[] = [];
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
      const plantSource = ((feature.properties as any).plant_source || '').toLowerCase();
      const plantMethod = ((feature.properties as any).plant_method || '').toLowerCase();
      const type = ((feature.properties as any).type || '').toLowerCase();
      
      return enabledTypes.some(enabledType => 
        plantSource.includes(enabledType.toLowerCase()) ||
        plantMethod.includes(enabledType.toLowerCase()) ||
        type.includes(enabledType.toLowerCase())
      );
    });
    
    setPlantData({ ...allPlantData, features: filteredFeatures });
  }, [allPlantData, showPlants, showNuclear, showSolar, showWind, showHydro, showGas, showCoal, showBiomass, showGeothermal, showOtherTypes]);

  // Optimized wildfire loading - only load once or when wildfires are toggled
  const [wildfireDataLoaded, setWildfireDataLoaded] = React.useState(false);
  const [allWildfireData, setAllWildfireData] = React.useState<WildfireData | null>(null);
  
  // Reset wildfire data when active filter changes
  React.useEffect(() => {
    setWildfireDataLoaded(false);
    setAllWildfireData(null);
  }, [showActiveWildfiresOnly]);
  
  React.useEffect(() => {
    async function loadAllWildfires() {
      if (wildfireDataLoaded || !showWildfires) return;
      
      try {
        // Load all wildfire data once with high zoom level to get comprehensive data
        const data = await getWildfires(
          22, // High zoom to get all data
          undefined, // status filter
          undefined, // state filter
          showActiveWildfiresOnly
        );
        console.log("All wildfire data loaded:", data);
        setAllWildfireData(data);
        setWildfireDataLoaded(true);
      } catch (error) {
        console.error("Failed to load wildfire data:", error);
        setAllWildfireData(null);
      }
    }
    
    if (showWildfires) {
      loadAllWildfires();
    }
  }, [showWildfires, showActiveWildfiresOnly, wildfireDataLoaded]);

  // Filter wildfire data based on zoom level (client-side progressive disclosure)
  React.useEffect(() => {
    if (!allWildfireData || !showWildfires) {
      setWildfireData(null);
      return;
    }
    
    // Client-side progressive disclosure based on zoom level
    let filteredFeatures = allWildfireData.features;
    
    if (viewport.zoom < 6) {
      // Show only major fires at low zoom levels (>1000 acres)
      filteredFeatures = filteredFeatures
        .filter(f => (f.properties.gis_acres || 0) > 1000)
        .slice(0, 50);
    } else if (viewport.zoom < 8) {
      // Show fires >100 acres at medium zoom
      filteredFeatures = filteredFeatures
        .filter(f => (f.properties.gis_acres || 0) > 100)
        .slice(0, 200);
    } else if (viewport.zoom < 10) {
      // Show most fires at higher zoom
      filteredFeatures = filteredFeatures.slice(0, 500);
    } else {
      // Show all fires at highest zoom
      filteredFeatures = filteredFeatures.slice(0, 1000);
    }
    
    setWildfireData({ ...allWildfireData, features: filteredFeatures });
  }, [allWildfireData, showWildfires, viewport.zoom]);

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

  // Legend content component - shared between modal and regular legend
  const LegendContent = () => (
    <div className="space-y-4 text-xs">
      {/* Selected Flowgate Info */}
      {selectedFlowgateGroup && (
        <div className="bg-cyan-50 border border-cyan-200 rounded-md p-3 mb-4">
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
                    { key: '500kV', label: '500kV', height: '3px', color: 'bg-green-500' },
                    { key: '230kV', label: '230kV', height: '2px', color: 'bg-green-500' },
                    { key: '115kV', label: '115kV', height: '1.5px', color: 'bg-green-500' },
                    { key: 'other', label: 'Other', height: '1px', color: 'bg-green-500' }
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

          {/* SNOTEL Stations */}
          <label className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-1.5 rounded-md transition-colors">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showSnotelStations}
                onChange={(e) => updateFilter(['infrastructure', 'snotelStations'], e.target.checked)}
                className="w-4 h-4 text-sky-600 border-gray-300 rounded focus:ring-sky-500"
              />
              <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="8" cy="8" r="5" fill="#0ea5e9" stroke="#FFFFFF" strokeWidth="2"/>
              </svg>
            </div>
            <span className="text-gray-700 font-medium">SNOTEL Stations</span>
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

      {/* Environmental Section */}
      <div className="border-t border-gray-200 pt-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-gray-800 text-xs uppercase tracking-wider">Environmental</h4>
        </div>
        <div className="space-y-2 pl-1">
          <div className="flex items-center justify-between">
            <label htmlFor="show-wildfires" className="text-xs text-gray-700 font-medium cursor-pointer">Wildfires</label>
            <Switch
              id="show-wildfires"
              checked={showWildfires}
              onCheckedChange={(checked) => updateFilter(['environmental', 'wildfires'], checked)}
            />
          </div>
          
          {showWildfires && (
            <div className="mt-2 border-t border-gray-100 pt-2">
              <div className="flex items-center justify-between">
                <label htmlFor="show-active-fires" className="text-xs text-gray-600 cursor-pointer">Active Only</label>
                <Switch
                  id="show-active-fires"
                  checked={showActiveWildfiresOnly}
                  onCheckedChange={(checked) => updateFilter(['environmental', 'activeOnly'], checked)}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );

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
          // Handle click events on power lines and generation markers
          const features = event.features;
          
          // Check if we clicked on a feature
          if (features && features.length > 0) {
            // Priority: SNOTEL Station
            const snotelFeature = features.find(f => f.layer?.id === 'snotel-points');
            if (snotelFeature && snotelFeature.properties) {
              handleSnotelStationClick(snotelFeature.properties as SnotelStationInfo);
              return; // Exit early
            }

            // Then: Wildfire
            const wildfireFeature = features.find(f => f.source === 'wildfires' && (f.layer?.id === 'wildfire-fills' || f.layer?.id === 'wildfire-outlines'));
            if (wildfireFeature && wildfireFeature.properties) {
              const wildfireData: WildfireClickData = {
                irwinId: wildfireFeature.properties.irwin_id,
                incidentName: wildfireFeature.properties.incident_name,
                gisAcres: wildfireFeature.properties.gis_acres,
                reportedAcres: wildfireFeature.properties.reported_acres,
                percentContained: wildfireFeature.properties.percent_contained,
                status: wildfireFeature.properties.status,
                incidentType: wildfireFeature.properties.incident_type,
                complexityLevel: wildfireFeature.properties.complexity_level,
                causeGeneral: wildfireFeature.properties.cause_general,
                state: wildfireFeature.properties.state,
                county: wildfireFeature.properties.county,
                discoveryTime: wildfireFeature.properties.discovery_time,
                perimeterTime: wildfireFeature.properties.perimeter_time,
                lastUpdateSrc: wildfireFeature.properties.last_update_src,
                ingestionTimestamp: wildfireFeature.properties.ingestion_timestamp
              };
              
              if (onWildfireClick) {
                onWildfireClick(wildfireData);
              }
              return;
            }

            // Then: Generation (Plant or Generator)
            const plantFeature = features.find(f => f.source === 'power-plants' && f.layer?.id === 'plant-points');
            const generatorFeature = features.find(f => f.source === 'power-generators' && f.layer?.id === 'generator-points');
            
            if (plantFeature && plantFeature.properties) {
              const plantData: GenerationClickData = {
                id: plantFeature.properties.id,
                name: plantFeature.properties.name || 'Unnamed Plant',
                type: 'plant',
                fuelType: (plantFeature.properties as any).plant_source || (plantFeature.properties as any).plant_method || (plantFeature.properties as any).type,
                capacity: (plantFeature.properties as any).capacity_mw,
                operator: (plantFeature.properties as any).operator,
                status: (plantFeature.properties as any).status,
                commissioningDate: (plantFeature.properties as any).commissioning_date
              };
              
              if (onGenerationClick) {
                onGenerationClick(plantData);
              }
              return;
            }
            
            if (generatorFeature && generatorFeature.properties) {
              const generatorData: GenerationClickData = {
                id: generatorFeature.properties.id,
                name: generatorFeature.properties.name || (generatorFeature.properties as any).plant_name || 'Unnamed Generator',
                type: 'generator',
                fuelType: (generatorFeature.properties as any).fuel_type,
                capacity: (generatorFeature.properties as any).capacity_mw,
                operator: (generatorFeature.properties as any).operator,
                status: (generatorFeature.properties as any).status,
                commissioningDate: (generatorFeature.properties as any).commissioning_date,
                plantName: (generatorFeature.properties as any).plant_name,
                technology: (generatorFeature.properties as any).technology
              };
              
              if (onGenerationClick) {
                onGenerationClick(generatorData);
              }
              return;
            }

            // Finally: Power Line
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
          const map = event.target;
          const existingQueryableLayers = queryableLayers.filter(layerId => map.getLayer(layerId));
          // Check if we're hovering over a power line or generation marker
          const features = map.queryRenderedFeatures(event.point, {
            layers: existingQueryableLayers
          });
          
          if (features.length > 0) {
            map.getCanvas().style.cursor = 'pointer';
          }
        }}
        onMouseLeave={() => {
          setHoveredGeneration(null);
          setHoveredSnotelStation(null);
          setHoveredPowerLine(null);
          setHoveredWildfire(null);
        }}
        onMouseMove={(event) => {
          const map = event.target;
          const existingQueryableLayers = queryableLayers.filter(layerId => map.getLayer(layerId));
          // Update cursor based on what we're hovering over
          const features = map.queryRenderedFeatures(event.point, {
            layers: existingQueryableLayers
          });
          
          map.getCanvas().style.cursor = features.length > 0 ? 'pointer' : '';

          const plantFeature = features.find(f => f.layer?.id === 'plant-points');
          const generatorFeature = features.find(f => f.layer?.id === 'generator-points');
          const snotelFeature = features.find(f => f.layer?.id === 'snotel-points');
          const powerLineFeature = features.find(f => f.layer?.id === 'power-lines' || f.layer?.id === 'power-lines-clickable');
          const wildfireFeature = features.find(f => f.source === 'wildfires' && (f.layer?.id === 'wildfire-fills' || f.layer?.id === 'wildfire-outlines'));

          if (plantFeature?.properties) {
            setHoveredGeneration({
              id: plantFeature.properties.id,
              name: plantFeature.properties.name || 'Unnamed Plant',
              type: (plantFeature.properties as any).plant_source || (plantFeature.properties as any).plant_method || 'Power Plant',
              operator: (plantFeature.properties as any).operator,
              longitude: event.lngLat.lng,
              latitude: event.lngLat.lat,
            });
            setHoveredSnotelStation(null);
            setHoveredPowerLine(null);
            setHoveredWildfire(null);
          } else if (generatorFeature?.properties) {
            setHoveredGeneration({
              id: generatorFeature.properties.id,
              name: generatorFeature.properties.name || (generatorFeature.properties as any).plant_name || 'Unnamed Generator',
              type: (generatorFeature.properties as any).fuel_type || 'Generator',
              operator: (generatorFeature.properties as any).operator,
              longitude: event.lngLat.lng,
              latitude: event.lngLat.lat,
            });
            setHoveredSnotelStation(null);
            setHoveredPowerLine(null);
            setHoveredWildfire(null);
          } else if (snotelFeature?.properties && snotelFeature.geometry.type === 'Point') {
            const coords = (snotelFeature.geometry as PointGeometry).coordinates;
            setHoveredSnotelStation({
              ...(snotelFeature.properties as SnotelStationInfo),
              longitude: coords[0],
              latitude: coords[1],
            });
            setHoveredGeneration(null);
            setHoveredPowerLine(null);
            setHoveredWildfire(null);
          } else if (powerLineFeature?.properties) {
            setHoveredPowerLine({
              name: powerLineFeature.properties.name,
              voltage: powerLineFeature.properties.voltage_formatted,
              longitude: event.lngLat.lng,
              latitude: event.lngLat.lat,
              flowgate: powerLineFeature.properties.flowgate,
              capacityFactor: powerLineFeature.properties.capacity_factor,
            });
            setHoveredGeneration(null);
            setHoveredSnotelStation(null);
            setHoveredWildfire(null);
          } else if (wildfireFeature?.properties) {
            setHoveredWildfire({
              name: wildfireFeature.properties.incident_name || 'Unnamed Fire',
              acres: wildfireFeature.properties.gis_acres || 0,
              percentContained: wildfireFeature.properties.percent_contained || 0,
              status: wildfireFeature.properties.status || 'Unknown',
              state: wildfireFeature.properties.state || '',
              county: wildfireFeature.properties.county || '',
              longitude: event.lngLat.lng,
              latitude: event.lngLat.lat,
            });
            setHoveredGeneration(null);
            setHoveredSnotelStation(null);
            setHoveredPowerLine(null);
          } else {
            setHoveredGeneration(null);
            setHoveredSnotelStation(null);
            setHoveredPowerLine(null);
            setHoveredWildfire(null);
          }
        }}
        interactiveLayerIds={queryableLayers}
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
        <Source
          id="power-infrastructure"
          type="geojson"
          data={powerInfrastructureData || { type: 'FeatureCollection', features: [] }}
        >
          {/* Invisible wider power lines for easier clicking */}
          <Layer
            id="power-lines-clickable"
            type="line"
            filter={["==", ["get", "geometry_type"], "ST_LineString"]}
            layout={{
              visibility: showPowerLines ? 'visible' : 'none',
              "line-cap": "round",
              "line-join": "round"
            }}
            paint={{
              "line-color": "transparent",
              "line-width": 8, // Much wider invisible line for easier clicking
              "line-opacity": 0
            }}
          />
          
          {/* Visible power lines (transmission lines) */}
          <Layer
            id="power-lines"
            type="line"
            filter={["==", ["get", "geometry_type"], "ST_LineString"]}
            layout={{
              visibility: showPowerLines ? 'visible' : 'none',
              "line-cap": "round",
              "line-join": "round"
            }}
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
                  // Green for capacity factor >= 1.0
                  [">=", ["get", "capacity_factor"], 1.0],
                  "#22c55e", // Green
                  // Yellow for capacity factor 0.8 to < 1.0
                  [">=", ["get", "capacity_factor"], 0.8],
                  "#eab308", // Yellow
                  // Orange for capacity factor 0.5 to < 0.8
                  [">=", ["get", "capacity_factor"], 0.5],
                  "#f97316", // Orange
                  // Red for capacity factor < 0.5
                  "#ef4444" // Red
                ],
                // All other non-flowgate lines are green
                "#22c55e"
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
                0.6
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
          />

          {/* Transmission Line Labels - Show at zoom 6+ */}
          <Layer
            id="power-line-labels"
            type="symbol"
            filter={["==", ["get", "geometry_type"], "ST_LineString"]}
            minzoom={6}
            layout={{
              visibility: showPowerLines ? 'visible' : 'none',
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

          {/* Power stations and plants (polygons) */}
          <Layer
            id="power-polygons"
            type="fill"
            filter={["in", ["get", "geometry_type"], ["literal", ["ST_Polygon", "ST_MultiPolygon"]]]}
            layout={{ visibility: showPlants ? 'visible' : 'none' }}
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
            layout={{ visibility: showPlants ? 'visible' : 'none' }}
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
            layout={{ visibility: showSubstations ? 'visible' : 'none' }}
            paint={{
              "circle-color": "#757575",
              "circle-radius": 4,
              "circle-opacity": 0.8,
              "circle-stroke-color": "#333333",
              "circle-stroke-width": 1
            }}
          />
        </Source>
        
        {/* SNOTEL Stations Layer - More performant than individual markers */}
        <Source id="snotel-stations" type="geojson" data={snotelGeoJsonData || { type: 'FeatureCollection', features: [] }}>
          <Layer
            id="snotel-points"
            type="circle"
            layout={{
              visibility: showSnotelStations && viewport.zoom >= 5.8 ? 'visible' : 'none'
            }}
            paint={{
              'circle-color': [
                'case',
                ['==', ['to-number', ['get', 'id']], selectedSnotelStationId || -1],
                '#2563eb', // Selected: Darker Blue
                '#0ea5e9'  // Default: Sky Blue
              ],
              'circle-radius': [
                'case',
                ['==', ['to-number', ['get', 'id']], selectedSnotelStationId || -1],
                8, // Selected radius
                5  // Default radius
              ],
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': 2,
              'circle-opacity': 0.9,
            }}
          />
        </Source>
        
        {/* Power Plant Layers */}
        <Source
          id="power-plants"
          type="geojson"
          data={plantData || { type: 'FeatureCollection', features: [] }}
        >
          {/* Plant polygons/points */}
          <Layer
            id="plant-points"
            type="circle"
            layout={{ visibility: showPlants ? 'visible' : 'none' }}
            paint={{
              "circle-color": [
                "case",
                // Selected state
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                "#ffeb3b", // Bright Yellow for selected
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
                6, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                  8, // Slightly larger radius when selected
                  4  // Default radius at zoom 6
                ],
                10, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                  12, // Slightly larger radius when selected
                  8   // Default radius at zoom 10
                ],
                14, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                  16, // Slightly larger radius when selected
                  12  // Default radius at zoom 14
                ]
              ],
              "circle-opacity": 0.8,
              "circle-stroke-color": [
                "case",
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                "#333333", // Dark stroke for selected
                "#ffffff"
              ],
              "circle-stroke-width": [
                "case",
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "plant", selectedGenType]],
                3, // Thicker stroke for selected
                2
              ]
            }}
          />
          
          {/* Plant labels at high zoom */}
          <Layer
            id="plant-labels"
            type="symbol"
            minzoom={10}
            layout={{
              visibility: showPlants ? 'visible' : 'none',
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
        
        {/* Power Generator Layers */}
        <Source
          id="power-generators"
          type="geojson"
          data={generatorData || { type: 'FeatureCollection', features: [] }}
        >
          {/* Generator points */}
          <Layer
            id="generator-points"
            type="circle"
            layout={{ visibility: showGenerators ? 'visible' : 'none' }}
            paint={{
              "circle-color": [
                "case",
                // Selected state
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                "#ffeb3b", // Bright Yellow for selected
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
                8, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                  4, // Slightly larger radius when selected
                  2  // Default radius at zoom 8
                ],
                12, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                  6, // Slightly larger radius when selected
                  4  // Default radius at zoom 12
                ],
                16, [
                  "case",
                  ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                  8, // Slightly larger radius when selected
                  6  // Default radius at zoom 16
                ]
              ],
              "circle-opacity": 0.8,
              "circle-stroke-color": [
                "case",
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                "#333333", // Dark stroke for selected
                "#ffffff"
              ],
              "circle-stroke-width": [
                "case",
                ["all", ["==", ["get", "id"], selectedGenId], ["==", "generator", selectedGenType]],
                2, // Thicker stroke for selected
                1
              ]
            }}
          />
          
          {/* Generator labels at very high zoom */}
          <Layer
            id="generator-labels"
            type="symbol"
            minzoom={14}
            layout={{
              visibility: showGenerators ? 'visible' : 'none',
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

        {/* Wildfire Layers */}
        <Source
          id="wildfires"
          type="geojson"
          data={wildfireData || { type: 'FeatureCollection', features: [] }}
        >
          {/* Wildfire perimeter fills */}
          <Layer
            id="wildfire-fills"
            type="fill"
            layout={{ visibility: showWildfires ? 'visible' : 'none' }}
            paint={{
              "fill-color": [
                "case",
                // Color based on containment percentage
                ["<", ["coalesce", ["get", "percent_contained"], 0], 25],
                "#ff4444", // Red for very active fires (< 25% contained)
                ["<", ["coalesce", ["get", "percent_contained"], 0], 50],
                "#ff8800", // Orange for moderately active fires (25-50% contained)
                ["<", ["coalesce", ["get", "percent_contained"], 0], 80],
                "#ffaa00", // Yellow-orange for mostly contained (50-80% contained)
                "#ffdd00"  // Yellow for nearly contained (80%+ contained)
              ],
              "fill-opacity": [
                "case",
                // More opaque for active fires
                ["<", ["coalesce", ["get", "percent_contained"], 0], 50],
                0.6,
                0.4
              ]
            }}
          />
          
          {/* Wildfire perimeter outlines */}
          <Layer
            id="wildfire-outlines"
            type="line"
            layout={{ visibility: showWildfires ? 'visible' : 'none' }}
            paint={{
              "line-color": [
                "case",
                // Darker outline colors
                ["<", ["coalesce", ["get", "percent_contained"], 0], 25],
                "#cc0000", // Dark red
                ["<", ["coalesce", ["get", "percent_contained"], 0], 50],
                "#cc4400", // Dark orange
                ["<", ["coalesce", ["get", "percent_contained"], 0], 80],
                "#cc6600", // Dark yellow-orange
                "#cc8800"  // Dark yellow
              ],
              "line-width": [
                "case",
                // Thicker lines for larger fires
                [">", ["coalesce", ["get", "gis_acres"], 0], 10000],
                3,
                [">", ["coalesce", ["get", "gis_acres"], 0], 1000],
                2,
                1.5
              ],
              "line-opacity": 0.8
            }}
          />
          
          {/* Wildfire labels for larger fires */}
          <Layer
            id="wildfire-labels"
            type="symbol"
            minzoom={8}
            layout={{
              visibility: showWildfires ? 'visible' : 'none',
              "text-field": [
                "format",
                ["coalesce", ["get", "incident_name"], "Unnamed Fire"], {},
                "\n", {},
                ["concat", ["number-format", ["coalesce", ["get", "gis_acres"], 0], {}], " acres"], { "font-scale": 0.8 },
                "\n", {},
                ["concat", ["number-format", ["coalesce", ["get", "percent_contained"], 0], {}], "% contained"], { "font-scale": 0.8 }
              ],
              "text-font": ["Open Sans Bold"],
              "text-size": 12,
              "text-anchor": "center",
              "text-max-width": 8
            }}
            paint={{
              "text-color": "#ffffff",
              "text-halo-color": "#000000",
              "text-halo-width": 2
            }}
            filter={[">", ["coalesce", ["get", "gis_acres"], 0], 500]} // Only show labels for fires > 500 acres
          />
        </Source>

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
            <div style={{ pointerEvents: 'none', color: '#333333', fontWeight: '500', fontSize: '14px' }}>
              {hoveredMarker.name || `Dam ${hoveredMarker.id}`}
            </div>
          </Popup>
        )}

        {/* SNOTEL Station hover popup */}
        {hoveredSnotelStation && (
          <Popup
            latitude={hoveredSnotelStation.latitude}
            longitude={hoveredSnotelStation.longitude}
            closeButton={false}
            closeOnClick={false}
            offset={[0, -20]}
            className="snotel-hover-popup"
            style={{ pointerEvents: 'none' }}
          >
            <div style={{ pointerEvents: 'none', color: '#333333', fontWeight: '500', fontSize: '14px' }}>
              <div className="font-medium">{hoveredSnotelStation.name}</div>
              {hoveredSnotelStation.elevation && (
                <div className="text-xs text-gray-600">{hoveredSnotelStation.elevation.toLocaleString()} ft</div>
              )}
            </div>
          </Popup>
        )}

        {/* Generation hover popup */}
        {hoveredGeneration && (
          <Popup
            latitude={hoveredGeneration.latitude}
            longitude={hoveredGeneration.longitude}
            closeButton={false}
            closeOnClick={false}
            offset={[0, -20]}
            className="generation-hover-popup"
            style={{ pointerEvents: 'none' }}
          >
            <div style={{ pointerEvents: 'none', color: '#333333', fontWeight: '500', fontSize: '14px' }}>
              <div className="font-medium">{hoveredGeneration.name}</div>
              <div className="text-xs text-gray-600 capitalize">{hoveredGeneration.type}</div>
              {hoveredGeneration.operator && (
                <div className="text-xs text-gray-500">Operator: {hoveredGeneration.operator}</div>
              )}
            </div>
          </Popup>
        )}

        {/* Power Line hover popup */}
        {hoveredPowerLine && (
          <Popup
            latitude={hoveredPowerLine.latitude}
            longitude={hoveredPowerLine.longitude}
            closeButton={false}
            closeOnClick={false}
            offset={[0, -15]}
            className="power-line-hover-popup"
            style={{ pointerEvents: 'none' }}
          >
            <div style={{ pointerEvents: 'none', color: '#333333', fontSize: '14px' }}>
              <div className="font-semibold">{hoveredPowerLine.name}</div>
              <div className="text-xs text-gray-600">{hoveredPowerLine.voltage}</div>
              {hoveredPowerLine.flowgate && hoveredPowerLine.flowgate !== 'null' && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  <div className="text-xs">
                    <span className="font-medium text-gray-700">Flowgate:</span>
                    <span className="font-mono text-xs ml-1">{hoveredPowerLine.flowgate}</span>
                  </div>
                  {hoveredPowerLine.capacityFactor !== undefined && hoveredPowerLine.capacityFactor !== null && (
                    <div className="text-xs">
                      <span className="font-medium text-gray-700">Capacity:</span>
                      <span className="font-mono text-xs ml-1">{(hoveredPowerLine.capacityFactor * 100).toFixed(1)}%</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </Popup>
        )}

        {/* Wildfire hover popup */}
        {hoveredWildfire && (
          <Popup
            latitude={hoveredWildfire.latitude}
            longitude={hoveredWildfire.longitude}
            closeButton={false}
            closeOnClick={false}
            offset={[0, -15]}
            className="wildfire-hover-popup"
            style={{ pointerEvents: 'none' }}
          >
            <div style={{ pointerEvents: 'none', color: '#333333', fontSize: '14px' }}>
              <div className="font-semibold">{hoveredWildfire.name}</div>
              <div className="text-xs text-gray-600">{hoveredWildfire.state}{hoveredWildfire.county && `, ${hoveredWildfire.county} County`}</div>
              <div className="mt-2 pt-2 border-t border-gray-200">
                <div className="text-xs">
                  <span className="font-medium text-gray-700">Size:</span>
                  <span className="font-mono text-xs ml-1">{hoveredWildfire.acres.toLocaleString()} acres</span>
                </div>
                <div className="text-xs">
                  <span className="font-medium text-gray-700">Contained:</span>
                  <span className="font-mono text-xs ml-1">{hoveredWildfire.percentContained}%</span>
                </div>
                {hoveredWildfire.status && hoveredWildfire.status !== 'Unknown' && (
                  <div className="text-xs">
                    <span className="font-medium text-gray-700">Status:</span>
                    <span className="font-mono text-xs ml-1">{hoveredWildfire.status}</span>
                  </div>
                )}
              </div>
            </div>
          </Popup>
        )}
      </ReactMapGL>

      {/* Mobile Modal for Map Layers */}
      {isMobileModalOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-[9999] flex items-end justify-center"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setIsMobileModalOpen(false);
            }
          }}
        >
          <div className="bg-white rounded-t-2xl w-full max-w-[calc(100vw-2rem)] mx-4 mb-4 max-h-[80vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b bg-gray-50">
              <h3 className="font-semibold text-gray-900 text-lg">Map Layers</h3>
              <button
                onClick={() => setIsMobileModalOpen(false)}
                className="p-2 rounded-full hover:bg-gray-200 transition-colors"
                aria-label="Close modal"
              >
                <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            {/* Modal Content */}
            <div className="p-4 overflow-y-auto max-h-[calc(80vh-80px)]">
              <LegendContent />
            </div>
          </div>
        </div>
      )}
      
      {/* Columbia River System Label Overlay with Full Screen Button */}
      <div 
        className="absolute top-4 left-0 bg-white/95 rounded-r-md px-3 py-2 border"
        style={{ zIndex: 40, width: '250px' }}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-blue-900">Columbia River Basin</h4>
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
      
      {/* Temporal Control Widget */}
      <div 
        className={`absolute top-20 left-0 transition-all duration-300 ${
          isTemporalControlCollapsed 
            ? 'w-12' 
            : 'w-[250px] bg-white/95 backdrop-blur-sm rounded-r-md border-r border-t border-b border-gray-200'
        }`}
        style={{ zIndex: 40 }}
      >
        <TemporalControl
          selectedDateTime={selectedDateTime}
          onDateTimeChange={setSelectedDateTime}
          isLoading={isTemporalDataLoading || isCacheLoading}
          hasCachedData={cachedTimeSeriesData !== null}
          cacheTimeRange={cachedTimeSeriesData?.time_range}
          className="!border-none !bg-transparent !backdrop-blur-none"
          isCollapsed={isTemporalControlCollapsed}
          onToggleCollapse={() => setIsTemporalControlCollapsed(!isTemporalControlCollapsed)}
        />
      </div>
      
      {/* Modern Legend */}
      <div 
        className="absolute bottom-2 right-2 bg-white/95 backdrop-blur-sm rounded-md border border-gray-200"
        style={{ zIndex: 40, minWidth: '240px', maxWidth: '280px' }}
      >
        <div className={isLegendVisible ? "p-4" : "p-3"}>
          <div className={`flex items-center justify-between ${(isLegendVisible && !isMobile) ? 'mb-3' : ''}`}>
            <h3 className="font-semibold text-gray-900 text-sm">Map Layers</h3>
            <button
              onClick={handleLegendToggle}
              className="p-1 rounded-full hover:bg-gray-200 transition-colors"
              title={isLegendVisible ? "Hide legend" : "Show legend"}
            >
              {(isLegendVisible && !isMobile) ? (
                <svg className="w-4 h-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 15l-6-6-6 6" />
                </svg>
              ) : (
                <svg className="w-4 h-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 9l6 6 6-6" />
                </svg>
              )}
            </button>
          </div>
          
          {/* Regular legend for desktop or fullscreen */}
          {isLegendVisible && !isMobile && <LegendContent />}
        </div>
      </div>
    </div>
  );

  return (
    <div 
      style={{ height, width: '100%' }} 
      className="rounded-xl border bg-card text-card-foreground overflow-hidden"
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