"use client"

import * as React from "react"
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Label, Legend } from "recharts"
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
import { InflowDataPoint, getInflowTimeseries, TimeRangeOption } from "@/lib/firebase" 

// Define the new time range options type
// type TimeRangeOption = "mtd" | "14d" | "7d"; // Already in firebase.ts, no need to redefine if imported

interface ProcessedChartData {
  date: string;
  inflow: number;
  type: 'observed' | 'forecast';
  timestamp: number;
  observed: number | null;
  forecast: number | null;
}

// Temporarily removed PACIFIC_TIMEZONE constant
// const PACIFIC_TIMEZONE = "America/Los_Angeles"

const chartConfig = {
  inflow: {
    label: "Inflow (cfs) - UTC",
    color: "hsl(var(--chart-1))", 
  },
  observed: {
    label: "Observed Inflow", 
    color: "hsl(120, 50%, 30%)", // Darker green
  },
  forecast: {
    label: "Forecast Inflow",
    color: "hsl(340, 50%, 40%)", // Darker red
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
  selectedDamId: number;
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

export function ChartAreaInteractive({ selectedDamId }: ChartAreaInteractiveProps) {
  const isMobile = useIsMobile()
  // Updated state type and default value
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>("14d") 
  const [processedChartData, setProcessedChartData] = React.useState<ProcessedChartData[]>([])
  const [isLoading, setIsLoading] = React.useState(true)

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
        const rawData: InflowDataPoint[] = await getInflowTimeseries(timeRange, selectedDamId)
        
        const transformed = rawData.map(point => {
          const timestamp = new Date(point.ts_utc).getTime() // Convert to timestamp
          return {
            date: point.ts_utc, // Keep original for tooltip
            timestamp: timestamp, // Add timestamp for X-axis
            observed: point.data_type === 'observed' ? Math.trunc(point.value_num) : null,
            forecast: point.data_type === 'forecast' ? Math.trunc(point.value_num) : null,
            inflow: Math.trunc(point.value_num),
            type: point.data_type
          }
        })
        setProcessedChartData(transformed)
      } catch (error) {
        console.error("Failed to fetch or process inflow data:", error)
        setProcessedChartData([]) 
      } finally {
        setIsLoading(false)
      }
    }
    fetchData()
  }, [timeRange, selectedDamId])

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>Inflows</CardTitle> {/* Title updated to cfs */}
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            {processedChartData.length > 0 ? (
              (() => {
                // Find the latest observed data point
                const latestObserved = processedChartData
                  .filter(d => d.type === 'observed')
                  .slice(-1)[0]; // Get the last observed point
                
                if (latestObserved) {
                  return `${latestObserved.inflow.toLocaleString()} cfs ${new Date(latestObserved.date).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} ${new Date(latestObserved.date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`;
                } else {
                  return "No observed data available for the selected period.";
                }
              })()
            ) : (
              "Daily inflow (cubic feet per second) for the selected period (times in UTC)."
            )}
          </span>
          <span className="@[540px]/card:hidden">
            {/* More dynamic description for mobile */}
            {timeRange === "mtd" ? "Month to Date (UTC)" : timeRange === "14d" ? "Last 14 days (UTC)" : "Last 7 days (UTC)"}
          </span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            // Updated onValueChange type
            onValueChange={(value: TimeRangeOption) => {
              if (value) setTimeRange(value)
            }}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
            {/* Updated ToggleGroupItems */}
            <ToggleGroupItem value="mtd">Month to Date</ToggleGroupItem>
            <ToggleGroupItem value="14d">Last 14 days</ToggleGroupItem>
            <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
          </ToggleGroup>
          <Select
            value={timeRange}
            // Updated onValueChange type
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
              <SelectItem value="mtd" className="rounded-lg">
                Month to Date
              </SelectItem>
              <SelectItem value="14d" className="rounded-lg">
                Last 14 days
              </SelectItem>
              <SelectItem value="7d" className="rounded-lg">
                Last 7 days
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
              <p>No inflow data available for the selected period.</p>
            </div>
          ) : (
            <LineChart data={processedChartData} margin={{ left: 30, right: 10, top: 5, bottom: 0 }}>
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
              <YAxis 
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                tickFormatter={(value) => {
                  if (typeof value === 'number') {
                    return value.toLocaleString(); 
                  }
                  return String(value);
                }}
                domain={[
                  (dataMin: number) => (Math.floor((dataMin * 0.95) / 5000) * 5000),
                  (dataMax: number) => (Math.ceil((dataMax * 1.05) / 5000) * 5000)
                ]}
              >
                <Label 
                  value="Inflow (cfs)" 
                  angle={-90} 
                  position="insideLeft" 
                  style={{ textAnchor: 'middle' }} 
                  dy={0}
                  offset={-20}
                />
              </YAxis>
              <ChartTooltip
                cursor={true} 
                content={
                  <ChartTooltipContent
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
                         return `${formattedDate} (${dataType})`;
                      }
                      return "Inflow (UTC)";
                    }}
                    formatter={(value, name, props) => {
                       const dataType = props.payload.type;
                       const typeLabel = dataType === 'forecast' ? 'Forecast' : 'Observed';
                       return [
                         `${props.payload.inflow.toLocaleString()} cfs (${typeLabel})`
                       ];
                    }}
                    indicator="dot" 
                  />
                }
              />
              <Line
                dataKey="observed"
                type="linear" 
                stroke="hsl(120, 50%, 30%)" // Darker green
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6 }}
                connectNulls={false}
              />
              <Line
                dataKey="forecast"
                type="linear" 
                stroke="hsl(340, 50%, 40%)" // Darker red
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                activeDot={{ r: 6, fill: "hsl(340, 50%, 40%)" }}
                connectNulls={false}
              />
            </LineChart>
          )}
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
