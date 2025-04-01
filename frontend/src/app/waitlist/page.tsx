"use client";

import { Button } from "@/components/ui/button";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Link from "next/link";
import { registerWaitlist } from "@/lib/firebase";

export default function WaitlistPage() {
  // State for the waitlist form
  const [waitlistForm, setWaitlistForm] = useState({
    firstName: "",
    email: ""
  });
  
  // State for submission feedback
  const [submitted, setSubmitted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Handle form input changes
  const handleWaitlistInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setWaitlistForm(prev => ({
      ...prev,
      [name]: value
    }));
    // Clear any previous error when user starts typing again
    if (error) setError(null);
  };
  
  // Handle waitlist submission
  const handleWaitlistSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    
    try {
      // Call the Firebase Cloud Function with the correct data structure
      const result = await registerWaitlist({
        email: waitlistForm.email,
        first_name: waitlistForm.firstName
      });
      
      console.log("Function result:", result.data); // Log the response data
      
      // Show success message
      setSubmitted(true);
      
      // Reset form after 3 seconds
      setTimeout(() => {
        setSubmitted(false);
        setWaitlistForm({
          firstName: "",
          email: ""
        });
      }, 3000);
    } catch (error: any) {
      console.error('Error submitting form:', error);
      // Extract error message from Firebase response
      const errorMessage = error.message || 
                          (error.details && error.details.error) || 
                          "Failed to register. Please try again later.";
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-neutral-50 dark:bg-neutral-50 p-4">
      <div
        className="w-full h-[calc(100vh-2rem)] rounded-lg bg-cover bg-center flex flex-col justify-center relative overflow-hidden"
        style={{
          backgroundImage: "url('/images/crystal-backg.png')",
        }}
      >
        {/* Background Image Layer with blur effect */}
        <div className="absolute inset-0 z-10 bg-cover bg-center after:absolute after:inset-0 after:bg-black/50 after:backdrop-blur-sm" 
          style={{ backgroundImage: "url('/images/crystal-backg.png')" }}>
        </div>
        
        {/* Back to home link */}
        <div className="absolute top-6 left-6 z-30">
          <Link href="/">
            <Button 
              variant="link" 
              className="text-white hover:text-green-400 transition-colors p-2 rounded-full hover:bg-white/10 group"
              style={{ fontFamily: 'var(--font-geist-sans)' }}
              aria-label="Back to home"
            >
              <svg 
                xmlns="http://www.w3.org/2000/svg" 
                width="24" 
                height="24" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="currentColor" 
                strokeWidth="2" 
                strokeLinecap="round" 
                strokeLinejoin="round"
                className="transition-transform duration-200 group-hover:translate-x-[-2px]"
              >
                <path d="m12 19-7-7 7-7"/>
                <path d="M19 12H5"/>
              </svg>
            </Button>
          </Link>
        </div>
        
        {/* Content */}
        <>
          <div className="flex items-center justify-center z-20 relative w-full">
            <img 
              src="/images/crystal-icon.png" 
              alt="Crystal Icon" 
              className="h-12 w-12" 
              style={{ filter: "brightness(0) invert(1)" }}
            />
            <h1 className="text-6xl font-bold text-white" style={{ fontFamily: 'Satoshi, sans-serif' }}>
              Crystal
            </h1>
          </div>
          <div className="relative p-2 mt-2 z-20 text-center w-full">
            <h2 className="relative text-xl sm:text-2xl text-white" style={{ fontFamily: 'var(--font-geist-sans)' }}>
              Querying for Deep<span className="text-green-500 animate-pulse drop-shadow-[0_0_8px_rgba(34,197,94,0.8)]" style={{ textShadow: '0 0 10px rgba(34, 197, 94, 0.8)' }}>er</span> Research into Public Records
            </h2>
          </div>
          
          {/* Waitlist Form */}
          <div className="z-20 relative w-full max-w-md mx-auto px-4 mt-8">
            <form 
              onSubmit={handleWaitlistSubmit}
              className="bg-black/40 backdrop-blur-md rounded-lg p-6 border border-white/30 shadow-xl"
            >
              <h3 className="text-white text-xl font-medium mb-4 text-center">
                Join our waitlist
              </h3>
              
              {submitted ? (
                <div className="bg-green-500/30 text-white p-4 rounded-md text-center border border-green-400/50">
                  <p className="font-medium">Thanks {waitlistForm.firstName}!</p>
                  <p>We'll notify you when we launch.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {error && (
                    <div className="bg-red-500/30 text-white p-3 rounded-md text-center border border-red-400/50 text-sm">
                      {error}
                    </div>
                  )}
                  
                  <div className="space-y-2">
                    <Label htmlFor="firstName" className="text-white">
                      First Name
                    </Label>
                    <Input
                      id="firstName"
                      name="firstName"
                      placeholder="Your first name"
                      value={waitlistForm.firstName}
                      onChange={handleWaitlistInputChange}
                      required
                      disabled={isSubmitting}
                      className="bg-white/20 border-white/30 text-white placeholder:text-white/80 focus:border-green-400/70 focus:ring-1 focus:ring-green-400/70"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="email" className="text-white">
                      Email
                    </Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      placeholder="your.email@example.com"
                      value={waitlistForm.email}
                      onChange={handleWaitlistInputChange}
                      required
                      disabled={isSubmitting}
                      className="bg-white/20 border-white/30 text-white placeholder:text-white/80 focus:border-green-400/70 focus:ring-1 focus:ring-green-400/70"
                    />
                  </div>
                  
                  <Button 
                    type="submit" 
                    className="w-full bg-green-500/80 hover:bg-green-500/90 text-white mt-2 font-medium transition-all"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? "Submitting..." : "Join Waitlist"}
                  </Button>
                </div>
              )}
            </form>
          </div>
        </>
      </div>
    </div>
  );
}
