# Test Document

This is a test document for our RAG bot that will be ingested into the system.

## Some Example Content

Discord bots can be created using discord.py, a powerful Python library for interacting with the Discord API.

### Key Features

1. Command handling
2. Event listening
3. Slash commands
4. Message components (buttons, select menus)

### Example Code

```python
import discord
from discord.ext import commands

bot = commands.Bot(command_prefix='!')

@bot.event
async def on_ready():
    print(f'Bot is online: {bot.user.name}')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

bot.run('YOUR_TOKEN_HERE')
```

## How RAG Works

Retrieval Augmented Generation (RAG) combines retrieval-based and generation-based approaches:

1. Store documents in a vector database
2. When a question is asked, retrieve relevant context
3. Send the context + question to an LLM
4. Return the LLM's response

This approach grounds the LLM's responses in factual information from your documents. 