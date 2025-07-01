"use client"

import * as React from "react"
import { TrendingUp, Zap, Activity } from "lucide-react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis, ResponsiveContainer, Label, ComposedChart, Line } from "recharts"
import { IconTable, IconChartLine } from "@tabler/icons-react"

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { getBPAGenerationTimeseries, BPAGenerationTimeseriesPoint, TimeRangeOption } from "@/lib/firebase"

const chartConfig = {
  Hydro: {
    label: "Hydro",
    color: "hsl(200, 80%, 50%)", // Blue for hydro
  },
  VER: {
    label: "Wind/Solar",
    color: "hsl(120, 60%, 50%)", // Green for renewables
  },
  "Fossil/Biomass": {
    label: "Fossil/Biomass", 
    color: "hsl(0, 0%, 20%)", // Dark gray to match chart
  },
  Nuclear: {
    label: "Nuclear",
    color: "hsl(280, 60%, 50%)", // Purple for nuclear
  },
  Load: {
    label: "BA Load",
    color: "hsl(0, 80%, 50%)", // Red for load
  },
} satisfies ChartConfig

export function ChartBPAGenerationMix() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>("1d") 
  const [data, setData] = React.useState<BPAGenerationTimeseriesPoint[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isChartView, setIsChartView] = React.useState(true)

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("1d") // Default to 1d for mobile
    } else {
      setTimeRange("1d") // Default to 1d for desktop (5-min intervals)
    }
  }, [isMobile])

  React.useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)
        const result = await getBPAGenerationTimeseries(timeRange)
        setData(result)
      } catch (err) {
        console.error('Error fetching BPA generation timeseries:', err)
        setError(err instanceof Error ? err.message : 'An error occurred')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    
    // Set up auto-refresh every 5 minutes for real-time data
    const interval = setInterval(fetchData, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [timeRange])

  // Prepare chart data - aggregate by time period for performance
  const chartData = React.useMemo(() => {
    if (data.length === 0) return []
    
    const uniqueData = new Map()
    
    // First, deduplicate by timestamp
    data.forEach(point => {
      const timestamp = new Date(point.timestamp).getTime()
      const key = timestamp.toString()
      
      if (!uniqueData.has(key) || uniqueData.get(key).timestamp < point.timestamp) {
        uniqueData.set(key, point)
      }
    })
    
    const sortedData = Array.from(uniqueData.values()).sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
    
    // Determine aggregation interval based on time range
    let intervalMs: number
    switch (timeRange) {
      case "1d":
        intervalMs = 5 * 60 * 1000 // 5 minutes - no aggregation needed
        break
      case "7d":
        intervalMs = 60 * 60 * 1000 // 1 hour
        break
      case "14d":
        intervalMs = 4 * 60 * 60 * 1000 // 4 hours
        break
      case "mtd":
        intervalMs = 24 * 60 * 60 * 1000 // 1 day
        break
      default:
        intervalMs = 60 * 60 * 1000
    }
    
    // For 1d, return data as-is (already 5-min intervals)
    if (timeRange === "1d") {
      return sortedData.map(point => {
        const timestamp = new Date(point.timestamp).getTime()
        return {
          timestamp,
          date: point.timestamp,
          Hydro: point.Hydro,
          VER: point.VER,
          "Fossil/Biomass": point['Fossil/Biomass'],
          Nuclear: point.Nuclear,
          Load: point.Load,
          Total_Generation: point.Total_Generation,
          Net_Interchange: point.Net_Interchange
        }
      })
    }
    
    // For longer periods, aggregate data
    const aggregatedData = new Map()
    
    sortedData.forEach(point => {
      const timestamp = new Date(point.timestamp).getTime()
      
      // Round timestamp to the nearest interval
      const intervalStart = Math.floor(timestamp / intervalMs) * intervalMs
      const key = intervalStart.toString()
      
      if (!aggregatedData.has(key)) {
        aggregatedData.set(key, {
          timestamp: intervalStart,
          date: new Date(intervalStart).toISOString(),
          count: 0,
          Hydro: 0,
          VER: 0,
          "Fossil/Biomass": 0,
          Nuclear: 0,
          Load: 0,
          Total_Generation: 0,
          Net_Interchange: 0
        })
      }
      
      const bucket = aggregatedData.get(key)
      bucket.count += 1
      bucket.Hydro += point.Hydro
      bucket.VER += point.VER
      bucket["Fossil/Biomass"] += point['Fossil/Biomass']
      bucket.Nuclear += point.Nuclear
      bucket.Load += point.Load
      bucket.Total_Generation += point.Total_Generation
      bucket.Net_Interchange += point.Net_Interchange
    })
    
    // Calculate averages and return sorted data
    return Array.from(aggregatedData.values())
      .map(bucket => ({
        timestamp: bucket.timestamp,
        date: bucket.date,
        Hydro: Math.round(bucket.Hydro / bucket.count),
        VER: Math.round(bucket.VER / bucket.count),
        "Fossil/Biomass": Math.round(bucket["Fossil/Biomass"] / bucket.count),
        Nuclear: Math.round(bucket.Nuclear / bucket.count),
        Load: Math.round(bucket.Load / bucket.count),
        Total_Generation: Math.round(bucket.Total_Generation / bucket.count),
        Net_Interchange: Math.round(bucket.Net_Interchange / bucket.count)
      }))
      .sort((a, b) => a.timestamp - b.timestamp)
  }, [data, timeRange])

  // Calculate tick configuration for X-axis - adjust based on time range
  const getXAxisTicks = React.useMemo(() => {
    if (chartData.length === 0) return []
    
    const ticks = new Set<number>()
    const startTime = chartData[0].timestamp
    const endTime = chartData[chartData.length - 1].timestamp
    
    switch (timeRange) {
      case "1d":
        // Show every 4 hours for 24h view
        for (let time = startTime; time <= endTime; time += 4 * 60 * 60 * 1000) {
          ticks.add(time)
        }
        break
      case "7d":
        // Show every 12 hours for 7d view
        for (let time = startTime; time <= endTime; time += 12 * 60 * 60 * 1000) {
          ticks.add(time)
        }
        break
      case "14d":
        // Show every day for 14d view
        chartData.forEach(point => {
          const date = new Date(point.timestamp)
          const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
          ticks.add(dayStart)
        })
        break
      case "mtd":
        // Show every few days for monthly view
        const dayInterval = Math.max(1, Math.floor((endTime - startTime) / (1000 * 60 * 60 * 24 * 7))) // Roughly 7 ticks
        chartData.forEach((point, index) => {
          if (index % dayInterval === 0) {
            const date = new Date(point.timestamp)
            const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
            ticks.add(dayStart)
          }
        })
        break
    }
    
    return Array.from(ticks).sort((a, b) => a - b)
  }, [chartData, timeRange])

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleString('en-US', {
      timeZone: 'UTC',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      timeZoneName: 'short'
    })
  }

  const formatMW = (value: number) => `${value.toLocaleString()} MW`

  // Current data for summary cards
  const currentData = data.length > 0 ? data[data.length - 1] : null

  if (loading) {
    return (
      <Card className="@container/card shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            BPA Generation Mix
          </CardTitle>
          <CardDescription>Loading generation data...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center">
            <div className="animate-pulse">Loading...</div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error || !currentData) {
    return (
      <Card className="@container/card shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            BPA Generation Mix
          </CardTitle>
          <CardDescription>Error loading generation data</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">{error || "Failed to fetch generation data"}</p>
              <p className="text-xs mt-1">Please try refreshing the page</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="@container/card shadow-none h-full flex flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          BPA Generation Mix
        </CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            {currentData ? `${currentData.Load.toLocaleString()} MW ${new Date(currentData.timestamp).toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: 'numeric' })} ${new Date(currentData.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC` : 'Loading...'}
          </span>
          <span className="@[540px]/card:hidden">
            {timeRange === "1d" ? "Last 24 hours (5-min intervals)" : 
             timeRange === "7d" ? "Last 7 days (hourly averages)" : 
             timeRange === "14d" ? "Last 14 days (4-hour averages)" : "Month to Date (daily averages)"}
          </span>
        </CardDescription>
        <CardAction className="flex gap-2 flex-wrap items-center">
          {/* View Toggle Buttons */}
          <div className="flex rounded-md border flex-shrink-0">
            <Button
              variant={isChartView ? "default" : "ghost"}
              size="sm"
              onClick={() => setIsChartView(true)}
              className="rounded-r-none border-r h-8"
            >
              <IconChartLine className="h-4 w-4" />
            </Button>
            <Button
              variant={!isChartView ? "default" : "ghost"}
              size="sm"
              onClick={() => setIsChartView(false)}
              className="rounded-l-none h-8"
            >
              <IconTable className="h-4 w-4" />
            </Button>
        </div>

          <ToggleGroup
            type="single"
            value={timeRange}
            onValueChange={(value: TimeRangeOption) => {
              if (value) setTimeRange(value)
            }}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
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
      <CardContent className="px-2 pt-2 sm:px-6 sm:pt-2 flex-1 flex flex-col">
        {isChartView ? (
          // Chart View
          <ChartContainer
            config={chartConfig}
            className="aspect-auto h-full w-full"
          >
            <ComposedChart
              data={chartData}
              margin={{ left: 12, right: 4, top: 4, bottom: 0 }}
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="timestamp"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                tickLine={false}
                axisLine={false}
                tickMargin={4}
                ticks={getXAxisTicks}
                tickFormatter={(timestamp) => {
                  const date = new Date(timestamp)
                  if (timeRange === "1d") {
                    return date.toLocaleTimeString('en-US', { 
                      hour: 'numeric',
                      timeZone: 'UTC'
                    })
                  } else {
                    return date.toLocaleDateString('en-US', { 
                      month: 'short',
                      day: 'numeric',
                      timeZone: 'UTC'
                    })
                  }
                }}
              />
              <YAxis 
                tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
                tickLine={false}
                axisLine={false}
                tickMargin={4}
                width={35}
              >
                <Label 
                  value="MW" 
                  angle={-90} 
                  position="insideLeft" 
                  style={{ textAnchor: 'middle' }} 
                  dy={0}
                  offset={-8}
                />
              </YAxis>
              <ChartTooltip 
                content={
                  <ChartTooltipContent
                    labelFormatter={(value, payload) => {
                      if (payload && payload.length > 0) {
                        const dataPoint = payload[0].payload
                        return formatTimestamp(dataPoint.date)
                      }
                      return "Generation Mix"
                    }}
                    formatter={(value, name, entry) => {
                      const formattedValue = `${Number(value).toLocaleString()} MW`
                      
                      // Get color from entry first (actual rendered color), then fallback to config
                      let color = entry?.color
                      if (!color) {
                        const configEntry = chartConfig[name as keyof typeof chartConfig]
                        color = configEntry?.color || '#666'
                      }
                      
                      return [
                        <div key={name} className="flex items-center gap-2">
                          <div 
                            className="w-3 h-3 rounded-sm flex-shrink-0"
                            style={{ backgroundColor: color }}
                          />
                          <span>{formattedValue}</span>
                        </div>, 
                        name
                      ]
                    }}
                    indicator="line"
                    footer={(payload) => {
                      if (payload && payload.length > 0) {
                        const dataPoint = payload[0].payload
                        const totalGeneration = dataPoint.Total_Generation
                        const load = dataPoint.Load
                        const netInterchange = dataPoint.Net_Interchange
                        
                        return (
                          <div className="border-t pt-2 mt-2 space-y-1 text-xs">
                            <div className="flex justify-between">
                              <span>Total Generation:</span>
                              <span className="font-mono">{totalGeneration.toLocaleString()} MW</span>
                            </div>
                            <div className="flex justify-between">
                              <span>BA Load:</span>
                              <span className="font-mono">{load.toLocaleString()} MW</span>
                            </div>
                            <div className="flex justify-between font-medium">
                              <span>Net Interchange:</span>
                              <span className={`font-mono ${netInterchange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                {netInterchange >= 0 ? '+' : ''}{netInterchange.toLocaleString()} MW
                              </span>
                            </div>
                            <div className="text-xs text-muted-foreground pt-1">
                              {netInterchange >= 0 
                                ? `Exporting ${Math.abs(netInterchange).toLocaleString()} MW`
                                : `Importing ${Math.abs(netInterchange).toLocaleString()} MW`
                              }
                            </div>
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                }
              />
              {/* Stacked generation sources */}
              <Bar
                dataKey="Hydro"
                stackId="generation"
                fill="var(--color-Hydro)"
                  radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="VER"
                stackId="generation"
                fill="var(--color-VER)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="Fossil/Biomass"
                stackId="generation"
                fill="var(--color-Fossil/Biomass)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="Nuclear"
                stackId="generation"
                fill="var(--color-Nuclear)"
                radius={[4, 4, 0, 0]}
              />
                
                {/* Load line */}
                <Line
                  type="monotone"
                  dataKey="Load"
                  stroke="var(--color-Load)"
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                />
            </ComposedChart>
          </ChartContainer>
        ) : (
          // Table View
          <div className="h-full w-full">
            <div className="h-full overflow-hidden rounded-md border">
              <div 
                className="h-full overflow-auto [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb:hover]:bg-muted-foreground/50"
                style={{
                  scrollbarWidth: 'thin',
                  scrollbarColor: 'hsl(var(--border)) transparent',
                }}
              >
                <table className="w-full caption-bottom text-sm">
                  <thead className="sticky top-0 bg-background z-10 shadow-sm border-b">
                    <tr className="border-b">
                      <th className="h-10 px-2 text-left align-middle font-medium whitespace-nowrap w-[140px] font-semibold bg-background">
                        Time (UTC)
                      </th>
                      <th className="h-10 px-2 text-right align-middle font-medium whitespace-nowrap min-w-[80px] font-semibold bg-background">
                        Hydro
                      </th>
                      <th className="h-10 px-2 text-right align-middle font-medium whitespace-nowrap min-w-[80px] font-semibold bg-background">
                        Wind/Solar
                      </th>
                      <th className="h-10 px-2 text-right align-middle font-medium whitespace-nowrap min-w-[80px] font-semibold bg-background">
                        Fossil/Bio
                      </th>
                      <th className="h-10 px-2 text-right align-middle font-medium whitespace-nowrap min-w-[80px] font-semibold bg-background">
                        Nuclear
                      </th>
                      <th className="h-10 px-2 text-right align-middle font-medium whitespace-nowrap min-w-[80px] font-semibold bg-background">
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.slice().reverse().map((row, index) => (
                      <tr key={index} className="border-b transition-colors hover:bg-muted/50">
                        <td className="p-2 align-middle whitespace-nowrap font-medium">
                          <div className="flex flex-col">
                            <span className="text-sm">
                              {new Date(row.timestamp).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                timeZone: 'UTC'
                              })}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {new Date(row.timestamp).toLocaleTimeString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit',
                                timeZone: 'UTC',
                                hour12: false
                              })}
                            </span>
                          </div>
                        </td>
                        <td className="p-2 align-middle whitespace-nowrap text-right">
                          <span className="font-mono font-medium">
                            {Math.trunc(row.Hydro).toLocaleString()}
                          </span>
                        </td>
                        <td className="p-2 align-middle whitespace-nowrap text-right">
                          <span className="font-mono font-medium">
                            {Math.trunc(row.VER).toLocaleString()}
                          </span>
                        </td>
                        <td className="p-2 align-middle whitespace-nowrap text-right">
                          <span className="font-mono font-medium">
                            {Math.trunc(row['Fossil/Biomass']).toLocaleString()}
                          </span>
                        </td>
                        <td className="p-2 align-middle whitespace-nowrap text-right">
                          <span className="font-mono font-medium">
                            {Math.trunc(row.Nuclear).toLocaleString()}
                          </span>
                        </td>
                        <td className="p-2 align-middle whitespace-nowrap text-right">
                          <span className="font-mono font-medium">
                            {Math.trunc(row.Total_Generation).toLocaleString()}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
} 