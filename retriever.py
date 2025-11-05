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
        
        # Check if collection exists and has correct dimensions
        try:
            self.chroma_collection = self.chroma_client.get_collection("discord_docs")
            print("Found existing collection 'discord_docs'")
        except NotFoundError:
            # Collection doesn't exist, create it with the correct embedding dimension
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
        
        # If the file is already in the docs directory, use it directly
        # Otherwise, copy it to docs directory
        if os.path.dirname(os.path.abspath(file_path)) == os.path.abspath('docs'):
            doc_path = file_path
        else:
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
    
    def ingest_content(self, content: str, filename: str) -> str:
        """Ingest content directly into the index."""
        # Save content to docs directory
        doc_path = os.path.join('docs', filename)
        
        # Save content
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Create document object
        document = Document(text=content, metadata={"source": filename})
        
        # Add to index
        if self.index is None:
            self.index = VectorStoreIndex.from_documents(
                [document],
                storage_context=self.storage_context
            )
        else:
            self.index.insert_nodes([document])
        
        return f"Ingested document: {filename}"
    
    def ingest_from_github_repo(self, repo_owner: str, repo_name: str, path: str = "", branch: str = "main", token: str = None) -> str:
        """Ingest all .md files from a GitHub repository.
        
        Args:
            repo_owner: GitHub username or organization name
            repo_name: Repository name
            path: Path within the repo to start from (default: root)
            branch: Branch to pull from (default: "main")
            token: Optional GitHub personal access token (for private repos or rate limits)
        
        Returns:
            String summary of ingestion results
        """
        base_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        headers["Accept"] = "application/vnd.github.v3.raw"
        
        # Function to recursively find all .md files
        def find_md_files(path_prefix: str = "") -> List[Dict[str, str]]:
            """Recursively find all .md files in the repo."""
            md_files = []
            api_url = f"{base_url}/contents/{path_prefix}" if path_prefix else f"{base_url}/contents"
            
            if branch != "main":
                api_url += f"?ref={branch}"
            
            try:
                response = requests.get(api_url, headers={**headers, "Accept": "application/json"})
                if response.status_code == 404:
                    # Try with default branch parameter if not already included
                    if branch == "main" and "?" not in api_url:
                        api_url_with_branch = f"{api_url}?ref=main"
                        response = requests.get(api_url_with_branch, headers={**headers, "Accept": "application/json"})
                
                response.raise_for_status()
                contents = response.json()
                
                for item in contents:
                    if item["type"] == "file" and item["name"].endswith((".md", ".mdx")):
                        md_files.append({
                            "path": item["path"],
                            "download_url": item["download_url"],
                            "name": item["name"]
                        })
                    elif item["type"] == "dir":
                        # Recursively search subdirectories
                        subdir_files = find_md_files(item["path"])
                        md_files.extend(subdir_files)
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    if e.response.status_code == 404:
                        error_msg = f"Repository not found or is private. Status: 404. {'A GitHub token may be required for private repos.' if not token else 'Check repository name and permissions.'}"
                    elif e.response.status_code == 403:
                        error_msg = f"Access forbidden. Status: 403. Rate limit may be exceeded or token may be invalid."
                print(f"Error accessing GitHub API for path {path_prefix}: {error_msg}")
            
            return md_files
        
        # Find all .md files
        print(f"Searching for .md files in {repo_owner}/{repo_name}...")
        md_files = find_md_files(path)
        
        if not md_files:
            return f"No .md or .mdx files found in {repo_owner}/{repo_name}"
        
        print(f"Found {len(md_files)} markdown file(s), ingesting...")
        
        # Ingest each file
        ingested_count = 0
        errors = []
        
        for file_info in md_files:
            try:
                # Download file content
                download_url = file_info["download_url"]
                file_response = requests.get(download_url, headers={"Authorization": f"token {token}"} if token else {})
                file_response.raise_for_status()
                content = file_response.text
                
                # Create filename with path structure to avoid conflicts
                # Use path as filename prefix to preserve directory structure
                safe_path = file_info["path"].replace("/", "_").replace("\\", "_")
                filename = f"github_{repo_owner}_{repo_name}_{safe_path}"
                
                # Save content to docs directory
                doc_path = os.path.join('docs', filename)
                with open(doc_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Create document object
                document = Document(
                    text=content,
                    metadata={
                        "source": f"github:{repo_owner}/{repo_name}/{file_info['path']}",
                        "github_path": file_info["path"],
                        "repo": f"{repo_owner}/{repo_name}"
                    }
                )
                
                # Add to index
                if self.index is None:
                    self.index = VectorStoreIndex.from_documents(
                        [document],
                        storage_context=self.storage_context
                    )
                else:
                    self.index.insert_nodes([document])
                
                ingested_count += 1
                print(f"  ✓ Ingested: {file_info['path']}")
                
            except Exception as e:
                error_msg = f"Error ingesting {file_info['path']}: {str(e)}"
                errors.append(error_msg)
                print(f"  ✗ {error_msg}")
        
        result = f"Ingested {ingested_count}/{len(md_files)} files from {repo_owner}/{repo_name}"
        if errors:
            result += f"\nErrors: {len(errors)} file(s) failed"
        
        return result
    
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
    
    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the docs directory."""
        if not os.path.exists('docs'):
            return []
        
        documents = []
        for filename in os.listdir('docs'):
            if os.path.isfile(os.path.join('docs', filename)):
                # Skip README and hidden files
                if filename == 'README.md' or filename.startswith('.'):
                    continue
                    
                file_path = os.path.join('docs', filename)
                file_size = os.path.getsize(file_path)
                file_time = os.path.getmtime(file_path)
                
                documents.append({
                    "filename": filename,
                    "size": file_size,
                    "last_modified": file_time,
                    "path": file_path
                })
        
        # Sort by last modified time (newest first)
        documents.sort(key=lambda x: x["last_modified"], reverse=True)
        
        return documents
    
    def delete_document(self, filename: str) -> str:
        """Delete a document from the docs directory and rebuild the index."""
        doc_path = os.path.join('docs', filename)
        
        # Check if file exists
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Document not found: {filename}")
        
        # Delete the file
        os.remove(doc_path)
        
        # Rebuild the index
        # For simplicity, we'll delete the collection and rebuild from scratch
        try:
            self.chroma_client.delete_collection("discord_docs")
        except Exception as e:
            print(f"Error deleting collection: {str(e)}")
        
        # Create new collection
        self.chroma_collection = self.chroma_client.create_collection(
            name="discord_docs",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Update vector store and storage context
        self.vector_store = ChromaVectorStore(chroma_collection=self.chroma_collection)
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        
        # Rebuild index if there are still documents
        if os.path.exists('docs') and len([f for f in os.listdir('docs') if not f.startswith('.') and f != 'README.md']) > 0:
            self.index = self._create_index()
        else:
            self.index = None
        
        return f"Deleted document: {filename}" 