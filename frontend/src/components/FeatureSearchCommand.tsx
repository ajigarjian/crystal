"use client"

import * as React from "react"
import { SearchIcon } from "lucide-react"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { DamInfo, PowerLineInfo, SnotelStationInfo, PlantInfo, GeneratorInfo } from "@/app/dashboard/page"
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
  type: 'dam' | 'powerline' | 'flowgate' | 'snotel' | 'plant' | 'generator';
  data: DamInfo | PowerLineInfo | FlowgateInfo | SnotelStationInfo | PlantInfo | GeneratorInfo;
}

interface FlowgateInfo {
  id: string;
  name: string;
  lineCount: number;
}

type FeatureTypeFilter = 'all' | 'dam' | 'powerline' | 'flowgate' | 'snotel' | 'plant' | 'generator';

interface FeatureSearchCommandProps {
  dams: DamInfo[];
  powerLines: SearchableFeature[];
  flowgates: SearchableFeature[];
  snotelStations: SearchableFeature[];
  powerPlants: SearchableFeature[];
  powerGenerators: SearchableFeature[];
  onDamSelect: (dam: DamInfo) => void;
  onPowerLineSelect: (powerLine: PowerLineInfo) => void;
  onFlowgateSelect: (flowgate: string) => void;
  onSnotelStationSelect: (station: SnotelStationInfo) => void;
  onPlantSelect: (plant: PlantInfo) => void;
  onGeneratorSelect: (generator: GeneratorInfo) => void;
}

export function FeatureSearchCommand({
  dams,
  powerLines,
  flowgates,
  snotelStations,
  powerPlants,
  powerGenerators,
  onDamSelect,
  onPowerLineSelect,
  onFlowgateSelect,
  onSnotelStationSelect,
  onPlantSelect,
  onGeneratorSelect,
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

    return [...damFeatures, ...powerLines, ...flowgates, ...snotelStations, ...powerPlants, ...powerGenerators];
  }, [dams, powerLines, flowgates, snotelStations, powerPlants, powerGenerators]);

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
      snotel: filteredFeatures.filter(f => f.type === 'snotel'),
      plant: filteredFeatures.filter(f => f.type === 'plant'),
      generator: filteredFeatures.filter(f => f.type === 'generator'),
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
      case 'snotel':
        onSnotelStationSelect(feature.data as SnotelStationInfo);
        break;
      case 'plant':
        onPlantSelect(feature.data as PlantInfo);
        break;
      case 'generator':
        onGeneratorSelect(feature.data as GeneratorInfo);
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
      case 'snotel': return '❄️';
      case 'plant': return '🏭';
      case 'generator': return '⚙️';
      default: return '📍';
    }
  };

  const getFilterCounts = () => {
    return {
      all: allFeatures.length,
      dam: dams.length,
      powerline: powerLines.length,
      flowgate: flowgates.length,
      snotel: snotelStations.length,
      plant: powerPlants.length,
      generator: powerGenerators.length,
    };
  };

  const filterCounts = getFilterCounts();

  const filterOptions: { key: FeatureTypeFilter; label: string; icon: string }[] = [
    { key: 'all', label: 'All', icon: '🔍' },
    { key: 'dam', label: 'Dams', icon: '🏗️' },
    { key: 'powerline', label: 'Lines', icon: '⚡' },
    { key: 'flowgate', label: 'Flowgates', icon: '🔗' },
    { key: 'snotel', label: 'Stations', icon: '❄️' },
    { key: 'plant', label: 'Plants', icon: '🏭' },
    { key: 'generator', label: 'Generators', icon: '⚙️' },
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
        <span className="text-left">Search infrastructure...</span>
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 hidden h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
          <span className="text-xs">⌘</span>K
        </kbd>
      </Button>
      
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="overflow-hidden p-0 sm:max-w-2xl lg:max-w-3xl xl:max-w-4xl">
          <DialogHeader className="sr-only">
            <DialogTitle>Search Features</DialogTitle>
            <DialogDescription>Search for power infrastructure and monitoring stations</DialogDescription>
          </DialogHeader>
          <Command className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group]]:px-2 [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3 [&_[cmdk-item]_svg]:h-5 [&_[cmdk-item]_svg]:w-5">
            {/* Filter buttons - Improved layout for better spacing */}
            <div className="flex items-center gap-2 p-4 pb-2 flex-wrap">
              <span className="text-xs text-muted-foreground mr-1">Filter:</span>
              <div className="flex items-center gap-2 flex-wrap">
                {filterOptions.map((filter) => (
                  <Button
                    key={filter.key}
                    variant={activeFilter === filter.key ? "default" : "outline"}
                    size="sm"
                    onClick={() => setActiveFilter(filter.key)}
                    className="h-8 text-xs gap-1.5 px-3"
                  >
                    <span>{filter.icon}</span>
                    <span className="whitespace-nowrap">{filter.label}</span>
                    <Badge 
                      variant="secondary" 
                      className="ml-1 h-4 min-w-4 text-[10px] px-1.5"
                    >
                      {filterCounts[filter.key]}
                    </Badge>
                  </Button>
                ))}
              </div>
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

              {groupedFeatures.plant.length > 0 && (activeFilter === 'all' || activeFilter === 'plant') && (
                <CommandGroup heading="Power Plants">
                  {groupedFeatures.plant.map((feature) => (
                    <CommandItem
                      key={`plant-${feature.id}`}
                      value={feature.name}
                      onSelect={() => handleSelect(feature)}
                      className="cursor-pointer"
                    >
                      <span className="mr-2">{getFeatureIcon('plant')}</span>
                      <span className="truncate">{feature.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {(feature.data as PlantInfo).fuelType || 'Plant'}
                      </span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}

              {groupedFeatures.generator.length > 0 && (activeFilter === 'all' || activeFilter === 'generator') && (
                <CommandGroup heading="Generators">
                  {groupedFeatures.generator.map((feature) => (
                    <CommandItem
                      key={`generator-${feature.id}`}
                      value={feature.name}
                      onSelect={() => handleSelect(feature)}
                      className="cursor-pointer"
                    >
                      <span className="mr-2">{getFeatureIcon('generator')}</span>
                      <span className="truncate">{feature.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {(feature.data as GeneratorInfo).capacity || 'Generator'}
                      </span>
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

              {groupedFeatures.snotel.length > 0 && (activeFilter === 'all' || activeFilter === 'snotel') && (
                <CommandGroup heading="SNOTEL Stations">
                  {groupedFeatures.snotel.map((feature) => (
                    <CommandItem
                      key={`snotel-${feature.id}`}
                      value={feature.name}
                      onSelect={() => handleSelect(feature)}
                      className="cursor-pointer"
                    >
                      <span className="mr-2">{getFeatureIcon('snotel')}</span>
                      <span>{feature.name}</span>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {(feature.data as SnotelStationInfo).elevation ? 
                          `${(feature.data as SnotelStationInfo).elevation}ft` : 
                          'Station'
                        }
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