"use client"

import * as React from "react"
import { Line, Bar, ComposedChart, CartesianGrid, XAxis, YAxis, Label, Legend } from "recharts"
// import { toZonedTime, format as formatDate } from "date-fns-tz" // Temporarily removed for UTC display

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"
import { InflowDataPoint, getMetricTimeseries, TimeRangeOption, getSnotelStationObservations, SnotelObservationDataPoint } from "@/lib/firebase" 

// Define the new time range options type
// type TimeRangeOption = "mtd" | "14d" | "7d"; // Already in firebase.ts, no need to redefine if imported

// Metric configuration to match backend METRICS_CONFIG
const METRICS_CONFIG = {
  "3": { name: "Headroom", unit: "ft", color: "hsl(var(--chart-1))" },
  "5": { name: "Reservoir Fill", unit: "%", color: "hsl(var(--chart-2))" },
  "6": { name: "Inflow", unit: "cfs", color: "hsl(var(--chart-1))" },
  "8": { name: "Spill", unit: "cfs", color: "hsl(var(--chart-3))" },
  "9": { name: "Spill %", unit: "%", color: "hsl(var(--chart-4))" },
  "10": { name: "Gates Open", unit: "gates", color: "hsl(var(--chart-5))" }
} as const;

// SNOTEL metric configuration
const SNOTEL_METRICS_CONFIG = {
  "25": { name: "Snow Water Equivalent", unit: "in", color: "#3b82f6" },
  "26": { name: "Precipitation", unit: "in", color: "#06b6d4" },
  "27": { name: "Snow Depth", unit: "in", color: "#8b5cf6" },
  "28": { name: "Air Temperature", unit: "°F", color: "#ef4444" },
  "29": { name: "Solar Radiation", unit: "W/m²", color: "#f59e0b" },
  "30": { name: "Relative Humidity", unit: "%", color: "#10b981" },
  "31": { name: "Wind Speed", unit: "mph", color: "#6b7280" }
} as const;

interface ProcessedChartData {
  date: string;
  value: number; // Generic value instead of inflow
  type: 'observed' | 'forecast' | 'forecast_error';
  timestamp: number;
  observed: number | null;
  forecast: number | null;
  // Replace dummy volume with actual forecast error
  forecast_error: number | null;
}

// Temporarily removed PACIFIC_TIMEZONE constant
// const PACIFIC_TIMEZONE = "America/Los_Angeles"

const chartConfig = {
  value: {
    label: "Value",
    color: "hsl(var(--chart-1))", 
  },
  observed: {
    label: "Observed", 
    color: "hsl(120, 50%, 30%)", // Darker green
  },
  forecast: {
    label: "Forecast",
    color: "hsl(340, 50%, 40%)", // Darker red
  },
  forecast_error: {
    label: "Forecast Error",
    color: "hsl(0, 70%, 50%)", // Red for errors
  },
} satisfies ChartConfig

// Helper to format date string (basic version for UTC)
// Updated to handle new TimeRangeOption types
const formatUtcDate = (isoString: string, range: TimeRangeOption): string => {
  const dateObj = new Date(isoString);
  if (String(dateObj) === "Invalid Date") {
    return "Invalid Date (UTC)"; 
  }
  
  // For different ranges, show different levels of detail
  if (range === "7d") {
    // For 7 days, show day and abbreviated month
    return dateObj.toLocaleDateString('en-US', { 
      day: 'numeric', 
      month: 'short',
      timeZone: 'UTC' 
    });
  } else {
    // For longer ranges, just show the day
    return dateObj.getUTCDate().toString();
  }
};

const formatUtcDateForDisplay = (isoString: string): string => {
  const dateObj = new Date(isoString);
  // Format as YYYY-MM-DD for data key and internal use
  return `${dateObj.getUTCFullYear()}-${(dateObj.getUTCMonth() + 1).toString().padStart(2, '0')}-${dateObj.getUTCDate().toString().padStart(2, '0')}`;
};

interface ChartAreaInteractiveProps {
  selectedDamId?: number;
  selectedStationId?: number;
  selectedMetricId: string;
  dataSource: 'dam' | 'snotel';
  stationName?: string; // For SNOTEL stations
}

// Add this helper function before the component
const generateEveryOtherDayTicks = (dataMin: number, dataMax: number): number[] => {
  const ticks: number[] = [];
  const startDate = new Date(dataMin);
  const endDate = new Date(dataMax);
  
  // Start from the beginning of the first day
  const currentDate = new Date(startDate.getUTCFullYear(), startDate.getUTCMonth(), startDate.getUTCDate());
  
  while (currentDate <= endDate) {
    ticks.push(currentDate.getTime());
    currentDate.setUTCDate(currentDate.getUTCDate() + 2); // Move to every other day
  }
  
  return ticks;
};

// Remove the generateDummyVolumeData function and replace with:
const processForecastError = (value: number, dataType: string): number | null => {
  return dataType === 'forecast_error' ? value : null;
};

// Updated CustomErrorBar with proper relative sizing
const CustomErrorBar = (props: any) => {
  const { payload, x, y, width, height, setHoveredErrorBar, maxErrorInData } = props;
  
  if (!payload || payload.forecast_error === null || payload.forecast_error === undefined) {
    return null;
  }
  
  const errorValue = payload.forecast_error;
  const isPositive = errorValue > 0;
  const fill = isPositive ? "hsl(0, 70%, 50%)" : "hsl(220, 70%, 50%)";
  
  // Calculate bar dimensions
  const barWidth = Math.max(width, 8); // Slightly wider for easier hovering
  const barX = x - (barWidth - width) / 2;
  
  const maxErrorHeight = 30;
  const errorMagnitude = Math.abs(errorValue);
  
  // Use the actual maximum error from the data for relative scaling
  const maxError = maxErrorInData || 10000; // Fallback to 10000 if no data
  const barHeight = Math.min((errorMagnitude / maxError) * maxErrorHeight, maxErrorHeight);
  
  // Position closer to the actual bottom of the chart area
  const chartBottom = 220; // Increased from 200 to move bars closer to bottom
  const barY = chartBottom - barHeight;
  
  return (
    <rect
      x={barX}
      y={barY}
      width={barWidth}
      height={barHeight}
      fill={fill}
      fillOpacity={0.7}
      stroke={fill}
      strokeWidth={0.5}
      rx={1}
      // Add hover handlers
      onMouseEnter={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        setHoveredErrorBar({
          x: rect.left + rect.width / 2,
          y: rect.top,
          value: errorValue,
          date: payload.date
        });
      }}
      onMouseLeave={() => {
        setHoveredErrorBar(null);
      }}
      style={{ cursor: 'pointer' }}
    />
  );
};

// Custom tooltip component for error bars
const ErrorBarTooltip = ({ data }: { data: { x: number; y: number; value: number; date: string } }) => {
  const errorType = data.value > 0 ? 'Under-forecasted' : 'Over-forecasted';
  const dateObj = new Date(data.date);
  // Remove time from error bar tooltips - just show date
  const formattedDate = dateObj.toLocaleDateString('en-US', { 
    year: 'numeric', month: 'short', day: 'numeric',
    timeZone: 'UTC' 
  });

  return (
    <div
      style={{
        position: 'fixed',
        left: data.x,
        top: data.y - 10,
        transform: 'translate(-50%, -100%)',
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        color: 'white',
        padding: '8px 12px',
        borderRadius: '4px',
        fontSize: '12px',
        pointerEvents: 'none',
        zIndex: 1000,
        whiteSpace: 'nowrap'
      }}
    >
      <div>{formattedDate}</div>
      <div>{Math.abs(data.value).toLocaleString()} cfs ({errorType})</div>
    </div>
  );
};

// Smart Y-axis scaling function - UPDATED with better percentage handling
const calculateOptimalYAxisDomain = (data: ProcessedChartData[], metricId: string): [number, number] => {
  // Get all valid metric values (observed and forecast, excluding forecast_error)
  const allValues = data
    .filter(point => point.observed !== null || point.forecast !== null)
    .map(point => point.observed || point.forecast)
    .filter(val => val !== null) as number[];

  if (allValues.length === 0) {
    return [0, 100]; // Default range if no data
  }

  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min;

  // If range is very small (flat line), create some padding
  if (range < 0.01) {
    const center = (min + max) / 2;
    const padding = Math.max(center * 0.1, 1); // 10% of center value or minimum 1
    return [center - padding, center + padding];
  }

  // Calculate appropriate step size and padding based on metric type and range
  let stepSize: number;
  let padding: number;

  if (metricId === "6") { // Inflow - larger values, use existing logic for compatibility
    stepSize = 5000;
    padding = 0.05; // 5% padding
  } else if (metricId === "5" || metricId === "9") { // Percentage metrics (Reservoir Fill, Spill %)
    // More granular percentage scaling based on actual data range
    if (range < 1) {
      stepSize = 0.1; // Very fine granularity for tiny ranges
    } else if (range < 5) {
      stepSize = 0.5; // Fine granularity for small ranges
    } else if (range < 15) {
      stepSize = 1; // 1% steps for moderate ranges
    } else if (range < 40) {
      stepSize = 2; // 2% steps for larger ranges
    } else if (range < 70) {
      stepSize = 5; // 5% steps for large ranges
    } else {
      stepSize = 10; // 10% steps for very large ranges
    }
    padding = 0.15; // 15% padding for better visibility of percentage trends
  } else if (metricId === "10") { // Gates Open - integer values
    stepSize = Math.max(1, Math.ceil(range / 8)); // Aim for ~8 ticks
    padding = 0.15; // 15% padding for better visibility
  } else { // Headroom, Spill - moderate values
    if (range < 10) {
      stepSize = 1;
    } else if (range < 100) {
      stepSize = 5;
    } else if (range < 1000) {
      stepSize = 50;
    } else {
      stepSize = 100;
    }
    padding = 0.1; // 10% padding
  }

  // Apply padding
  const paddedMin = min - (range * padding);
  const paddedMax = max + (range * padding);

  // Round to nice numbers based on step size
  const domainMin = Math.floor(paddedMin / stepSize) * stepSize;
  const domainMax = Math.ceil(paddedMax / stepSize) * stepSize;

  // Different minimum range logic for different metrics
  let finalMin: number;
  let finalMax: number;

  if (metricId === "5" || metricId === "9") { // Percentage metrics
    // For percentages, be more flexible with the minimum range
    finalMin = Math.max(0, domainMin); // Don't go below 0%
    
    // Smart upper bound for percentages based on actual data
    if (max <= 15) {
      // For small percentages (≤15%), cap at reasonable upper bound
      finalMax = Math.min(25, Math.max(domainMax, finalMin + stepSize * 4));
    } else if (max <= 50) {
      // For moderate percentages, allow some room but don't go to 100%
      finalMax = Math.min(Math.max(max * 1.3, 60), Math.max(domainMax, finalMin + stepSize * 3));
    } else {
      // For large percentages, can go up to 100%
      finalMax = Math.min(100, Math.max(domainMax, finalMin + stepSize * 3));
    }
  } else if (metricId === "10") { // Gates Open
    finalMin = Math.max(0, domainMin);
    finalMax = Math.max(finalMin + Math.max(2, stepSize * 2), domainMax); // Minimum 2 gates range
  } else { // Other metrics (Headroom, Spill, Inflow)
    finalMin = Math.max(0, domainMin);
    finalMax = Math.max(finalMin + stepSize * 2, domainMax); // Ensure minimum range
  }

  console.log(`Y-axis domain calculation for ${metricId}:`, {
    metricName: metricId === "5" ? "Reservoir Fill" : metricId === "9" ? "Spill %" : "Other",
    dataRange: { min, max, range },
    stepSize,
    padding,
    beforeMinRange: [domainMin, domainMax],
    finalDomain: [finalMin, finalMax]
  });

  return [finalMin, finalMax];
};

// Keep backward compatibility - alias for inflow specifically
export const getInflowTimeseries = (range: TimeRangeOption, damId: number): Promise<InflowDataPoint[]> => 
  getMetricTimeseries(range, damId, 6);

export function ChartAreaInteractive({ selectedDamId, selectedStationId, selectedMetricId, dataSource, stationName }: ChartAreaInteractiveProps) {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>("14d") 
  const [processedChartData, setProcessedChartData] = React.useState<ProcessedChartData[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  
  // Move the hoveredErrorBar state INSIDE the component
  const [hoveredErrorBar, setHoveredErrorBar] = React.useState<{
    x: number;
    y: number;
    value: number;
    date: string;
  } | null>(null);

  // Get metric configuration based on data source
  const metricConfig = dataSource === 'dam' 
    ? METRICS_CONFIG[selectedMetricId as keyof typeof METRICS_CONFIG]
    : SNOTEL_METRICS_CONFIG[selectedMetricId as keyof typeof SNOTEL_METRICS_CONFIG];
  
  const isInflowMetric = selectedMetricId === "6" && dataSource === 'dam';

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d") // Default to 7d for mobile
    } else {
      setTimeRange("14d") // Default to 14d for desktop
    }
  }, [isMobile])

  React.useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true)
      try {
        let processedData: ProcessedChartData[] = [];
        
        if (dataSource === 'dam' && selectedDamId) {
          const damData = await getMetricTimeseries(timeRange, selectedDamId, parseInt(selectedMetricId));
          
          processedData = damData.map(point => {
            const timestamp = new Date(point.ts_utc).getTime()
            
            // Smart precision handling based on metric type
            let metricValue: number;
            if (metricConfig?.unit === '%') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else if (metricConfig?.unit === 'ft' || metricConfig?.unit === 'in') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else if (metricConfig?.unit === 'gates') {
              metricValue = Math.round(point.value_num);
            } else if (metricConfig?.unit === '°F') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else {
              metricValue = Math.trunc(point.value_num);
            }
            
            return {
              date: point.ts_utc,
              timestamp: timestamp,
              observed: point.data_type === 'observed' ? metricValue : null,
              forecast: point.data_type === 'forecast' ? metricValue : null,
              value: point.data_type !== 'forecast_error' ? metricValue : Math.abs(metricValue),
              type: point.data_type,
              forecast_error: isInflowMetric && point.data_type === 'forecast_error' ? metricValue : null
            }
          });
          
        } else if (dataSource === 'snotel' && selectedStationId) {
          // Convert time range to days for SNOTEL API
          const days = timeRange === "7d" ? 7 : timeRange === "14d" ? 14 : 30;
          const snotelData = await getSnotelStationObservations(selectedStationId, days, parseInt(selectedMetricId));
          
          // Transform SNOTEL data to ProcessedChartData format
          processedData = snotelData.map(point => {
            const timestamp = new Date(point.ts_utc).getTime()
            
            // Smart precision handling based on metric type
            let metricValue: number;
            if (metricConfig?.unit === '%') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else if (metricConfig?.unit === 'ft' || metricConfig?.unit === 'in') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else if (metricConfig?.unit === '°F') {
              metricValue = Math.round(point.value_num * 10) / 10;
            } else if (metricConfig?.unit === 'W/m²' || metricConfig?.unit === 'mph') {
              metricValue = Math.round(point.value_num);
            } else {
              metricValue = Math.trunc(point.value_num);
            }
            
            return {
              date: point.ts_utc,
              timestamp: timestamp,
              observed: metricValue, // SNOTEL only has observed data
              forecast: null,
              value: metricValue,
              type: 'observed' as const,
              forecast_error: null
            }
          });
        }
        
        setProcessedChartData(processedData)
      } catch (error) {
        console.error("Failed to fetch or process metric data:", error)
        setProcessedChartData([]) 
      } finally {
        setIsLoading(false)
      }
    }
    fetchData()
  }, [timeRange, selectedDamId, selectedStationId, selectedMetricId, metricConfig?.name, isInflowMetric, dataSource])

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>{metricConfig?.name || "Metric"}</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            {processedChartData.length > 0 ? (
              (() => {
                // Find the latest observed data point
                const latestObserved = processedChartData
                  .filter(d => d.type === 'observed')
                  .slice(-1)[0]; // Get the last observed point
                
                if (latestObserved) {
                  // Smart formatting for the description based on metric type
                  const unit = metricConfig?.unit || '';
                  let formattedValue: string;
                  
                  if (unit === '%' || unit === 'ft') {
                    // Show 1 decimal place for percentages and feet
                    formattedValue = Number(latestObserved.value).toFixed(1);
                  } else {
                    // Show whole numbers for other metrics
                    formattedValue = latestObserved.value.toLocaleString();
                  }
                  
                  return `${formattedValue} ${unit} ${new Date(latestObserved.date).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} ${new Date(latestObserved.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`;
                } else {
                  return "No observed data available for the selected period.";
                }
              })()
            ) : (
              `Daily ${metricConfig?.name.toLowerCase() || 'metric'} for the selected period.`
            )}
          </span>
          <span className="@[540px]/card:hidden">
            {/* More dynamic description for mobile */}
            {timeRange === "1d" ? "Last 24 hours (UTC)" : 
             timeRange === "mtd" ? "Month to Date (UTC)" : 
             timeRange === "14d" ? "Last 14 days (UTC)" : "Last 7 days (UTC)"}
          </span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            onValueChange={(value: TimeRangeOption) => {
              if (value) setTimeRange(value)
            }}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
            {/* Updated ToggleGroupItems */}
            <ToggleGroupItem value="1d">Last 24 hours</ToggleGroupItem>
            <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
            <ToggleGroupItem value="14d">Last 14 days</ToggleGroupItem>
            <ToggleGroupItem value="mtd">Month to Date</ToggleGroupItem>
          </ToggleGroup>
          <Select
            value={timeRange}
            onValueChange={(value: TimeRangeOption) => {
               if (value) setTimeRange(value)
            }}
          >
            <SelectTrigger
              className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Select a time range"
            >
              <SelectValue placeholder="Select time range" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              {/* Updated SelectItems */}
              <SelectItem value="1d" className="rounded-lg">
                Last 24 hours
              </SelectItem>
              <SelectItem value="7d" className="rounded-lg">
                Last 7 days
              </SelectItem>
              <SelectItem value="14d" className="rounded-lg">
                Last 14 days
              </SelectItem>
              <SelectItem value="mtd" className="rounded-lg">
                Month to Date
              </SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[250px] w-full"
        >
          {isLoading ? (
            <div className="flex h-full w-full items-center justify-center">
              <p>Loading chart data...</p>
            </div>
          ) : processedChartData.length === 0 && !isLoading ? (
             <div className="flex h-full w-full items-center justify-center">
              <p>No {metricConfig?.name.toLowerCase() || 'metric'} data available for the selected period.</p>
            </div>
          ) : (
            <ComposedChart data={processedChartData} margin={{ left: 30, right: 10, top: 5, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="timestamp"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                ticks={processedChartData.length > 0 ? generateEveryOtherDayTicks(
                  Math.min(...processedChartData.map(d => d.timestamp)),
                  Math.max(...processedChartData.map(d => d.timestamp))
                ) : []}
                tickFormatter={(timestamp) => {
                  const date = new Date(timestamp);
                  return date.getUTCDate().toString();
                }}
              />
              {/* Left Y-axis for metric values with smart scaling */}
              <YAxis 
                yAxisId="left"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={(value) => {
                  if (typeof value === 'number') {
                    // Smart formatting for Y-axis labels based on metric type
                    const unit = metricConfig?.unit || '';
                    if (unit === '%' || unit === 'ft') {
                      // Show 1 decimal place for percentages and feet if not whole numbers
                      return value % 1 === 0 ? value.toString() : value.toFixed(1);
                    } else {
                      return value.toLocaleString(); 
                    }
                  }
                  return String(value);
                }}
                domain={(() => {
                  const [min, max] = calculateOptimalYAxisDomain(processedChartData, selectedMetricId);
                  return [min, max];
                })()}
              >
                <Label 
                  value={`${metricConfig?.name || 'Value'} (${metricConfig?.unit || ''})`}
                  angle={-90} 
                  position="insideLeft" 
                  style={{ textAnchor: 'middle' }} 
                  dy={0}
                  offset={-20}
                />
              </YAxis>
              {/* Right Y-axis for forecast error bars (only for inflow) */}
              {isInflowMetric && (
                <YAxis 
                  yAxisId="right"
                  orientation="right"
                  hide={true}
                  domain={[
                    (dataMin: number) => Math.min(dataMin * 1.1, 0), // Allow negative values
                    (dataMax: number) => Math.max(dataMax * 1.1, 0)  // Allow positive values
                  ]}
                />
              )}
              <ChartTooltip
                cursor={true}
                animationDuration={0}
                content={(props) => {
                  const { active, payload, label } = props;
                  
                  // If we're hovering over an error bar, don't show the line tooltip
                  if (hoveredErrorBar) {
                    return null;
                  }
                  
                  // Only show tooltip if we have an active payload with actual data
                  if (!active || !payload || payload.length === 0) {
                    return null;
                  }
                  
                  // Filter out null/undefined values and forecast_error data for the main tooltip
                  const validPayload = payload.filter(entry => {
                    const dataType = entry.payload?.type;
                    return dataType !== 'forecast_error' && 
                           entry.value !== null && 
                           entry.value !== undefined &&
                           entry.dataKey !== 'forecast_error';
                  });
                  
                  // If no valid data to show, don't render tooltip
                  if (validPayload.length === 0) {
                    return null;
                  }
                  
                  return (
                    <ChartTooltipContent
                      active={active}
                      payload={validPayload}
                      label={label}
                      labelFormatter={(value, payload) => {
                        if (payload && payload.length > 0 && payload[0].payload.date) {
                          const dateStringFromPayload = payload[0].payload.date;
                          const dateObj = new Date(dateStringFromPayload);
                          const dataType = payload[0].payload.type;
                          
                          if (String(dateObj) === "Invalid Date") {
                            return "Invalid Date UTC";
                          }
                          const formattedDate = dateObj.toLocaleDateString('en-US', { 
                            year: 'numeric', month: 'short', day: 'numeric', 
                            hour: '2-digit', minute: '2-digit', timeZone: 'UTC' 
                          }) + " UTC";
                          // Capitalize the data type in the title
                          const capitalizedType = dataType.charAt(0).toUpperCase() + dataType.slice(1);
                          return `${formattedDate} (${capitalizedType})`;
                        }
                        return `${metricConfig?.name || 'Metric'} (UTC)`;
                      }}
                      formatter={(value, name, props) => {
                        // Smart formatting based on metric type - FIXED!
                        const unit = metricConfig?.unit || '';
                        let formattedValue: string;
                        
                        if (unit === '%' || unit === 'ft') {
                          // Show 1 decimal place for percentages and feet
                          formattedValue = Number(props.payload.value).toFixed(1);
                        } else {
                          // Show whole numbers for other metrics
                          formattedValue = props.payload.value.toLocaleString();
                        }
                        
                        return [`${formattedValue} ${unit}`];
                      }}
                      indicator="dot"
                    />
                  );
                }}
              />
              {/* Forecast error bars (only for inflow) */}
              {isInflowMetric && (
                <Bar
                  yAxisId="right"
                  dataKey="forecast_error"
                  shape={(props: any) => {
                    // Calculate max error once for all bars
                    const maxErrorInData = Math.max(...processedChartData
                      .filter(d => d.forecast_error !== null)
                      .map(d => Math.abs(d.forecast_error!))
                    );
                    return <CustomErrorBar {...props} setHoveredErrorBar={setHoveredErrorBar} maxErrorInData={maxErrorInData} />;
                  }}
                  stroke="none"
                  fill="transparent"
                />
              )}
              {/* Observed metric line - UPDATED to conditionally show dots */}
              <Line
                yAxisId="left"
                dataKey="observed"
                type="linear" 
                stroke="hsl(120, 70%, 40%)"
                strokeWidth={2}
                dot={false}
                activeDot={isInflowMetric ? { r: 8 } : false}
                connectNulls={true}
              />
              {/* Forecast metric line - UPDATED to conditionally show dots */}
              <Line
                yAxisId="left"
                dataKey="forecast"
                type="linear" 
                stroke="hsl(340, 50%, 40%)"
                strokeWidth={2}
                strokeDasharray={isInflowMetric ? "5 5" : "none"}
                dot={false}
                activeDot={isInflowMetric ? { r: 6, fill: "hsl(340, 50%, 40%)" } : false}
                connectNulls={false}
              />
            </ComposedChart>
          )}
        </ChartContainer>
        {hoveredErrorBar && <ErrorBarTooltip data={hoveredErrorBar} />}
      </CardContent>
    </Card>
  )
}
