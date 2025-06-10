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
  // Get the display name based on feature type
  const getDisplayName = (): string => {
    if (selectedFeature.type === 'dam') {
      const damData = selectedFeature.data as DamInfo;
      return damData.name;
    } else if (selectedFeature.type === 'powerline') {
      const powerLineData = selectedFeature.data as PowerLineInfo;
      return powerLineData.name;
    }
    return 'Unknown Feature';
  };

  // Get a visual indicator of feature type
  const getFeatureTypeIndicator = (): string => {
    return selectedFeature.type === 'dam' ? '🏗️' : '⚡';
  };

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 data-[orientation=vertical]:h-4"
        />
        
        {/* Current Feature Display */}
        <div className="flex items-center gap-2">
          <span className="text-lg" title={`Selected ${selectedFeature.type}`}>
            {getFeatureTypeIndicator()}
          </span>
          <div className="text-base font-medium text-foreground">
            {getDisplayName()}
          </div>
          <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded-full">
            {selectedFeature.type}
          </span>
        </div>

        {/* Search Component */}
        <div className="ml-auto flex items-center gap-2">
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
    </header>
  )
}
