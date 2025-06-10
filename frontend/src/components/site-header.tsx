import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { SelectedFeature, DamInfo, PowerLineInfo } from "@/app/dashboard/page";

interface SiteHeaderProps {
  selectedFeature: SelectedFeature;
}

export function SiteHeader({ selectedFeature }: SiteHeaderProps) {
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
        <div className="ml-auto flex items-center gap-2">
          {/* <Button variant="ghost" asChild size="sm" className="hidden sm:flex">
            <a
              href="https://github.com/shadcn-ui/ui/tree/main/apps/v4/app/(examples)/dashboard"
              rel="noopener noreferrer"
              target="_blank"
              className="dark:text-foreground"
            >
              GitHub
            </a>
          </Button> */}
        </div>
      </div>
    </header>
  )
}
