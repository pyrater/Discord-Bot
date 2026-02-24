import logging
import asyncio
import sys

# Try to replicate brain.py imports
try:
    from ddgs import DDGS
    print("✅ Imported DDGS from 'ddgs'")
except ImportError:
    try:
        from duckduckgo_search import DDGS
        print("⚠️ Imported DDGS from 'duckduckgo_search' (fallback)")
    except ImportError:
        print("❌ Failed to import DDGS")
        sys.exit(1)

async def test_search(query):
    print(f"🔎 Testing search for: '{query}'")
    loop = asyncio.get_event_loop()
    def search():
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=5))
        except Exception as e:
            return f"Error in thread: {e}"
    
    results = await loop.run_in_executor(None, search)
    print(f"Results type: {type(results)}")
    if isinstance(results, list):
        print(f"Number of results: {len(results)}")
        for r in results[:2]:
            print(f"- {r.get('title')}")
    else:
        print(f"Failure: {results}")

if __name__ == "__main__":
    asyncio.run(test_search("top places to eat in new york"))
