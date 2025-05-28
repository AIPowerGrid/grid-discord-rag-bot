import importlib
from pathlib import Path

def check_import(import_path):
    try:
        mod = importlib.import_module(import_path)
        print(f"✓ {import_path} - Successfully imported")
        return True
    except ImportError as e:
        print(f"✗ {import_path} - Import error: {str(e)}")
        return False

# List of potential import paths to test
import_paths = [
    "llama_index",
    "llama_index.core",
    "llama_index.core.vector_stores",
    "llama_index.vector_stores",
    "llama_index.vector_stores.chroma",
]

print("Testing LlamaIndex imports...")
for path in import_paths:
    check_import(path)

print("\nLooking for ChromaVectorStore in available modules...")
for path in import_paths:
    if check_import(path):
        try:
            mod = importlib.import_module(path)
            if hasattr(mod, "ChromaVectorStore"):
                print(f"Found ChromaVectorStore in {path}")
            
            # Check submodules
            if hasattr(mod, "__path__"):
                for finder, name, ispkg in pkgutil.iter_modules(mod.__path__):
                    full_name = f"{path}.{name}"
                    try:
                        submod = importlib.import_module(full_name)
                        if hasattr(submod, "ChromaVectorStore"):
                            print(f"Found ChromaVectorStore in {full_name}")
                    except ImportError:
                        pass
        except Exception as e:
            print(f"Error checking {path}: {str(e)}")

# Additional test
try:
    import pkgutil
    print("\nListing all modules in llama_index package:")
    
    try:
        import llama_index
        for finder, name, ispkg in pkgutil.iter_modules(llama_index.__path__, "llama_index."):
            print(name, "is a package" if ispkg else "is a module")
    except Exception as e:
        print(f"Error listing llama_index modules: {str(e)}")
        
except Exception as e:
    print(f"Error in additional test: {str(e)}") 