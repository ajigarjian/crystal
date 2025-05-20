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

import data from "./data.json"
import { getDashboardSectionCards, SectionCardData } from "@/lib/firebase"

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

  return (
    <SidebarProvider
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
                  <div className="px-4 lg:px-6">
                    <ChartAreaInteractive selectedDamId={selectedDam.id} />
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
