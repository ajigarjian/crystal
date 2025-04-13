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

export default function AboutPage() {
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
            <CardTitle className="text-2xl">The Crystal Manifesto</CardTitle>
            <CardDescription className="text-base">
              By Ari and Cedric, Co-Founders
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-neutral-800 dark:text-neutral-200">
            <section className="space-y-4">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Our Vision</h2>
              <p>
                We built Crystal with a simple but powerful belief: <span className="font-medium">government data belongs to everyone</span>, but too often it remains locked away in difficult-to-access systems, scattered across agencies, or buried in complex formats.
              </p>
              <p>
                We envision a world where public data is truly public—where citizens, researchers, journalists, students, and businesses can easily find, understand, and use the wealth of information our government collects. Transparency isn't just a buzzword; it's the foundation of an informed democracy.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-4">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Why We Started Crystal</h2>
              
              <div className="space-y-3 pl-2 border-l-2 border-green-500 dark:border-green-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white">The Data Divide</h3>
                <p>
                  Today, those with technical skills and institutional knowledge can navigate the complex ecosystem of government data. Everyone else is left behind. This creates a fundamental inequality in who can access public information—information that was collected using taxpayer dollars and that belongs to all of us.
                </p>
                <p>
                  We've spent countless hours searching for datasets across fragmented government portals, dealing with inconsistent interfaces, and translating bureaucratic terminology. Each time we thought: there must be a better way.
                </p>
              </div>

              <div className="space-y-3 pl-2 border-l-2 border-blue-500 dark:border-blue-500/70 mt-4">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white">Bridging the Gap</h3>
                <p>
                  Crystal is our solution—a unified search layer across government data sources. We're building the tool we wished existed, one that breaks down the technical and knowledge barriers that prevent people from accessing public information.
                </p>
                <p>
                  By making public data truly accessible, we aim to empower citizens, drive evidence-based policy decisions, enable innovative research, and create a more transparent relationship between government and the public it serves.
                </p>
              </div>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Our Principles</h2>
              <ul className="list-disc pl-5 space-y-3">
                <li>
                  <span className="font-medium">Universal Access:</span> We believe information asymmetry creates inequality. Crystal is designed for everyone, not just technical users or those with specialized knowledge.
                </li>
                <li>
                  <span className="font-medium">Radical Clarity:</span> Government data should be easy to find and understand. We're committed to making the complex simple through thoughtful design and plain language.
                </li>
                <li>
                  <span className="font-medium">Open by Default:</span> While building a sustainable business, we're committed to transparency in how we operate and to contributing to the open data ecosystem.
                </li>
                <li>
                  <span className="font-medium">Empowerment, Not Replacement:</span> We amplify the work of agencies publishing open data, connecting more people to valuable public information sources.
                </li>
                <li>
                  <span className="font-medium">Data Independence:</span> We provide access without altering the underlying data, ensuring faithfulness to original information while making it more discoverable.
                </li>
              </ul>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">The Road Ahead</h2>
              <p>
                Crystal begins with search, but our ambitions stretch further. We're building a complete ecosystem for public data discovery, accessibility, and analysis. Our roadmap includes:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Advanced data visualization tools that anyone can use</li>
                <li>APIs that enable developers to build applications using public data</li>
                <li>Educational resources to improve data literacy</li>
                <li>Collaborative features for researchers and journalists</li>
                <li>Advocacy for better open data practices in government</li>
              </ul>
              <p className="mt-4">
                This is just the beginning. Crystal represents our commitment to a more open, informed, and data-driven society. We invite you to join us on this journey.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Join Our Mission</h2>
              <p>
                We're building Crystal for you—citizens, researchers, journalists, students, businesses, and anyone else who believes in the power of accessible public data.
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
                <Link href="/">
                  <Button variant="outline" className="w-full sm:w-auto">
                    Try Crystal Now
                  </Button>
                </Link>
              </div>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">About the Founders</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
                <div className="space-y-2">
                  <h3 className="text-lg font-medium text-neutral-900 dark:text-white">Ari</h3>
                  <p className="text-sm">
                    [Short bio placeholder - This is where Ari can add a personal bio, background, and motivation for starting Crystal.]
                  </p>
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-medium text-neutral-900 dark:text-white">Cedric</h3>
                  <p className="text-sm">
                    [Short bio placeholder - This is where Cedric can add a personal bio, background, and motivation for starting Crystal.]
                  </p>
                </div>
              </div>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Connect With Us</h2>
              <p>
                We'd love to hear from you! Reach out with questions, feedback, or partnership inquiries:
              </p>
              <p className="mt-2">
                <strong className="font-bold">Email:</strong> <span className="font-medium text-green-600 dark:text-green-400">hello@crystal-data.com</span>
              </p>
            </section>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
