"use client";

import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { 
  Card, 
  CardContent, 
  CardDescription, 
  CardHeader, 
  CardTitle 
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export default function ChangelogPage() {
  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-16">
      {/* Navigation */}
      <div className="container mx-auto px-4 py-6">
        <div className="flex items-center">
          <Link href="/">
            <Button 
              variant="ghost" 
              className="p-2 mr-2 group"
              aria-label="Back to home"
            >
              <ArrowLeft 
                className="h-5 w-5 transition-transform duration-200 group-hover:translate-x-[-2px]" 
              />
            </Button>
          </Link>
        </div>
      </div>

      {/* Content */}
      <div className="container mx-auto px-4 py-6 max-w-4xl">
        <Card className="bg-neutral-100/50 dark:bg-neutral-800/30 border-neutral-200 dark:border-neutral-700">
          <CardHeader>
            <CardTitle className="text-4xl">Changelog</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 text-neutral-800 dark:text-neutral-200">

          <section className="space-y-3">
              <div className="flex items-baseline gap-3">
                <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Version 1.1.1</h2>
                <span className="text-sm text-neutral-600 dark:text-neutral-400">April 18, 2025</span>
              </div>
              <div className="pl-2 border-l-2 border-green-500 dark:border-green-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">New Features</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Added ability to stop long searches</li>
                  <li>Added query suggestions & guidance</li>
                </ul>
              </div>
              <div className="pl-2 border-l-2 border-blue-500 dark:border-blue-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">Improvements</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Reduced average search time by ~18s via new LLM model</li>
                  <li>Improved search box design for easier use</li>
                  <li>Increased max search time to avoid timeouts</li>
                </ul>
              </div>
              <div className="pl-2 border-l-2 border-red-500 dark:border-red-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">Bug Fixes</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Fixed scrollbar glitching issues</li>
                </ul>
              </div>
            </section>

            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <div className="flex items-baseline gap-3">
                <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Version 1.1.0</h2>
                <span className="text-sm text-neutral-600 dark:text-neutral-400">April 13, 2025</span>
              </div>
              <div className="pl-2 border-l-2 border-green-500 dark:border-green-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">New Features</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Added download buttons for search</li>
                </ul>
              </div>
              <div className="pl-2 border-l-2 border-blue-500 dark:border-blue-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">Improvements</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Updated frontend UI for search</li>
                  <li>Updated UI for better mobile responsiveness</li>
                  <li>Optimized search speed</li>
                  <li>Removed analyze while it is refined</li>
                </ul>
              </div>
              <div className="pl-2 border-l-2 border-red-500 dark:border-red-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">Bug Fixes</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Fixed mobile view</li>
                  <li>Resolved dark mode inconsistencies</li>
                </ul>
              </div>
            </section>

            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />

            {/* Initial Release Example */}
            <section className="space-y-3">
              <div className="flex items-baseline gap-3">
                <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Version 1.0.0</h2>
                <span className="text-sm text-neutral-600 dark:text-neutral-400">March 27, 2025</span>
              </div>
              <div className="pl-2 border-l-2 border-green-500 dark:border-green-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white mb-2">Initial Release</h3>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Launched basic search functionality</li>
                  <li>Launched basic analysis</li>
                </ul>
              </div>
            </section>

          </CardContent>
        </Card>
      </div>
    </div>
  );
}
