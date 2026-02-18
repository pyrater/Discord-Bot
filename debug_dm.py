from memory_engine import MemoryEngine
import re

# Initialize
mem = MemoryEngine()
collection = mem.collection

print("🔍 Scanning DM memories for missing user_id...")

# Get all DM memories
results = collection.get(where={"guild_id": "DM"}, include=["metadatas", "documents"])
ids = results['ids']
metadatas = results['metadatas']
documents = results['documents']

updates_ids = []
updates_metadatas = []

count = 0
fixed = 0

for i, doc_id in enumerate(ids):
    meta = metadatas[i]
    doc = documents[i]
    
    # Check if user_id is missing or "None"
    if "user_id" not in meta or meta["user_id"] == "None" or meta["user_id"] is None:
        count += 1
        print(f"\n[MISSING USER_ID] ID: {doc_id}")
        print(f"Content: {doc}")
        print(f"Metadata: {meta}")
        
        # Try to infer from username if we have a mapping? 
        # Or if the document text follows "Username said:" pattern
        # "Username said: ..."
        # But we need the ID, not just the name.
        
        # If we can't find it easily, we might have to skip or manually map.
        # But wait, audit_logs might have it!
        
        pass

print(f"\nFound {count} memories with missing user_id in DM.")

# If we find memories, we need a way to fix them. 
# Since I don't have a map of username -> user_id handy, 
# I will just ensure that AT LEAST the current user's memories are fixed if I can find them.

# Actually, the user says "Retrieved Memory: None".
# If they just chatted, the NEW memory should have user_id.

# Wait, if "Recent History" is None, that's not Chroma. That's `conversation_history` dict.
# `conversation_history` is in-memory. If the bot restarted, it's gone.
# But `get_recent_interactions` pulls from SQLite.

# Let's check `get_recent_interactions` in `memory_engine.py` too.
