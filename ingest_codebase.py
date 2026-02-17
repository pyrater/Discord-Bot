import os
import glob
from memory_engine import MemoryEngine
from bot_config import settings
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)

def ingest_codebase():
    logging.info("🧠 Initializing Memory Engine for Codebase Ingestion...")
    try:
        mem = MemoryEngine(db_path=settings.DB_PATH, chroma_path=settings.CHROMA_PATH)
    except Exception as e:
        logging.error(f"❌ Failed to init MemoryEngine (DB Locked?): {e}")
        return

    # Define root
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Find all Python files
    # Using glob for simplicity, excluding venv/deps if any
    files = glob.glob(os.path.join(ROOT_DIR, "**", "*.py"), recursive=True)
    
    # Filter out unwanted directories
    ignore_dirs = {"chroma_db", "__pycache__", ".git", "deps", "venv"}
    files = [f for f in files if not any(d in f.split(os.sep) for d in ignore_dirs)]
    
    logging.info(f"📂 Found {len(files)} Python files to ingest.")
    
    total_chunks = 0
    for file_path in files:
        rel_path = os.path.relpath(file_path, ROOT_DIR)
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            if not content.strip():
                continue
                
            # Naive Chunking for Code
            # 1500 chars overlap 200
            chunk_size = 1500
            overlap = 200
            
            chunks = []
            for i in range(0, len(content), chunk_size - overlap):
                chunks.append(content[i:i + chunk_size])
            
            # Store
            for i, chunk in enumerate(chunks):
                mem.store_knowledge(
                    text=f"FILE: {rel_path}\nCHUNKS: {i+1}/{len(chunks)}\n\n{chunk}",
                    source=rel_path,
                    title=f"Codebase: {rel_path}"
                )
            
            total_chunks += len(chunks)
            logging.info(f"✅ Ingested {rel_path} ({len(chunks)} chunks)")
            
        except Exception as e:
            logging.error(f"❌ Error reading {rel_path}: {e}")

    logging.info(f"🎉 Codebase Ingestion Complete! Added {total_chunks} chunks.")

if __name__ == "__main__":
    ingest_codebase()
