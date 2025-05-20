import { IconTrendingDown, IconTrendingUp, IconClock, IconAlertCircle, IconMinus } from "@tabler/icons-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { SectionCardData } from "@/lib/firebase"

// Define the props for the SectionCards component
interface SectionCardsProps {
  data: SectionCardData[];
}

// Helper component to render the correct trend icon
const TrendIcon = ({ trend }: { trend: SectionCardData['trend'] }) => {
  if (trend === 'up') return <IconTrendingUp className="size-4 text-green-500" />;
  if (trend === 'down') return <IconTrendingDown className="size-4 text-red-500" />;
  // Optionally, render a neutral icon if needed, or null if no icon for neutral
  return <IconMinus className="size-4 text-muted-foreground" />;
};

export function SectionCards({ data }: SectionCardsProps) {
  // Handle loading state or empty data state
  // Note: With Server Components, loading is often handled by Suspense higher up,
  // but providing a fallback for empty or error states is good practice.
  if (!data || data.length === 0) {
    return (
      <div className="col-span-1 flex items-center justify-center rounded-lg border border-dashed p-8 text-center sm:col-span-2 lg:col-span-3">
        <div className="flex flex-col items-center">
          <IconAlertCircle className="mb-2 size-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Operational data for cards is currently unavailable.</p>
          <p className="text-xs text-muted-foreground">This might be due to a temporary issue or no data being found.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:shadow-none sm:grid-cols-2 lg:grid-cols-3 lg:px-6">
      {data.map((card) => (
        <Card key={card.id} className="@container/card flex flex-col">
          <CardHeader className="pb-2">
            <CardDescription>{card.title}</CardDescription>
            <CardAction>
              <Badge variant="outline" className="flex items-center gap-1">
                <IconClock className="size-3.5" />
                <span>
                  {(() => {
                    try {
                      const dateObj = new Date(card.timestamp);
                      if (String(dateObj) === "Invalid Date") {
                        return "Invalid Time";
                      }
                      return `${dateObj.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true, timeZone: 'UTC' })} UTC`;
                    } catch (e) {
                      console.error("Error formatting card timestamp:", e);
                      return "Time N/A";
                    }
                  })()}
                </span>
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="py-0 px-6">
            <div className="text-3xl font-semibold tabular-nums @[250px]/card:text-4xl">
              {(() => {
                const valueStr = card.value;
                const num = parseFloat(valueStr);

                if (isNaN(num)) {
                  return valueStr;
                }

                let displayNum = num;
                if (isFinite(num) && num !== 0 && Math.abs(num) < 1) {
                  displayNum = num * 100;
                }

                let formattedText;
                if (isFinite(displayNum)) {
                  formattedText = displayNum.toLocaleString(undefined, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 1,
                  });
                } else {
                  formattedText = displayNum.toString();
                }

                const unitRegex = /^\s*(-?\d*\.?\d+)\s*(.*)\s*$/;
                const unitMatch = valueStr.match(unitRegex);
                const unit = (unitMatch && unitMatch[2]) ? unitMatch[2].trim() : '';

                return `${formattedText}${unit ? ' ' + unit : ''}`;
              })()}
            </div>
          </CardContent>
          <CardFooter className="flex-col items-start gap-1.5 text-sm pt-4">
            <div className="line-clamp-1 flex items-center gap-2 font-medium">
              <TrendIcon trend={card.trend} />
              <span>{card.trendDescription}</span>
            </div>
            <div className="text-muted-foreground">
              {card.footerNote}
            </div>
          </CardFooter>
        </Card>
      ))}
    </div>
  )
}
