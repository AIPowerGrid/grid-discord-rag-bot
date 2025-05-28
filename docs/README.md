# Documentation Directory

This directory contains documentation that has been ingested into the RAG system. The bot uses these documents to answer questions about AI Power Grid.

## Included Documents

- **aipg_documentation.md**: General information about AI Power Grid, its features, and functionality
- **aipg_security.md**: Details about AI Power Grid's security and privacy features
- **sample_discord_doc.md**: Sample Discord-related documentation (for testing purposes)
- **test_doc.md**: A test document for verifying the ingestion process

## Adding New Documents

To add new documents to the knowledge base:

1. Add your markdown (.md) files to this directory
2. Run the ingestion script:
   ```bash
   python ingest.py --dir docs
   ```
   
Or ingest a specific file:
```bash
python ingest.py -f your_file.md
```

Or ingest from a URL:
```bash
python ingest.py -u https://example.com/document
``` 