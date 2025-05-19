"use client"

import * as React from "react"
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Label } from "recharts"
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
import { InflowDataPoint, getInflowTimeseries } from "@/lib/firebase" 

// Define the new time range options type
type TimeRangeOption = "mtd" | "14d" | "7d";

interface ProcessedChartData {
  date: string // Will store UTC date string, e.g., "YYYY-MM-DD HH:mm"
  inflow: number // Value in cfs, truncated
}

// Temporarily removed PACIFIC_TIMEZONE constant
// const PACIFIC_TIMEZONE = "America/Los_Angeles"

const chartConfig = {
  inflow: {
    label: "Inflow (cfs) - UTC", // Updated label to cfs
    color: "hsl(var(--chart-1))", 
  },
} satisfies ChartConfig

// Helper to format date string (basic version for UTC)
// Updated to handle new TimeRangeOption types
const formatUtcDate = (isoString: string, range: TimeRangeOption): string => {
  const dateObj = new Date(isoString);
  if (String(dateObj) === "Invalid Date") {
    return "Invalid Date (UTC)"; 
  }
  // Show only the day number (UTC)
  return dateObj.getUTCDate().toString();
};

const formatUtcDateForDisplay = (isoString: string): string => {
  const dateObj = new Date(isoString);
  // Format as YYYY-MM-DD for data key and internal use
  return `${dateObj.getUTCFullYear()}-${(dateObj.getUTCMonth() + 1).toString().padStart(2, '0')}-${dateObj.getUTCDate().toString().padStart(2, '0')}`;
};


export function ChartAreaInteractive() {
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
        const rawData: InflowDataPoint[] = await getInflowTimeseries(timeRange)
        
        const transformed = rawData.map(point => {
          // Using UTC date directly
          return {
            // Store full ISO string for potential time display on X-axis for 'today' view
            date: point.ts_utc, // Keep as ISO string for now, format in XAxis tickFormatter
            inflow: Math.trunc(point.value_num), // Value is now cfs, just truncate
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
  }, [timeRange]) 

  return (
    <Card className="@container/card shadow-none">
      <CardHeader>
        <CardTitle>Inflow History</CardTitle> {/* Title updated to cfs */}
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            {processedChartData.length > 0 ? (
              `Latest Observation: ${processedChartData[processedChartData.length - 1].inflow.toLocaleString()} cfs ${new Date(processedChartData[processedChartData.length - 1].date).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} ${new Date(processedChartData[processedChartData.length - 1].date).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`
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
                dataKey="date" // This will be the full ISO string
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={16} // Set to 32 as all ranges are multi-day
                tickFormatter={(value) => formatUtcDate(value, timeRange) // Use new UTC formatter
                }
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
                // Dynamically set the domain based on data, with padding
                domain={[
                  (dataMin: number) => (Math.floor((dataMin * 0.95) / 5000) * 5000), // Pad 5% below, rounded to nearest 5000
                  (dataMax: number) => (Math.ceil((dataMax * 1.05) / 5000) * 5000)  // Pad 5% above, rounded to nearest 5000
                ]}
                tickCount={6} // Reduced tickCount to aim for one less grid line
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
                      // console.log("[Chart] Tooltip labelFormatter - Value:", value); // REMOVED
                      if (payload && payload.length > 0 && payload[0].payload.date) {
                         const dateStringFromPayload = payload[0].payload.date;
                         // console.log("[Chart] Tooltip labelFormatter - Date string from payload:", dateStringFromPayload); // REMOVED
                         const dateObj = new Date(dateStringFromPayload);
                         // console.log("[Chart] Tooltip labelFormatter - Parsed dateObj:", dateObj); // REMOVED
                         if (String(dateObj) === "Invalid Date") {
                            return "Invalid Date UTC"; 
                         }
                         return dateObj.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + " UTC";
                      }
                      // console.warn("[Chart] Tooltip labelFormatter - Payload or date missing"); // REMOVED
                      return "Inflow (UTC)";
                    }}
                    formatter={(value, name, props) => {
                       return [
                         `${props.payload.inflow.toLocaleString()} cfs` // Add toLocaleString for tooltip value too
                       ];
                    }}
                    indicator="dot" 
                  />
                }
              />
              <Line
                dataKey="inflow"
                type="monotone" 
                stroke="lime"
                strokeWidth={2}
                dot={{
                  r: 4, 
                }}
                activeDot={{
                  r: 6, 
                }}
              />
            </LineChart>
          )}
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
