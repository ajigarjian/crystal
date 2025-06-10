"use client"

import * as React from "react"
import { SearchIcon } from "lucide-react"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Button } from "@/components/ui/button"
import { DamInfo, PowerLineInfo } from "@/app/dashboard/page"

interface SearchableFeature {
  id: string | number;
  name: string;
  type: 'dam' | 'powerline' | 'flowgate';
  data: DamInfo | PowerLineInfo | FlowgateInfo;
}

interface FlowgateInfo {
  id: string;
  name: string;
  lineCount: number;
}

interface FeatureSearchCommandProps {
  dams: DamInfo[];
  powerLines: SearchableFeature[];
  flowgates: SearchableFeature[];
  onDamSelect: (dam: DamInfo) => void;
  onPowerLineSelect: (powerLine: PowerLineInfo) => void;
  onFlowgateSelect: (flowgate: string) => void;
}

export function FeatureSearchCommand({
  dams,
  powerLines,
  flowgates,
  onDamSelect,
  onPowerLineSelect,
  onFlowgateSelect,
}: FeatureSearchCommandProps) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")

  // Combine all features for searching
  const allFeatures: SearchableFeature[] = React.useMemo(() => {
    const damFeatures: SearchableFeature[] = dams.map(dam => ({
      id: dam.id,
      name: dam.name,
      type: 'dam' as const,
      data: dam
    }));

    return [...damFeatures, ...powerLines, ...flowgates];
  }, [dams, powerLines, flowgates]);

  // Filter features based on search term
  const filteredFeatures = React.useMemo(() => {
    if (!search) return allFeatures;
    
    return allFeatures.filter(feature =>
      feature.name.toLowerCase().includes(search.toLowerCase())
    );
  }, [allFeatures, search]);

  // Group filtered features by type
  const groupedFeatures = React.useMemo(() => {
    const groups = {
      dam: filteredFeatures.filter(f => f.type === 'dam'),
      powerline: filteredFeatures.filter(f => f.type === 'powerline'),
      flowgate: filteredFeatures.filter(f => f.type === 'flowgate'),
    };
    return groups;
  }, [filteredFeatures]);

  const handleSelect = (feature: SearchableFeature) => {
    switch (feature.type) {
      case 'dam':
        onDamSelect(feature.data as DamInfo);
        break;
      case 'powerline':
        onPowerLineSelect(feature.data as PowerLineInfo);
        break;
      case 'flowgate':
        const flowgateData = feature.data as FlowgateInfo;
        onFlowgateSelect(flowgateData.name);
        break;
    }
    setOpen(false);
    setSearch("");
  };

  // Handle keyboard shortcut
  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((open) => !open)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [])

  const getFeatureIcon = (type: string) => {
    switch (type) {
      case 'dam': return '🏗️';
      case 'powerline': return '⚡';
      case 'flowgate': return '🔗';
      default: return '📍';
    }
  };

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="relative h-8 w-full justify-start rounded-md bg-muted/50 text-sm font-normal text-muted-foreground shadow-none sm:pr-12 md:w-40 lg:w-56"
      >
        <SearchIcon className="mr-2 h-4 w-4" />
        <span className="hidden lg:inline-flex">Search features...</span>
        <span className="inline-flex lg:hidden">Search...</span>
        <kbd className="pointer-events-none absolute right-[0.3rem] top-[0.3rem] hidden h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
          <span className="text-xs">⌘</span>K
        </kbd>
      </Button>
      
      <CommandDialog 
        open={open} 
        onOpenChange={setOpen}
        title="Search Features"
        description="Search for dams, power lines, and flowgates"
      >
        <CommandInput 
          placeholder="Type a feature name..." 
          value={search}
          onValueChange={setSearch}
        />
        <CommandList>
          <CommandEmpty>No features found.</CommandEmpty>
          
          {groupedFeatures.dam.length > 0 && (
            <CommandGroup heading="Dams">
              {groupedFeatures.dam.map((feature) => (
                <CommandItem
                  key={`dam-${feature.id}`}
                  value={feature.name}
                  onSelect={() => handleSelect(feature)}
                  className="cursor-pointer"
                >
                  <span className="mr-2">{getFeatureIcon('dam')}</span>
                  <span>{feature.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">Dam</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {groupedFeatures.powerline.length > 0 && (
            <CommandGroup heading="Power Lines">
              {groupedFeatures.powerline.map((feature) => (
                <CommandItem
                  key={`powerline-${feature.id}`}
                  value={feature.name}
                  onSelect={() => handleSelect(feature)}
                  className="cursor-pointer"
                >
                  <span className="mr-2">{getFeatureIcon('powerline')}</span>
                  <span className="truncate">{feature.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">Line</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {groupedFeatures.flowgate.length > 0 && (
            <CommandGroup heading="Flowgates">
              {groupedFeatures.flowgate.map((feature) => (
                <CommandItem
                  key={`flowgate-${feature.id}`}
                  value={feature.name}
                  onSelect={() => handleSelect(feature)}
                  className="cursor-pointer"
                >
                  <span className="mr-2">{getFeatureIcon('flowgate')}</span>
                  <span className="font-mono text-sm">{feature.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">
                    {(feature.data as FlowgateInfo).lineCount} lines
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  )
} 