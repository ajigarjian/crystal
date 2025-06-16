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
import { Badge } from "@/components/ui/badge"
import { DamInfo, PowerLineInfo } from "@/app/dashboard/page"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

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

type FeatureTypeFilter = 'all' | 'dam' | 'powerline' | 'flowgate';

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
  const [activeFilter, setActiveFilter] = React.useState<FeatureTypeFilter>('all')

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

  // Filter features based on search term and active filter
  const filteredFeatures = React.useMemo(() => {
    let features = allFeatures;
    
    // Apply type filter
    if (activeFilter !== 'all') {
      features = features.filter(feature => feature.type === activeFilter);
    }
    
    // Apply search filter
    if (search) {
      features = features.filter(feature =>
        feature.name.toLowerCase().includes(search.toLowerCase())
      );
    }
    
    return features;
  }, [allFeatures, search, activeFilter]);

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

  // Reset filters when dialog closes
  const handleOpenChange = (open: boolean) => {
    setOpen(open);
    if (!open) {
      setActiveFilter('all');
      setSearch("");
    }
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

  const getFilterCounts = () => {
    return {
      all: allFeatures.length,
      dam: dams.length,
      powerline: powerLines.length,
      flowgate: flowgates.length,
    };
  };

  const filterCounts = getFilterCounts();

  const filterOptions: { key: FeatureTypeFilter; label: string; icon: string }[] = [
    { key: 'all', label: 'All', icon: '🔍' },
    { key: 'dam', label: 'Dams', icon: '🏗️' },
    { key: 'powerline', label: 'Lines', icon: '⚡' },
    { key: 'flowgate', label: 'Flowgates', icon: '🔗' },
  ];

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="relative h-9 w-full justify-start rounded-md bg-muted/50 text-sm font-normal text-muted-foreground shadow-none hover:bg-muted transition-colors"
      >
        <SearchIcon className="mr-2 h-4 w-4" />
        <span className="text-left">Search for dams, power lines, and flowgates...</span>
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 hidden h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
          <span className="text-xs">⌘</span>K
        </kbd>
      </Button>
      
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="overflow-hidden p-0 sm:max-w-xl">
          <DialogHeader className="sr-only">
            <DialogTitle>Search Features</DialogTitle>
            <DialogDescription>Search for dams, power lines, and flowgates</DialogDescription>
          </DialogHeader>
          <Command className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group]]:px-2 [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3 [&_[cmdk-item]_svg]:h-5 [&_[cmdk-item]_svg]:w-5">
            {/* Filter buttons */}
            <div className="flex items-center gap-1 p-3 pb-0">
              <span className="text-xs text-muted-foreground mr-2">Filter:</span>
              {filterOptions.map((filter) => (
                <Button
                  key={filter.key}
                  variant={activeFilter === filter.key ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveFilter(filter.key)}
                  className="h-7 text-xs gap-1"
                >
                  <span>{filter.icon}</span>
                  <span>{filter.label}</span>
                  <Badge 
                    variant="secondary" 
                    className="ml-1 h-4 min-w-4 text-[10px] px-1"
                  >
                    {filterCounts[filter.key]}
                  </Badge>
                </Button>
              ))}
            </div>
            
            <CommandInput 
              placeholder={`Type a ${activeFilter === 'all' ? 'feature' : activeFilter} name...`}
              value={search}
              onValueChange={setSearch}
              autoFocus={true}
            />
            <CommandList>
              <CommandEmpty>
                No {activeFilter === 'all' ? 'features' : `${activeFilter}s`} found.
              </CommandEmpty>
              
              {groupedFeatures.dam.length > 0 && (activeFilter === 'all' || activeFilter === 'dam') && (
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

              {groupedFeatures.powerline.length > 0 && (activeFilter === 'all' || activeFilter === 'powerline') && (
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

              {groupedFeatures.flowgate.length > 0 && (activeFilter === 'all' || activeFilter === 'flowgate') && (
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
          </Command>
        </DialogContent>
      </Dialog>
    </>
  )
} 