import chromadb
import os
import shutil

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "user_memories"

def repair():
    print(f"🛠️ Starting TARS Neural Repair for collection: '{COLLECTION_NAME}'")
    
    # Try to connect
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
    except Exception as e:
        print(f"❌ FATAL: Could not connect to ChromaDB: {e}")
        return

    try:
        collection = client.get_collection(COLLECTION_NAME)
        print(f"✅ Found collection. Attempting to extract documents...")
        
        # Try to get data
        data = collection.get()
        print(f"📦 Successfully extracted {len(data['ids'])} documents.")
        
        # Backup data in memory
        ids = data['ids']
        documents = data['documents']
        metadatas = data['metadatas']
        
        print(f"🗑️ Deleting corrupted collection index...")
        client.delete_collection(COLLECTION_NAME)
        
        print(f"✨ Re-creating collection '{COLLECTION_NAME}'...")
        new_col = client.create_collection(COLLECTION_NAME)
        
        print(f"📥 Re-ingesting {len(ids)} neural points...")
        if ids:
            new_col.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
        print(f"✅ REPAIR COMPLETE. Collection '{COLLECTION_NAME}' is now healthy.")
        
    except Exception as e:
        print(f"❌ REPAIR FAILED: {e}")
        print("💡 Suggestion: If extraction failed, the index might be beyond simple repair.")
        print("   Consider deleting the 'chroma_db' folder and re-running ingestion if you have backups.")

if __name__ == "__main__":
    repair()
