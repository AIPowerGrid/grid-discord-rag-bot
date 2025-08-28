import os
import json
import time
import re
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GRID_API_KEY = os.getenv('GRID_API_KEY')
GRID_MODEL = os.getenv('GRID_MODEL', 'grid/meta-llama/llama-4-maverick-17b-128e-instruct')

# API endpoints from example
TEXT_GENERATION_ENDPOINT = 'https://api.aipowergrid.io/api/v2/generate/text/async'
TEXT_GENERATION_STATUS_ENDPOINT = 'https://api.aipowergrid.io/api/v2/generate/text/status'

class GridClient:
    """Client for interacting with AI Power Grid API."""
    
    def __init__(self):
        """Initialize the Grid client."""
        if not GRID_API_KEY:
            print("Warning: GRID_API_KEY not set in environment variables")
        else:
            print(f"Using model: {GRID_MODEL}")
    
    async def get_answer(self, question: str, context: List[Dict[str, Any]]) -> str:
        """Get answer from AI Power Grid API using retrieved context."""
        if not GRID_API_KEY:
            return "Error: AI Power Grid API key not configured"
        
        # Format context into a single string
        formatted_context = ""
        for i, item in enumerate(context):
            formatted_context += f"[Document {i+1}] {item['text']}\n\n"
        
        # Check if this is a follow-up question
        is_followup = "previous question:" in question.lower() or "follow-up question:" in question.lower()
        
        # Create prompt with context and question
        if is_followup:
            prompt = f"""
You are a helpful assistant answering questions about AI Power Grid.
Use only the following context and previous conversation to answer the question. 
If you don't know the answer based on the context, say "I don't have enough information to answer this question."

CONTEXT:
{formatted_context}

CONVERSATION HISTORY AND CURRENT QUESTION:
{question}

ANSWER:
"""
        else:
            prompt = f"""
You are a helpful assistant answering questions about AI Power Grid.
Use only the following context to answer the question. If you don't know the answer based on the context, say "I don't have enough information to answer this question."

CONTEXT:
{formatted_context}

QUESTION:
{question}

ANSWER:
"""
        
        try:
            # Prepare request payload based on example
            request_body = {
                "prompt": prompt,
                "params": {
                    "max_length": 1024,  # Maximum allowed by the API
                    "max_context_length": 8192,
                    "temperature": 0.7,
                    "rep_pen": 1.1,
                    "top_p": 0.92,
                    "top_k": 100,
                    "stop_sequence": ["<|endoftext|>"],  # Removed "\n\n" which was causing truncation
                },
                "models": [GRID_MODEL],  # Use model from environment variables
            }
            
            # Set headers
            headers = {
                'Content-Type': 'application/json',
                'apikey': GRID_API_KEY,
                'Client-Agent': 'GridRAGBot:1.0'
            }
            
            # Print request details for debugging
            print(f"Using API key: {GRID_API_KEY[:5]}...")
            print(f"Using model: {GRID_MODEL}")
            
            # Step 1: Submit the generation request
            print("Sending request to API...")
            response = requests.post(
                TEXT_GENERATION_ENDPOINT,
                headers=headers,
                json=request_body
            )
            
            # Print response details for debugging
            print(f"Response status code: {response.status_code}")
            
            # Check response - 202 is success for async operations
            if response.status_code == 202:
                # This is the expected success code for async operations
                result = response.json()
            elif response.status_code != 200:
                try:
                    error_detail = response.json()
                    return f"API Error ({response.status_code}): {json.dumps(error_detail)}"
                except:
                    return f"API Error ({response.status_code}): {response.text}"
            else:
                # Parse JSON response for 200 responses
                result = response.json()
            
            # Get the generation ID
            if not result or not result.get("id"):
                return "Error: Failed to start text generation. No generation ID received."
            
            generation_id = result["id"]
            print(f"Text generation request submitted with ID: {generation_id}")
            
            # Step 2: Poll for the results
            generation_result = await self._poll_for_text_results(generation_id)
            
            # Step 3: Process and return the result
            if generation_result.get("error"):
                return f"Error: {generation_result['error']}"
                
            if not generation_result.get("text"):
                return "Error: No text was generated"
            
            # Return the generated text
            return self._normalize_api_text(generation_result["text"])
            
        except requests.RequestException as e:
            return f"Error calling AI Power Grid API: {str(e)}"
    
    async def _poll_for_text_results(self, generation_id, max_wait_time_seconds=120):
        """Poll for text generation results."""
        try:
            print(f"Starting to poll for text generation results for ID: {generation_id}")
            
            # Keep track of polling attempts
            attempts = 0
            poll_interval_seconds = 3  # How often to poll in seconds
            max_attempts = max_wait_time_seconds // poll_interval_seconds
            
            # Poll in a loop until max attempts reached
            while attempts < max_attempts:
                attempts += 1
                print(f"Polling attempt {attempts}/{max_attempts} for text generation...")
                
                # Sleep between polling attempts to avoid rate limiting
                if attempts > 1:
                    import asyncio
                    await asyncio.sleep(poll_interval_seconds)
                
                # Make the API request to check the status
                status_response = requests.get(
                    f"{TEXT_GENERATION_STATUS_ENDPOINT}/{generation_id}", 
                    headers={
                        'apikey': GRID_API_KEY,
                        'Client-Agent': 'GridRAGBot:1.0'
                    }
                )
                
                status_data = status_response.json()
                
                # Check if generation is complete
                if status_data.get("done") == True:
                    print('Text generation completed successfully')
                    
                    # Check if we have valid generations
                    if status_data.get("generations") and len(status_data["generations"]) > 0:
                        generation = status_data["generations"][0]
                        
                        # Make sure the generation has text
                        if generation.get("text"):
                            return {
                                "text": generation["text"],
                                "model": generation.get("model", "unknown"),
                                "done": True
                            }
                        else:
                            return {"error": "Generated text is empty", "done": True}
                    else:
                        return {"error": "No generations found", "done": True}
                elif status_data.get("faulted") == True:
                    # Check if generation failed
                    fault_message = status_data.get("faulted_message", "Unknown error")
                    return {"error": fault_message, "done": True, "faulted": True}
                else:
                    # Log progress metrics
                    waiting = status_data.get("waiting", 0)
                    processing = status_data.get("processing", 0)
                    finished = status_data.get("finished", 0)
                    print(f"Text generation still in progress: {waiting} waiting, {processing} processing, {finished} finished")
            
            # If we've reached the maximum attempts, timeout
            return {"error": f"Polling timed out after {max_wait_time_seconds} seconds", "done": False}
            
        except Exception as e:
            return {"error": str(e), "done": False}
    
    def _normalize_api_text(self, text):
        """Normalize text from AI Power Grid API responses."""
        if not text:
            return ""
        
        # Remove newlines that break words (keep only if they're between sentences)
        normalized = re.sub(r'(\S)\n(\S)', r'\1 \2', text)
        
        # Normalize standard newlines
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        
        # Don't remove legitimate paragraph breaks
        # normalized = re.sub(r'\n{3,}', '\n\n', normalized).strip()
        
        return normalized.strip() 