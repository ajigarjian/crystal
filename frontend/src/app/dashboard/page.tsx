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
import { TradingSummary } from "@/components/TradingSummary"
import { ChartAreaInteractive } from '@/components/chart-area-interactive'
import { ChartTTCFlowgate } from '@/components/chart-ttc-flowgate'
import { Terminal, Mic, Square } from "lucide-react"
import { Separator } from "@/components/ui/separator"

import { getDashboardSectionCards, SectionCardData, getDamLocations, DamLocation, getSnotelStations, SnotelStationData } from "@/lib/firebase"

export interface DamInfo {
  id: number;
  name: string;
  plantName?: string;
  technology?: string;
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
  type: 'dam' | 'powerline' | 'flowgate';
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
  const [damMarkers, setDamMarkers] = React.useState<DamLocation[]>([]);
  const [snotelStations, setSnotelStations] = React.useState<SnotelStationData[]>([]);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  // Add state to track power infrastructure data for search
  const [powerInfrastructureData, setPowerInfrastructureData] = React.useState<any>(null);

  const [selectedFlowgate, setSelectedFlowgate] = React.useState<string | null>(null);

  const [isTradingSummaryLoading, setIsTradingSummaryLoading] = React.useState(true);

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
        setDamMarkers(locations);
      } catch (error) {
        console.error("Failed to load dam locations for map:", error);
        setDamMarkers([]); 
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
        const { getPowerInfrastructure } = await import("@/lib/firebase");
        const data = await getPowerInfrastructure();
        setPowerInfrastructureData(data);
      } catch (error) {
        console.error("Failed to load power infrastructure for search:", error);
      }
    }
    
    loadPowerInfrastructureForSearch();
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

  // Updated search handlers
  const handleSearchDamSelect = (dam: DamInfo) => {
    // Clear flowgate selection when selecting dam
    setSelectedFlowgate(null);
    setSelectedFeature({
      type: 'dam',
      data: dam
    });
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
    console.log('Dashboard handling SNOTEL station click:', stationData);
    setSelectedFlowgate(null); // Clear other selections
    setSelectedFeature({
      type: 'snotel',
      data: stationData
    });
  };

  const handleMapMarkerClick = (marker: { id: string | number; name?: string; latitude: number; longitude: number }) => {
    // Clear flowgate selection when clicking dam
    setSelectedFlowgate(null);
    
    const clickedDam = AVAILABLE_DAMS.find(dam => dam.id === Number(marker.id));
    if (clickedDam) {
      console.log('Dashboard handling dam click:', clickedDam);
      setSelectedFeature({
        type: 'dam',
        data: clickedDam
      });
    } else {
      console.warn(`No matching dam found for marker ID: ${marker.id}`);
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
    if (cf < 0.7) return "Normal"
    if (cf < 1.0) return "Elevated" 
    if (cf < 1.3) return "High"
    return "Critical"
  }

  // Add the missing badge variant function
  const getCapacityFactorBadgeVariant = (cf: number): "default" | "secondary" | "destructive" | "outline" => {
    if (cf < 0.7) return "secondary"  // Green - Normal
    if (cf < 1.0) return "outline"    // Yellow - Elevated
    if (cf < 1.3) return "default"    // Orange - High  
    return "destructive"              // Red - Critical
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
          selectedFeature={selectedFeature}
          dams={AVAILABLE_DAMS}
          powerLines={searchPowerLines}
          flowgates={searchFlowgates}
          onDamSelect={handleSearchDamSelect}
          onPowerLineSelect={handleSearchPowerLineSelect}
          onFlowgateSelect={handleSearchFlowgateSelect}
        />
        <div className="flex flex-1 flex-col pt-4">
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col gap-2">
              <div className="flex flex-col gap-4 pt-2 md:gap-6 min-h-[calc(100vh-200px)]">
                <div className="flex grid grid-cols-5 gap-4 px-4 lg:px-6 flex-1">
                  <div className="col-span-3 min-h-[600px] h-[85vh]">
                    {mapboxToken ? (
                      <InteractiveMap 
                        mapboxAccessToken={mapboxToken} 
                        height="100%" 
                        markers={damMarkers} 
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
                  <div className="col-span-2 flex flex-col gap-6">
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
                      <TradingSummary />
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
                      <>
                        <div className="min-h-[300px] flex-shrink-0">
                          <ChartAreaInteractive selectedDamId={currentDam.id} />
                        </div>
                        {isLoadingCards ? (
                          <div className="grid grid-cols-2 gap-3">
                            {Array.from({ length: 6 }).map((_, index) => (
                              <SectionCardSkeleton key={index} />
                            ))}
                          </div>
                        ) : (
                          <div className="grid grid-cols-2 gap-3">
                            {currentSectionCardData.map((card, index) => (
                              <div key={index} className="p-3 rounded-lg border bg-card text-card-foreground shadow-sm">
                                <div className="text-sm font-medium text-muted-foreground mb-1">{card.title}</div>
                                <div className="text-lg font-bold">{card.value}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </>
                    )}

                    {selectedFeature?.type === 'powerline' && currentPowerLine && (
                      <>
                        {/* TTC Chart First - Primary Data */}
                        {currentPowerLine.flowgate && (
                          <ChartTTCFlowgate selectedFlowgate={currentPowerLine.flowgate} />
                        )}

                        {/* Power Line Details Second - Supporting Context */}
                        <Card className="flex-shrink-0">
                          <CardHeader>
                            <CardTitle className="text-sm text-muted-foreground">Power Line Details</CardTitle>
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
                              {currentPowerLine.ref && (
                                <div className="col-span-2">
                                  <span className="font-medium text-muted-foreground">Reference:</span>
                                  <div className="font-medium">{currentPowerLine.ref}</div>
                                </div>
                              )}
                              <div>
                                <span className="font-medium text-muted-foreground">Line Capacity Factor:</span>
                                <div className="flex items-center gap-2">
                                  <div className="font-medium">{formatCapacityFactor(currentPowerLine.capacityFactor)}</div>
                                  <Badge variant={getCapacityFactorBadgeVariant(currentPowerLine.capacityFactor)}>
                                    {getCapacityFactorStatus(currentPowerLine.capacityFactor)}
                                  </Badge>
                                </div>
                              </div>
                            </div>

                            {/* Flowgate Information */}
                            {currentPowerLine.flowgate && (
                              <>
                                <Separator />
                                <div className="space-y-3">
                                  <div>
                                    <span className="font-medium text-muted-foreground">Flowgate:</span>
                                    <div className="font-medium">{currentPowerLine.flowgate}</div>
                                  </div>
                                  
                                  {/* Flowgate Capacity Factor - Prominent Display */}
                                  <div className="p-3 rounded-lg bg-muted/30 border">
                                    <div className="flex items-center justify-between">
                                      <div>
                                        <div className="text-sm font-medium text-muted-foreground">Flowgate Capacity Factor</div>
                                        <div className="text-lg font-bold">{formatCapacityFactor(currentPowerLine.capacityFactor)}</div>
                                      </div>
                                      <Badge 
                                        variant={getCapacityFactorBadgeVariant(currentPowerLine.capacityFactor)}
                                        className="text-sm font-medium"
                                      >
                                        {getCapacityFactorStatus(currentPowerLine.capacityFactor)}
                                      </Badge>
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-1">
                                      All lines in this flowgate share this capacity factor
                                    </div>
                                  </div>
                                  
                                  {currentPowerLine.associatedLines && currentPowerLine.associatedLines.length > 0 ? (
                                    <div>
                                      <div className="text-sm font-medium text-muted-foreground mb-2">
                                        Other Lines in this Flowgate ({currentPowerLine.associatedLines.length})
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
                                  ) : (
                                    <div className="text-xs text-muted-foreground italic">
                                      No other lines found in this flowgate
                                    </div>
                                  )}
                                </div>
                              </>
                            )}
                          </CardContent>
                        </Card>
                      </>
                    )}

                    {selectedFeature?.type === 'generation' && currentGeneration && (
                      <>
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
                      </>
                    )}

                    {selectedFeature?.type === 'snotel' && currentSnotelStation && (
                      <>
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
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
