import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { FeatureSearchCommand } from "@/components/FeatureSearchCommand"
import { SelectedFeature, DamInfo, PowerLineInfo } from "@/app/dashboard/page";

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate';
  data: any;
}

interface SiteHeaderProps {
  selectedFeature: SelectedFeature;
  // Search data
  dams: DamInfo[];
  powerLines: SearchableFeature[];
  flowgates: SearchableFeature[];
  // Search handlers
  onDamSelect: (dam: DamInfo) => void;
  onPowerLineSelect: (powerLine: PowerLineInfo) => void;
  onFlowgateSelect: (flowgate: string) => void;
}

export function SiteHeader({ 
  selectedFeature,
  dams,
  powerLines,
  flowgates,
  onDamSelect,
  onPowerLineSelect,
  onFlowgateSelect
}: SiteHeaderProps) {
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-4 px-4 lg:px-6">
        {/* Left side - Navigation */}
        <div className="flex items-center gap-2">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="data-[orientation=vertical]:h-4"
          />
        </div>
        
        {/* Center - Prominent Search */}
        <div className="flex-1 flex justify-center max-w-2xl mx-auto">
          <div className="w-full max-w-md">
            <FeatureSearchCommand
              dams={dams}
              powerLines={powerLines}
              flowgates={flowgates}
              onDamSelect={onDamSelect}
              onPowerLineSelect={onPowerLineSelect}
              onFlowgateSelect={onFlowgateSelect}
            />
          </div>
        </div>
        
        {/* Right side - Future features (empty for now) */}
        <div className="flex items-center gap-2">
          {/* Space for future features like user menu, notifications, etc. */}
        </div>
      </div>
    </header>
  )
}
