# Grid Discord RAG Bot

A Discord bot that can answer questions about AI Power Grid using local document storage with ChromaDB and AI Power Grid for inference.

## Features

- Process and index documentation about your project
- Store vector embeddings locally using ChromaDB
- Retrieve relevant context when users ask questions
- Send retrieved context + question to AI Power Grid API
- Format and return responses in Discord
- Maintain conversation context for follow-up questions
- Respond to both mentions and replies to previous messages
- Upload documents directly through Discord attachments
- List and manage documents in the knowledge base

## Setup

1. Clone this repository
2. Create and activate a Python virtual environment:
   ```bash
   # Create virtual environment
   python3 -m venv venv
   
   # Activate virtual environment
   # On macOS/Linux:
   source venv/bin/activate
   # On Windows:
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install additional dependencies for embeddings:
   ```bash
   pip install "llama-index-vector-stores-chroma>=0.1.0" "llama-index-embeddings-huggingface>=0.1.0" sentence-transformers
   ```
5. Copy `.env.example` to `.env` and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
6. Add your documents to the `docs` folder or use the included documents
7. Run the document ingestion script:
   ```bash
   python ingest.py --dir docs
   ```
   - Or ingest a single file: `python ingest.py -f your_file.md`
   - Or ingest from a URL: `python ingest.py -u https://example.com/document`
8. Start the bot:
   ```bash
   python bot.py
   ```

## Environment Variables

- `DISCORD_TOKEN`: Your Discord bot token
- `GRID_API_KEY`: Your AI Power Grid API key
- `GRID_MODEL`: The AI Power Grid model to use (default: grid/meta-llama/llama-4-maverick-17b-128e-instruct)
- `DISCORD_CHANNELS`: Comma-separated list of Discord channel IDs where the bot will listen for mentions and commands
- `LISTENING_CHANNEL_ID`: Channel ID where the bot will actively listen and respond to messages (optional)
- `ADMIN_USER_ID`: Discord user ID of the admin authorized to manage documents
- `CHROMA_DB_PATH`: Path to store ChromaDB data (default: ./chroma_db)
- `BOT_NAME`: Name of the bot (default: ask-ai)
- `GITHUB_REPO`: GitHub repository to auto-ingest on startup (format: owner/repo, e.g., `AIPowerGrid/docs`)
- `GITHUB_REPO_PATH`: Optional path within the GitHub repo to start from (default: root)
- `GITHUB_REPO_BRANCH`: Branch to pull from (default: main)
- `GITHUB_TOKEN`: Optional GitHub personal access token (for private repos or higher rate limits)

## Usage

### Initial Questions
The bot can respond in two ways:

**1. Active Listening (if LISTENING_CHANNEL_ID is set):**
- In the designated listening channel, the bot will automatically classify messages and respond when it thinks it can help
- No need to mention the bot - just ask questions naturally
- The bot uses AI classification to determine when to respond

**2. Mentions (in DISCORD_CHANNELS):**
- Mention the bot in one of the configured channels with your question:
  - `@BotName What is AI Power Grid?`
  - `@BotName How does AI Power Grid handle text generation?`
  - `@BotName What security features does AI Power Grid offer?`
- If you mention the bot without a question, it will display a help message

### Follow-up Questions
To ask follow-up questions and continue the conversation:
- Reply directly to the bot's previous answer with your follow-up question
- The bot will maintain context from the previous interaction to provide more relevant answers

The bot remembers up to 10 recent messages in each channel to maintain conversation context and provide more natural responses.

### Document Management (Admin Only)
Administrators (specified by ADMIN_USER_ID) can manage documents directly through Discord:

- **Upload Documents**: 
  - Use `!upload` command with attached files (.txt, .md, .mdx)
  - Or simply attach files to a message in an allowed channel

- **List Documents**: 
  - Use `!list` command to see all available documents

- **Delete Documents**: 
  - Use `!delete [filename]` to remove a document from the knowledge base

## Troubleshooting

If you encounter any issues with importing modules, make sure you've installed all the required dependencies in your virtual environment. 

If the bot doesn't respond in a channel, verify that the channel ID is included in the `DISCORD_CHANNELS` environment variable. 
