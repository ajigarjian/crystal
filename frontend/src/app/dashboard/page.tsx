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

const AVAILABLE_DAMS: DamInfo[] = [
  { id: 1, name: "Grand Coulee Dam" },
  { id: 2, name: "Chief Joseph Dam" },
  { id: 3, name: "Wells Dam" },
  { id: 4, name: "Rocky Reach Dam" },
  { id: 6, name: "The Dalles Lock and Dam" },
  { id: 7, name: "Bonneville Locks and Dam"}

];

export default function Page() {
  const [selectedDam, setSelectedDam] = React.useState<DamInfo>(AVAILABLE_DAMS[0]);
  const [currentSectionCardData, setCurrentSectionCardData] = React.useState<SectionCardData[]>([]);
  const [isLoadingCards, setIsLoadingCards] = React.useState<boolean>(true);
  const [damMarkers, setDamMarkers] = React.useState<DamLocation[]>([]);

  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  // Fetch section card data when selectedDam changes
  React.useEffect(() => {
    async function loadSectionCards() {
      setIsLoadingCards(true);
      try {
        const data = await getDashboardSectionCards(selectedDam.id);
        setCurrentSectionCardData(data);
      } catch (error) {
        console.error("Failed to load section card data for dam: ", selectedDam.id, error);
        setCurrentSectionCardData([]); // Set to empty on error
      }
      setIsLoadingCards(false);
    }

    if (selectedDam) { // Ensure selectedDam is available
      loadSectionCards();
    }
  }, [selectedDam]); // Re-run when selectedDam object changes

  // Fetch dam locations for the map
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
  }, []); // Empty dependency array means this runs once on mount

  // Handle map marker clicks to update selected dam
  const handleMapMarkerClick = (marker: { id: string | number; name?: string; latitude: number; longitude: number }) => {
    // Find the corresponding dam in AVAILABLE_DAMS by matching the ID
    const clickedDam = AVAILABLE_DAMS.find(dam => dam.id === Number(marker.id));
    if (clickedDam) {
      setSelectedDam(clickedDam);
    } else {
      console.warn(`No matching dam found for marker ID: ${marker.id}`);
    }
  };

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
          availableDams={AVAILABLE_DAMS}
          selectedDam={selectedDam}
          onDamChange={setSelectedDam}
        />
        <div className="flex flex-1 flex-col pt-4">
          <div className="flex flex-1 flex-col">
            <div className="@container/main flex flex-1 flex-col gap-2">
              <div className="flex flex-col gap-4 pt-2 pb-4 md:gap-6 md:pb-6 min-h-[calc(100vh-200px)]">
                <div className="flex grid grid-cols-3 gap-4 px-4 lg:px-6 flex-1">
                  <div className="col-span-2 min-h-[600px]">
                    {mapboxToken ? (
                      <InteractiveMap 
                        mapboxAccessToken={mapboxToken} 
                        height="100%" 
                        markers={damMarkers} 
                        onMarkerClick={handleMapMarkerClick}
                        selectedMarkerId={selectedDam.id}
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
                    <div className="min-h-[300px] flex-shrink-0">
                      <ChartAreaInteractive selectedDamId={selectedDam.id} />
                    </div>
                    {/* Section cards in right column */}
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
                  </div>
                </div>
                {/* <DataTable data={data} /> */}
              </div>
            </div>
          </div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
