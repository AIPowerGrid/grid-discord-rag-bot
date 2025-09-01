FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies for embeddings
RUN pip install "llama-index-vector-stores-chroma>=0.1.0" "llama-index-embeddings-huggingface>=0.1.0" sentence-transformers

# Copy application code
COPY . .

# Create directory for ChromaDB
RUN mkdir -p chroma_db

# Expose port (if needed for health checks)
EXPOSE 8000

# Run the bot
CMD ["python", "bot.py"]
