import os
import sys
import glob
import logging
import asyncio
import httpx
from urllib.parse import urlparse
from src.memory_engine import MemoryEngine
from src.bot_config import settings

# Setup Logging
logging.basicConfig(level=logging.INFO)

# File extensions to ingest from a GitHub repository
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".md", ".yaml", ".yml", ".toml", ".json",
    ".sh", ".cfg", ".ini", ".env.example",
}

# Max concurrent file downloads
MAX_CONCURRENCY = 10

# Default GitHub repo to ingest when no URL is provided
DEFAULT_GITHUB_URL = "https://github.com/TARS-AI-Community/TARS-AI/tree/V3"


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def parse_github_url(url):
    """
    Parses a GitHub URL and returns (owner, repo, branch_or_None).

    Handles:
      https://github.com/owner/repo
      https://github.com/owner/repo/
      https://github.com/owner/repo/tree/branch
      https://github.com/owner/repo/tree/branch/sub/path
    """
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub URL: {url}")
    owner, repo = parts[0], parts[1]
    branch = parts[3] if len(parts) >= 4 and parts[2] in ("tree", "blob") else None
    return owner, repo, branch


def _github_headers():
    """Returns GitHub API headers, including auth if GITHUB_TOKEN is set."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


async def fetch_default_branch(client, owner, repo):
    """Queries the GitHub API to get the repository's default branch."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = await client.get(url, headers=_github_headers())
    resp.raise_for_status()
    return resp.json().get("default_branch", "main")


async def fetch_github_tree(client, owner, repo, branch):
    """Returns the full recursive file tree for a branch via the GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    resp = await client.get(url, headers=_github_headers())
    resp.raise_for_status()
    return resp.json().get("tree", [])


async def process_github_file(sem, client, mem, owner, repo, branch, item):
    """Downloads and ingests a single file from GitHub under a concurrency semaphore."""
    path = item["path"]
    if os.path.splitext(path)[1].lower() not in CODE_EXTENSIONS:
        return 0

    async with sem:
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            resp = await client.get(raw_url)
            if resp.status_code != 200 or not resp.text.strip():
                return 0
            content = resp.text
        except Exception as e:
            logging.error(f"Failed to fetch {path}: {e}")
            return 0

        chunk_size, overlap = 1500, 200
        chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size - overlap)]
        source_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{path}"

        for i, chunk in enumerate(chunks):
            try:
                mem.store_knowledge(
                    text=f"FILE: {path}\nCHUNK: {i+1}/{len(chunks)}\n\n{chunk}",
                    source=source_url,
                    title=f"Codebase: {path}",
                    kb_type="code"
                )
            except Exception as e:
                logging.error(f"Failed to store chunk {i} for {path}: {e}")

        logging.info(f"Ingested {path} ({len(chunks)} chunks)")
        return len(chunks)


async def ingest_github(github_url):
    """Ingests a remote GitHub repository into the TARS knowledge base."""
    owner, repo, branch = parse_github_url(github_url)

    try:
        mem = MemoryEngine(db_path=settings.DB_PATH, chroma_path=settings.CHROMA_PATH)
    except Exception as e:
        logging.error(f"Failed to init MemoryEngine: {e}")
        return

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        if not branch:
            branch = await fetch_default_branch(client, owner, repo)

        logging.info(f"Ingesting github.com/{owner}/{repo} @ {branch}...")

        tree = await fetch_github_tree(client, owner, repo, branch)
        files = [item for item in tree if item["type"] == "blob"]
        logging.info(f"Found {len(files)} files. Filtering by extension...")

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        results = await asyncio.gather(*[
            process_github_file(sem, client, mem, owner, repo, branch, f)
            for f in files
        ])

    total_chunks = sum(results)
    mem.persist()
    logging.info(f"GitHub ingestion complete. Added {total_chunks} chunks.")


# ---------------------------------------------------------------------------
# Local ingestion (original behaviour)
# ---------------------------------------------------------------------------

def ingest_local():
    """Ingests Python files from the local codebase directory."""
    logging.info("Initializing Memory Engine for local codebase ingestion...")
    try:
        mem = MemoryEngine(db_path=settings.DB_PATH, chroma_path=settings.CHROMA_PATH)
    except Exception as e:
        logging.error(f"Failed to init MemoryEngine: {e}")
        return

    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    files = glob.glob(os.path.join(ROOT_DIR, "**", "*.py"), recursive=True)

    chroma_basename = os.path.basename(settings.CHROMA_PATH)
    ignore_dirs = {chroma_basename, "__pycache__", ".git", "deps", "venv"}
    files = [f for f in files if not any(d in f.split(os.sep) for d in ignore_dirs)]

    logging.info(f"Found {len(files)} Python files to ingest.")

    total_chunks = 0
    for file_path in files:
        rel_path = os.path.relpath(file_path, ROOT_DIR)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            chunk_size, overlap = 1500, 200
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size - overlap)]

            for i, chunk in enumerate(chunks):
                mem.store_knowledge(
                    text=f"FILE: {rel_path}\nCHUNK: {i+1}/{len(chunks)}\n\n{chunk}",
                    source=rel_path,
                    title=f"Codebase: {rel_path}",
                    kb_type="code"
                )

            total_chunks += len(chunks)
            logging.info(f"Ingested {rel_path} ({len(chunks)} chunks)")

        except Exception as e:
            logging.error(f"Error reading {rel_path}: {e}")

    mem.persist()
    logging.info(f"Local codebase ingestion complete. Added {total_chunks} chunks.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GITHUB_URL
    asyncio.run(ingest_github(url))
