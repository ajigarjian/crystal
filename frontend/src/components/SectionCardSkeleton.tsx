import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardHeader,
  CardDescription,
  CardTitle,
  CardAction,
  CardFooter,
} from "@/components/ui/card";

export function SectionCardSkeleton() {
  return (
    <Card className="@container/card flex flex-col">
      <CardHeader className="flex-grow">
        <CardDescription>
          <Skeleton className="h-4 w-2/3" />
        </CardDescription>
        <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
          <Skeleton className="h-8 w-1/2 mt-1" />
        </CardTitle>
        <CardAction className="mt-2">
          <Skeleton className="h-6 w-24" /> 
        </CardAction>
      </CardHeader>
      <CardFooter className="flex-col items-start gap-1.5 text-sm">
        <div className="line-clamp-1 flex items-center gap-2 font-medium w-full">
          <Skeleton className="h-4 w-4 rounded-full" /> 
          <Skeleton className="h-4 w-3/4" />
        </div>
        <div className="text-muted-foreground w-full mt-1">
          <Skeleton className="h-4 w-full" />
        </div>
      </CardFooter>
    </Card>
  );
} 