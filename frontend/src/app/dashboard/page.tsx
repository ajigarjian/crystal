import { AppSidebar } from "@/components/app-sidebar"
import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { DataTable } from "@/components/data-table"
import { SectionCards } from "@/components/section-cards"
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

export default async function Page() {
  let sectionCardData: SectionCardData[] = []
  try {
    sectionCardData = await getDashboardSectionCards()
  } catch (error) {
    console.error("Failed to load section card data for dashboard page:", error)
  }

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
        <SiteHeader />
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
                  <SectionCards data={sectionCardData} />
                  <div className="px-4 lg:px-6">
                    <ChartAreaInteractive />
                  </div>
                  <DataTable data={data} />
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
