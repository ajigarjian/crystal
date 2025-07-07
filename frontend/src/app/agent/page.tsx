"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Send, Sparkles, Zap, MessageCircle, ArrowRight } from "lucide-react";
import { streamAgentResponse } from "@/lib/gcp";
import { ToolCallDisplay } from "@/components/ToolCallDisplay";

interface ToolCallContent {
  name: string;
  arguments: Record<string, unknown>;
}

interface Message {
  id: string;
  type: "user" | "assistant" | "tool_code";
  content: string | ToolCallContent;
  timestamp: Date;
}

const FormattedMessageContent = ({ content }: { content: string }) => {
  if (!content) {
    return null;
  }
  const parts = content.split(/(\*\*.*?\*\*)/g);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={index}>{part.slice(2, -2)}</strong>;
        }
        return part;
      })}
    </>
  );
};

const examplePrompts = [
  {
    title: "Analyze Infrastructure",
    description: "Find all power plants within 50km of Seattle",
    icon: Zap,
  },
  {
    title: "Dam Operations",
    description: "Compare and forecast dams in the service area",
    icon: Sparkles,
  },
  {
    title: "Interconnection Queue",
    description: "Understand the existing queue backlog",
    icon: MessageCircle,
  },
];

export default function AgentMode() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: input,
      timestamp: new Date(),
    };
    
    const currentInput = input;
    setInput("");
    setIsLoading(true);

    const newMessages: Message[] = [...messages, userMessage];
    setMessages(newMessages);

    const assistantMessageId = (Date.now() + 1).toString();
    setMessages((prev) => [
        ...prev,
        {
            id: assistantMessageId,
            type: 'assistant',
            content: '',
            timestamp: new Date(),
        }
    ]);

    const history = newMessages
      .filter(msg => msg.type === 'user' || msg.type === 'assistant')
      .map((msg) => ({
          role: msg.type as 'user' | 'assistant',
          content: msg.content as string,
      }));
    history.pop(); 

    await streamAgentResponse(
      currentInput,
      history,
      (chunk) => {
        if (chunk.type === "text" && typeof chunk.content === 'string') {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId 
              ? { ...msg, content: (msg.content as string) + chunk.content }
              : msg
          ));
        } else if (chunk.type === "tool_code") {
          const toolMessage: Message = {
            id: (Date.now() + Math.random()).toString(),
            type: "tool_code",
            content: chunk.content as ToolCallContent,
            timestamp: new Date(),
          };
          setMessages(prev => {
            const assistantIndex = prev.findIndex(m => m.id === assistantMessageId);
            if (assistantIndex > -1) {
              const newMsgs = [...prev];
              newMsgs.splice(assistantIndex, 0, toolMessage);
              return newMsgs;
            }
            return [...prev, toolMessage];
          });
        } else if (chunk.type === "error") {
          setMessages(prev => prev.map(msg => 
            msg.id === assistantMessageId 
              ? { ...msg, content: (msg.content as string) + `\n\n**Error:** ${chunk.content}` }
              : msg
          ));
        }
      },
      () => { // onClose
        setIsLoading(false);
        inputRef.current?.focus();
      },
      (error) => { // onError
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMessageId 
            ? { ...msg, content: (msg.content as string) + `\n\n**API Error:** ${error.message}` }
            : msg
        ));
        setIsLoading(false);
      }
    );
  };

  const handleExamplePrompt = (prompt: string) => {
    setInput(prompt);
    inputRef.current?.focus();
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <div className="border-b bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900 dark:text-white">
                Mid-C Market Agent
              </h1>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                AI analysis and insights for the Mid C Market
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Welcome Screen */}
        {messages.length === 0 && (
          <div className="text-center space-y-8">
            {/* Character Animation Placeholder */}
            <div className="relative">
              <div className="w-48 h-48 mx-auto rounded-full bg-gradient-to-br from-blue-100 to-purple-100 dark:from-blue-900/20 dark:to-purple-900/20 flex items-center justify-center border-2 border-blue-200 dark:border-blue-800 overflow-hidden">
                <video
                  src="/purple_bear.mp4"
                  loop
                  autoPlay
                  muted
                  playsInline
                  tabIndex={0}
                  aria-label="Animated purple bear"
                  className="w-full h-full object-cover rounded-full cursor-pointer"
                  onClick={e => {
                    const video = e.currentTarget;
                    if (video.paused) {
                      video.play();
                    } else {
                      video.pause();
                    }
                  }}
                />
              </div>
              <div className="absolute inset-0 rounded-full bg-gradient-to-r from-blue-500/20 to-purple-500/20 animate-pulse pointer-events-none" />
            </div>

            <div className="space-y-4">
              <h2 className="text-3xl font-bold text-slate-900 dark:text-white">
                How can I help you today?
              </h2>
              <p className="text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
                Ask me anything about infrastructure data, environmental analysis, or get insights from our comprehensive datasets.
              </p>
            </div>

            {/* Example Prompts */}
            <div className="grid md:grid-cols-3 gap-4 mt-8">
              {examplePrompts.map((prompt, index) => (
                <Card
                  key={index}
                  className="p-4 hover:shadow-lg transition-all duration-200 cursor-pointer border-slate-200 dark:border-slate-700 hover:border-blue-300 dark:hover:border-blue-600 group"
                  onClick={() => handleExamplePrompt(prompt.description)}
                >
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-900 transition-colors">
                      <prompt.icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div className="flex-1 text-left">
                      <h3 className="font-medium text-slate-900 dark:text-white mb-1">
                        {prompt.title}
                      </h3>
                      <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                        {prompt.description}
                      </p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-blue-500 transition-colors" />
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Chat Messages */}
        {messages.length > 0 && (
          <div className="space-y-6">
            <ScrollArea className="h-[60vh]">
              <div className="space-y-4">
                {messages.map((message) => {
                  if (message.type === 'tool_code') {
                    const toolContent = message.content as ToolCallContent;
                    return (
                      <ToolCallDisplay
                        key={message.id}
                        name={toolContent.name}
                        args={toolContent.arguments}
                      />
                    );
                  }
                  return (
                    <div
                      key={message.id}
                      className={`flex ${
                        message.type === "user" ? "justify-end" : "justify-start"
                      }`}
                    >
                      <div
                        className={`max-w-xs md:max-w-md lg:max-w-lg xl:max-w-xl p-4 rounded-2xl ${
                          message.type === "user"
                            ? "bg-blue-500 text-white"
                            : "bg-white dark:bg-slate-800 text-slate-900 dark:text-white border border-slate-200 dark:border-slate-700"
                        }`}
                      >
                        <p className="whitespace-pre-wrap leading-relaxed">
                          <FormattedMessageContent content={message.content as string} />
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          <span
                            className={`text-xs ${
                              message.type === "user"
                                ? "text-blue-100"
                                : "text-slate-500 dark:text-slate-400"
                            }`}
                          >
                            {message.timestamp.toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {isLoading && (
                  <div className="flex justify-start">
                    <div className="max-w-xs md:max-w-md lg:max-w-lg xl:max-w-xl p-4 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-4 w-1/2" />
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <div ref={messagesEndRef} />
            </ScrollArea>
          </div>
        )}

        {/* Input Area */}
        <div className="fixed bottom-0 left-0 right-0 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-t border-slate-200 dark:border-slate-700 p-4">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <Input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask me anything about infrastructure data..."
                  className="min-h-[48px] resize-none border-slate-300 dark:border-slate-600 focus:border-blue-500 dark:focus:border-blue-400 rounded-xl px-4 py-3"
                  disabled={isLoading}
                />
              </div>
              <Button
                onClick={handleSendMessage}
                disabled={!input.trim() || isLoading}
                size="lg"
                className="h-12 px-6 rounded-xl bg-blue-500 hover:bg-blue-600 text-white"
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
            <div className="flex items-center justify-between mt-2">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Press Enter to send, Shift + Enter for new line
              </p>
              <Badge variant="secondary" className="text-xs">
                Powered by AI
              </Badge>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}