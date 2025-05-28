import os
import discord
from dotenv import load_dotenv
from retriever import DocumentRetriever
from grid_client import GridClient

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNELS = os.getenv('DISCORD_CHANNELS', '').split(',')
ALLOWED_CHANNEL_IDS = [int(channel_id.strip()) for channel_id in DISCORD_CHANNELS if channel_id.strip()]

# Initialize the bot
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Initialize document retriever and Grid client
retriever = DocumentRetriever()
grid_client = GridClient()

@client.event
async def on_ready():
    """Event called when the bot is ready."""
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print(f'Listening in channels: {ALLOWED_CHANNEL_IDS}')
    print('------')

@client.event
async def on_message(message):
    """Event called when a message is received."""
    # Ignore messages from the bot itself
    if message.author == client.user:
        return
    
    # Check if the message is in an allowed channel
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
            help_embed = discord.Embed(
                title="Grid Discord RAG Bot Help",
                description="I can answer questions about AI Power Grid using stored documentation.",
                color=discord.Color.green()
            )
            
            help_embed.add_field(
                name="How to use",
                value="Mention me with your question: `@BotName What is AI Power Grid?`",
                inline=False
            )
            
            help_embed.add_field(
                name="Example",
                value="@BotName What security features does AI Power Grid offer?",
                inline=False
            )
            
            await message.channel.send(embed=help_embed)
            return
        
        # Send a typing indicator to show the bot is processing
        async with message.channel.typing():
            try:
                # Retrieve relevant documents
                context = retriever.get_relevant_context(question)
                
                # Send to Grid API for answer
                answer = grid_client.get_answer(question, context)
                
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