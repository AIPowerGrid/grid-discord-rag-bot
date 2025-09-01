import os
import discord
import datetime
from io import BytesIO
from dotenv import load_dotenv
from retriever import DocumentRetriever
from grid_client import GridClient

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
client = discord.Client(intents=intents)

# Initialize document retriever and Grid client
retriever = DocumentRetriever()
grid_client = GridClient()

# Store conversation history
channel_message_history = {}
MAX_MESSAGE_HISTORY = 10  # Number of messages to remember per channel

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
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print(f'Bot name: {BOT_NAME}')
    print(f'Listening in channels: {ALLOWED_CHANNEL_IDS}')
    print(f'Listening for messages in channel: {LISTENING_CHANNEL_ID}')
    print(f'Admin user ID: {ADMIN_USER_ID}')
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

def format_channel_history(channel_id, max_messages=10):
    """Format the channel history for context."""
    history = get_channel_history(channel_id)
    if not history:
        return ""
    
    # Get the most recent messages
    recent_messages = history[-max_messages:]
    
    formatted_history = "Recent conversation:\n"
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
    
    print(f"\n🔍 Processing message: '{content}' from {author_name}")
    
    # Add the message to channel history
    add_to_channel_history(message.channel.id, author_name, content)
    
    # Check basic conditions first
    if not should_respond_to_message(content, message.author.id):
        return False
    
    try:
        # Get conversation history for context
        conversation_history = format_channel_history(message.channel.id, max_messages=10)
        
        # Retrieve relevant documents for the response
        context = retriever.get_relevant_context(content)
        
                # Single API call with JSON response
        current_time = datetime.datetime.now()
        timestamp = current_time.strftime("%B %d, %Y at %I:%M %p")
        
        single_prompt = f"""
You are {BOT_NAME}, a helpful Discord bot for AI Power Grid discussions.

Current time: {timestamp}

Recent conversation:
{conversation_history}

Latest message from {author_name}: "{content}"

Context from AI Power Grid documentation:
{chr(10).join([f"[{i+1}] {item['text']}" for i, item in enumerate(context)])}

Only respond if someone is asking for help or talking to you already.
Be conversational but selective. Don't respond to every casual remark, but feel free to engage in ongoing discussions when it makes sense.
You are fun but informative, and you are a discord entity for the AI Power Grid community. You have a wealth of knoweldge you can draw upon to answer questions and provide support.
If you decide that you should respond, return a JSON object like:
{{"respond": true, "message": "your response here"}}

If you should NOT respond, return:
{{"respond": false}}

Only return valid JSON. And only respond if you deem it necessary, no need to be overly chatty.
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
                if response_message:
                    # Add bot response to channel history
                    add_to_channel_history(message.channel.id, BOT_NAME, response_message, is_bot=True)
                    
                    # Show typing indicator for 1-2 seconds before responding
                    async with message.channel.typing():
                        import asyncio
                        await asyncio.sleep(1.5)  # 1.5 second delay
                    
                    # Send the response naturally
                    await message.channel.send(response_message)
                    print(f"Responding with: '{response_message}'")
                    return True
                else:
                    print("Response data has respond=true but no message")
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
    
    # Handle direct file uploads (if user is admin and in allowed channel)
    if (message.author.id == ADMIN_USER_ID and 
        message.channel.id in ALLOWED_CHANNEL_IDS and 
        message.attachments and 
        not message.content.startswith('!')):
        
        # If this appears to be just a file upload with no command
        if not message.content or message.content.isspace():
            await handle_upload_command(message)
            return
    
    # Listen for messages in the designated listening channel
    if LISTENING_CHANNEL_ID and message.channel.id == LISTENING_CHANNEL_ID:
        await classify_and_respond(message)
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
                        
                        # Create and send response
                        embed = discord.Embed(
                            title="Answer",
                            description=answer,
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Question", value=question, inline=False)
                        
                        await message.channel.send(embed=embed)
                    except Exception as e:
                        await message.channel.send(f"Error: {str(e)}")
                
                # We've handled the reply, so return
                return
        except Exception as e:
            print(f"Error handling reply: {str(e)}")
    
    # Regular mention handling - only in allowed channels
    if ALLOWED_CHANNEL_IDS and message.channel.id not in ALLOWED_CHANNEL_IDS:
        return
    
    # Check if the bot is mentioned in the message
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
                
                # Create and send response
                embed = discord.Embed(
                    title="Answer",
                    description=answer,
                    color=discord.Color.blue()
                )
                embed.add_field(name="Question", value=question, inline=False)
                
                await message.channel.send(embed=embed)
            except Exception as e:
                await message.channel.send(f"Error: {str(e)}")

if __name__ == "__main__":
    client.run(DISCORD_TOKEN) 