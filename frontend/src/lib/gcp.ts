interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

interface ToolCallContent {
  name: string;
  arguments: Record<string, unknown>;
}

interface StreamOnChunkData {
  type: "text" | "tool_code" | "error";
  content: string | ToolCallContent;
}

export const streamAgentResponse = async (
  message: string,
  history: HistoryMessage[],
  onChunk: (data: StreamOnChunkData) => void,
  onClose: () => void,
  onError: (error: Error) => void
) => {
  const url = process.env.NEXT_PUBLIC_GCP_FUNCTION_URL || "http://127.0.0.1:8081/energy_agent";

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message, history }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Response body is empty");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep the last partial line in the buffer

      for (const line of lines) {
        if (line.trim()) {
            try {
                const parsed = JSON.parse(line);
                onChunk(parsed);
            } catch (error) {
                console.error("Failed to parse stream chunk:", line, error);
            }
        }
      }
    }
    
    if (buffer.trim()) {
        try {
            const parsed = JSON.parse(buffer);
            onChunk(parsed);
        } catch (error) {
            console.error("Failed to parse final stream chunk:", buffer, error);
        }
    }

  } catch (error) {
    console.error("Streaming failed:", error);
    if (error instanceof Error) {
        onError(error);
    } else {
        onError(new Error("An unknown error occurred during streaming."));
    }
  } finally {
    onClose();
  }
}; 