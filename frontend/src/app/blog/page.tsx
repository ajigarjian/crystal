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

export default function BlogPage() {
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
        <h1 className="text-4xl font-bold text-neutral-900 dark:text-white mb-8">Blog</h1>
        
        {/* Blog Posts */}
        <div className="space-y-12">
          {/* Sample Blog Post 1 */}
          <Card className="bg-neutral-100/50 dark:bg-neutral-800/30 border-neutral-200 dark:border-neutral-700">
            <CardHeader>
              <CardTitle className="text-3xl">Democratizing Access to Public Data</CardTitle>
              <CardDescription className="text-base flex items-center gap-2">
                <span className="font-medium">Cedric Fitzgerald</span>
                <span className="text-neutral-500">•</span>
                <span>April 15, 2025</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="prose dark:prose-invert max-w-none">
              <p>
                When we started Crystal, we had a simple but ambitious goal: make public data truly accessible to everyone. 
                Today, I want to share our journey and vision for the future of public data accessibility.
              </p>
              
              <h2>The Challenge</h2>
              <p>
                Despite living in a digital age, much of our government's data remains trapped in outdated systems, 
                scattered across countless agencies, or hidden behind complex interfaces. This isn't just an 
                inconvenience—it's a barrier to transparency, innovation, and informed decision-making.
              </p>
              
              <h2>Our Approach</h2>
              <p>
                We're tackling this challenge through three key principles:
              </p>
              <ul>
                <li>
                  <strong>Simplicity First:</strong> Advanced features shouldn't come at the cost of basic usability. 
                  Our interface is designed to be intuitive for everyone, from students to seasoned researchers.
                </li>
                <li>
                  <strong>Intelligent Search:</strong> We're leveraging cutting-edge AI to understand not just keywords, 
                  but the context and intent behind your searches.
                </li>
                <li>
                  <strong>Data Intelligence:</strong> Beyond just finding data, we're building tools to help you 
                  understand and analyze it effectively.
                </li>
              </ul>

              <h2>Looking Forward</h2>
              <p>
                This is just the beginning. We're working on features that will transform how people interact with 
                public data, including:
              </p>
              <ul>
                <li>Real-time data updates and notifications</li>
                <li>Advanced visualization tools</li>
                <li>Collaborative research capabilities</li>
                <li>API access for developers</li>
              </ul>

              <p>
                We believe that when public data is truly accessible, it becomes a powerful tool for positive change. 
                Whether you're a journalist investigating a story, a researcher studying trends, or a citizen interested 
                in your local government, Crystal is here to help you find the information you need.
              </p>

              <h2>Join Us</h2>
              <p>
                We're excited about the road ahead and invite you to be part of this journey. Try out Crystal, 
                share your feedback, and help us build a more transparent future.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
