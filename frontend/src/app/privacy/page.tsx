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

export default function PrivacyPage() {
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
            <CardTitle className="text-2xl">Privacy Policy</CardTitle>
            <CardDescription className="text-base">
              Last Updated: March 25, 2025
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-neutral-800 dark:text-neutral-200">
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Introduction</h2>
              <p>
                <span className="font-medium">Crystal</span> ("we", "our", or "us") is committed to protecting your privacy. This Privacy Policy explains how we collect, use, disclose, and safeguard your information when you use our data querying service for public records.
              </p>
              <p>
                We value transparency and want you to understand how we handle your data. Please read this policy carefully. By using Crystal, you consent to our Privacy Policy.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-4">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Information We Collect</h2>
              
              <div className="space-y-3 pl-2 border-l-2 border-green-500 dark:border-green-500/70">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white">Information You Provide</h3>
                <p>We may collect information that you voluntarily provide when using our service, including:</p>
                <ul className="list-disc pl-5 space-y-1">
                  <li>Search queries you submit</li>
                  <li>Account information if you create an account (email address, name)</li>
                  <li>Feedback, support requests, or correspondence</li>
                  <li>Information provided when joining our beta waitlist</li>
                </ul>
              </div>

              <div className="space-y-3 pl-2 border-l-2 border-blue-500 dark:border-blue-500/70 mt-4">
                <h3 className="text-lg font-medium text-neutral-900 dark:text-white">Information Collected Automatically</h3>
                <p>When you access Crystal, our servers may automatically record information including:</p>
                <ul className="list-disc pl-5 space-y-1">
                  <li>IP address</li>
                  <li>Browser type and version</li>
                  <li>Operating system</li>
                  <li>Referring/exit pages</li>
                  <li>Date/time of visits</li>
                  <li>Session activity including search patterns</li>
                  <li>Performance data and error logs</li>
                </ul>
              </div>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">How We Use Your Information</h2>
              <p>We use the information we collect for various purposes, including to:</p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Process and respond to your queries about public data</li>
                <li>Provide, maintain, and improve our services</li>
                <li>Develop new features and functionality</li>
                <li>Monitor and analyze usage patterns and trends</li>
                <li>Detect, prevent, and address technical issues</li>
                <li>Communicate with you about updates, security alerts, and support</li>
                <li>Deliver relevant search results based on your query history (with your consent)</li>
              </ul>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Public Data Processing</h2>
              <p>
                Crystal is designed to query and analyze <span className="font-medium">public records and data</span>. We do not own this data but provide a service to help you access and understand it. When you submit a query:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>We process your request through our secure systems</li>
                <li>We may store your queries to improve our service and provide history features</li>
                <li>We may use aggregated query data to enhance our search algorithms</li>
                <li>We never modify or alter the underlying public data sources</li>
              </ul>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Data Security</h2>
              <p>
                We implement a variety of security measures to maintain the safety of your personal information, including:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Encryption of transmitted data</li>
                <li>Regular security assessments</li>
                <li>Access controls for our systems and databases</li>
                <li>Continuous monitoring for suspicious activities</li>
              </ul>
              <p className="italic text-neutral-700 dark:text-neutral-400 text-sm mt-2">
                However, no method of transmission over the Internet or electronic storage is 100% secure. While we strive to use commercially acceptable means to protect your personal information, we cannot guarantee its absolute security.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Third-Party Services</h2>
              <p>
                We may use third-party services to support our application, such as:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Cloud infrastructure providers</li>
                <li>Analytics services</li>
                <li>Error tracking tools</li>
              </ul>
              <p>
                These third parties may have access to your information only to perform specific tasks on our behalf and are obligated not to disclose or use it for any other purpose.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Your Data Rights</h2>
              <p>
                Depending on your location, you may have certain rights regarding your personal information, including:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Right to access information we have about you</li>
                <li>Right to rectify or update your personal information</li>
                <li>Right to erase your personal data (subject to certain exceptions)</li>
                <li>Right to restrict or object to processing</li>
                <li>Right to data portability</li>
                <li>Right to withdraw consent</li>
              </ul>
              <p className="mt-2">
                To exercise any of these rights, please contact us at <span className="font-medium text-green-600 dark:text-green-400">privacy@crystal-data.com</span>.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Cookies and Similar Technologies</h2>
              <p>
                We use cookies and similar tracking technologies to track activity on our service and hold certain information. Cookies are files with a small amount of data that may include an anonymous unique identifier.
              </p>
              <p>
                You can instruct your browser to refuse all cookies or to indicate when a cookie is being sent. However, if you do not accept cookies, you may not be able to use some portions of our service.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Children's Privacy</h2>
              <p>
                Our service is not intended for use by children under the age of 13. We do not knowingly collect personally identifiable information from children under 13. If you are a parent or guardian and you are aware that your child has provided us with personal information, please contact us.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Changes to This Privacy Policy</h2>
              <p>
                We may update our Privacy Policy from time to time. We will notify you of any changes by posting the new Privacy Policy on this page and updating the "Last Updated" date.
              </p>
              <p>
                You are advised to review this Privacy Policy periodically for any changes. Changes to this Privacy Policy are effective when they are posted on this page.
              </p>
            </section>
            
            <Separator className="my-6 bg-neutral-300 dark:bg-neutral-700" />
            
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">Contact Us</h2>
              <p>
                If you have any questions about this Privacy Policy, please contact us at:
              </p>
              <p className="mt-2">
                <strong className="font-bold">Email:</strong> <span className="font-medium text-green-600 dark:text-green-400">privacy@crystal-data.com</span>
              </p>
            </section>
          </CardContent>
        </Card>
      </div>
    </div>
  );
} 