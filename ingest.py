import os
import sys
import argparse
from retriever import DocumentRetriever

def main():
    """Main function to ingest documents."""
    parser = argparse.ArgumentParser(description="Ingest documents into the RAG system")
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a file to ingest"
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        help="URL of a document to ingest"
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        help="Path to a directory containing documents to ingest"
    )
    parser.add_argument(
        "--github", "-g",
        type=str,
        help="GitHub repository in format 'owner/repo' (e.g., 'user/repo')"
    )
    parser.add_argument(
        "--github-path",
        type=str,
        default="",
        help="Path within GitHub repo to start from (optional, default: root)"
    )
    parser.add_argument(
        "--github-branch",
        type=str,
        default="main",
        help="GitHub branch to pull from (default: main)"
    )
    parser.add_argument(
        "--github-token",
        type=str,
        help="GitHub personal access token (optional, for private repos or higher rate limits)"
    )
    
    args = parser.parse_args()
    
    # Create retriever
    retriever = DocumentRetriever()
    
    # Check if any arguments were provided
    if not (args.file or args.url or args.dir or args.github):
        print("No input specified. Please provide a file, URL, directory, or GitHub repo.")
        parser.print_help()
        return 1
    
    # Ingest file
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            return 1
        
        print(f"Ingesting file: {args.file}")
        try:
            result = retriever.ingest_file(args.file)
            print(result)
        except Exception as e:
            print(f"Error ingesting {args.file}: {str(e)}")
            return 1
    
    # Ingest URL
    if args.url:
        print(f"Ingesting URL: {args.url}")
        try:
            result = retriever.ingest_from_url(args.url)
            print(result)
        except Exception as e:
            print(f"Error ingesting URL: {str(e)}")
            return 1
    
    # Ingest directory
    if args.dir:
        if not os.path.exists(args.dir) or not os.path.isdir(args.dir):
            print(f"Error: Directory not found: {args.dir}")
            return 1
        
        print(f"Ingesting files from directory: {args.dir}")
        count = 0
        
        # Get absolute path of docs directory to avoid trying to ingest it again
        docs_dir = os.path.abspath('docs')
        
        for filename in os.listdir(args.dir):
            file_path = os.path.join(args.dir, filename)
            
            # Skip if it's the docs directory itself
            if os.path.abspath(file_path) == docs_dir:
                continue
                
            if os.path.isfile(file_path):
                try:
                    # Create a unique ID for the document to avoid conflicts
                    file_id = os.path.basename(file_path)
                    result = retriever.ingest_file(file_path)
                    print(result)
                    count += 1
                except Exception as e:
                    print(f"Error ingesting {file_path}: {str(e)}")
        
        print(f"Ingested {count} files from {args.dir}")
    
    # Ingest from GitHub repo
    if args.github:
        print(f"Ingesting from GitHub repository: {args.github}")
        try:
            # Parse owner/repo from input
            if "/" not in args.github:
                print("Error: GitHub repo must be in format 'owner/repo'")
                return 1
            
            owner, repo = args.github.split("/", 1)
            result = retriever.ingest_from_github_repo(
                repo_owner=owner,
                repo_name=repo,
                path=args.github_path,
                branch=args.github_branch,
                token=args.github_token
            )
            print(result)
        except Exception as e:
            print(f"Error ingesting from GitHub: {str(e)}")
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 