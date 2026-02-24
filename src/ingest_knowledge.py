import os
import sys
import logging
import asyncio
import httpx
from bs4 import BeautifulSoup
from src.memory_engine import MemoryEngine
from src.bot_config import settings
from urllib.parse import urljoin, urlparse

# Setup Logging
logging.basicConfig(level=logging.INFO)

# TARS Knowledge Sources
SOURCES = [
    "https://github.com/TARS-AI-Community/TARS-AI/wiki",
    "https://github.com/TARS-AI-Community/TARS-AI/blob/main/README.md"
]

# Wiki index targets to crawl all articles
CRAWL_INDEXES = [
    "https://interstellarfilm.fandom.com/wiki/Special:AllPages"
]

async def fetch_page(url):
    """Fetches and cleans text content from a URL."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logging.error(f"Failed to fetch {url}: {resp.status_code}")
                return None
            
            # Simple text extraction
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Remove scripts, styles, etc
            for script in soup(["script", "style", "nav", "footer", "aside"]):
                script.decompose()
                
            # Focus on fandom content if applicable
            content_div = soup.find(class_="mw-parser-output")
            if content_div:
                text = content_div.get_text()
            else:
                text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return clean_text
        except Exception as e:
            logging.error(f"Error fetching {url}: {e}")
            return None

async def discover_all_wiki_pages(index_url):
    """Recursively crawls Special:AllPages to find every article on the wiki."""
    all_article_urls = set()
    current_url = index_url
    
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        while current_url:
            logging.info(f"🔎 Scanning index: {current_url}")
            try:
                resp = await client.get(current_url)
                if resp.status_code != 200:
                    logging.error(f"Failed to fetch index {current_url}: {resp.status_code}")
                    break
                
                soup = BeautifulSoup(resp.content, "html.parser")
                parsed_base = urlparse(index_url)
                domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
                
                # 1. Extract all wiki links from the index list
                # Fandom uses 'allpages-body' or similar for the list
                list_container = soup.find(class_="mw-allpages-body") or soup.find(class_="mw-parser-output")
                if list_container:
                    for a in list_container.find_all("a", href=True):
                        href = a["href"]
                        # Filter for real articles (usually /wiki/ without : except for Special:AllPages)
                        if href.startswith("/wiki/") and ":" not in href[6:]:
                            full_url = urljoin(domain, href)
                            all_article_urls.add(full_url)
                
                # 2. Find "Next Page" link
                next_link = None
                # Fandom navigation usually has "Next page" text or a specific class
                nav = soup.find(class_="mw-allpages-nav")
                if nav:
                    for a in nav.find_all("a", href=True):
                        if "next page" in a.get_text().lower() or "→" in a.get_text():
                            next_link = urljoin(domain, a["href"])
                            break
                
                current_url = next_link # Move to next page or None
                if next_link:
                    logging.info(f"⏭️ Found next index page: {next_link}")
                
            except Exception as e:
                logging.error(f"Error crawling index {current_url}: {e}")
                break
                
    logging.info(f"✅ Discovered {len(all_article_urls)} total wiki articles.")
    return all_article_urls

def recursive_chunker(text, max_size=1000):
    """Semantically chunks text by Paragraphs > Lines."""
    if len(text) <= max_size:
        return [text]
    
    chunks = []
    current_chunk = ""
    paragraphs = text.split("\n\n")
    
    for para in paragraphs:
        if len(para) > max_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            # Sub-split long paragraphs by lines
            sub_lines = para.split("\n")
            for line in sub_lines:
                if len(line) > max_size:
                    # Hard split as last resort
                    chunks.extend([line[i:i+max_size] for i in range(0, len(line), max_size)])
                elif len(current_chunk) + len(line) + 1 <= max_size:
                    current_chunk += line + "\n"
                else:
                    chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
        elif len(current_chunk) + len(para) + 2 <= max_size:
            current_chunk += para + "\n\n"
        else:
            chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
            
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

async def ingest():
    logging.info("🧠 Initializing Memory Engine for Knowledge Ingestion...")
    mem = MemoryEngine(db_path=settings.DB_PATH, chroma_path=settings.CHROMA_PATH)
    
    all_urls = set(SOURCES)
    
    # Discovery phase via Special:AllPages
    for index in CRAWL_INDEXES:
        wiki_pages = await discover_all_wiki_pages(index)
        all_urls.update(wiki_pages)
    
    logging.info(f"🚀 Starting ingestion for {len(all_urls)} URLs...")
    
    # Use a set to track already ingested URLs in this session to avoid duplicates
    processed_urls = set()
    
    for url in all_urls:
        if url in processed_urls: continue
        processed_urls.add(url)
        
        logging.info(f"📚 Processing {url}...")
        content = await fetch_page(url)
        
        if content:
            chunks = recursive_chunker(content, max_size=1000)
            logging.info(f"🧩 Ingesting {len(chunks)} chunks for {url}")
            
            # Simple title extraction from URL path
            path_parts = urlparse(url).path.split('/')
            page_title = path_parts[-1].replace("_", " ") if path_parts else "Wiki Article"
            
            for i, chunk in enumerate(chunks):
                mem.store_knowledge(
                    text=chunk,
                    source=url,
                    title=f"Knowledge: {page_title} (Part {i+1})"
                )
    
    mem.persist() # Signal ChromaDB to flush to disk
    logging.info("✅ ALL Knowledge Ingestion Complete!")

if __name__ == "__main__":
    asyncio.run(ingest())
