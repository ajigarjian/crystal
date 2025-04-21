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
import { FeedbackWidget } from "@/components/FeedbackWidget";

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-neutral-50 dark:bg-neutral-900 pb-16 relative">
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
            <CardTitle className="text-2xl">The Crystal Mission</CardTitle>
            <CardDescription className="text-base">
                Ari and Cedric, April 13, 2025
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-neutral-800 dark:text-neutral-200">
            <section className="space-y-4">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Our Vision</h2>
              <p>
                We built Crystal with a simple but powerful belief: <span className="font-medium">government data belongs to everyone</span>, but too often it remains locked away in difficult-to-access systems, scattered across agencies, or buried in complex formats.
              </p>
              <p>
                We envision a world where public data is truly public; where citizens, researchers, journalists, students, businesses, and consultants - yes, even consultants - can easily find, understand, and use the wealth of information our government collects. Transparency isn't just a buzzword; it's the foundation of an informed democracy.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">The Road Ahead</h2>
              <p>
                Crystal begins with search, but our ambitions stretch further. We're ultimately building a platform that enables anyone to find, understand, and use public data. Roadmap ideas include:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>U.S. government data from more sources besides just data.gov</li>
                <li>International government data from sources like the World Bank and OECD</li>
                <li>APIs that enable developers to build applications using public data</li>
                <li>An analysis tool that takes search results and actually analyzes them for you</li>
                <li>Educational resources to improve data literacy</li>
                <li>Collaborative features for researchers and journalists</li>
                <li>Advocacy for better open data practices in government</li>
              </ul>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Join Our Mission</h2>
              <p>
                We're building Crystal for you: citizens, researchers, journalists, students, consultants, businesses, and anyone else who believes in the power of accessible public data.
              </p>
              <p>
                Your feedback shapes our product. Your use cases inspire our features. And your support fuels our mission.
              </p>
              <p className="mt-4">
                Together, we can transform how society interacts with public information.
              </p>
              <div className="mt-6 flex flex-col sm:flex-row gap-4">
                <Link href="/waitlist">
                  <Button className="bg-green-600 hover:bg-green-700 text-white w-full sm:w-auto">
                    Join the Beta Waitlist
                  </Button>
                </Link>
                <Link href="/search">
                  <Button variant="outline" className="w-full sm:w-auto">
                    Try Crystal Now
                  </Button>
                </Link>
              </div>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Connect With Us</h2>
              <p>
                We'd love to hear from you! Reach out with questions, feedback, or partnership inquiries:
              </p>
              
              <div className="space-y-2 mt-3">
                <p className="font-medium">Email us directly:</p>
                <ul className="list-disc pl-5 space-y-1">
                  <li><strong className="font-semibold">Ari:</strong> <a href="mailto:ari@askcrystal.info" className="text-green-600 dark:text-green-400 hover:underline">ari@askcrystal.info</a></li>
                  <li><strong className="font-semibold">Cedric:</strong> <a href="mailto:cedric@askcrystal.info" className="text-green-600 dark:text-green-400 hover:underline">cedric@askcrystal.info</a></li>
                </ul>
              </div>
              
              <div className="mt-4 flex items-center gap-4">
                <p className="font-medium">Follow us:</p>
                <div className="flex gap-3">
                  <a 
                    href="https://x.com/askwithcrystal" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="p-2 bg-green-100 hover:bg-green-200 dark:bg-green-900/30 dark:hover:bg-green-800/50 rounded-full transition-colors"
                    aria-label="Follow us on X"
                  >
                    <img 
                      src="/images/xlogo.png" 
                      alt="X logo" 
                      className="h-5 w-5" 
                    />
                  </a>
                  <a 
                    href="https://discord.com/invite/ngKpsdKEyD" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="p-2 bg-green-100 hover:bg-green-200 dark:bg-green-900/30 dark:hover:bg-green-800/50 rounded-full transition-colors"
                    aria-label="Join our Discord"
                  >
                    <img 
                      src="/images/discordlogo.svg" 
                      alt="Discord logo" 
                      className="h-5 w-5" 
                    />
                  </a>
                </div>
              </div>
            </section>
          </CardContent>
        </Card>
      </div>
      
      {/* Feedback Widget */}
      <FeedbackWidget />
    </div>
  );
}
