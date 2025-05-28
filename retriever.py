import os
import shutil
from typing import List, Dict, Any
import requests
from dotenv import load_dotenv
from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    Document,
    StorageContext,
    Settings
)
import chromadb
from chromadb.errors import NotFoundError

# Import ChromaVectorStore from the right package
from llama_index.vector_stores.chroma import ChromaVectorStore

# Import HuggingFaceEmbedding from the correct module
try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
except ImportError:
    try:
        from llama_index.core.embeddings import HuggingFaceEmbedding
    except ImportError:
        print("Could not import HuggingFaceEmbedding from any known location")
        HuggingFaceEmbedding = None

# Load environment variables
load_dotenv()
CHROMA_DB_PATH = os.getenv('CHROMA_DB_PATH', './chroma_db')

class DocumentRetriever:
    """Class to handle document ingestion and retrieval."""
    
    def __init__(self):
        """Initialize the document retriever."""
        # Create docs directory if it doesn't exist
        os.makedirs('docs', exist_ok=True)
        
        # Configure embedding model first
        # Use HuggingFace embeddings for better results
        self.embedding_dim = 384  # Default for BAAI/bge-small-en-v1.5
        
        if HuggingFaceEmbedding is not None:
            try:
                Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
                print("Using HuggingFace embeddings")
            except Exception as e:
                print(f"Failed to load HuggingFace embeddings: {str(e)}")
                print("Using default embeddings")
                Settings.embed_model = None  # Use default
                self.embedding_dim = 1536  # Default OpenAI-like dimension
        else:
            print("HuggingFaceEmbedding not available, using default embeddings")
            Settings.embed_model = None
            self.embedding_dim = 1536  # Default OpenAI-like dimension
        
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        
        # Check if collection exists and create if needed
        try:
            self.chroma_collection = self.chroma_client.get_collection("discord_docs")
            print("Found existing collection 'discord_docs'")
        except NotFoundError:
            # Collection doesn't exist, create it
            print(f"Creating new collection 'discord_docs'")
            self.chroma_collection = self.chroma_client.create_collection(
                name="discord_docs",
                metadata={"hnsw:space": "cosine"}  # Use cosine similarity
            )
        
        # Create vector store
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        
        # Create storage context
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        
        # Configure global settings
        Settings.llm = None  # Use default
        
        # Load index if documents exist
        if os.path.exists('docs') and len(os.listdir('docs')) > 0:
            try:
                self.index = self._load_index()
            except Exception as e:
                print(f"Error loading index: {str(e)}")
                self.index = self._create_index()
        else:
            self.index = None
    
    def _load_index(self):
        """Load the index from the vector store."""
        return VectorStoreIndex.from_vector_store(
            self.vector_store
        )
    
    def _create_index(self):
        """Create a new index from documents."""
        if not os.path.exists('docs') or len(os.listdir('docs')) == 0:
            return None
            
        # Load documents
        documents = SimpleDirectoryReader('docs').load_data()
        
        # Create index
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=self.storage_context
        )
        
        return index
    
    def ingest_file(self, file_path: str) -> str:
        """Ingest a file into the index."""
        # Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Determine the path for the document
        doc_path = file_path
        
        # If the file is not already in the docs directory, copy it there
        if not file_path.startswith(os.path.abspath('docs')):
            doc_path = os.path.join('docs', os.path.basename(file_path))
            shutil.copy2(file_path, doc_path)
        
        # Load document
        documents = SimpleDirectoryReader(input_files=[doc_path]).load_data()
        
        # Add to index
        if self.index is None:
            self.index = VectorStoreIndex.from_documents(
                documents,
                storage_context=self.storage_context
            )
        else:
            self.index.insert_nodes(documents)
        
        return f"Ingested {os.path.basename(file_path)}"
    
    def ingest_from_url(self, url: str) -> str:
        """Ingest a document from a URL."""
        # Download content
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        
        # Create a document
        file_name = url.split('/')[-1] if '/' in url else 'document.txt'
        doc_path = os.path.join('docs', file_name)
        
        # Save content
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Create document object
        document = Document(text=content, metadata={"source": url})
        
        # Add to index
        if self.index is None:
            self.index = VectorStoreIndex.from_documents(
                [document],
                storage_context=self.storage_context
            )
        else:
            self.index.insert_nodes([document])
        
        return f"Ingested document from {url}"
    
    def get_relevant_context(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant context for a query."""
        if self.index is None:
            return []
        
        # Create retriever
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        
        # Get relevant nodes
        nodes = retriever.retrieve(query)
        
        # Format context
        context = []
        for i, node in enumerate(nodes):
            context.append({
                "text": node.text,
                "score": node.score,
                "source": node.metadata.get("source", "Unknown")
            })
        
        return context 