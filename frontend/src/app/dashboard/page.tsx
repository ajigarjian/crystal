"use client";

import * as React from "react";
import { AppSidebar } from "@/components/app-sidebar"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { SectionCards } from "@/components/section-cards"
import { SectionCardSkeleton } from "@/components/SectionCardSkeleton"
import { SiteHeader } from "@/components/site-header"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"
import { InteractiveMap } from "@/components/InteractiveMap"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { TradingSummary } from "@/components/TradingSummary"

import { getDashboardSectionCards, SectionCardData, getDamLocations, DamLocation } from "@/lib/firebase"

export interface DamInfo {
  id: number;
  name: string;
}

export interface PowerLineInfo {
  id: number;
  name: string;
  flowgate?: string | null;
  voltage?: string;
  operator?: string;
  ref?: string;
  associatedLines?: string[];
}

export type SelectedFeatureType = 'dam' | 'powerline';

export interface SelectedFeature {
  type: SelectedFeatureType;
  data: DamInfo | PowerLineInfo;
}

const AVAILABLE_DAMS: DamInfo[] = [
  { id: 1, name: "Grand Coulee Dam" },
  { id: 2, name: "Chief Joseph Dam" },
  { id: 3, name: "Wells Dam" },
  { id: 4, name: "Rocky Reach Dam" },
  { id: 6, name: "The Dalles Lock and Dam" },
  { id: 7, name: "Bonneville Locks and Dam"}
];

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate';
  data: any;
}

export default function Page() {
  const [selectedFeature, setSelectedFeature] = React.useState<SelectedFeature | null>(null);
  
  const [currentSectionCardData, setCurrentSectionCardData] = React.useState<SectionCardData[]>([]);
  const [isLoadingCards, setIsLoadingCards] = React.useState<boolean>(true);
  const [damMarkers, setDamMarkers] = React.useState<DamLocation[]>([]);

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

  React.useEffect(() => {
    async function loadSectionCards() {
      setIsLoadingCards(true);
      try {
        if (selectedFeature?.type === 'dam') {
          const damData = selectedFeature.data as DamInfo;
          const data = await getDashboardSectionCards(damData.id);
          setCurrentSectionCardData(data);
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
    
    return powerInfrastructureData.features
      .filter((feature: any) => 
        feature.properties.power_type === 'line' && 
        feature.properties.name && 
        feature.properties.name !== 'Unnamed'
      )
      .map((feature: any) => ({
        id: feature.properties.gid,
        name: feature.properties.name,
        type: 'powerline' as const,
        data: {
          id: feature.properties.gid,
          name: feature.properties.name,
          flowgate: feature.properties.flowgate,
          voltage: feature.properties.voltage,
          operator: feature.properties.operator,
          ref: feature.properties.ref || '',
        }
      }));
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
    
    // Pick a random power line from this flowgate for the right panel
    const flowgateLines = searchPowerLines.filter(line => 
      (line.data as PowerLineInfo).flowgate === flowgate
    );
    
    if (flowgateLines.length > 0) {
      // Pick a random line instead of always the first one
      const randomIndex = Math.floor(Math.random() * flowgateLines.length);
      const randomLine = flowgateLines[randomIndex];
      
      setSelectedFeature({
        type: 'powerline',
        data: randomLine.data as PowerLineInfo
      });
    }
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
        associatedLines: powerLineData.associatedLines || []
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
    }
    return null;
  };

  const currentDam = getCurrentDam();
  const currentPowerLine = getCurrentPowerLine();
  const selectedDisplay = getSelectedFeatureDisplay();

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
                <div className="flex grid grid-cols-3 gap-4 px-4 lg:px-6 flex-1">
                  <div className="col-span-2 min-h-[600px] h-[85vh] max-h-[85vh]">
                    {mapboxToken ? (
                      <InteractiveMap 
                        mapboxAccessToken={mapboxToken} 
                        height="100%" 
                        markers={damMarkers} 
                        onMarkerClick={handleMapMarkerClick}
                        onPowerLineClick={handlePowerLineClick}
                        selectedMarkerId={currentDam?.id}
                        selectedPowerLineId={currentPowerLine?.id}
                        selectedFlowgate={selectedFlowgate}
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
                  <div className="col-span-1 flex flex-col gap-6">
                    {/* Selected Feature Header */}
                    {selectedDisplay && (
                      <div className="pb-2 border-b">
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="min-w-0">
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
                      </div>
                    )}

                    {/* Trading Summary - shown when no feature is selected */}
                    {!selectedFeature && (
                      <TradingSummary />
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
                        <div className="min-h-[300px] flex-shrink-0 p-4 rounded-lg border bg-card">
                          <div className="text-sm font-medium text-muted-foreground mb-2">Power Line Details</div>
                          
                          <div className="space-y-2 text-sm">
                            <div><strong>Voltage:</strong> {currentPowerLine.voltage || 'Unknown'}</div>
                            <div><strong>Operator:</strong> {currentPowerLine.operator || 'Unknown'}</div>
                            {currentPowerLine.ref && (
                              <div><strong>Reference:</strong> {currentPowerLine.ref}</div>
                            )}
                            {currentPowerLine.flowgate && (
                              <div><strong>Flowgate:</strong> {currentPowerLine.flowgate}</div>
                            )}
                          </div>
                        </div>

                        {currentPowerLine.flowgate && (
                          <div className="p-4 rounded-lg border bg-card">
                            <div className="text-sm font-medium text-muted-foreground mb-2">
                              Flowgate: {currentPowerLine.flowgate}
                            </div>
                            
                            {currentPowerLine.associatedLines && currentPowerLine.associatedLines.length > 0 ? (
                              <>
                                <div className="text-sm font-medium mb-2">
                                  Other Lines in this Flowgate ({currentPowerLine.associatedLines.length})
                                </div>
                                <div className="space-y-1 max-h-32 overflow-y-auto">
                                  {currentPowerLine.associatedLines.map((lineName, index) => (
                                    <div 
                                      key={index} 
                                      className="text-xs p-2 bg-muted rounded text-muted-foreground"
                                    >
                                      {lineName}
                                    </div>
                                  ))}
                                </div>
                              </>
                            ) : (
                              <div className="text-xs text-muted-foreground italic">
                                No other lines found in this flowgate
                              </div>
                            )}
                            
                            <div className="text-xs text-muted-foreground mt-3 p-2 bg-muted rounded">
                              TTC chart for this flowgate will be implemented in the next steps.
                            </div>
                          </div>
                        )}
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
