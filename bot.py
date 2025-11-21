import os
import discord
import datetime
from io import BytesIO
from dotenv import load_dotenv
from retriever import DocumentRetriever
from grid_client import GridClient
from coingecko_mcp import get_crypto_context
from conversation_db import (
    init_db, add_message, format_channel_history,
    format_mood, format_memories, format_recent_happenings
)

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNELS = os.getenv('DISCORD_CHANNELS', '').split(',')
ALLOWED_CHANNEL_IDS = []
for channel_id in DISCORD_CHANNELS:
    if channel_id.strip():
        try:
            ALLOWED_CHANNEL_IDS.append(int(channel_id.strip()))
        except ValueError:
            print(f"Warning: Invalid channel ID '{channel_id}', skipping")

LISTENING_CHANNEL_ID = 0
try:
    LISTENING_CHANNEL_ID = int(os.getenv('LISTENING_CHANNEL_ID', '0'))
except ValueError:
    print(f"Warning: Invalid LISTENING_CHANNEL_ID, using 0")
BOT_NAME = os.getenv('BOT_NAME', 'ask-ai')  # Configurable bot name
admin_id_str = os.getenv('ADMIN_USER_ID', '0')
print(f"Admin ID from env: '{admin_id_str}'")
ADMIN_USER_ID = 0
try:
    ADMIN_USER_ID = int(admin_id_str)
except ValueError:
    print(f"Warning: Invalid ADMIN_USER_ID '{admin_id_str}', using 0")

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # Make sure we have message intents
intents.reactions = True  # Need reactions for voting
intents.members = True  # Need members intent for banning
client = discord.Client(intents=intents)

# Initialize document retriever and Grid client
retriever = DocumentRetriever()
grid_client = GridClient()

# Store conversation history
channel_message_history = {}
MAX_MESSAGE_HISTORY = 10  # Number of messages to remember per channel

# Scam detection and voting
BAN_VOTE_THRESHOLD = 3  # Number of upvotes needed to ban
DISMISS_VOTE_THRESHOLD = 3  # Number of downvotes needed to dismiss
pending_ban_votes = {}  # {message_id: {'target_user_id': int, 'reason': str, 'upvotes': set, 'downvotes': set}}

# Command prefixes
COMMANDS = {
    'help': '!help',
    'upload': '!upload',
    'list': '!list',
    'delete': '!delete'
}

@client.event
async def on_ready():
    """Event called when the bot is ready."""
    # Initialize database
    init_db()
    
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print(f'Bot name: {BOT_NAME}')
    print(f'Listening in ALL channels for automatic responses')
    print(f'Admin commands allowed in channels: {ALLOWED_CHANNEL_IDS}')
    print(f'Admin user ID: {ADMIN_USER_ID}')
    print('------')

def get_channel_history(channel_id):
    """Get the conversation history for a channel."""
    if channel_id not in channel_message_history:
        channel_message_history[channel_id] = []
    return channel_message_history[channel_id]

# add_to_channel_history is now handled by add_message from conversation_db

# format_channel_history is now imported from conversation_db

def extract_urls_from_message(message_content: str) -> list[str]:
    """Extract all URLs from a message."""
    import re
    url_patterns = [
        r'https?://[^\s\)]+',  # Match URLs, stop at whitespace or closing paren
        r'www\.[^\s\)]+',
    ]
    
    urls = []
    for pattern in url_patterns:
        matches = re.findall(pattern, message_content)
        urls.extend(matches)
    
    return urls

def is_forbidden_link_type(url: str, message_content: str) -> tuple[bool, str]:
    """Check if a URL is a forbidden type (DEX, DeFi, support, Discord invite).
    Returns (is_forbidden, reason)"""
    import re
    url_lower = url.lower()
    content_lower = message_content.lower()
    
    # Discord invites (always forbidden)
    discord_patterns = [
        r'discord\.gg/',
        r'discord\.com/invite/',
        r'discordapp\.com/invite/',
    ]
    for pattern in discord_patterns:
        if re.search(pattern, url_lower):
            return True, "posted a Discord invite link"
    
    # Support ticket/help desk links
    support_keywords = ['support', 'help', 'ticket', 'helpdesk', 'zendesk', 'freshdesk']
    support_domains = ['support', 'help', 'ticket', 'helpdesk']
    if any(keyword in url_lower for keyword in support_keywords) or any(domain in url_lower for domain in support_domains):
        return True, "posted a support ticket/help link"
    
    # DEX (Decentralized Exchange) links
    dex_keywords = ['dex', 'uniswap', 'pancakeswap', 'sushiswap', '1inch', 'dydx', 'curve', 'balancer', 'kyberswap']
    dex_domains = ['uniswap', 'pancakeswap', 'sushiswap', '1inch', 'dydx', 'curve.fi', 'balancer', 'kyberswap']
    if any(keyword in url_lower for keyword in dex_keywords) or any(domain in url_lower for domain in dex_domains):
        return True, "posted a DEX (decentralized exchange) link"
    
    # DeFi platform links
    defi_keywords = ['defi', 'lending', 'borrowing', 'yield', 'farm', 'staking', 'liquidity', 'pool']
    defi_domains = ['aave', 'compound', 'makerdao', 'yearn', 'convex', 'frax']
    if any(keyword in url_lower for keyword in defi_keywords) or any(domain in url_lower for domain in defi_domains):
        # But allow if it's clearly about AIPG staking/pools (legitimate)
        if 'aipg' in content_lower or 'aipowergrid' in content_lower or 'power grid' in content_lower:
            return False, ""
        return True, "posted a DeFi platform link"
    
    return False, ""

def detect_discord_invite(message_content: str) -> tuple[bool, str]:
    """Quick check for Discord invites (always flag these)."""
    import re
    content_lower = message_content.lower()
    
    discord_invite_patterns = [
        r'discord\.gg/\w+',
        r'discord\.com/invite/\w+',
        r'discordapp\.com/invite/\w+',
    ]
    
    for pattern in discord_invite_patterns:
        if re.search(pattern, content_lower):
            return True, "posted a Discord invite link"
    
    return False, ""

async def analyze_link_with_ai(message_content: str, urls: list[str]) -> tuple[bool, str]:
    """Use AI Power Grid to analyze if a message with links is a scam."""
    import json
    
    urls_text = "\n".join([f"- {url}" for url in urls])
    
    analysis_prompt = f"""
You are a security bot analyzing Discord messages for scams and phishing attempts.

Analyze this message and determine if it's a scam:

MESSAGE:
"{message_content}"

LINKS IN MESSAGE:
{urls_text}

Common scam patterns to look for:
- Fake support tickets or help desk links
- Fake airdrop or token claim links
- Fake DEX (decentralized exchange) links
- Fake wallet verification or migration links
- Phishing sites trying to steal credentials
- Suspicious domains that don't match official services
- Urgent language trying to get users to click quickly
- Promises of free tokens, airdrops, or rewards

Return ONLY a JSON object with this exact format:
{{"is_scam": true/false, "reason": "brief explanation of why it's suspicious or safe"}}

If it's a scam, be specific about what type (e.g., "fake support ticket link", "suspicious airdrop claim", "phishing site", etc.).
If it's safe, reason should be something like "appears to be legitimate" or "no scam indicators detected".

Only return the JSON object, nothing else.
"""
    
    try:
        result = await grid_client.get_answer(analysis_prompt, [])
        print(f"AI Scam Analysis Response: '{result}'")
        
        # Try to extract JSON from response
        result_clean = result.strip()
        
        # Remove markdown code blocks if present
        if result_clean.startswith('```'):
            result_clean = result_clean.split('```')[1]
            if result_clean.startswith('json'):
                result_clean = result_clean[4:]
        
        result_clean = result_clean.strip()
        
        # Parse JSON
        analysis = json.loads(result_clean)
        
        is_scam = analysis.get('is_scam', False)
        reason = analysis.get('reason', 'analyzed by AI')
        
        return is_scam, reason
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse AI scam analysis JSON: {e}")
        print(f"Raw response: '{result}'")
        # If AI fails, default to flagging it (safer)
        return True, "AI analysis failed - flagged for review"
    except Exception as e:
        print(f"Error in AI scam analysis: {e}")
        # If AI fails, default to flagging it (safer)
        return True, "AI analysis error - flagged for review"

async def handle_scam_detection(message):
    """Handle detected scam messages by creating a vote."""
    # Don't check admins
    if message.author.id == ADMIN_USER_ID:
        print(f"⏭️  Skipping scam check for admin: {message.author.display_name}")
        return False
    
    print(f"🔍 Checking message for scams: '{message.content[:100]}...' from {message.author.display_name}")
    
    # Check for URLs
    urls = extract_urls_from_message(message.content)
    print(f"🔗 Extracted {len(urls)} URL(s): {urls}")
    
    if not urls:
        # No links, not a scam
        print(f"⏭️  No URLs found in message, skipping scam check")
        return False
    
    # Check each URL for forbidden types (DEX, DeFi, support, Discord invites)
    is_scam = False
    reason = ""
    
    for url in urls:
        is_forbidden, forbidden_reason = is_forbidden_link_type(url, message.content)
        if is_forbidden:
            print(f"🚨 Forbidden link type detected: {forbidden_reason} - URL: {url}")
            is_scam = True
            reason = forbidden_reason
            break
    
    if not is_scam:
        # No forbidden links found, use AI to analyze for other scam patterns
        print(f"🔍 No forbidden link types detected. Analyzing {len(urls)} link(s) with AI for other scam patterns...")
        is_scam, reason = await analyze_link_with_ai(message.content, urls)
        print(f"🤖 AI Analysis Result: is_scam={is_scam}, reason='{reason}'")
    
    if not is_scam:
        return False
    
    # Create vote message
    vote_message_text = f"🚨 **Ban {message.author.mention} ({message.author.display_name})?**\nReason: {reason}\n\nReact ✅ to ban, ❌ to dismiss"
    
    try:
        vote_message = await message.channel.send(vote_message_text)
        
        # Bot automatically adds its own ban vote (1 vote from bot, chat needs 2 more)
        await vote_message.add_reaction('✅')
        await vote_message.add_reaction('❌')
        
        # Store vote info with bot's vote already counted
        pending_ban_votes[vote_message.id] = {
            'target_user_id': message.author.id,
            'target_user_name': message.author.display_name,
            'reason': reason,
            'original_message_id': message.id,
            'channel_id': message.channel.id,
            'upvotes': {client.user.id},  # Bot's vote counts as 1
            'downvotes': set()
        }
        
        print(f"🚨 Scam detected! Created ban vote for {message.author.display_name}: {reason} (Bot voted ✅, chat needs 2 more)")
        return True
        
    except Exception as e:
        print(f"Error creating ban vote: {e}")
        return False

def should_respond_to_message(content, author_id):
    """Basic filters - don't respond to bots, commands, or empty messages."""
    # Don't respond to bot messages
    if author_id == client.user.id:
        return False
    
    # Don't respond to commands
    if content.startswith('!'):
        return False
    
    # Don't respond to empty messages
    if not content.strip():
        return False
    
    return True

def has_obvious_trigger(content: str, message) -> bool:
    """Quick implicit filter - like human skimming. Returns True if message catches attention."""
    content_lower = content.lower()
    
    # Always respond to direct mentions
    if client.user.mentioned_in(message):
        return True
    
    # Always respond to replies to bot
    if message.reference and message.reference.message_id:
        try:
            # We'll check if it's a reply to us in the main flow, but flag it here
            return True
        except:
            pass
    
    # Question patterns
    if '?' in content:
        return True
    
    # Bot name mentioned
    if BOT_NAME.lower() in content_lower:
        return True
    
    # Explicit help requests
    help_words = ['help', 'how do', 'how to', 'what is', 'what\'s', 'explain', 'tell me about', 'can you', 'could you']
    if any(word in content_lower for word in help_words):
        return True
    
    # Explicit price queries
    price_patterns = ['price of', 'price for', 'what\'s the price', 'how much is', 'price?', 'cost']
    if any(pattern in content_lower for pattern in price_patterns):
        return True
    
    # Reaction requests
    react_patterns = ['react', 'emoji', 'thumbs up', 'thumbsup', 'checkmark', 'like this', 'react to', 'react with']
    if any(pattern in content_lower for pattern in react_patterns):
        return True
    
    # AIPG/Power Grid related keywords (might need help)
    aipg_keywords = ['aipg', 'power grid', 'staking', 'bridge', 'migration', 'worker', 'token']
    if any(keyword in content_lower for keyword in aipg_keywords):
        return True
    
    # Otherwise, skip (like human ignoring most messages)
    return False

def format_file_size(size_bytes):
    """Format file size in a human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def format_timestamp(timestamp):
    """Format a Unix timestamp to a human-readable date."""
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

async def handle_help_command(message):
    """Handle the !help command."""
    help_embed = discord.Embed(
        title="Grid Discord RAG Bot Help",
        description="I can answer questions about AI Power Grid using stored documentation.",
        color=discord.Color.green()
    )
    
    help_embed.add_field(
        name="How to use",
        value="Mention me with your question or ask naturally in the listening channel! I'll respond when I think I can help.",
        inline=False
    )
    
    help_embed.add_field(
        name="Example",
        value="@BotName What security features does AI Power Grid offer?",
        inline=False
    )
    
    help_embed.add_field(
        name="Conversation",
        value="I remember recent conversation context to provide better answers.",
        inline=False
    )
    
    # Add document management commands
    if message.author.id == ADMIN_USER_ID:
        help_embed.add_field(
            name="Document Management (Admin Only)",
            value=f"`{COMMANDS['upload']}` - Upload a document (attach a file)\n"
                  f"`{COMMANDS['list']}` - List all documents\n"
                  f"`{COMMANDS['delete']} [filename]` - Delete a document",
            inline=False
        )
    
    await message.channel.send(embed=help_embed)

async def handle_upload_command(message):
    """Handle the !upload command."""
    # Check if user is authorized
    if message.author.id != ADMIN_USER_ID:
        await message.channel.send("You don't have permission to upload documents.")
        return
    
    # Check if there are attachments
    if not message.attachments:
        await message.channel.send("Please attach a file to upload.")
        return
    
    # Process each attachment
    results = []
    for attachment in message.attachments:
        filename = attachment.filename
        file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Check if file type is supported
        if file_ext not in ['txt', 'md', 'mdx']:
            results.append(f"❌ {filename}: Unsupported file type. Only .txt, .md, and .mdx files are supported.")
            continue
        
        try:
            # Download the file content
            content = await attachment.read()
            content_str = content.decode('utf-8')
            
            # Ingest the content
            result = retriever.ingest_content(content_str, filename)
            results.append(f"✅ {result}")
        except Exception as e:
            results.append(f"❌ {filename}: Error - {str(e)}")
    
    # Send results
    result_message = "\n".join(results)
    await message.channel.send(f"Document upload results:\n{result_message}")

async def handle_list_command(message):
    """Handle the !list command."""
    # Check if user is authorized
    if message.author.id != ADMIN_USER_ID:
        await message.channel.send("You don't have permission to list documents.")
        return
    
    documents = retriever.list_documents()
    
    if not documents:
        await message.channel.send("No documents found.")
        return
    
    # Create an embed to display the documents
    list_embed = discord.Embed(
        title="Available Documents",
        description=f"Total documents: {len(documents)}",
        color=discord.Color.blue()
    )
    
    # Add each document to the embed
    for i, doc in enumerate(documents[:25]):  # Limit to 25 to avoid Discord embed limits
        file_size = format_file_size(doc['size'])
        modified_time = format_timestamp(doc['last_modified'])
        list_embed.add_field(
            name=f"{i+1}. {doc['filename']}",
            value=f"Size: {file_size}\nLast modified: {modified_time}",
            inline=True
        )
    
    # If there are more documents than we displayed
    if len(documents) > 25:
        list_embed.set_footer(text=f"Showing 25 of {len(documents)} documents. Use {COMMANDS['list']} to view more.")
    
    await message.channel.send(embed=list_embed)

async def handle_delete_command(message):
    """Handle the !delete command."""
    # Check if user is authorized
    if message.author.id != ADMIN_USER_ID:
        await message.channel.send("You don't have permission to delete documents.")
        return
    
    # Extract the filename from the command
    command_parts = message.content.split(maxsplit=1)
    if len(command_parts) < 2:
        await message.channel.send(f"Please specify a document to delete. Usage: `{COMMANDS['delete']} [filename]`")
        return
    
    filename = command_parts[1].strip()
    
    try:
        result = retriever.delete_document(filename)
        await message.channel.send(f"✅ {result}")
    except FileNotFoundError:
        await message.channel.send(f"❌ Document not found: {filename}")
    except Exception as e:
        await message.channel.send(f"❌ Error deleting document: {str(e)}")

async def classify_and_respond(message):
    """Classify if the bot should respond and generate a natural response."""
    content = message.content.strip()
    author_name = message.author.display_name
    
    # Check basic conditions first
    if not should_respond_to_message(content, message.author.id):
        return False
    
    # Add the message to channel history (always save, but don't always process)
    add_message(message.channel.id, author_name, content, author_id=message.author.id, is_bot=False)
    
    # STAGE 1: Quick implicit filter (like human skimming)
    if not has_obvious_trigger(content, message):
        print(f"⏭️  Skipped (no obvious trigger): '{content[:50]}...'")
        return False
    
    # STAGE 2: Full processing (only if we got here - message caught attention)
    print(f"\n🔍 Processing message: '{content}' from {author_name}")
    
    try:
        # Get conversation history for context
        conversation_history = format_channel_history(message.channel.id, max_messages=10)
        
        # Retrieve relevant documents for the response
        context = retriever.get_relevant_context(content)
        
        # Get crypto market data if relevant
        crypto_context = await get_crypto_context(content)
        
        # Get mood, memories, and recent happenings
        mood_info = format_mood()
        memories_info = format_memories()
        happenings_info = format_recent_happenings()
        
        # Get channel information
        channel_name = message.channel.name if hasattr(message.channel, 'name') else f"Channel {message.channel.id}"
        channel_topic = ""
        if hasattr(message.channel, 'topic') and message.channel.topic:
            channel_topic = message.channel.topic
        elif hasattr(message.channel, 'description') and message.channel.description:
            channel_topic = message.channel.description
        
        channel_info = f"Channel: #{channel_name}"
        if channel_topic:
            channel_info += f"\nChannel description: {channel_topic}"
        
        # Single API call with JSON response
        current_time = datetime.datetime.now()
        timestamp = current_time.strftime("%B %d, %Y at %I:%M %p")
        
        single_prompt = f"""
You are {BOT_NAME}, a helpful Discord bot for AI Power Grid discussions.

Current time: {timestamp}

{channel_info}

{mood_info}
{memories_info}
{happenings_info}

Recent conversation:
{conversation_history}

Latest message from {author_name}: "{content}"

Context from AI Power Grid documentation:
{chr(10).join([f"[{i+1}] {item['text']}" for i, item in enumerate(context)])}
{crypto_context}

DEFAULT BEHAVIOR: Stay quiet unless you have something valuable to add. Most messages don't need a response - that's normal and expected. Think like a human: you naturally stay quiet most of the time.

Only respond when:
- You're directly mentioned or asked a question
- Someone needs help you can provide
- You have relevant information that adds value
- Someone asks you to react/acknowledge something

DO NOT respond to:
- Casual conversation between others
- General statements that don't need acknowledgment
- Messages where you don't have anything useful to add
- Off-topic discussions unless directly asked

You are fun but informative, and you are a discord entity for the AI Power Grid community. You have a wealth of knowledge you can draw upon to answer questions and provide support.

IMPORTANT: Respond naturally in plain text. No templates, no structured formats, no embeds. Just talk like a normal person. If someone asks about crypto prices, just tell them naturally - don't use any special formatting or templates.

EMOJI REACTIONS: For short confirmations, affirmatives, or acknowledgments, prefer using emoji reactions instead of text messages. You can use any emoji that fits the situation - be creative! Common uses:
- Confirmations/agreement: 👍 ✅ 👌
- Disagreement/no: 👎 ❌
- Appreciation: ❤️ 🙏
- Excitement/celebration: 🎉 🔥 🚀
- Or any other emoji that fits the context

Only send a text message if you need to provide information, ask a question, or explain something. For simple confirmations/acknowledgments, just react with an emoji.

If you decide that you should respond, return a JSON object like:
{{"respond": true, "message": "your response here"}}

For short confirmations/affirmatives, prefer just reacting (use any appropriate emoji):
{{"respond": true, "react": "👍"}}

Or combine both if you need to say something AND acknowledge:
{{"respond": true, "message": "your response here", "react": "👍"}}

You can use any Discord emoji - be creative and pick what fits best!

If you should NOT respond (most cases), return:
{{"respond": false}}

Only return valid JSON. Default to staying quiet - only respond when you have value to add.
"""
        
        # Get response from Grid API (no typing indicator during decision)
        result = await grid_client.get_answer(single_prompt, [])
        
        print(f"API Response: '{result}'")
        
        # Try to parse JSON response
        try:
            import json
            # Clean up the response to extract JSON
            result_clean = result.strip()
            if result_clean.startswith('```json'):
                result_clean = result_clean[7:]
            if result_clean.endswith('```'):
                result_clean = result_clean[:-3]
            result_clean = result_clean.strip()
            
            response_data = json.loads(result_clean)
            
            if response_data.get("respond", False):
                response_message = response_data.get("message", "")
                react_emoji = response_data.get("react", None)
                
                # Handle reactions - check if we need to react to a previous message
                if react_emoji:
                    target_message = message  # Default to current message
                    
                    # Check if user wants to react to a previous message
                    content_lower = content.lower()
                    needs_previous = any(phrase in content_lower for phrase in [
                        'few messages ago', 'previous message', 'earlier message', 
                        'that message', 'my message', 'a few messages ago'
                    ])
                    
                    if needs_previous:
                        # Fetch recent messages to find the target
                        try:
                            messages_found = []
                            async for msg in message.channel.history(limit=20):
                                # Skip the current message and bot messages
                                if msg.id == message.id or msg.author == client.user:
                                    continue
                                messages_found.append(msg)
                            
                            # If they said "my message", find their message
                            if 'my message' in content_lower:
                                user_messages = [msg for msg in messages_found if msg.author.id == message.author.id]
                                
                                # If they also said "few messages ago", skip forward a bit
                                if 'few' in content_lower or 'several' in content_lower:
                                    # Find their message that's a few back (skip first 1-2 of their messages)
                                    skip_own = 1 if len(user_messages) > 1 else 0
                                    if len(user_messages) > skip_own:
                                        target_message = user_messages[skip_own]
                                        print(f"Found user's message {skip_own+1} back: {target_message.id} - '{target_message.content[:50]}...'")
                                    elif len(user_messages) > 0:
                                        target_message = user_messages[0]
                                        print(f"Found user's most recent message: {target_message.id} - '{target_message.content[:50]}...'")
                                else:
                                    # Just "my message" - find their most recent
                                    if len(user_messages) > 0:
                                        target_message = user_messages[0]
                                        print(f"Found user's most recent message: {target_message.id} - '{target_message.content[:50]}...'")
                            # Otherwise, find a message a few back (skip 1-3 messages)
                            else:
                                # Try to find message 2-4 messages back
                                skip_count = 2  # Default: 2 messages back
                                if 'few' in content_lower or 'several' in content_lower:
                                    skip_count = 3
                                
                                if len(messages_found) > skip_count:
                                    target_message = messages_found[skip_count]
                                    print(f"Found message {skip_count} back: {target_message.id} - '{target_message.content[:50]}...'")
                                elif len(messages_found) > 0:
                                    # Fallback to first non-bot message found
                                    target_message = messages_found[0]
                                    print(f"Found first previous message: {target_message.id} - '{target_message.content[:50]}...'")
                                    
                        except Exception as e:
                            print(f"Error fetching message history: {e}")
                    
                    try:
                        await target_message.add_reaction(react_emoji)
                        print(f"Reacted with {react_emoji} to message {target_message.id} from {target_message.author.display_name}")
                    except Exception as e:
                        print(f"Error adding reaction: {e}")
                
                if response_message:
                    # Add bot response to channel history
                    add_message(message.channel.id, BOT_NAME, response_message, author_id=client.user.id, is_bot=True)
                    
                    # Show typing indicator for 1-2 seconds before responding
                    async with message.channel.typing():
                        import asyncio
                        await asyncio.sleep(1.5)  # 1.5 second delay
                    
                    # Send the response naturally
                    await message.channel.send(response_message)
                    print(f"Responding with: '{response_message}'")
                    return True
                elif react_emoji:
                    # Only reacted, no message
                    return True
                else:
                    print("Response data has respond=true but no message or reaction")
                    return False
            else:
                print(f"Not responding to message: '{content}'")
                return False
                
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Raw response: '{result}'")
            return False
        
    except Exception as e:
        print(f"Error in classify_and_respond: {str(e)}")
        return False

@client.event
async def on_reaction_add(reaction, user):
    """Handle reactions on ban vote messages."""
    # Ignore bot's own reactions
    if user == client.user:
        return
    
    # Check if this is a ban vote message
    if reaction.message.id not in pending_ban_votes:
        return
    
    vote_info = pending_ban_votes[reaction.message.id]
    
    # Ignore reactions from the target user
    if user.id == vote_info['target_user_id']:
        return
    
    # Handle upvote (✅)
    if str(reaction.emoji) == '✅':
        vote_info['upvotes'].add(user.id)
        print(f"✅ Upvote added for ban vote. Total: {len(vote_info['upvotes'])}/{BAN_VOTE_THRESHOLD}")
        
        # Check if threshold met
        if len(vote_info['upvotes']) >= BAN_VOTE_THRESHOLD:
            await execute_ban(reaction.message, vote_info)
    
    # Handle downvote (❌)
    elif str(reaction.emoji) == '❌':
        vote_info['downvotes'].add(user.id)
        print(f"❌ Downvote added for ban vote. Total: {len(vote_info['downvotes'])}/{DISMISS_VOTE_THRESHOLD}")
        
        # If downvotes reach threshold, dismiss
        if len(vote_info['downvotes']) >= DISMISS_VOTE_THRESHOLD:
            await reaction.message.edit(content=f"❌ Vote dismissed. {vote_info['target_user_name']} will not be banned.")
            del pending_ban_votes[reaction.message.id]

async def execute_ban(vote_message, vote_info):
    """Execute the ban after threshold is met."""
    try:
        channel = vote_message.channel
        target_user_id = vote_info['target_user_id']
        target_user_name = vote_info['target_user_name']
        reason = vote_info['reason']
        
        # Get the member object
        member = channel.guild.get_member(target_user_id)
        if not member:
            await vote_message.edit(content=f"❌ User {target_user_name} not found in server.")
            del pending_ban_votes[vote_message.id]
            return
        
        # Ban the user
        await member.ban(reason=f"Community vote: {reason}")
        
        # Update vote message
        await vote_message.edit(content=f"✅ **{target_user_name} has been banned.**\nReason: {reason}\nVotes: {len(vote_info['upvotes'])} ✅")
        
        # Clean up
        del pending_ban_votes[vote_message.id]
        
        print(f"✅ Banned {target_user_name} ({target_user_id}) - Reason: {reason}")
        
    except discord.Forbidden:
        await vote_message.edit(content=f"❌ Missing permissions to ban {target_user_name}.")
        del pending_ban_votes[vote_message.id]
    except Exception as e:
        await vote_message.edit(content=f"❌ Error banning user: {str(e)}")
        del pending_ban_votes[vote_message.id]
        print(f"Error executing ban: {e}")

@client.event
async def on_message(message):
    """Event called when a message is received."""
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Check for scam messages first
    if await handle_scam_detection(message):
        return  # Don't process further if scam detected
    
    # Handle document management commands in allowed channels
    if message.channel.id in ALLOWED_CHANNEL_IDS:
        # Handle help command
        if message.content.startswith(COMMANDS['help']):
            await handle_help_command(message)
            return
        
        # Handle upload command
        if message.content.startswith(COMMANDS['upload']):
            await handle_upload_command(message)
            return
        
        # Handle list command
        if message.content.startswith(COMMANDS['list']):
            await handle_list_command(message)
            return
        
        # Handle delete command
        if message.content.startswith(COMMANDS['delete']):
            await handle_delete_command(message)
            return
    
    # Handle direct file uploads (if user is admin and in allowed channel)
    if (message.author.id == ADMIN_USER_ID and 
        message.channel.id in ALLOWED_CHANNEL_IDS and 
        message.attachments and 
        not message.content.startswith('!')):
        
        # If this appears to be just a file upload with no command
        if not message.content or message.content.isspace():
            await handle_upload_command(message)
            return
    
    # Listen for messages in ALL channels (automatic classification)
    # Return early if we already responded to avoid duplicate handling
    if await classify_and_respond(message):
        return
    
    # Handle replied messages regardless of channel
    if message.reference and message.reference.message_id:
        try:
            # Get the message being replied to
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
            
            # Check if the referenced message is from our bot
            if referenced_message.author == client.user:
                # Extract the question from the reply
                question = message.content.strip()
                
                # If no question was provided, ignore
                if not question:
                    return
                
                # Send a typing indicator to show the bot is processing
                async with message.channel.typing():
                    try:
                        # Retrieve relevant documents
                        context = retriever.get_relevant_context(question)
                        
                        # Send to Grid API for answer
                        answer = await grid_client.get_answer(question, context)
                        
                        # Send natural text response (no embeds)
                        await message.channel.send(answer)
                    except Exception as e:
                        await message.channel.send(f"Error: {str(e)}")
                
                # We've handled the reply, so return
                return
        except Exception as e:
            print(f"Error handling reply: {str(e)}")
    
    # Check if the bot is mentioned in the message (works in all channels)
    if client.user.mentioned_in(message):
        # Extract the question by removing the mention
        content = message.content
        mention = f'<@{client.user.id}>'
        question = content.replace(mention, '').strip()
        
        # If no question was provided, show help message
        if not question:
            await handle_help_command(message)
            return
        
        # Send a typing indicator to show the bot is processing
        async with message.channel.typing():
            try:
                # Retrieve relevant documents
                context = retriever.get_relevant_context(question)
                
                # Send to Grid API for answer
                answer = await grid_client.get_answer(question, context)
                
                # Send natural text response (no embeds)
                await message.channel.send(answer)
            except Exception as e:
                await message.channel.send(f"Error: {str(e)}")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN) 