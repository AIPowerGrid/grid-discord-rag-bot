import os
import sys
import shutil
import chromadb
from dotenv import load_dotenv
from retriever import DocumentRetriever

def main():
    """Rebuild the ChromaDB index from all documents in the docs directory."""
    print("Starting index rebuild process...")
    
    # Load environment variables
    load_dotenv()
    CHROMA_DB_PATH = os.getenv('CHROMA_DB_PATH', './chroma_db')
    
    # Check if docs directory exists
    if not os.path.exists('docs') or not os.path.isdir('docs'):
        print("Error: 'docs' directory not found.")
        return 1
    
    # Count the number of documents
    doc_files = [f for f in os.listdir('docs') if os.path.isfile(os.path.join('docs', f)) 
                and not f.startswith('.') and f != 'README.md']
    
    if not doc_files:
        print("No documents found in 'docs' directory.")
        return 1
    
    print(f"Found {len(doc_files)} documents in 'docs' directory.")
    
    # Backup the existing ChromaDB (if any)
    if os.path.exists(CHROMA_DB_PATH):
        backup_path = f"{CHROMA_DB_PATH}_backup"
        print(f"Backing up existing ChromaDB to {backup_path}")
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path)
        shutil.copytree(CHROMA_DB_PATH, backup_path)
        
        # Delete the existing ChromaDB
        print("Deleting existing ChromaDB collection...")
        try:
            shutil.rmtree(CHROMA_DB_PATH)
        except Exception as e:
            print(f"Error deleting ChromaDB: {str(e)}")
            return 1
    
    # Create a new retriever (which will initialize a new ChromaDB)
    print("Creating new ChromaDB collection...")
    retriever = DocumentRetriever()
    
    # Ingest all documents
    print("Ingesting documents...")
    for filename in doc_files:
        file_path = os.path.join('docs', filename)
        try:
            print(f"Ingesting {filename}...")
            result = retriever.ingest_file(file_path)
            print(f"  {result}")
        except Exception as e:
            print(f"  Error ingesting {filename}: {str(e)}")
    
    print("Index rebuild complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 