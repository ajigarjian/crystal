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

export default function Page() {
  const [selectedFeature, setSelectedFeature] = React.useState<SelectedFeature>({
    type: 'dam',
    data: AVAILABLE_DAMS[0]
  });
  
  const [currentSectionCardData, setCurrentSectionCardData] = React.useState<SectionCardData[]>([]);
  const [isLoadingCards, setIsLoadingCards] = React.useState<boolean>(true);
  const [damMarkers, setDamMarkers] = React.useState<DamLocation[]>([]);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const getCurrentDam = (): DamInfo | null => {
    return selectedFeature.type === 'dam' ? selectedFeature.data as DamInfo : null;
  };

  const getCurrentPowerLine = (): PowerLineInfo | null => {
    return selectedFeature.type === 'powerline' ? selectedFeature.data as PowerLineInfo : null;
  };

  React.useEffect(() => {
    async function loadSectionCards() {
      setIsLoadingCards(true);
      try {
        if (selectedFeature.type === 'dam') {
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

  const handleMapMarkerClick = (marker: { id: string | number; name?: string; latitude: number; longitude: number }) => {
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

  const currentDam = getCurrentDam();
  const currentPowerLine = getCurrentPowerLine();

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
        />
        <div className="flex flex-1 flex-col pt-4">
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col gap-2">
              <div className="flex flex-col gap-4 pt-2 md:gap-6 md:pb-6 min-h-[calc(100vh-200px)]">
                <div className="flex grid grid-cols-3 gap-4 px-4 lg:px-6 flex-1">
                  <div className="col-span-2 min-h-[600px]">
                    {mapboxToken ? (
                      <InteractiveMap 
                        mapboxAccessToken={mapboxToken} 
                        height="100%" 
                        markers={damMarkers} 
                        onMarkerClick={handleMapMarkerClick}
                        onPowerLineClick={handlePowerLineClick}
                        selectedMarkerId={currentDam?.id}
                        selectedPowerLineId={currentPowerLine?.id}
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
                    {selectedFeature.type === 'dam' && currentDam && (
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

                    {selectedFeature.type === 'powerline' && currentPowerLine && (
                      <>
                        <div className="min-h-[300px] flex-shrink-0 p-4 rounded-lg border bg-card">
                          <div className="text-sm font-medium text-muted-foreground mb-2">Power Line Details</div>
                          <div className="text-lg font-bold mb-3">{currentPowerLine.name}</div>
                          
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
