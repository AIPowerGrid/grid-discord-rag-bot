#!/usr/bin/env python3
"""
Simulation script to show what the bot would see and how it would classify messages.
This helps understand the conversation flow and classification logic.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_NAME = os.getenv('BOT_NAME', 'GridBot')

def format_channel_history(messages):
    """Format the channel history for context (simulated)."""
    if not messages:
        return ""
    
    formatted_history = "Recent conversation:\n"
    for msg in messages:
        author = msg['author']
        content = msg['content']
        formatted_history += f"{author}: {content}\n"
    
    return formatted_history

def simulate_classification_prompt(author_name, content, conversation_history):
    """Simulate the classification prompt the bot would send to the LLM."""
    prompt = f"""
You are {BOT_NAME}, an AI assistant in a Discord channel. You have access to documentation about AI Power Grid.

Recent conversation:
{conversation_history}

Current message from {author_name}: "{content}"

Should you respond to this message? Consider:
1. Is this a question or request for help?
2. Can you provide useful information about AI Power Grid?
3. Would your response be helpful and relevant?
4. Is the person asking for assistance or information you can provide?

Respond with only "YES" or "NO".
"""
    return prompt

def simulate_response_prompt(author_name, content, conversation_history, context_docs):
    """Simulate the response prompt the bot would send to the LLM."""
    prompt = f"""
You are {BOT_NAME}, a helpful assistant in a Discord channel. Respond naturally as if you're a regular user, not a bot.

Recent conversation:
{conversation_history}

Current message from {author_name}: "{content}"

Context from AI Power Grid documentation:
{context_docs}

Respond naturally and conversationally. Don't mention that you're an AI or bot. Just answer the question or provide helpful information as if you're a knowledgeable person in the chat.
"""
    return prompt

def main():
    """Simulate different conversation scenarios."""
    print(f"🤖 Bot Name: {BOT_NAME}")
    print("=" * 50)
    
    # Scenario 1: Direct question about AI Power Grid
    print("\n📝 SCENARIO 1: Direct question about AI Power Grid")
    print("-" * 40)
    
    conversation_1 = [
        {"author": "Alice", "content": "Hey everyone!"},
        {"author": "Bob", "content": "Hi Alice!"},
        {"author": "Charlie", "content": "What is AI Power Grid?"}
    ]
    
    current_message = "What is AI Power Grid?"
    author = "Charlie"
    
    print(f"Conversation History:")
    print(format_channel_history(conversation_1))
    print(f"\nCurrent Message: {author}: {current_message}")
    
    print(f"\n🔍 Classification Prompt:")
    print(simulate_classification_prompt(author, current_message, format_channel_history(conversation_1)))
    
    print(f"\n✅ Expected Classification: YES")
    print(f"💬 Would generate response using AI Power Grid documentation")
    
    # Scenario 2: General conversation (not a question)
    print("\n\n📝 SCENARIO 2: General conversation")
    print("-" * 40)
    
    conversation_2 = [
        {"author": "Alice", "content": "How's everyone's day going?"},
        {"author": "Bob", "content": "Pretty good! Working on some new features."},
        {"author": "Charlie", "content": "That sounds interesting!"}
    ]
    
    current_message = "That sounds interesting!"
    author = "Charlie"
    
    print(f"Conversation History:")
    print(format_channel_history(conversation_2))
    print(f"\nCurrent Message: {author}: {current_message}")
    
    print(f"\n🔍 Classification Prompt:")
    print(simulate_classification_prompt(author, current_message, format_channel_history(conversation_2)))
    
    print(f"\n❌ Expected Classification: NO")
    print(f"🤐 Would not respond")
    
    # Scenario 3: Follow-up question in conversation
    print("\n\n📝 SCENARIO 3: Follow-up question")
    print("-" * 40)
    
    conversation_3 = [
        {"author": "Alice", "content": "What is AI Power Grid?"},
        {"author": BOT_NAME, "content": "AI Power Grid is a platform that provides access to various AI models and APIs. It allows developers to easily integrate AI capabilities into their applications."},
        {"author": "Alice", "content": "How does it handle security?"}
    ]
    
    current_message = "How does it handle security?"
    author = "Alice"
    
    print(f"Conversation History:")
    print(format_channel_history(conversation_3))
    print(f"\nCurrent Message: {author}: {current_message}")
    
    print(f"\n🔍 Classification Prompt:")
    print(simulate_classification_prompt(author, current_message, format_channel_history(conversation_3)))
    
    print(f"\n✅ Expected Classification: YES")
    print(f"💬 Would generate response about AI Power Grid security features")
    
    # Scenario 4: Question about unrelated topic
    print("\n\n📝 SCENARIO 4: Unrelated question")
    print("-" * 40)
    
    conversation_4 = [
        {"author": "Alice", "content": "What's the weather like today?"},
        {"author": "Bob", "content": "I think it's sunny"},
        {"author": "Charlie", "content": "What's the best pizza place around here?"}
    ]
    
    current_message = "What's the best pizza place around here?"
    author = "Charlie"
    
    print(f"Conversation History:")
    print(format_channel_history(conversation_4))
    print(f"\nCurrent Message: {author}: {current_message}")
    
    print(f"\n🔍 Classification Prompt:")
    print(simulate_classification_prompt(author, current_message, format_channel_history(conversation_4)))
    
    print(f"\n❌ Expected Classification: NO")
    print(f"🤐 Would not respond (not related to AI Power Grid)")
    
    # Scenario 5: Technical question that might be relevant
    print("\n\n📝 SCENARIO 5: Technical question")
    print("-" * 40)
    
    conversation_5 = [
        {"author": "Alice", "content": "I'm having trouble with my API integration"},
        {"author": "Bob", "content": "What kind of API?"},
        {"author": "Alice", "content": "It's a machine learning API, any tips?"}
    ]
    
    current_message = "It's a machine learning API, any tips?"
    author = "Alice"
    
    print(f"Conversation History:")
    print(format_channel_history(conversation_5))
    print(f"\nCurrent Message: {author}: {current_message}")
    
    print(f"\n🔍 Classification Prompt:")
    print(simulate_classification_prompt(author, current_message, format_channel_history(conversation_5)))
    
    print(f"\n✅ Expected Classification: YES")
    print(f"💬 Would provide tips about AI Power Grid API integration")

if __name__ == "__main__":
    main()
