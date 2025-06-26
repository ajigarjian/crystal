import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { FeatureSearchCommand } from "@/components/FeatureSearchCommand"
import { DamInfo, PowerLineInfo } from "@/app/dashboard/page";

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate';
  data: DamInfo | PowerLineInfo | { id: string; name: string; lineCount: number };
}

interface SiteHeaderProps {
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
  dams,
  powerLines,
  flowgates,
  onDamSelect,
  onPowerLineSelect,
  onFlowgateSelect
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
        
        {/* Center - Prominent Search */}
        <div className="flex-1 flex justify-center min-w-0">
          <div className="w-full max-w-xs sm:max-w-md lg:max-w-2xl">
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
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Space for future features like user menu, notifications, etc. */}
        </div>
      </div>
    </header>
  )
}
