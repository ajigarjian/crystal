from openai_client import chat_completion

if __name__ == "__main__":
    print("Testing chat completion function...")
    
    response = chat_completion("Is Starbucks an ethical company?")

    print(response)
    