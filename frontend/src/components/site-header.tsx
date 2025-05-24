import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DamInfo } from "@/app/dashboard/page"; // Adjust path if DamInfo is moved

interface SiteHeaderProps {
  availableDams: DamInfo[];
  selectedDam: DamInfo;
  onDamChange: (dam: DamInfo) => void;
}

export function SiteHeader({ availableDams, selectedDam, onDamChange }: SiteHeaderProps) {
  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
        <SidebarTrigger className="-ml-1" />
        <Separator
          orientation="vertical"
          className="mx-2 data-[orientation=vertical]:h-4"
        />
        <Select
          value={String(selectedDam.id)}
          onValueChange={(damIdString) => {
            const newSelectedDam = availableDams.find(dam => dam.id === Number(damIdString));
            if (newSelectedDam) {
              onDamChange(newSelectedDam);
            }
          }}
        >
          <SelectTrigger className="w-auto min-w-[200px] text-base font-medium border-0 shadow-none focus:ring-0"> {/* Adjusted styling for a cleaner look */}
            <SelectValue placeholder="Select a dam" />
          </SelectTrigger>
          <SelectContent>
            {availableDams.map((dam) => (
              <SelectItem key={dam.id} value={String(dam.id)}>
                {dam.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" asChild size="sm" className="hidden sm:flex">
            <a
              href="https://github.com/shadcn-ui/ui/tree/main/apps/v4/app/(examples)/dashboard"
              rel="noopener noreferrer"
              target="_blank"
              className="dark:text-foreground"
            >
              GitHub
            </a>
          </Button>
        </div>
      </div>
    </header>
  )
}
