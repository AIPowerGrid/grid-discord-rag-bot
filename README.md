# Grid Discord RAG Bot

A Discord bot that can answer questions about AI Power Grid using local document storage with ChromaDB and AI Power Grid for inference.

## Features

- Process and index documentation about AI Power Grid
- Store vector embeddings locally using ChromaDB
- Retrieve relevant context when users ask questions
- Send retrieved context + question to AI Power Grid API
- Format and return responses in Discord

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
- `DISCORD_CHANNELS`: Comma-separated list of Discord channel IDs where the bot will listen for mentions
- `CHROMA_DB_PATH`: Path to store ChromaDB data (default: ./chroma_db)

## Usage

In Discord, mention the bot in one of the configured channels with your question:
- `@BotName What is AI Power Grid?`
- `@BotName How does AI Power Grid handle text generation?`
- `@BotName What security features does AI Power Grid offer?`

If you mention the bot without a question, it will display a help message.

## Troubleshooting

If you encounter any issues with importing modules, make sure you've installed all the required dependencies in your virtual environment. 

If the bot doesn't respond in a channel, verify that the channel ID is included in the `DISCORD_CHANNELS` environment variable. 