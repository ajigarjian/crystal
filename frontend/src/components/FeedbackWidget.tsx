"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { MessageSquareIcon, ThumbsUpIcon, BugIcon, LightbulbIcon, AlertCircle, Loader2 } from "lucide-react";
import { submitFeedback } from "@/lib/firebase";

export const FeedbackWidget = () => {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [feedbackType, setFeedbackType] = useState<string>("suggestion");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    
    console.log("Starting feedback submission");
    
    try {
      const result = await submitFeedback({
        feedback_type: feedbackType,
        title,
        description,
        email: email || undefined,
        page_url: window.location.href,
        tags: [],
        metadata: {}
      });
      
      console.log("Submission successful:", result);
      
      setSubmitted(true);
      
      setTimeout(() => {
        setOpen(false);
        setTimeout(() => {
          setSubmitted(false);
          setTitle("");
          setDescription("");
          setEmail("");
          setFeedbackType("suggestion");
        }, 300);
      }, 3000);
    } catch (error: any) {
      console.error("Error submitting feedback:", error);
      setError(error.message || "Failed to submit feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="default"
          size="sm"
          className="fixed bottom-6 right-6 z-50 rounded-full shadow-lg flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white transition-all duration-200 hover:scale-105"
        >
          <MessageSquareIcon className="h-4 w-4" />
          <span>Feedback</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Send Feedback</DialogTitle>
          <DialogDescription>
            Help us improve Crystal with your suggestions and feedback.
          </DialogDescription>
        </DialogHeader>
        
        {submitted ? (
          <div className="py-6 space-y-4 text-center">
            <div className="mx-auto bg-green-100 text-green-800 rounded-full p-3 w-fit">
              <ThumbsUpIcon className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-lg">Thank you for your feedback!</h3>
            <p className="text-sm text-gray-500">
              We appreciate your input and will take it into consideration.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 py-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            
            <div className="space-y-2">
              <Label htmlFor="feedback-type" className="text-sm font-medium">
                Feedback Type
              </Label>
              <RadioGroup 
                value={feedbackType} 
                onValueChange={setFeedbackType}
                className="grid grid-cols-2 gap-2"
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="suggestion" id="suggestion" />
                  <Label htmlFor="suggestion" className="flex items-center text-sm cursor-pointer">
                    <LightbulbIcon className="mr-1 h-3 w-3" />
                    Suggestion
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="bug" id="bug" />
                  <Label htmlFor="bug" className="flex items-center text-sm cursor-pointer">
                    <BugIcon className="mr-1 h-3 w-3" />
                    Bug report
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="feature_request" id="feature_request" />
                  <Label htmlFor="feature_request" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUpIcon className="mr-1 h-3 w-3" />
                    Feature request
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="praise" id="praise" />
                  <Label htmlFor="praise" className="flex items-center text-sm cursor-pointer">
                    <ThumbsUpIcon className="mr-1 h-3 w-3" />
                    Praise
                  </Label>
                </div>
              </RadioGroup>
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-title" className="text-sm font-medium">
                Title
              </Label>
              <Input
                id="feedback-title"
                placeholder="Brief summary of your feedback"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full"
                required
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-description" className="text-sm font-medium">
                Description
              </Label>
              <Textarea
                id="feedback-description"
                placeholder="Please provide more details about your feedback..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="min-h-[100px]"
                required
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="feedback-email" className="text-sm font-medium">
                Email (optional)
              </Label>
              <Input
                id="feedback-email"
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <p className="text-xs text-gray-500">
                We'll only use this to follow up on your feedback if needed.
              </p>
            </div>
            
            <DialogFooter className="pt-2">
              <Button 
                variant="outline" 
                type="button" 
                onClick={() => setOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button 
                type="submit" 
                disabled={submitting}
                className="bg-green-600 hover:bg-green-700"
              >
                {submitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Submitting...
                  </>
                ) : "Submit Feedback"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
};