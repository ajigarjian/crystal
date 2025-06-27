import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { FeatureSearchCommand } from "@/components/FeatureSearchCommand"
import { DamInfo, PowerLineInfo, SnotelStationInfo } from "@/app/dashboard/page";

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate' | 'snotel';
  data: DamInfo | PowerLineInfo | { id: string; name: string; lineCount: number } | SnotelStationInfo;
}

interface SiteHeaderProps {
  // Search data
  dams: DamInfo[];
  powerLines: SearchableFeature[];
  flowgates: SearchableFeature[];
  snotelStations: SearchableFeature[];
  // Search handlers
  onDamSelect: (dam: DamInfo) => void;
  onPowerLineSelect: (powerLine: PowerLineInfo) => void;
  onFlowgateSelect: (flowgate: string) => void;
  onSnotelStationSelect: (station: SnotelStationInfo) => void;
}

export function SiteHeader({ 
  dams,
  powerLines,
  flowgates,
  snotelStations,
  onDamSelect,
  onPowerLineSelect,
  onFlowgateSelect,
  onSnotelStationSelect
}: SiteHeaderProps) {
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-2 sm:gap-4 px-2 sm:px-4 lg:px-6 min-w-0">
        {/* Left side - Navigation */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="data-[orientation=vertical]:h-4 hidden sm:block"
          />
        </div>
        
        {/* Center - Prominent Search - Made wider to accommodate all filters */}
        <div className="flex-1 flex justify-center min-w-0">
          <div className="w-full max-w-sm sm:max-w-lg lg:max-w-3xl xl:max-w-4xl">
            <FeatureSearchCommand
              dams={dams}
              powerLines={powerLines}
              flowgates={flowgates}
              snotelStations={snotelStations}
              onDamSelect={onDamSelect}
              onPowerLineSelect={onPowerLineSelect}
              onFlowgateSelect={onFlowgateSelect}
              onSnotelStationSelect={onSnotelStationSelect}
            />
          </div>
        </div>
        
        {/* Right side - Future features (empty for now) */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Space for future features like user menu, notifications, etc. */}
        </div>
      </div>
    </header>
  )
}
