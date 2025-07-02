"use client";

import * as React from "react";
import { IconTrendingDown, IconTrendingUp, IconMinus, IconAlertCircle, IconHelpCircle, IconEye } from "@tabler/icons-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

// Generic interface for metric data - element-agnostic naming
export interface MetricRowData {
  id: string;
  name: string;
  value: string;
  unit?: string;
  timestamp: string;
  trend: 'up' | 'down' | 'neutral';
  trendDescription: string;
  description?: string; // Optional plain English description for tooltip
  yearOverYearChange?: string; // Placeholder for year-over-year comparison
  change24h?: number;        // Add 24-hour change
  change24hPercent?: number; // Add 24-hour percentage change
  isNotAvailable?: boolean;  // Add flag to indicate N/A values
}

interface MetricsTableProps {
  data: MetricRowData[];
  isLoading?: boolean;
  emptyStateTitle?: string;
  emptyStateDescription?: string;
  className?: string;
  selectedMetricId?: string; // Add selected metric ID
  onMetricSelect?: (metricId: string) => void; // Add callback for metric selection
  skeletonRowCount?: number; // Add skeleton row count prop
}

// Enhanced helper function to format 24-hour change
const format24HourChange = (change: number | undefined, changePercent: number | undefined, unit?: string): string => {
  if (change === undefined || change === null) return "";
  
  const absChange = Math.abs(change);
  const sign = change >= 0 ? "+" : "-";
  
  // Format the absolute change value
  let formattedChange = "";
  if (absChange >= 1000) {
    formattedChange = `${(absChange / 1000).toFixed(1)}k`;
  } else if (absChange >= 1) {
    formattedChange = absChange.toFixed(1);
  } else {
    formattedChange = absChange.toFixed(2);
  }
  
  // Remove unnecessary decimals
  if (formattedChange.endsWith(".0")) {
    formattedChange = formattedChange.slice(0, -2);
  }
  
  return `${sign}${formattedChange}${unit ? ` ${unit}` : ""}`;
};

// Enhanced TrendIcon component with 24-hour change display
const TrendIcon = ({ trend, change24h, change24hPercent, unit }: { 
  trend: MetricRowData['trend']; 
  change24h?: number; 
  change24hPercent?: number;
  unit?: string;
}) => {
  const changeText = format24HourChange(change24h, change24hPercent, unit);
  
  if (trend === 'up') {
    return (
      <div className="flex items-center gap-1 text-green-600">
        <IconTrendingUp className="size-4" />
        {changeText && <span className="text-xs font-medium">{changeText}</span>}
      </div>
    );
  }
  
  if (trend === 'down') {
    return (
      <div className="flex items-center gap-1 text-red-600">
        <IconTrendingDown className="size-4" />
        {changeText && <span className="text-xs font-medium">{changeText}</span>}
      </div>
    );
  }
  
  return (
    <div className="flex items-center gap-1 text-muted-foreground">
      <IconMinus className="size-4" />
      {changeText && <span className="text-xs font-medium">{changeText}</span>}
    </div>
  );
};

// Helper function to get metric descriptions
const getMetricDescription = (metricName: string): string => {
  const descriptions: Record<string, string> = {
    // Dam metrics
    "Headroom": "The difference between current reservoir level and full capacity, indicating available storage space.",
    "Reservoir Fill": "Current reservoir level as a percentage of total capacity, showing how full the reservoir is.",
    "Inflow": "The rate of water flowing into the reservoir, measured in cubic feet per second.",
    "Outflow": "The rate of water flowing out through turbines for power generation, measured in cubic feet per second.",
    "Spill %": "Percentage of water being released through spillways rather than turbines for power generation.",
    "Spill": "The volume of water being released through spillways, measured in cubic feet per second.",
    "Gates Open": "Number of spillway gates currently open for water release operations.",
    "Generation Flow": "The turbine discharge specifically used for power generation, measured in cubic feet per second.",
    
    // SNOTEL weather metrics
    "Snow Water Equivalent": "The amount of water contained in the snowpack, measured as the depth of water if the snow were melted.",
    "Precipitation": "Cumulative precipitation measurement, adjusted for snow conditions.",
    "Snow Depth": "The total depth of snow on the ground at the measurement site.",
    "Air Temperature": "Current air temperature measured at the weather station.",
    "Solar Radiation": "Incoming solar energy measured at the station, indicating sun exposure and weather conditions.",
    "Relative Humidity": "The amount of moisture in the air relative to the maximum it can hold at current temperature.",
    "Wind Speed": "Average wind speed measured at the station, indicating weather conditions and potential for snow redistribution."
  };
  
  return descriptions[metricName] || "Operational metric data";
};

// Helper function to format timestamp
const formatTimestamp = (timestamp: string): string => {
  try {
    const dateObj = new Date(timestamp);
    if (String(dateObj) === "Invalid Date") {
      return "Invalid Time";
    }
    return `${dateObj.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit', 
      hour12: true, 
      timeZone: 'UTC' 
    })} UTC`;
  } catch (e) {
    return "Time N/A";
  }
};

// Loading skeleton component - matches actual table structure and text height exactly
const MetricsTableSkeleton = ({ rowCount = 8 }: { rowCount?: number }) => (
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Metric</TableHead>
        <TableHead className="text-right">Value</TableHead>
        <TableHead className="text-center">24H Trend</TableHead>
        <TableHead className="text-center w-12"></TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {Array.from({ length: rowCount }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <div className="flex items-center gap-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4 rounded-full flex-shrink-0" />
            </div>
          </TableCell>
          
          <TableCell className="text-right">
            <Skeleton className="h-4 w-16 ml-auto" />
          </TableCell>
          
          <TableCell className="text-center">
            <div className="flex justify-center">
              <Skeleton className="h-4 w-4" />
            </div>
          </TableCell>
          
          <TableCell className="text-center">
            <div className="flex justify-center">
              <Skeleton className="h-4 w-4" />
            </div>
          </TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
);

export function MetricsTable({ 
  data, 
  isLoading = false, 
  emptyStateTitle = "No metrics available",
  emptyStateDescription = "Operational metrics are currently unavailable.",
  className = "",
  selectedMetricId,
  onMetricSelect,
  skeletonRowCount = 8 // Default to 8 rows for dam data
}: MetricsTableProps) {
  
  if (isLoading) {
    return (
      <div className={className}>
        <MetricsTableSkeleton rowCount={skeletonRowCount} />
      </div>
    );
  }
  
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed p-6 text-center">
        <div className="flex flex-col items-center">
          <IconAlertCircle className="mb-2 size-6 text-muted-foreground" />
          <p className="text-sm text-muted-foreground font-medium">{emptyStateTitle}</p>
          <p className="text-xs text-muted-foreground">{emptyStateDescription}</p>
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className={className}>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Metric</TableHead>
              <TableHead className="text-right">Value</TableHead>
              <TableHead className="text-center">24H Trend</TableHead>
              <TableHead className="text-center w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((metric) => {
              const isNotAvailable = metric.isNotAvailable || metric.value.includes('N/A');
              const isSelected = selectedMetricId === metric.id;
              const isClickable = onMetricSelect && !isNotAvailable;
              
              const rowClassName = `
                ${isNotAvailable ? 'bg-muted/30' : 'hover:bg-transparent'}
                ${isClickable ? 'cursor-pointer group' : ''}
              `.trim();
              
              return (
                <TableRow 
                  key={metric.id} 
                  className={rowClassName}
                  onClick={isClickable ? () => onMetricSelect(metric.id) : undefined}
                >
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className={`font-medium ${
                        isNotAvailable ? 'text-muted-foreground' : 'text-foreground'
                      }`}>
                        {metric.name}
                      </span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <IconHelpCircle className="size-4 text-muted-foreground hover:text-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-xs">
                          <p>{metric.description || getMetricDescription(metric.name)}</p>
                          {isNotAvailable && (
                            <p className="text-sm text-muted-foreground mt-1">
                              This metric is not recorded for this dam.
                            </p>
                          )}
                          {isClickable && !isSelected && (
                            <p className="text-sm text-muted-foreground mt-1">
                              Click to view time series chart
                            </p>
                          )}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                  </TableCell>
                  
                  <TableCell className="text-right">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className={`font-medium tabular-nums cursor-help ${
                          isNotAvailable ? 'text-muted-foreground' : 'text-foreground'
                        }`}>
                          {metric.value}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="left">
                        {isNotAvailable ? (
                          <p className="text-xs">
                            This metric is not available for this dam
                          </p>
                        ) : (
                          <p className="text-xs">
                            Latest reading: {formatTimestamp(metric.timestamp)}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  </TableCell>
                  
                  <TableCell className="text-center">
                    {!isNotAvailable ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="inline-flex items-center gap-1 cursor-help">
                            <TrendIcon 
                              trend={metric.trend} 
                              change24h={metric.change24h}
                              change24hPercent={metric.change24hPercent}
                              unit={metric.unit}
                            />
                          </div>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-sm">{metric.trendDescription}</p>
                          {metric.change24h !== undefined && (
                            <p className="text-sm text-muted-foreground">
                              24h change: {format24HourChange(metric.change24h, metric.change24hPercent, metric.unit)}
                            </p>
                          )}
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <div className="flex justify-center">
                        <IconMinus className="size-4 text-muted-foreground" />
                      </div>
                    )}
                  </TableCell>
                  
                  <TableCell className="text-center">
                    {isSelected && !isNotAvailable ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <IconEye className="size-4 text-primary cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-sm">Currently viewing this metric</p>
                        </TooltipContent>
                      </Tooltip>
                    ) : isClickable && !isNotAvailable ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <IconEye className="size-4 text-muted-foreground/50 opacity-0 group-hover:opacity-100 transition-opacity cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent>
                          <p className="text-sm">Click to view this metric</p>
                        </TooltipContent>
                      </Tooltip>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </TooltipProvider>
  );
}

// Update the transformation function
export const transformSectionCardDataToMetrics = (cards: any[]): MetricRowData[] => {
  return cards.map(card => {
    const isNotAvailable = card.value && card.value.includes('N/A');
    
    return {
      id: card.id,
      name: card.title,
      value: card.value,
      timestamp: card.timestamp,
      trend: card.trend,
      trendDescription: card.trendDescription,
      description: undefined,
      yearOverYearChange: undefined,
      change24h: card.change24h,
      change24hPercent: card.change24hPercent,
      isNotAvailable: isNotAvailable,
      unit: card.title === "Headroom" ? "ft" : 
            card.title === "Reservoir Fill" ? "%" :
            card.title === "Inflow" ? "cfs" :
            card.title === "Outflow" ? "cfs" :
            card.title === "Spill %" ? "%" :
            card.title === "Spill" ? "cfs" :
            card.title === "Gates Open" ? "gates" :
            card.title === "Generation Flow" ? "cfs" : undefined
    };
  });
}; 