import * as React from "react"
import { CheckCircle2 } from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarRail,
} from "@/components/ui/sidebar"

interface StepProps {
  title: string;
  description: string;
  completed: boolean;
  isLast?: boolean;
}

const Step = ({ title, description, completed, isLast = false }: StepProps) => {
  return (
    <div className="relative">
      <div className="flex items-center">
        <div className={`z-10 flex h-6 w-6 items-center justify-center rounded-full ${
          completed 
            ? "bg-teal-600 text-white"
            : "border border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-800"
        }`}>
          {completed && <CheckCircle2 className="h-4 w-4" />}
        </div>
        <div className="ml-3">
          <h3 className="text-xs font-medium">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      {!isLast && (
        <div className="absolute left-3 top-6 -ml-px h-full w-0.5 -translate-x-1/2 bg-gray-300 dark:bg-gray-600"></div>
      )}
    </div>
  );
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  // All steps are initially uncompleted
  const steps = [
    {
      title: "Gather datasets",
      description: "Searching for relevant datasets",
      completed: false
    },
    {
      title: "Screen datasets",
      description: "Pending dataset screening",
      completed: false
    },
    {
      title: "Extract data",
      description: "Waiting for data extraction",
      completed: false
    },
    {
      title: "Generate report",
      description: "Report pending",
      completed: false
    }
  ];

  return (
    <Sidebar {...props}>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Report Status</SidebarGroupLabel>
          <SidebarGroupContent>
            <div className="px-3 py-4 space-y-6">
              {steps.map((step, index) => (
                <Step 
                  key={index}
                  title={step.title}
                  description={step.description}
                  completed={step.completed}
                  isLast={index === steps.length - 1}
                />
              ))}
            </div>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}