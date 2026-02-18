import chromadb
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
chroma_path = os.path.join(base_dir, "chroma_db")

print(f"📂 Checking ChromaDB at: {chroma_path}")
client = chromadb.PersistentClient(path=chroma_path)

collections = client.list_collections()
print(f"📊 Found {len(collections)} collections:")

for col in collections:
    count = col.count()
    print(f"- Collection: '{col.name}' | Count: {count}")
    if count > 0:
        peek = col.peek(limit=1)
        print(f"  Sample ID: {peek['ids'][0]}")
        print(f"  Sample Context: {peek['documents'][0][:100]}...")
