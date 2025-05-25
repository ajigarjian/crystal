"use client";

import * as React from "react";
import { AppSidebar } from "@/components/app-sidebar"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { DataTable } from "@/components/data-table"
import { SectionCards } from "@/components/section-cards"
import { SectionCardSkeleton } from "@/components/SectionCardSkeleton"
import { SiteHeader } from "@/components/site-header"
import {
  SidebarInset,
  SidebarProvider,
} from "@/components/ui/sidebar"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { InteractiveMap } from "@/components/InteractiveMap"

import data from "./data.json"
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
];

export default function Page() {
  const [selectedDam, setSelectedDam] = React.useState<DamInfo>(AVAILABLE_DAMS[0]);
  const [currentSectionCardData, setCurrentSectionCardData] = React.useState<SectionCardData[]>([]);
  const [isLoadingCards, setIsLoadingCards] = React.useState<boolean>(true);
  const [damMarkers, setDamMarkers] = React.useState<DamLocation[]>([]);
  const [isLoadingMapMarkers, setIsLoadingMapMarkers] = React.useState<boolean>(true);

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
      setIsLoadingMapMarkers(true);
      try {
        const locations = await getDamLocations();
        setDamMarkers(locations);
      } catch (error) {
        console.error("Failed to load dam locations for map:", error);
        setDamMarkers([]); 
      }
      setIsLoadingMapMarkers(false);
    }
  
    loadDamMapData();
  }, []); // Empty dependency array means this runs once on mount

  // Handle "Go to Dam" from map tooltip
  const handleGoToDam = React.useCallback((damId: string | number) => {
    // Convert damId to number if it's a string
    const numericDamId = typeof damId === 'string' ? parseInt(damId, 10) : damId;
    
    // Find the dam in AVAILABLE_DAMS
    const targetDam = AVAILABLE_DAMS.find(dam => dam.id === numericDamId);
    
    if (targetDam) {
      setSelectedDam(targetDam);
    } else {
      console.warn(`Dam with ID ${damId} not found in available dams`);
    }
  }, []);

  // Convert DamLocation to MapMarker format for the InteractiveMap
  const mapMarkers = React.useMemo(() => {
    return damMarkers.map(dam => ({
      id: dam.id,
      name: dam.name,
      latitude: dam.latitude,
      longitude: dam.longitude,
      // Pass through all the metadata
      owner_name: dam.owner_name,
      operator_agency: dam.operator_agency,
      river: dam.river,
      city: dam.city,
      county: dam.county,
      state: dam.state,
      structural_height_ft: dam.structural_height_ft,
      hydraulic_height_ft: dam.hydraulic_height_ft,
      dam_length_ft: dam.dam_length_ft,
      storage_max_acft: dam.storage_max_acft,
      capacity_mw: dam.capacity_mw,
      year_completed: dam.year_completed,
      gate_count: dam.gate_count,
      gate_type: dam.gate_type,
    }));
  }, [damMarkers]);

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
        <Tabs defaultValue="operational" className="flex flex-1 flex-col pt-4">
          <div className="px-4 lg:px-6">
            <TabsList>
              <TabsTrigger value="operational">Operational</TabsTrigger>
              <TabsTrigger value="weather">Weather</TabsTrigger>
              <TabsTrigger value="data-curve">Data Curve</TabsTrigger>
              <TabsTrigger value="environmental">Environmental</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="operational" className="flex flex-1 flex-col">
            <div className="flex flex-1 flex-col">
              <div className="@container/main flex flex-1 flex-col gap-2">
                <div className="flex flex-col gap-4 pt-2 pb-4 md:gap-6 md:pb-6">
                  <div className="flex grid grid-cols-3 gap-4 px-4 lg:px-6">
                    <div className="col-span-2">
                      <ChartAreaInteractive selectedDamId={selectedDam.id} />
                    </div>
                    <div className="col-span-1 h-full">
                      {mapboxToken ? (
                        <InteractiveMap 
                          mapboxAccessToken={mapboxToken} 
                          height="100%" 
                          markers={mapMarkers}
                          onGoToDam={handleGoToDam}
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
                  </div>
                  {/* Pass currentSectionCardData to SectionCards */}
                  {/* Optionally, show a loading state for cards */}
                  {isLoadingCards ? (
                    <div className="grid grid-cols-1 gap-4 px-4 sm:grid-cols-2 lg:grid-cols-3 lg:px-6">
                      {Array.from({ length: 6 }).map((_, index) => (
                        <SectionCardSkeleton key={index} />
                      ))}
                    </div>
                  ) : (
                    <SectionCards data={currentSectionCardData} />
                  )}
                  {/* <DataTable data={data} /> */}
                </div>
              </div>
            </div>
          </TabsContent>
          <TabsContent value="weather" className="flex flex-1 flex-col p-4 lg:p-6">
            <p>Weather data will go here.</p>
          </TabsContent>
          <TabsContent value="data-curve" className="flex flex-1 flex-col p-4 lg:p-6">
            <p>Data Curve information will go here.</p>
          </TabsContent>
          <TabsContent value="environmental" className="flex flex-1 flex-col p-4 lg:p-6">
            <p>Environmental details will go here.</p>
          </TabsContent>
        </Tabs>
      </SidebarInset>
    </SidebarProvider>
  )
}
