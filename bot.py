import os
import discord
import datetime
from io import BytesIO
from dotenv import load_dotenv
from retriever import DocumentRetriever
from grid_client import GridClient
from coingecko_mcp import get_crypto_context, generate_chart_image

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

# GitHub repo configuration for auto-ingestion
GITHUB_REPO = os.getenv('GITHUB_REPO', '')  # Format: owner/repo
GITHUB_REPO_PATH = os.getenv('GITHUB_REPO_PATH', '')  # Optional path within repo
GITHUB_REPO_BRANCH = os.getenv('GITHUB_REPO_BRANCH', 'main')  # Branch to pull from
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Optional token for private repos

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True  # Make sure we have message intents
client = discord.Client(intents=intents)

# Initialize document retriever and Grid client
retriever = DocumentRetriever()
grid_client = GridClient()

# Store conversation history
channel_message_history = {}
MAX_MESSAGE_HISTORY = 25  # Number of messages to remember per channel

# Command prefixes
COMMANDS = {
    'help': '!help',
    'upload': '!upload',
    'list': '!list',
    'delete': '!delete',
    'sync-github': '!sync-github'
}

@client.event
async def on_ready():
    """Event called when the bot is ready."""
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print(f'Bot name: {BOT_NAME}')
    print(f'Listening in ALL channels for automatic responses')
    print(f'Admin commands allowed in channels: {ALLOWED_CHANNEL_IDS}')
    print(f'Admin user ID: {ADMIN_USER_ID}')
    
    # Auto-ingest from GitHub repo if configured
    if GITHUB_REPO:
        if "/" not in GITHUB_REPO:
            print(f'Warning: Invalid GITHUB_REPO format "{GITHUB_REPO}". Expected format: owner/repo')
        else:
            owner, repo = GITHUB_REPO.split("/", 1)
            print(f'🔄 Auto-ingesting from GitHub repo: {owner}/{repo} (path: {GITHUB_REPO_PATH or "root"}, branch: {GITHUB_REPO_BRANCH})')
            try:
                # Run ingestion in background task (don't await - let it run in background)
                import asyncio
                asyncio.create_task(ingest_github_on_startup(owner, repo))
            except Exception as e:
                print(f'Error starting GitHub ingestion: {str(e)}')
    
    print('------')

def get_channel_history(channel_id):
    """Get the conversation history for a channel."""
    if channel_id not in channel_message_history:
        channel_message_history[channel_id] = []
    return channel_message_history[channel_id]

def add_to_channel_history(channel_id, author_name, content, is_bot=False):
    """Add a message to the channel's history."""
    history = get_channel_history(channel_id)
    history.append({
        'author': author_name,
        'content': content,
        'is_bot': is_bot,
        'timestamp': datetime.datetime.now()
    })
    # Keep only the most recent messages
    channel_message_history[channel_id] = history[-MAX_MESSAGE_HISTORY:]

def format_channel_history(channel_id, max_messages=25):
    """Format the channel history for context."""
    history = get_channel_history(channel_id)
    if not history:
        return ""
    
    # Get the most recent messages
    recent_messages = history[-max_messages:]
    
    formatted_history = "Recent chat (last messages):\n"
    for msg in recent_messages:
        author = msg['author']
        content = msg['content']
        formatted_history += f"{author}: {content}\n"
    
    return formatted_history

def should_respond_to_message(content, author_id):
    """ALWAYS let the AI decide - minimal checks only."""
    # Don't respond to bot messages
    if author_id == client.user.id:
        return False
    
    # Don't respond to commands
    if content.startswith('!'):
        return False
    
    # Don't respond to empty messages
    if not content.strip():
        return False
    
    # Everything else - let the AI decide
    print(f"Message passed basic checks, letting AI decide: '{content}'")
    return True

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

async def ingest_github_on_startup(owner: str, repo: str):
    """Ingest from GitHub repo on startup (runs in background)."""
    import asyncio
    try:
        # Run ingestion in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            retriever.ingest_from_github_repo,
            owner,
            repo,
            GITHUB_REPO_PATH,
            GITHUB_REPO_BRANCH,
            GITHUB_TOKEN
        )
        print(f'✅ {result}')
    except Exception as e:
        print(f'❌ Error ingesting from GitHub on startup: {str(e)}')

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
                  f"`{COMMANDS['delete']} [filename]` - Delete a document\n"
                  f"`{COMMANDS['sync-github']} owner/repo [path] [branch]` - Sync .md files from GitHub repo",
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

async def handle_sync_github_command(message):
    """Handle the !sync-github command."""
    # Check if user is authorized
    if message.author.id != ADMIN_USER_ID:
        await message.channel.send("You don't have permission to sync from GitHub.")
        return
    
    # Extract the repo from the command
    # Format: !sync-github owner/repo [path] [branch]
    command_parts = message.content.split()
    if len(command_parts) < 2:
        await message.channel.send(
            f"Please specify a GitHub repository. Usage: `{COMMANDS['sync-github']} owner/repo [path] [branch]`\n"
            f"Example: `{COMMANDS['sync-github']} AIPowerGrid/docs` or `{COMMANDS['sync-github']} user/repo docs/main master`"
        )
        return
    
    repo_str = command_parts[1]
    if "/" not in repo_str:
        await message.channel.send("❌ Invalid format. Use `owner/repo` (e.g., `AIPowerGrid/docs`)")
        return
    
    owner, repo = repo_str.split("/", 1)
    path = command_parts[2] if len(command_parts) > 2 else ""
    branch = command_parts[3] if len(command_parts) > 3 else "main"
    
    # Use the global GitHub token
    
    # Send processing message
    await message.channel.send(f"🔄 Syncing markdown files from `{owner}/{repo}`...")
    
    try:
        result = retriever.ingest_from_github_repo(
            repo_owner=owner,
            repo_name=repo,
            path=path,
            branch=branch,
            token=GITHUB_TOKEN
        )
        await message.channel.send(f"✅ {result}")
    except Exception as e:
        await message.channel.send(f"❌ Error syncing from GitHub: {str(e)}")

async def classify_and_respond(message):
    """Classify if the bot should respond and generate a natural response."""
    content = message.content.strip()
    author_name = message.author.display_name
    
    print(f"\n🔍 Processing message: '{content}' from {author_name}")
    
    # Add the message to channel history
    add_to_channel_history(message.channel.id, author_name, content)
    
    # Check basic conditions first
    if not should_respond_to_message(content, message.author.id):
        return False
    
    try:
        # Get conversation history for context
        conversation_history = format_channel_history(message.channel.id, max_messages=25)
        
        # Retrieve relevant documents for the response
        context = retriever.get_relevant_context(content)
        
        # Get crypto market data if relevant
        crypto_context = await get_crypto_context(content)
        
        # Single API call with JSON response
        current_time = datetime.datetime.now()
        timestamp = current_time.strftime("%B %d, %Y at %I:%M %p")
        
        # Check if message is from admin
        is_admin = message.author.id == ADMIN_USER_ID
        admin_note = f"\nNote: The user '{author_name}' (ID: {message.author.id}) is the server admin." if is_admin else ""
        
        # Get channel name and topic for context
        channel_name = message.channel.name if hasattr(message.channel, 'name') else "unknown"
        channel_topic = message.channel.topic if hasattr(message.channel, 'topic') and message.channel.topic else ""
        channel_info = f"Current channel: #{channel_name}"
        if channel_topic:
            channel_info += f"\nChannel description: {channel_topic}"
        
        # Get admin name for context (if available)
        admin_name_context = ""
        if is_admin:
            admin_name_context = f"\nIMPORTANT: {author_name} is the server admin - pay extra attention to their messages and be more likely to respond or react."
        
        single_prompt = f"""
You're {BOT_NAME}, just hanging out in this Discord server reading messages as they come in.

{channel_info}
Current time: {timestamp}

You just saw this message from {author_name}: "{content}"
{admin_name_context}

Recent chat (last 25 messages):
{conversation_history}

Context you know about AI Power Grid:
{chr(10).join([f"[{i+1}] {item['text']}" for i, item in enumerate(context)])}
{crypto_context}

Think like a human reading Discord:
- Did someone mention you or ask you something? → Respond or react
- Is the admin ({author_name if is_admin else "someone"}) saying something? → Pay extra attention, more likely to engage
- Something funny/interesting/you agree with? → React with an emoji (humans do this all the time)
- A question that needs an answer? → Help if you know it
- People talking to each other? → Only jump in if relevant, otherwise just react or stay quiet

Your personality: Direct, snarky when appropriate, crypto-native, helpful but not a pushover. No fluff.

CRITICAL INFORMATION ABOUT AIPG:
- ⚠️ PROOF-OF-WORK MINING IS DEAD - The PoW chain is deprecated and no longer operational
- ✅ STAKING ON BASE IS LIVE - Users should stake AIPG on Base network, not mine on PoW
- Staking interface: https://aipowergrid.io/staking
- Staking contract: 0x3ED14A6D5A48614D77f313389611410d38fd8277 on Base
- When anyone mentions mining, PoW, or asks how to earn AIPG, DIRECTLY tell them:
  "PoW mining is dead. Stake your AIPG on Base instead: https://aipowergrid.io/staking"
- Do NOT provide price information unless someone EXPLICITLY asks about price (e.g., "what's the price", "how much is", "show me the price")

When providing crypto price information (ONLY when explicitly asked):
- You CAN look up ANY cryptocurrency by name or symbol using CoinGecko's search - try searching first before saying you don't know
- If someone asks about a coin you don't recognize, search for it first before saying you don't know
- Link to CoinGecko page: https://www.coingecko.com/en/coins/[coin-name] (use this for price info, charts, market data)
- Only mention Uniswap when someone asks about BUYING or TRADING: https://app.uniswap.org/swap?outputCurrency=0xa1c0deCaFE3E9Bf06A5F29B7015CD373a9854608&chain=base
- For price questions, always use CoinGecko link, not Uniswap

Emoji reactions are normal - use them often like humans do:
- 👍 = agree/correct/good point
- 😂 = funny  
- ❤️ = like/appreciate
- ✅ = confirmed/works
- 🤔 = thinking about it
- 😮 = surprised/interesting
- 🎉 = celebration/excitement
- 🔥 = something is hot/good
- 💀 = something is so funny/ridiculous it killed you
- Or any other emoji that fits - be creative, humans use tons of emojis

Admin priority: If {author_name if is_admin else "the admin"} says something, you're more likely to respond or react. They're important.

Return JSON only:
- {{"respond": true, "message": "text here"}} - send a message
- {{"respond": true, "react": "👍"}} - just react (use any emoji)
- {{"respond": true, "message": "text", "react": "👍"}} - both
- {{"respond": false}} - do nothing

Only valid JSON. No other text.
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
                emoji_reaction = response_data.get("react", "")
                
                # Handle emoji reaction (if present)
                if emoji_reaction:
                    try:
                        await message.add_reaction(emoji_reaction)
                        print(f"Reacted with: {emoji_reaction}")
                    except Exception as e:
                        print(f"Error adding reaction: {e}")
                
                # Handle text response (if present)
                if response_message:
                    # Add bot response to channel history
                    add_to_channel_history(message.channel.id, BOT_NAME, response_message, is_bot=True)
                    
                    # Check if this is a price-related message and generate chart
                    content_lower = content.lower()
                    coin_id = None
                    coin_name = None
                    if "aipg" in content_lower or "ai power grid" in content_lower:
                        coin_id = "ai-power-grid"
                        coin_name = "AIPG"
                    elif "bitcoin" in content_lower or "btc" in content_lower:
                        coin_id = "bitcoin"
                        coin_name = "Bitcoin"
                    elif "ethereum" in content_lower or "eth" in content_lower:
                        coin_id = "ethereum"
                        coin_name = "Ethereum"
                    
                    # Check if message asks about price/chart
                    is_price_query = any(word in content_lower for word in ["price", "chart", "graph", "how much", "what's the", "cost", "show me"])
                    is_chart_request = any(word in content_lower for word in ["chart", "graph", "show me"])
                    
                    # Show typing indicator while generating chart
                    async with message.channel.typing():
                        import asyncio
                        
                        # Generate chart if it's a price query OR explicit chart request
                        chart_file = None
                        if coin_id and (is_price_query or is_chart_request):
                            try:
                                print(f"📊 Generating chart for {coin_name} (coin_id={coin_id})...")
                                chart_buffer = await generate_chart_image(coin_id, coin_name, days=7, use_candlesticks=True)
                                if chart_buffer:
                                    chart_file = discord.File(chart_buffer, filename=f"{coin_id}_chart.png")
                                    print(f"✅ Generated chart for {coin_name} ({len(chart_buffer.getvalue())} bytes)")
                                else:
                                    print(f"⚠️ Chart generation returned None for {coin_name}")
                            except Exception as e:
                                print(f"❌ Error generating chart: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            if coin_id:
                                print(f"⚠️ Chart not generated: coin_id={coin_id}, is_price_query={is_price_query}, is_chart_request={is_chart_request}")
                        
                        # Small delay before sending
                        await asyncio.sleep(0.5)
                    
                    # Send the response with chart embed if available
                    if chart_file:
                        # Create embed with chart
                        embed = discord.Embed(
                            title=f"{coin_name} Price",
                            description=response_message,
                            color=0x8cc84b  # CoinGecko green
                        )
                        embed.set_image(url=f"attachment://{coin_id}_chart.png")
                        embed.add_field(
                            name="View on CoinGecko",
                            value=f"https://www.coingecko.com/en/coins/{coin_id}",
                            inline=False
                        )
                        await message.channel.send(embed=embed, file=chart_file)
                        print(f"Sent response with chart embed")
                    else:
                        # Check if we should use DexScreener chart URL instead
                        from coingecko_mcp import get_dexscreener_url
                        
                        # Use DexScreener for AIPG since it's DEX-focused
                        if coin_id == "ai-power-grid":
                            dex_url = get_dexscreener_url("0xa1c0deCaFE3E9Bf06A5F29B7015CD373a9854608", "base")
                            # Create embed with DexScreener chart
                            embed = discord.Embed(
                                title=f"{coin_name} Price",
                                description=response_message,
                                color=0x6366f1  # DexScreener purple-ish
                            )
                            # DexScreener doesn't provide direct image URLs, but we can link to it
                            embed.add_field(
                                name="📊 Chart on DexScreener",
                                value=f"[View Live Chart]({dex_url})",
                                inline=False
                            )
                            embed.add_field(
                                name="📈 CoinGecko",
                                value=f"[Price & Market Data](https://www.coingecko.com/en/coins/{coin_id})",
                                inline=False
                            )
                            await message.channel.send(embed=embed)
                            print(f"Sent response with DexScreener chart link")
                        else:
                            # Send the response naturally
                            await message.channel.send(response_message)
                            print(f"Responding with: '{response_message}'")
                    return True
                elif emoji_reaction:
                    # Only reaction, no message - that's fine
                    print(f"Only reacted with emoji: {emoji_reaction}")
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
async def on_message(message):
    """Event called when a message is received."""
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
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
        
        # Handle sync-github command
        if message.content.startswith(COMMANDS['sync-github']):
            await handle_sync_github_command(message)
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
                        # Get conversation history
                        conversation_history = format_channel_history(message.channel.id, max_messages=10)
                        
                        # Retrieve relevant documents
                        context = retriever.get_relevant_context(question)
                        
                        # Get crypto market data if relevant
                        crypto_context = await get_crypto_context(question)
                        
                        # Build prompt for reply
                        current_time = datetime.datetime.now()
                        timestamp = current_time.strftime("%B %d, %Y at %I:%M %p")
                        
                        is_admin = message.author.id == ADMIN_USER_ID
                        admin_note = f"\nNote: The user '{message.author.display_name}' (ID: {message.author.id}) is the server admin." if is_admin else ""
                        
                        # Get channel name for context
                        channel_name = message.channel.name if hasattr(message.channel, 'name') else "unknown"
                        
                        prompt = f"""
You are {BOT_NAME}, a member of this Discord server.

Current channel: #{channel_name}
Current time: {timestamp}
{admin_note}

Recent conversation:
{conversation_history}

User asked: "{question}"

Context from AI Power Grid documentation:
{chr(10).join([f"[{i+1}] {item['text']}" for i, item in enumerate(context)])}
{crypto_context}

CRITICAL INFORMATION ABOUT AIPG:
- ⚠️ PROOF-OF-WORK MINING IS DEAD - The PoW chain is deprecated and no longer operational
- ✅ STAKING ON BASE IS LIVE - Users should stake AIPG on Base network, not mine on PoW
- Staking interface: https://aipowergrid.io/staking
- When anyone mentions mining, PoW, or asks how to earn AIPG, DIRECTLY tell them:
  "PoW mining is dead. Stake your AIPG on Base instead: https://aipowergrid.io/staking"
- Do NOT provide price information unless someone EXPLICITLY asks about price

Answer naturally and conversationally. If you don't know something, say it casually like "not sure about that" or "don't have info on that" - never say "I don't have enough information to answer this question" or any formal corporate-speak.
Be brief and helpful. No embeds, just natural text response.

When providing crypto price information (ONLY when explicitly asked):
- You CAN look up ANY cryptocurrency by name or symbol using CoinGecko's search - try searching first before saying you don't know
- If someone asks about a coin you don't recognize, search for it first before saying you don't know
- Link to CoinGecko page: https://www.coingecko.com/en/coins/[coin-name] (use this for price info, charts, market data)
- Only mention Uniswap when someone asks about BUYING or TRADING: https://app.uniswap.org/swap?outputCurrency=0xa1c0deCaFE3E9Bf06A5F29B7015CD373a9854608&chain=base
- For price questions, always use CoinGecko link, not Uniswap
"""
                        
                        # Send to Grid API for answer
                        answer = await grid_client.get_answer(prompt, [])
                        
                        # Send natural response (no embed)
                        await message.channel.send(answer)
                        
                        # Add bot response to history
                        add_to_channel_history(message.channel.id, BOT_NAME, answer, is_bot=True)
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
        
        # Add to channel history
        add_to_channel_history(message.channel.id, message.author.display_name, content)
        
        # Send a typing indicator to show the bot is processing
        async with message.channel.typing():
            try:
                # Get conversation history
                conversation_history = format_channel_history(message.channel.id, max_messages=10)
                
                # Retrieve relevant documents
                context = retriever.get_relevant_context(question)
                
                # Get crypto market data if relevant
                crypto_context = await get_crypto_context(question)
                
                # Build prompt similar to classify_and_respond but for direct mentions
                current_time = datetime.datetime.now()
                timestamp = current_time.strftime("%B %d, %Y at %I:%M %p")
                
                is_admin = message.author.id == ADMIN_USER_ID
                admin_note = f"\nNote: The user '{message.author.display_name}' (ID: {message.author.id}) is the server admin." if is_admin else ""
                
                # Get channel name and topic for context
                channel_name = message.channel.name if hasattr(message.channel, 'name') else "unknown"
                channel_topic = message.channel.topic if hasattr(message.channel, 'topic') and message.channel.topic else ""
                channel_info = f"Current channel: #{channel_name}"
                if channel_topic:
                    channel_info += f"\nChannel description: {channel_topic}"
                
                prompt = f"""
You are {BOT_NAME}, a member of this Discord server.

{channel_info}
Current time: {timestamp}
{admin_note}

Recent conversation:
{conversation_history}

User asked: "{question}"

Context from AI Power Grid documentation:
{chr(10).join([f"[{i+1}] {item['text']}" for i, item in enumerate(context)])}
{crypto_context}

CRITICAL INFORMATION ABOUT AIPG:
- ⚠️ PROOF-OF-WORK MINING IS DEAD - The PoW chain is deprecated and no longer operational
- ✅ STAKING ON BASE IS LIVE - Users should stake AIPG on Base network, not mine on PoW
- Staking interface: https://aipowergrid.io/staking
- When anyone mentions mining, PoW, or asks how to earn AIPG, DIRECTLY tell them:
  "PoW mining is dead. Stake your AIPG on Base instead: https://aipowergrid.io/staking"
- Do NOT provide price information unless someone EXPLICITLY asks about price

Answer naturally and conversationally. If you don't know something, say it casually like "not sure about that" or "don't have info on that" - never say "I don't have enough information to answer this question" or any formal corporate-speak.
Be brief and helpful. No embeds, just natural text response.

When providing crypto price information (ONLY when explicitly asked):
- You CAN look up ANY cryptocurrency by name or symbol using CoinGecko's search - try searching first before saying you don't know
- If someone asks about a coin you don't recognize, search for it first before saying you don't know
- Link to CoinGecko page: https://www.coingecko.com/en/coins/[coin-name] (use this for price info, charts, market data)
- Only mention Uniswap when someone asks about BUYING or TRADING: https://app.uniswap.org/swap?outputCurrency=0xa1c0deCaFE3E9Bf06A5F29B7015CD373a9854608&chain=base
- For price questions, always use CoinGecko link, not Uniswap
"""
                
                # Send to Grid API for answer
                answer = await grid_client.get_answer(prompt, [])
                
                # Send natural response (no embed)
                await message.channel.send(answer)
                
                # Add bot response to history
                add_to_channel_history(message.channel.id, BOT_NAME, answer, is_bot=True)
            except Exception as e:
                await message.channel.send(f"Error: {str(e)}")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN) 