"""
Image vision handler for Discord bot.
Processes images from attachments, embeds, and URLs.
"""
import os
import base64
import aiohttp
import re
from typing import List, Dict, Optional, Tuple
from io import BytesIO
from PIL import Image
import discord

# Supported image formats
SUPPORTED_IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_DIMENSION = 4096

def is_image_url(url: str) -> bool:
    """Check if URL points to an image."""
    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
    url_lower = url.lower()
    return any(url_lower.endswith(ext) for ext in image_extensions) or \
           any(domain in url_lower for domain in ['imgur.com', 'i.imgur.com', 'gyazo.com', 'discordapp.com', 'cdn.discordapp.com'])

def is_image_attachment(attachment: discord.Attachment) -> bool:
    """Check if attachment is an image."""
    if not attachment.filename:
        return False
    ext = os.path.splitext(attachment.filename)[1].lower()
    return ext in SUPPORTED_IMAGE_FORMATS

async def download_image(url: str) -> Optional[bytes]:
    """Download image from URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    content_type = response.headers.get('Content-Type', '')
                    if 'image' in content_type:
                        return await response.read()
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
    return None

async def process_image(image_data: bytes, mime_type: str = "image/png") -> Optional[str]:
    """Convert image to base64 for API."""
    try:
        # Validate image size
        if len(image_data) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            print(f"Image too large: {len(image_data) / 1024 / 1024:.2f}MB")
            return None
        
        # Validate dimensions
        img = Image.open(BytesIO(image_data))
        width, height = img.size
        if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            # Resize if too large
            ratio = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            output = BytesIO()
            img.save(output, format='PNG')
            image_data = output.getvalue()
            mime_type = "image/png"
        
        # Convert to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        return base64_image
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

async def extract_images_from_message(message: discord.Message) -> List[Dict[str, str]]:
    """Extract all images from a Discord message.
    
    Returns list of dicts with:
    - 'data': base64 encoded image
    - 'mimeType': MIME type
    - 'source': 'attachment', 'embed', or 'url'
    """
    images = []
    
    # 1. Check attachments
    for attachment in message.attachments:
        if is_image_attachment(attachment):
            try:
                image_data = await attachment.read()
                mime_type = attachment.content_type or "image/png"
                base64_data = await process_image(image_data, mime_type)
                if base64_data:
                    images.append({
                        'data': base64_data,
                        'mimeType': mime_type,
                        'source': 'attachment',
                        'filename': attachment.filename
                    })
            except Exception as e:
                print(f"Error processing attachment {attachment.filename}: {e}")
    
    # 2. Check embeds
    for embed in message.embeds:
        if embed.image:
            image_url = embed.image.url
            image_data = await download_image(image_url)
            if image_data:
                base64_data = await process_image(image_data)
                if base64_data:
                    images.append({
                        'data': base64_data,
                        'mimeType': 'image/png',
                        'source': 'embed',
                        'url': image_url
                    })
        if embed.thumbnail:
            thumbnail_url = embed.thumbnail.url
            image_data = await download_image(thumbnail_url)
            if image_data:
                base64_data = await process_image(image_data)
                if base64_data:
                    images.append({
                        'data': base64_data,
                        'mimeType': 'image/png',
                        'source': 'embed_thumbnail',
                        'url': thumbnail_url
                    })
    
    # 3. Check message content for image URLs
    if message.content:
        # Simple URL regex
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, message.content)
        for url in urls:
            if is_image_url(url):
                image_data = await download_image(url)
                if image_data:
                    base64_data = await process_image(image_data)
                    if base64_data:
                        images.append({
                            'data': base64_data,
                            'mimeType': 'image/png',
                            'source': 'url',
                            'url': url
                        })
    
    return images

async def describe_image_with_vision(
    image_data: str, 
    mime_type: str,
    context: str = "",
    grid_client=None
) -> Optional[str]:
    """Describe image using vision API.
    
    Options:
    1. Use AI Power Grid if it supports vision
    2. Use OpenAI Vision API (if API key available)
    3. Use Claude Vision API (if API key available)
    4. Fallback to basic image analysis
    """
    # Try OpenAI Vision first (if available)
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=openai_key)
            
            prompt = f"""Describe this image in detail. Be specific about what you see.
{context}
Focus on: objects, text, people, actions, context, mood, style."""
            
            response = await client.chat.completions.create(
                model="gpt-4o",  # or "gpt-4-vision-preview"
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI Vision error: {e}")
    
    # Try Claude Vision (if available)
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=anthropic_key)
            
            prompt = f"""Describe this image in detail. Be specific about what you see.
{context}
Focus on: objects, text, people, actions, context, mood, style."""
            
            message = await client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            
            return message.content[0].text
        except Exception as e:
            print(f"Claude Vision error: {e}")
    
    # Fallback: Basic description
    return "Image detected but vision API not configured. Enable OPENAI_API_KEY or ANTHROPIC_API_KEY for image analysis."

def format_image_context(images: List[Dict[str, str]], descriptions: List[str]) -> str:
    """Format image context for prompt."""
    if not images:
        return ""
    
    context = "\nImages in this message:\n"
    for i, (img, desc) in enumerate(zip(images, descriptions), 1):
        source_info = img.get('filename') or img.get('url', 'unknown')
        context += f"[Image {i}] ({img['source']}: {source_info})\n"
        context += f"Description: {desc}\n\n"
    
    return context



