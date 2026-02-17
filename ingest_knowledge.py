import os
import sys
import logging
import asyncio
import httpx
from bs4 import BeautifulSoup
from memory_engine import MemoryEngine
from bot_config import settings

# Setup Logging
logging.basicConfig(level=logging.INFO)

# TARS Knowledge Sources
SOURCES = [
    "https://github.com/TARS-AI-Community/TARS-AI/wiki",
    "https://github.com/TARS-AI-Community/TARS-AI/blob/main/README.md"
]

async def fetch_page(url):
    """Fetches and cleans text content from a URL."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logging.error(f"Failed to fetch {url}: {resp.status_code}")
                return None
            
            # Simple text extraction
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Remove scripts, styles
            for script in soup(["script", "style", "nav", "footer"]):
                script.decompose()
                
            # Get text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return clean_text
        except Exception as e:
            logging.error(f"Error fetching {url}: {e}")
            return None

async def ingest():
    logging.info("🧠 Initializing Memory Engine for Knowledge Ingestion...")
    mem = MemoryEngine(db_path=settings.DB_PATH, chroma_path=settings.CHROMA_PATH)
    
    for url in SOURCES:
        logging.info(f"📚 Fetching {url}...")
        content = await fetch_page(url)
        
        if content:
            # Chunking (Naive)
            # Split by rough paragraph/headers to fit in context
            chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
            
            logging.info(f"🧩 Ingesting {len(chunks)} chunks for {url}")
            
            for i, chunk in enumerate(chunks):
                mem.store_knowledge(
                    text=chunk,
                    source=url,
                    title=f"TARS Knowledge Part {i+1}"
                )
    
    logging.info("✅ Knowledge Ingestion Complete!")

if __name__ == "__main__":
    asyncio.run(ingest())
