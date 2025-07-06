"use client";

import * as React from 'react'
import { useState, useEffect, useRef, useCallback } from 'react'
import dynamic from 'next/dynamic'
import { AppSidebar } from "@/components/app-sidebar"
import { SectionCards } from "@/components/section-cards"
import { SectionCardSkeleton } from "@/components/SectionCardSkeleton"
import { SiteHeader } from "@/components/site-header"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { InteractiveMap } from "@/components/InteractiveMap"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { TradingSummary } from "@/components/TradingSummary"
import { ChartAreaInteractive } from '@/components/chart-area-interactive'
import { ChartTTCFlowgate } from '@/components/chart-ttc-flowgate'
import { Terminal, Mic, Square, TrendingUp, MapPin, Activity, Info, Zap } from "lucide-react"
import { Separator } from "@/components/ui/separator"
import { MetricsTable, transformSectionCardDataToMetrics } from "@/components/metrics-table"
import { ChartBPAGenerationMix } from "@/components/chart-bpa-generation-mix"
import { 
  getDashboardSectionCards, 
  SectionCardData, 
  getDamLocations, 
  DamLocation, 
  getSnotelStations, 
  SnotelStationData, 
  getSnotelStationSummary 
} from "@/lib/firebase"
import { 
  getPowerGenerators, 
  GeneratorData, 
  getPowerPlants, 
  PowerPlantsData 
} from "@/lib/gcp"

export interface DamInfo {
  id: number;
  name: string;
  nidId?: string;
  federalId?: string;
  ownerName?: string;
  operatorAgency?: string;
  river?: string;
  city?: string;
  county?: string;
  state?: string;
  structuralHeightFt?: number;
  hydraulicHeightFt?: number;
  nidHeightFt?: number;
  damLengthFt?: number;
  damVolumeCy?: number;
  storageMaxAcft?: number;
  storageNormalAcft?: number;
  surfaceAreaAcres?: number;
  drainageAreaSqmi?: number;
  maxDischargeCfs?: number;
  capacityMw?: number;
  activeStorageAcft?: number;
  gateCount?: number;
  gateType?: string;
  yearCompleted?: number;
  yearModified?: string;
  damCode?: string;
}

export interface PowerLineInfo {
  id: number;
  name: string;
  flowgate?: string | null;
  voltage?: string;
  operator?: string;
  ref?: string;
  associatedLines?: string[];
  capacityFactor: number;
}

export interface GenerationInfo {
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

// Add specific interfaces for plants and generators
export interface PlantInfo {
  id: number;
  name: string;
  operator?: string;
  fuelType?: string;
  capacity?: string;
  status?: string;
  commissioningDate?: string;
  altName?: string;
  technology?: string;
}

export interface GeneratorInfo {
  id: number;
  name: string;
  operator?: string;
  fuelType?: string;
  capacity?: string;
  status?: string;
  commissioningDate?: string;
  plantName?: string;
  technology?: string;
}

export interface SnotelStationInfo {
  id: number;
  name: string;
  triplet: string;
  elevation: number | null;
  latitude: number;
  longitude: number;
}

export type SelectedFeatureType = 'dam' | 'powerline' | 'generation' | 'snotel';

export interface SelectedFeature {
  type: SelectedFeatureType;
  data: DamInfo | PowerLineInfo | GenerationInfo | SnotelStationInfo;
}

const AVAILABLE_DAMS: DamInfo[] = [
  { id: 1, name: "Grand Coulee Dam" },
  { id: 2, name: "Chief Joseph Dam" },
  { id: 3, name: "Wells Dam" },
  { id: 4, name: "Rocky Reach Dam" },
  { id: 6, name: "The Dalles Lock and Dam" },
  { id: 7, name: "Bonneville Locks and Dam"},
  { id: 8, name: "Albeni Falls Dam"},
  { id: 9, name: "Rock Island Dam"},
  { id: 10, name: "Wanapum Dam"},
  { id: 11, name: "Priest Rapids Dam"},
  { id: 12, name: "McNary Locks and Dam"},
  { id: 13, name: "John Day Lock and Dam"},
  { id: 14, name: "Ice Harbor Lock and Dam"},
  { id: 15, name: "Lower Monumental Lock and Dam"},
  { id: 16, name: "Little Goose Lock and Dam"},
  { id: 17, name: "Lower Granite Lock and Dam"},
  { id: 18, name: "Dworshak Dam"},
];

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate' | 'snotel' | 'plant' | 'generator';
  data: any;
}

// Utility function to convert voltage to kV format
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

export default function Page() {
  const [selectedFeature, setSelectedFeature] = React.useState<SelectedFeature | null>(null);
  
  const [currentSectionCardData, setCurrentSectionCardData] = React.useState<SectionCardData[]>([]);
  const [isLoadingCards, setIsLoadingCards] = React.useState<boolean>(true);
  const [damMapData, setDamMapData] = React.useState<DamLocation[]>([]);
  const [snotelStations, setSnotelStations] = React.useState<SnotelStationData[]>([]);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  // Add state to track power infrastructure data for search
  const [powerInfrastructureData, setPowerInfrastructureData] = React.useState<any>(null);
  
  // Add state for power plants and generators
  const [powerPlantsData, setPowerPlantsData] = React.useState<PowerPlantsData | null>(null);
  const [powerGeneratorsData, setPowerGeneratorsData] = React.useState<GeneratorData | null>(null);

  const [selectedFlowgate, setSelectedFlowgate] = React.useState<string | null>(null);

  const [isTradingSummaryLoading, setIsTradingSummaryLoading] = React.useState(true);

  const [selectedMetricId, setSelectedMetricId] = React.useState<string>("6"); // Default to Inflow
  const [selectedSnotelMetricId, setSelectedSnotelMetricId] = React.useState<string>("25"); // Default to WTEQ

  const getCurrentDam = (): DamInfo | null => {
    return selectedFeature?.type === 'dam' ? selectedFeature.data as DamInfo : null;
  };

  const getCurrentPowerLine = (): PowerLineInfo | null => {
    return selectedFeature?.type === 'powerline' ? selectedFeature.data as PowerLineInfo : null;
  };

  const getCurrentGeneration = (): GenerationInfo | null => {
    return selectedFeature?.type === 'generation' ? selectedFeature.data as GenerationInfo : null;
  };

  const getCurrentSnotelStation = (): SnotelStationInfo | null => {
    return selectedFeature?.type === 'snotel' ? selectedFeature.data as SnotelStationInfo : null;
  };

  React.useEffect(() => {
    async function loadSectionCards() {
      setIsLoadingCards(true);
      try {
        if (selectedFeature?.type === 'dam') {
          const damData = selectedFeature.data as DamInfo;
          const data = await getDashboardSectionCards(damData.id);
          setCurrentSectionCardData(data);
        } else if (selectedFeature?.type === 'snotel') {
          const snotelData = selectedFeature.data as SnotelStationInfo;
          const data = await getSnotelStationSummary(snotelData.id);
          setCurrentSectionCardData(data);
        } else if (selectedFeature?.type === 'generation') {
          // For now, generation nodes don't have section cards
          setCurrentSectionCardData([]);
        } else {
          setCurrentSectionCardData([]);
        }
      } catch (error) {
        console.error("Failed to load section card data:", error);
        setCurrentSectionCardData([]);
      }
      setIsLoadingCards(false);
    }

    loadSectionCards();
  }, [selectedFeature]);

  React.useEffect(() => {
    async function loadDamMapData() {
      try {
        const locations = await getDamLocations();
        setDamMapData(locations);
      } catch (error) {
        console.error("Failed to load dam locations for map:", error);
        setDamMapData([]); 
      }
    }
  
    loadDamMapData();
  }, []);

  React.useEffect(() => {
    async function loadSnotelStations() {
      try {
        const stations = await getSnotelStations();
        setSnotelStations(stations);
      } catch (error) {
        console.error("Failed to load SNOTEL stations for map:", error);
        setSnotelStations([]);
      }
    }
    loadSnotelStations();
  }, []);

  // Fetch power infrastructure data for search
  React.useEffect(() => {
    async function loadPowerInfrastructureForSearch() {
      try {
        const { getPowerInfrastructure } = await import("@/lib/gcp");
        const data = await getPowerInfrastructure();
        setPowerInfrastructureData(data);
      } catch (error) {
        console.error("Failed to load power infrastructure for search:", error);
      }
    }
    
    loadPowerInfrastructureForSearch();
  }, []);

  // Add useEffect to load power plants for search
  React.useEffect(() => {
    async function loadPowerPlantsForSearch() {
      try {
        const data = await getPowerPlants(22); // Load all plants
        setPowerPlantsData(data);
      } catch (error) {
        console.error("Failed to load power plants for search:", error);
        setPowerPlantsData(null);
      }
    }
    
    loadPowerPlantsForSearch();
  }, []);

  React.useEffect(() => {
    async function loadPowerGeneratorsForSearch() {
      try {
        const data = await getPowerGenerators(22); // Load all generators
        setPowerGeneratorsData(data);
      } catch (error) {
        console.error("Failed to load power generators for search:", error);
        setPowerGeneratorsData(null);
      }
    }
    
    loadPowerGeneratorsForSearch();
  }, []);

  // Prepare search data
  const searchPowerLines: SearchableFeature[] = React.useMemo(() => {
    if (!powerInfrastructureData?.features) return [];
    
    interface BasicPowerLineInfo {
      id: number;
      name: string;
      flowgate: string | null;
      voltage: string;
      operator: string;
      ref: string;
      capacityFactor: number;
    }

    const allLines: BasicPowerLineInfo[] = powerInfrastructureData.features
      .filter((feature: any) => 
        feature.properties.power_type === 'line' && 
        feature.properties.name && 
        feature.properties.name !== 'Unnamed'
      )
      .map((feature: any): BasicPowerLineInfo => ({
        id: feature.properties.gid,
        name: feature.properties.name,
        flowgate: feature.properties.flowgate,
        voltage: feature.properties.voltage,
        operator: feature.properties.operator,
        ref: feature.properties.ref || '',
        capacityFactor: feature.properties.capacityFactor,
      }));

    return allLines.map((line: BasicPowerLineInfo) => {
      const associatedLines = (line.flowgate && line.flowgate !== 'null')
        ? allLines
            .filter(other => other.flowgate === line.flowgate && other.id !== line.id)
            .map(other => other.name)
        : [];
      
      return {
        id: line.id,
        name: line.name,
        type: 'powerline' as const,
        data: {
          ...line,
          associatedLines: associatedLines
        }
      };
    });
  }, [powerInfrastructureData]);

  const searchFlowgates: SearchableFeature[] = React.useMemo(() => {
    if (!powerInfrastructureData?.features) return [];
    
    const flowgateMap = new Map<string, number>();
    
    powerInfrastructureData.features.forEach((feature: any) => {
      const flowgate = feature.properties.flowgate;
      if (flowgate && flowgate !== 'null') {
        flowgateMap.set(flowgate, (flowgateMap.get(flowgate) || 0) + 1);
      }
    });

    return Array.from(flowgateMap.entries()).map(([flowgate, lineCount]) => ({
      id: flowgate,
      name: flowgate,
      type: 'flowgate' as const,
      data: {
        id: flowgate,
        name: flowgate,
        lineCount: lineCount
      }
    }));
  }, [powerInfrastructureData]);

  // Prepare search data for SNOTEL stations
  const searchSnotelStations: SearchableFeature[] = React.useMemo(() => {
    return snotelStations.map((station) => ({
      id: station.id,
      name: station.name,
      type: 'snotel' as const,
      data: {
        id: station.id,
        name: station.name,
        triplet: station.triplet,
        elevation: station.elevation,
        latitude: station.latitude,
        longitude: station.longitude,
      }
    }));
  }, [snotelStations]);

  // Prepare search data for power plants
  const searchPowerPlants: SearchableFeature[] = React.useMemo(() => {
    if (!powerPlantsData?.features || !Array.isArray(powerPlantsData.features)) return [];
    
    return powerPlantsData.features.map((feature) => ({
      id: feature.properties.id,
      name: feature.properties.name || 'Unnamed Plant',
      type: 'plant' as const,
      data: {
        id: feature.properties.id,
        name: feature.properties.name || 'Unnamed Plant',
        operator: feature.properties.operator,
        fuelType: feature.properties.fuel_type || (feature.properties as any).plant_source || (feature.properties as any).type,
        capacity: feature.properties.capacity_mw,
        status: feature.properties.status,
        commissioningDate: feature.properties.commissioning_date,
        altName: (feature.properties as any).alt_name,
        technology: feature.properties.technology,
      } as PlantInfo
    }));
  }, [powerPlantsData]);

  // Prepare search data for power generators
  const searchPowerGenerators: SearchableFeature[] = React.useMemo(() => {
    if (!powerGeneratorsData?.features || !Array.isArray(powerGeneratorsData.features)) return [];
    
    return powerGeneratorsData.features.map((feature) => ({
      id: feature.properties.id,
      name: feature.properties.name || feature.properties.plant_name || 'Unnamed Generator',
      type: 'generator' as const,
      data: {
        id: feature.properties.id,
        name: feature.properties.name || 'Unnamed Generator',
        operator: feature.properties.operator,
        fuelType: feature.properties.fuel_type,
        capacity: feature.properties.capacity_mw,
        status: feature.properties.status,
        commissioningDate: feature.properties.commissioning_date,
        plantName: feature.properties.plant_name,
        technology: feature.properties.technology,
      } as GeneratorInfo
    }));
  }, [powerGeneratorsData]);

  // Updated search handlers
  const handleSearchDamSelect = (dam: DamInfo) => {
    setSelectedFeature({ type: 'dam', data: dam });
    setSelectedFlowgate(null);
    setSelectedMetricId("6"); // Reset to Inflow when dam changes
  };

  const handleSearchPowerLineSelect = (powerLine: PowerLineInfo) => {
    // Set flowgate if this power line has one
    setSelectedFlowgate(powerLine.flowgate || null);
    setSelectedFeature({
      type: 'powerline',
      data: powerLine
    });
  };

  const handleSearchFlowgateSelect = (flowgate: string) => {
    // Set the flowgate for map highlighting
    setSelectedFlowgate(flowgate);
    
    // Pick a power line from this flowgate for the right panel
    const flowgateLines = searchPowerLines.filter(line => 
      (line.data as PowerLineInfo).flowgate === flowgate
    );
    
    if (flowgateLines.length > 0) {
      // Use the first line consistently to avoid hydration mismatches
      const selectedLine = flowgateLines[0];
      
      setSelectedFeature({
        type: 'powerline',
        data: selectedLine.data as PowerLineInfo
      });
    }
  };

  const handleGenerationClick = (generationData: {
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
  }) => {
    console.log('Dashboard handling generation click:', generationData);
    
    // Clear flowgate selection when clicking generation
    setSelectedFlowgate(null);
    
    setSelectedFeature({
      type: 'generation',
      data: {
        id: generationData.id,
        name: generationData.name,
        type: generationData.type,
        fuelType: generationData.fuelType,
        capacity: generationData.capacity,
        operator: generationData.operator,
        status: generationData.status,
        commissioningDate: generationData.commissioningDate,
        plantName: generationData.plantName,
        technology: generationData.technology,
      }
    });
  };

  const handleSnotelStationClick = (stationData: SnotelStationInfo) => {
    setSelectedFeature({ type: 'snotel', data: stationData });
    setSelectedFlowgate(null);
    setSelectedSnotelMetricId("25"); // Reset to WTEQ when station changes
  };

  const handleMapMarkerClick = (marker: { id: string | number; name?: string; latitude: number; longitude: number }) => {
    // Find the dam by ID - handle both string and number types
    const damLocation = damMapData.find(dam => dam.id.toString() === marker.id.toString());
    if (damLocation) {
      // Create DamInfo with all the rich metadata from DamLocation
      const damInfo: DamInfo = {
        id: typeof damLocation.id === 'string' ? parseInt(damLocation.id) : damLocation.id,
        name: damLocation.name,
        nidId: damLocation.nidId,
        federalId: damLocation.federalId,
        ownerName: damLocation.ownerName,
        operatorAgency: damLocation.operatorAgency,
        river: damLocation.river,
        city: damLocation.city,
        county: damLocation.county,
        state: damLocation.state,
        structuralHeightFt: damLocation.structuralHeightFt,
        hydraulicHeightFt: damLocation.hydraulicHeightFt,
        nidHeightFt: damLocation.nidHeightFt,
        damLengthFt: damLocation.damLengthFt,
        damVolumeCy: damLocation.damVolumeCy,
        storageMaxAcft: damLocation.storageMaxAcft,
        storageNormalAcft: damLocation.storageNormalAcft,
        surfaceAreaAcres: damLocation.surfaceAreaAcres,
        drainageAreaSqmi: damLocation.drainageAreaSqmi,
        maxDischargeCfs: damLocation.maxDischargeCfs,
        capacityMw: damLocation.capacityMw,
        activeStorageAcft: damLocation.activeStorageAcft,
        gateCount: damLocation.gateCount,
        gateType: damLocation.gateType,
        yearCompleted: damLocation.yearCompleted,
        yearModified: damLocation.yearModified,
        damCode: damLocation.damCode
      };
      
      setSelectedFeature({ type: 'dam', data: damInfo });
      setSelectedFlowgate(null);
      setSelectedMetricId("6"); // Reset to Inflow when dam changes
    }
  };

  const handlePowerLineClick = (powerLineData: {
    id: number;
    name: string;
    flowgate?: string | null;
    voltage?: string;
    operator?: string;
    ref?: string;
    associatedLines?: string[];
    capacityFactor: number;
  }) => {
    console.log('Dashboard handling power line click:', powerLineData);
    
    // Set flowgate selection for map highlighting
    setSelectedFlowgate(powerLineData.flowgate || null);
    
    setSelectedFeature({
      type: 'powerline',
      data: {
        id: powerLineData.id,
        name: powerLineData.name,
        flowgate: powerLineData.flowgate,
        voltage: powerLineData.voltage,
        operator: powerLineData.operator,
        ref: powerLineData.ref,
        associatedLines: powerLineData.associatedLines || [],
        capacityFactor: powerLineData.capacityFactor,
      }
    });
  };

  const handleSearchSnotelStationSelect = (station: SnotelStationInfo) => {
    setSelectedFeature({ type: 'snotel', data: station });
    setSelectedFlowgate(null);
    setSelectedSnotelMetricId("25"); // Reset to WTEQ when station changes
  };

  // Add handlers for plant and generator selection
  const handleSearchPlantSelect = (plant: PlantInfo) => {
    setSelectedFeature({ type: 'generation', data: { ...plant, type: 'plant' } as GenerationInfo });
    setSelectedFlowgate(null);
  };

  const handleSearchGeneratorSelect = (generator: GeneratorInfo) => {
    setSelectedFeature({ type: 'generation', data: { ...generator, type: 'generator' } as GenerationInfo });
    setSelectedFlowgate(null);
  };

  // Helper function to get display info for selected feature
  const getSelectedFeatureDisplay = () => {
    if (!selectedFeature) return null;
    
    if (selectedFeature.type === 'dam') {
      const dam = selectedFeature.data as DamInfo;
      return dam.name;
    } else if (selectedFeature.type === 'powerline') {
      const powerLine = selectedFeature.data as PowerLineInfo;
      return powerLine.name;
    } else if (selectedFeature.type === 'generation') {
      const generation = selectedFeature.data as GenerationInfo;
      return generation.name;
    } else if (selectedFeature.type === 'snotel') {
      const station = selectedFeature.data as SnotelStationInfo;
      return station.name;
    }
    return null;
  };

  const currentDam = getCurrentDam();
  const currentPowerLine = getCurrentPowerLine();
  const currentGeneration = getCurrentGeneration();
  const currentSnotelStation = getCurrentSnotelStation();
  const selectedDisplay = getSelectedFeatureDisplay();

  // Add deselection handler
  const handleDeselection = () => {
    setSelectedFeature(null);
    setSelectedFlowgate(null);
    setSelectedMetricId("6"); // Reset to Inflow when deselecting
  };

  // Add ESC key handler
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && selectedFeature) {
        handleDeselection();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [selectedFeature]);

  const formatCapacityFactor = (cf: number) => `${(cf * 100).toFixed(1)}%`
  const getCapacityFactorStatus = (cf: number) => {
    if (cf < 0.5) return "Excellent"
    if (cf < 0.8) return "Good" 
    if (cf < 1.0) return "Fair"
    return "Critical"
  }

  // Badge variant function - keep same colors but with corrected logic
  const getCapacityFactorBadgeVariant = (cf: number): "default" | "secondary" | "destructive" | "outline" => {
    if (cf < 0.5) return "secondary"     // Green - Excellent
    if (cf < 0.8) return "outline"       // Gray - Good
    if (cf < 1.0) return "default"       // Orange - Fair
    return "destructive"                 // Red - Critical
  }

  return (
    <SidebarProvider
      defaultOpen={false}
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar variant="inset" />
      <SidebarInset>
        <SiteHeader 
          dams={AVAILABLE_DAMS}
          powerLines={searchPowerLines}
          flowgates={searchFlowgates}
          snotelStations={searchSnotelStations}
          powerPlants={searchPowerPlants}
          powerGenerators={searchPowerGenerators}
          onDamSelect={handleSearchDamSelect}
          onPowerLineSelect={handleSearchPowerLineSelect}
          onFlowgateSelect={handleSearchFlowgateSelect}
          onSnotelStationSelect={handleSearchSnotelStationSelect}
          onPlantSelect={handleSearchPlantSelect}
          onGeneratorSelect={handleSearchGeneratorSelect}
        />
        <div className="flex flex-1 flex-col">
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col">
              <div className="flex flex-col lg:grid lg:grid-cols-5 gap-2 lg:gap-4 p-2 lg:px-4 lg:py-4 flex-1 h-[calc(100vh-4rem)] lg:h-[calc(100vh-6rem)]">
                <div className="lg:col-span-3 min-h-[45vh] lg:min-h-[600px] h-[45vh] lg:h-full flex-shrink-0">
                    {mapboxToken ? (
                      <InteractiveMap 
                        mapboxAccessToken={mapboxToken} 
                        height="100%" 
                        markers={damMapData} 
                        snotelStations={snotelStations}
                        onMarkerClick={handleMapMarkerClick}
                        onPowerLineClick={handlePowerLineClick}
                        onGenerationClick={handleGenerationClick}
                        onSnotelStationClick={handleSnotelStationClick}
                        onEmptyMapClick={handleDeselection}
                        selectedMarkerId={currentDam?.id}
                        selectedPowerLineId={currentPowerLine?.id}
                        selectedFlowgate={selectedFlowgate}
                        selectedSnotelStationId={currentSnotelStation?.id}
                        selectedGeneration={currentGeneration ? { id: currentGeneration.id, type: currentGeneration.type } : null}
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center rounded-xl border border-dashed bg-muted/50 p-4 text-center">
                        <p className="text-sm text-muted-foreground">
                          Map cannot be displayed. <br />
                          (Mapbox token not configured)
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="lg:col-span-2 flex flex-col gap-4 lg:gap-6 min-h-0 flex-1 overflow-hidden">
                    {/* Selected Feature Header with Clear Button */}
                    {selectedDisplay && (
                      <div className="pb-2 border-b flex items-center justify-between">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="min-w-0 flex-1">
                                <div className="text-lg font-semibold text-foreground truncate">
                                  {selectedDisplay}
                                </div>
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" align="start">
                              <p className="max-w-xs break-words">{selectedDisplay}</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                        {/* Clear Selection Button */}
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                onClick={handleDeselection}
                                className="ml-2 p-1 rounded-md hover:bg-muted transition-colors"
                                aria-label="Clear selection"
                              >
                                <svg
                                  className="w-4 h-4 text-muted-foreground hover:text-foreground"
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M6 18L18 6M6 6l12 12"
                                  />
                                </svg>
                              </button>
                            </TooltipTrigger>
                            <TooltipContent>
                              <p>Clear selection (ESC)</p>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      </div>
                    )}

                    {/* Trading Summary - shown when no feature is selected */}
                    {!selectedFeature && (
                      <div className="flex flex-col h-full gap-4 lg:gap-6">
                        <div className="h-[30vh] overflow-y-auto flex-shrink-0">
                          <TradingSummary />
                        </div>
                        <div className="flex-1 min-h-0">
                          <ChartBPAGenerationMix />
                        </div>
                      </div>
                    )}

                    {/* Flowgate only selection - shown when flowgate is selected without a specific feature */}
                    {!selectedFeature && selectedFlowgate && (
                      <>
                        <div className="p-4 rounded-lg border bg-card">
                          <div className="text-sm font-medium text-muted-foreground mb-2">
                            Selected Flowgate: {selectedFlowgate}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            Viewing TTC limits for this flowgate path
                          </div>
                        </div>
                        <ChartTTCFlowgate selectedFlowgate={selectedFlowgate} />
                      </>
                    )}

                    {selectedFeature?.type === 'dam' && currentDam && (
                      <Tabs defaultValue="data" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="data" className="flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Data
                          </TabsTrigger>
                          <TabsTrigger value="about" className="flex items-center gap-2">
                            <Info className="h-4 w-4" />
                            About
                          </TabsTrigger>
                        </TabsList>
                        
                        <TabsContent value="data" className="space-y-4 mt-4">
                          <div className="flex flex-col gap-2">
                            <div className="min-h-[300px] flex-shrink-0">
                              <ChartAreaInteractive 
                                selectedDamId={currentDam.id} 
                                selectedMetricId={selectedMetricId}
                                dataSource="dam"
                              />
                            </div>
                            
                            {/* Replace the cards with the metrics table */}
                            <MetricsTable 
                              data={transformSectionCardDataToMetrics(currentSectionCardData)}
                              isLoading={isLoadingCards}
                              emptyStateTitle="No operational data available"
                              emptyStateDescription="Dam operational metrics are currently unavailable. This might be due to a temporary issue or no data being found."
                              selectedMetricId={selectedMetricId}
                              onMetricSelect={setSelectedMetricId}
                            />
                          </div>
                        </TabsContent>
                        
                        <TabsContent value="about" className="space-y-4 mt-4">
                          <Card>
                            <CardHeader>
                              <CardTitle className="text-sm text-muted-foreground">Dam Information</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              {/* Basic Dam Information */}
                              <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                  <span className="font-medium text-muted-foreground">Name:</span>
                                  <div className="font-medium">{currentDam.name}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">River:</span>
                                  <div className="font-medium">{currentDam.river || 'N/A'}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Owner:</span>
                                  <div className="font-medium">{currentDam.ownerName || 'N/A'}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Operator:</span>
                                  <div className="font-medium">{currentDam.operatorAgency || 'N/A'}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Location:</span>
                                  <div className="font-medium">
                                    {currentDam.city && currentDam.state ? `${currentDam.city}, ${currentDam.state}` : 'N/A'}
                                  </div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Year Completed:</span>
                                  <div className="font-medium">{currentDam.yearCompleted || 'N/A'}</div>
                                </div>
                              </div>
                              
                              <Separator />
                              
                              {/* Technical Specifications */}
                              <div>
                                <div className="text-sm font-medium text-muted-foreground mb-2">Technical Specifications</div>
                                <div className="grid grid-cols-2 gap-3 text-sm">
                                  <div>
                                    <span className="font-medium text-muted-foreground">Height:</span>
                                    <div className="font-medium">
                                      {currentDam.structuralHeightFt ? `${currentDam.structuralHeightFt.toLocaleString()} ft` : 'N/A'}
                                    </div>
                                  </div>
                                  <div>
                                    <span className="font-medium text-muted-foreground">Length:</span>
                                    <div className="font-medium">
                                      {currentDam.damLengthFt ? `${currentDam.damLengthFt.toLocaleString()} ft` : 'N/A'}
                                    </div>
                                  </div>
                                  <div>
                                    <span className="font-medium text-muted-foreground">Capacity:</span>
                                    <div className="font-medium">
                                      {currentDam.capacityMw ? `${currentDam.capacityMw.toLocaleString()} MW` : 'N/A'}
                                    </div>
                                  </div>
                                  <div>
                                    <span className="font-medium text-muted-foreground">Gate Type:</span>
                                    <div className="font-medium">{currentDam.gateType || 'N/A'}</div>
                                  </div>
                                  {currentDam.gateCount && (
                                    <div>
                                      <span className="font-medium text-muted-foreground">Gate Count:</span>
                                      <div className="font-medium">{currentDam.gateCount}</div>
                                    </div>
                                  )}
                                  {currentDam.drainageAreaSqmi && (
                                    <div>
                                      <span className="font-medium text-muted-foreground">Drainage Area:</span>
                                      <div className="font-medium">{currentDam.drainageAreaSqmi.toLocaleString()} sq mi</div>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Storage Information */}
                              {(currentDam.storageMaxAcft || currentDam.storageNormalAcft || currentDam.activeStorageAcft) && (
                                <>
                                  <Separator />
                                  <div>
                                    <div className="text-sm font-medium text-muted-foreground mb-2">Storage Capacity</div>
                                    <div className="grid grid-cols-2 gap-3 text-sm">
                                      {currentDam.storageMaxAcft && (
                                        <div>
                                          <span className="font-medium text-muted-foreground">Max Storage:</span>
                                          <div className="font-medium">{currentDam.storageMaxAcft.toLocaleString()} ac-ft</div>
                                        </div>
                                      )}
                                      {currentDam.storageNormalAcft && (
                                        <div>
                                          <span className="font-medium text-muted-foreground">Normal Storage:</span>
                                          <div className="font-medium">{currentDam.storageNormalAcft.toLocaleString()} ac-ft</div>
                                        </div>
                                      )}
                                      {currentDam.activeStorageAcft && (
                                        <div className="col-span-2">
                                          <span className="font-medium text-muted-foreground">Active Storage:</span>
                                          <div className="font-medium">{currentDam.activeStorageAcft.toLocaleString()} ac-ft</div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </>
                              )}

                              {/* Additional Information */}
                              {(currentDam.nidId || currentDam.federalId || currentDam.damCode) && (
                                <>
                                  <Separator />
                                  <div>
                                    <div className="text-sm font-medium text-muted-foreground mb-2">Identification</div>
                                    <div className="grid grid-cols-2 gap-3 text-sm">
                                      {currentDam.nidId && (
                                        <div>
                                          <span className="font-medium text-muted-foreground">NID ID:</span>
                                          <div className="font-medium font-mono text-xs">{currentDam.nidId}</div>
                                        </div>
                                      )}
                                      {currentDam.damCode && (
                                        <div>
                                          <span className="font-medium text-muted-foreground">Dam Code:</span>
                                          <div className="font-medium font-mono text-xs">{currentDam.damCode}</div>
                                        </div>
                                      )}
                                      {currentDam.federalId && (
                                        <div className="col-span-2">
                                          <span className="font-medium text-muted-foreground">Federal ID:</span>
                                          <div className="font-medium font-mono text-xs">{currentDam.federalId}</div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </>
                              )}
                            </CardContent>
                          </Card>
                        </TabsContent>
                      </Tabs>
                    )}

                    {selectedFeature?.type === 'powerline' && currentPowerLine && (
                      <Tabs defaultValue="data" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="data" className="flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Data
                          </TabsTrigger>
                          <TabsTrigger value="about" className="flex items-center gap-2">
                            <Info className="h-4 w-4" />
                            About
                          </TabsTrigger>
                        </TabsList>
                        
                        <TabsContent value="data" className="space-y-4 mt-4">
                          {/* TTC Chart First - Primary Data */}
                          {currentPowerLine.flowgate ? (
                            <ChartTTCFlowgate selectedFlowgate={currentPowerLine.flowgate} />
                          ) : (
                            <Card>
                              <CardContent className="pt-6">
                                <div className="text-center text-muted-foreground">
                                  <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                  <p className="text-sm">No live data available for this power line</p>
                                  <p className="text-xs mt-1">This line is not part of a monitored flowgate</p>
                                </div>
                              </CardContent>
                            </Card>
                          )}
                        </TabsContent>
                        
                        <TabsContent value="about" className="space-y-4 mt-4">
                          {/* Power Line Details */}
                          <Card className="flex-shrink-0 relative">
                            <CardHeader>
                              <CardTitle className="text-sm text-muted-foreground">Power Line Specifications</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              {/* Basic Power Line Information */}
                              <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                  <span className="font-medium text-muted-foreground">Voltage:</span>
                                  <div className="font-medium">{formatVoltageToKV(currentPowerLine.voltage)}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Operator:</span>
                                  <div className="font-medium">{currentPowerLine.operator || 'Unknown'}</div>
                                </div>
                                {currentPowerLine.flowgate && (
                                  <div>
                                    <span className="font-medium text-muted-foreground">Flowgate:</span>
                                    <div className="font-medium">
                                      <Badge variant="outline" className="font-mono">
                                        {currentPowerLine.flowgate}
                                      </Badge>
                                    </div>
                                  </div>
                                )}
                                {currentPowerLine.ref && (
                                  <div className="col-span-2">
                                    <span className="font-medium text-muted-foreground">Reference:</span>
                                    <div className="font-medium font-mono text-xs">{currentPowerLine.ref}</div>
                                  </div>
                                )}
                                {/* Only show capacity factor if this line is part of a flowgate */}
                                {currentPowerLine.flowgate && (
                                  <div className="col-span-2">
                                    <span className="font-medium text-muted-foreground">Capacity Factor:</span>
                                    <div className="flex items-center gap-2">
                                      <div className="font-medium">{formatCapacityFactor(currentPowerLine.capacityFactor)}</div>
                                      <Badge variant={getCapacityFactorBadgeVariant(currentPowerLine.capacityFactor)}>
                                        {getCapacityFactorStatus(currentPowerLine.capacityFactor)}
                                      </Badge>
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-1">
                                      All lines in this flowgate share this capacity factor
                                    </div>
                                  </div>
                                )}
                              </div>

                              {/* Flowgate Information */}
                              {currentPowerLine.flowgate && currentPowerLine.associatedLines && currentPowerLine.associatedLines.length > 0 && (
                                <>
                                  <Separator />
                                  <div className="space-y-3">
                                    <div>
                                      <div className="text-sm font-medium text-muted-foreground mb-2">
                                        Related Lines ({currentPowerLine.associatedLines.length})
                                      </div>
                                      <div className="space-y-1 max-h-32 overflow-y-auto">
                                        {currentPowerLine.associatedLines
                                          .filter(lineName => lineName !== currentPowerLine.name)
                                          .map((lineName, index) => {
                                            const lineInfo = searchPowerLines.find(p => p.name === lineName)?.data as PowerLineInfo | undefined;
                                            return (
                                              <Badge 
                                                key={index} 
                                                variant="secondary"
                                                className="text-xs block w-full justify-start py-1 px-2 font-normal cursor-pointer hover:bg-muted"
                                                onClick={() => lineInfo && handleSearchPowerLineSelect(lineInfo)}
                                              >
                                                {lineName}
                                              </Badge>
                                            )
                                          })}
                                      </div>
                                    </div>
                                  </div>
                                </>
                              )}
                            </CardContent>
                          </Card>
                        </TabsContent>
                      </Tabs>
                    )}

                    {selectedFeature?.type === 'generation' && currentGeneration && (
                      <Tabs defaultValue="about" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="data" className="flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Data
                          </TabsTrigger>
                          <TabsTrigger value="about" className="flex items-center gap-2">
                            <Info className="h-4 w-4" />
                            About
                          </TabsTrigger>
                        </TabsList>
                        
                        <TabsContent value="data" className="space-y-4 mt-4">
                          <Card>
                            <CardContent className="pt-6">
                              <div className="text-center text-muted-foreground">
                                <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
                                <p className="text-sm">No operational data available</p>
                                <p className="text-xs mt-1">Live generation data is not currently available</p>
                              </div>
                            </CardContent>
                          </Card>
                        </TabsContent>
                        
                        <TabsContent value="about" className="space-y-4 mt-4">
                          {/* Generation Details */}
                          <Card className="flex-shrink-0">
                            <CardHeader>
                              <CardTitle className="text-sm text-muted-foreground">
                                {currentGeneration.type === 'plant' ? 'Power Plant' : 'Generator'} Details
                              </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              {/* Basic Generation Information */}
                              <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                  <span className="font-medium text-muted-foreground">Type:</span>
                                  <div className="font-medium capitalize">{currentGeneration.fuelType || 'Unknown'}</div>
                                </div>
                                {currentGeneration.capacity && (
                                  <div>
                                    <span className="font-medium text-muted-foreground">Capacity:</span>
                                    <div className="font-medium">{currentGeneration.capacity} MW</div>
                                  </div>
                                )}
                                {currentGeneration.operator && (
                                  <div>
                                    <span className="font-medium text-muted-foreground">Operator:</span>
                                    <div className="font-medium">{currentGeneration.operator}</div>
                                  </div>
                                )}
                                {currentGeneration.status && (
                                  <div>
                                    <span className="font-medium text-muted-foreground">Status:</span>
                                    <div className="font-medium capitalize">{currentGeneration.status}</div>
                                  </div>
                                )}
                                {currentGeneration.commissioningDate && (
                                  <div className="col-span-2">
                                    <span className="font-medium text-muted-foreground">Commissioning Date:</span>
                                    <div className="font-medium">{currentGeneration.commissioningDate}</div>
                                  </div>
                                )}
                                {currentGeneration.plantName && currentGeneration.type === 'generator' && (
                                  <div className="col-span-2">
                                    <span className="font-medium text-muted-foreground">Plant:</span>
                                    <div className="font-medium">{currentGeneration.plantName}</div>
                                  </div>
                                )}
                                {currentGeneration.technology && (
                                  <div className="col-span-2">
                                    <span className="font-medium text-muted-foreground">Technology:</span>
                                    <div className="font-medium">{currentGeneration.technology}</div>
                                  </div>
                                )}
                              </div>
                            </CardContent>
                          </Card>
                        </TabsContent>
                      </Tabs>
                    )}

                    {selectedFeature?.type === 'snotel' && currentSnotelStation && (
                      <Tabs defaultValue="data" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                          <TabsTrigger value="data" className="flex items-center gap-2">
                            <Activity className="h-4 w-4" />
                            Data
                          </TabsTrigger>
                          <TabsTrigger value="about" className="flex items-center gap-2">
                            <Info className="h-4 w-4" />
                            About
                          </TabsTrigger>
                        </TabsList>
                        
                        <TabsContent value="data" className="space-y-4 mt-4">
                          <div className="flex flex-col gap-2">
                            {/* SNOTEL Station Chart */}
                            <div className="min-h-[300px] flex-shrink-0">
                              <ChartAreaInteractive 
                                selectedStationId={currentSnotelStation.id}
                                selectedMetricId={selectedSnotelMetricId}
                                dataSource="snotel"
                                stationName={currentSnotelStation.name}
                              />
                            </div>
                            
                            {/* SNOTEL Metrics Table */}
                            <MetricsTable 
                              data={transformSectionCardDataToMetrics(currentSectionCardData)}
                              isLoading={isLoadingCards}
                              emptyStateTitle="No weather data available"
                              emptyStateDescription="SNOTEL station metrics are currently unavailable. This might be due to a temporary issue or no data being found."
                              selectedMetricId={selectedSnotelMetricId}
                              onMetricSelect={(metricId) => setSelectedSnotelMetricId(metricId)}
                            />
                          </div>
                        </TabsContent>
                        
                        <TabsContent value="about" className="space-y-4 mt-4">
                          {/* SNOTEL Station Details */}
                          <Card className="flex-shrink-0">
                            <CardHeader>
                              <CardTitle className="text-sm text-muted-foreground">SNOTEL Station Details</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                              <div className="grid grid-cols-2 gap-3 text-sm">
                                <div>
                                  <span className="font-medium text-muted-foreground">Triplet:</span>
                                  <div className="font-medium">{currentSnotelStation.triplet}</div>
                                </div>
                                <div>
                                  <span className="font-medium text-muted-foreground">Elevation:</span>
                                  <div className="font-medium">{currentSnotelStation.elevation ? `${currentSnotelStation.elevation.toLocaleString()} ft` : 'N/A'}</div>
                                </div>
                                <div className="col-span-2">
                                  <span className="font-medium text-muted-foreground">Coordinates:</span>
                                  <div className="font-medium">Lat: {currentSnotelStation.latitude.toFixed(4)}, Lon: {currentSnotelStation.longitude.toFixed(4)}</div>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        </TabsContent>
                      </Tabs>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
