import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Cog } from "lucide-react";

interface ToolCallDisplayProps {
  name: string;
  args: Record<string, unknown>;
}

export const ToolCallDisplay = ({ name, args }: ToolCallDisplayProps) => {
  return (
    <Card className="bg-slate-100 dark:bg-slate-800/50 my-2">
      <CardHeader className="flex flex-row items-center gap-2 p-3">
        <Cog className="w-4 h-4 text-slate-500" />
        <CardTitle className="text-sm font-medium text-slate-700 dark:text-slate-300">
          Running tool: <span className="font-mono text-blue-600 dark:text-blue-400">{name}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <pre className="p-3 bg-slate-200 dark:bg-slate-900 rounded-md text-xs text-slate-800 dark:text-slate-200 overflow-x-auto">
          <code>{JSON.stringify(args, null, 2)}</code>
        </pre>
      </CardContent>
    </Card>
  );
}; 