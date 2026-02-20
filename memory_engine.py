import os
import json
import sqlite3
import logging
import chromadb
import tiktoken
import asyncio
from datetime import datetime
from collections import deque
from functools import lru_cache as from_functools_import_lru_cache
import contextlib

class MemoryEngine:
    def __init__(self, db_path=None, chroma_path=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or os.path.join(base_dir, "tars_state.db")
        self.chroma_path = chroma_path or os.path.join(base_dir, "chroma_db")
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.fact_queue = asyncio.Queue()
        
        # Initialize Database connection
        self._init_sqlite()
        
        # Initialize Vector Store
        self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(name="user_memories")
        self.knowledge_collection = self.chroma_client.get_or_create_collection(name="tars_knowledge")
        self.summary_collection = self.chroma_client.get_or_create_collection(name="conversation_summaries")
        
    @contextlib.contextmanager
    def _get_connection(self, use_row_factory=False):
        """Context manager for robust SQLite connections."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        if use_row_factory:
            conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

        
    def warmup(self):
        """Forces the embedding model to load into memory."""
        try:
            logging.info("🧠 Memory Engine: Warming up embedding model...")
            # Performing a dummy query forces the model to load
            self.collection.query(query_texts=["warmup"], n_results=1)
            logging.info("🔥 Memory Engine: Warmup complete!")
        except Exception as e:
            logging.warning(f"⚠️ Memory Warmup failed (non-critical): {e}")

    async def get_noodle_vibe(self, user_id):
        def _fetch():
            with self._get_connection(use_row_factory=True) as conn:
                row = conn.execute("SELECT * FROM emotional_state WHERE user_id = ?", (str(user_id),)).fetchone()
                return row

        loop = asyncio.get_event_loop()
        row = await loop.run_in_executor(None, _fetch)

        if not row: return "Neutral"
        
        emotions = dict(row)
        if 'user_id' in emotions: emotions.pop('user_id')
        sorted_vibe = sorted([(k, v) for k, v in emotions.items() if v > 0.1], key=lambda x: x[1], reverse=True)
        return ", ".join([f"{k} ({v:.2f})" for k, v in sorted_vibe[:3]]) if sorted_vibe else "Neutral"

    async def wipe_user(self, user_id):
        """Deletes ALL data for a user (SQL + Vector)."""
        uid = str(user_id)
        
        def _wipe_sql():
            with self._get_connection() as conn:
                conn.execute("DELETE FROM emotional_state WHERE user_id = ?", (uid,))
                conn.execute("DELETE FROM audit_logs WHERE user_id = ?", (uid,))
                conn.execute("DELETE FROM facts WHERE user_id = ?", (uid,))
                conn.commit()

        try:
            # 1. SQLite Deletions
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _wipe_sql)
            
            # 2. Chroma Deletion
            self.collection.delete(where={"user_id": uid})
            logging.info(f"🧠 Wiped all data for {uid}")
            return True
        except Exception as e:
            logging.error(f"❌ Wipe failed for {uid}: {e}")
            return False

    async def wipe_all(self):
        """Administrator-only: Wipes ENTIRE database and vector store."""
        try:
            # 1. SQLite Wipe
            def _wipe_sql_global():
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM emotional_state")
                    conn.execute("DELETE FROM audit_logs")
                    conn.execute("DELETE FROM facts")
                    conn.execute("DELETE FROM reminders")
                    conn.commit()
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _wipe_sql_global)
            
            # 2. Chroma Wipe
            # Deleting and recreating is cleaner than deleting items
            for col_name in ["user_memories", "tars_knowledge", "conversation_summaries"]:
                try:
                    self.chroma_client.delete_collection(col_name)
                except Exception as e:
                    logging.warning(f"Note: Could not delete collection {col_name} (already gone?): {e}")
            
            # Recreate
            self.collection = self.chroma_client.get_or_create_collection(name="user_memories")
            self.knowledge_collection = self.chroma_client.get_or_create_collection(name="tars_knowledge")
            self.summary_collection = self.chroma_client.get_or_create_collection(name="conversation_summaries")
            
            logging.warning("⚠️ CRITICAL: MEMORY ENGINE GLOBALLY WIPED")
            return True
        except Exception as e:
            logging.error(f"❌ Global Wipe failed: {e}")
            return False

    async def log_interaction(self, user_id, prompt, response, mood, full_prompt, memories, emo_results):
        """Logs the interaction and updates emotional state in SQLite (Threaded)."""
        def _write():
            try:
                with self._get_connection() as conn:
                    # 1. Update Emotional State
                    conn.execute("INSERT OR IGNORE INTO emotional_state (user_id) VALUES (?)", (str(user_id),))
                    for res in emo_results:
                        label, score = res['label'], res['score']
                        conn.execute(f"UPDATE emotional_state SET {label} = ({label} * 0.7) + ? WHERE user_id = ?", (score * 0.3, str(user_id)))
                    
                    # 2. Append to Audit Log
                    memories_json = json.dumps(memories) if isinstance(memories, list) else str(memories)
                    conn.execute("""INSERT INTO audit_logs 
                                 (timestamp, user_id, prompt, response, mood, full_prompt, memories_retrieved) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                 (datetime.now().isoformat(), str(user_id), prompt, response, mood, 
                                  full_prompt, memories_json))
                    
                    conn.commit()
                return True
            except Exception as e:
                logging.error(f"❌ SQLite Log Error for {user_id}: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _write)

        # Background Queue for Fact Extraction to avoid concurrency limits
        self.fact_queue = asyncio.Queue()
        # Task must be started explicitly when loop is running
    
    async def start(self):
        """Starts background workers."""
        asyncio.create_task(self._process_fact_queue())

    def persist(self):
        """Forces a persistent client to flush to disk (ChromaDB specific logic)."""
        # PersistentClient handles this automatically in newer versions, 
        # but heartbeating or closing the client can trigger a sync in Docker.
        try:
            self.chroma_client.heartbeat()
            logging.info("💾 Memory Engine: ChromaDB Persistence signaled.")
        except Exception as e:
            logging.warning(f"⚠️ Persistence signal failed: {e}")

    def _init_sqlite(self):
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            
            # 1. Facts Table (Knowledge Graph)
            conn.execute("""CREATE TABLE IF NOT EXISTS facts 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          user_id TEXT, 
                          guild_id TEXT DEFAULT 'DM',
                          subject TEXT, 
                          predicate TEXT, 
                          object TEXT, 
                          confidence REAL,
                          timestamp TEXT)""")
    
            # 2. Audit Logs (Chat History)
            conn.execute("""CREATE TABLE IF NOT EXISTS audit_logs 
                         (timestamp TEXT, user_id TEXT, prompt TEXT, response TEXT, mood TEXT, 
                          full_prompt TEXT, memories_retrieved TEXT)""")
            
            # 3. Reminders Table
            conn.execute("""CREATE TABLE IF NOT EXISTS reminders 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          user_id TEXT, 
                          channel_id TEXT, 
                          due_time TEXT, 
                          note TEXT)""")
            
            # Migrations for Audit Logs
            try:
                conn.execute("ALTER TABLE audit_logs ADD COLUMN full_prompt TEXT")
            except sqlite3.OperationalError: pass 
            try:
                conn.execute("ALTER TABLE audit_logs ADD COLUMN memories_retrieved TEXT")
            except sqlite3.OperationalError: pass

            # Migration for facts table: Add guild_id
            try:
                conn.execute("ALTER TABLE facts ADD COLUMN guild_id TEXT DEFAULT 'DM'")
            except sqlite3.OperationalError: pass
    
            # 3. Emotional State
            EMOTION_LABELS = [
                "admiration", "amusement", "anger", "annoyance", "approval", "caring", 
                "confusion", "curiosity", "desire", "disappointment", "disapproval", 
                "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief", 
                "joy", "love", "nervousness", "optimism", "pride", "realization", 
                "relief", "remorse", "sadness", "surprise", "neutral"
            ]
            emo_cols = ", ".join([f"{emo} REAL DEFAULT 0.0" for emo in EMOTION_LABELS])
            conn.execute(f"CREATE TABLE IF NOT EXISTS emotional_state (user_id TEXT PRIMARY KEY, {emo_cols})")
            
            conn.commit()

    @property
    def _encoding(self):
        # Lazy load encoding
        if not hasattr(self, "_enc"):
            self._enc = tiktoken.get_encoding("cl100k_base")
        return self._enc

    @from_functools_import_lru_cache
    def count_tokens(self, text):
        return len(self._encoding.encode(text))
    async def _process_fact_queue(self):
        """Worker loop to process fact extraction sequentially."""
        logging.info("🧠 Memory Engine: Fact Extraction Worker Started and waiting for tasks.")
        while True:
            user_id, username, user_text, llm_client, model_name, guild_id = await self.fact_queue.get()
            logging.info(f"🧠 Memory Engine: Processing fact extraction task for {username} in {guild_id}...")
            try:
                # Wait a bit to let the main chat interaction clear the concurrency slot
                await asyncio.sleep(2.0) 
                await self._extract_facts_logic(user_id, username, user_text, llm_client, model_name, guild_id)
            except Exception as e:
                logging.error(f"❌ Fact queue error: {e}")
            finally:
                self.fact_queue.task_done()
                logging.info(f"🧠 Memory Engine: Fact task for {username} marked as done.")

    async def queue_fact_extraction(self, user_id, username, user_text, llm_client, model_name, guild_id="DM"):
        """Adds a fact extraction task to the background queue."""
        await self.fact_queue.put((user_id, username, user_text, llm_client, model_name, guild_id))

    async def _extract_facts_logic(self, user_id, username, user_text, llm_client, model_name, guild_id="DM"):
        """
        Internal logic to call LLM and store facts.
        """
        logging.info(f"🔎 Memory Engine: Extracting facts from: '{user_text[:50]}...'")
        extraction_prompt = f"""
        Extract permanent facts from this message. 
        Format as a JSON list of objects with keys: "subject", "predicate", "object", "overwrite".
        Self-reference (I, my) should be normalized to "{username}".
        "overwrite": boolean. Set to true ONLY if this fact explicitly corrects or updates a previous fact (e.g., "My name is actually...").
        If no facts, return empty list [].
        
        Message: "{user_text}"
        Facts JSON:
        """
        try:
            response = await llm_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=200, temperature=0.0
            )
            data = response.choices[0].message.content
            # Clean possible markdown code blocks
            data = data.replace("```json", "").replace("```", "").strip()
            if not data: return

            facts = json.loads(data)
            if facts:
                def _save_facts():
                    with self._get_connection() as conn:
                        for f in facts:
                            if f.get('overwrite'):
                                logging.info(f"✏️ Overwriting fact for {user_id} in {guild_id}: {f.get('subject')} {f.get('predicate')}")
                                conn.execute("DELETE FROM facts WHERE user_id = ? AND guild_id = ? AND subject = ? AND predicate = ?", 
                                             (str(user_id), str(guild_id), f.get('subject'), f.get('predicate')))
                            
                            conn.execute("INSERT INTO facts (user_id, guild_id, subject, predicate, object, confidence, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (str(user_id), str(guild_id), f.get('subject'), f.get('predicate'), f.get('object'), 0.9, datetime.now().isoformat()))
                        conn.commit()

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _save_facts)
                
                logging.info(f"🧠 Stored {len(facts)} new facts for {user_id}")
        except Exception as e:
            logging.error(f"Fact extraction failed: {e}")

    async def get_facts(self, user_id, guild_id="DM"):
        """
        Retrieves knowledge graph facts for a user with privacy filtering.
        - Privacy Rules:
            1. If guild_id is 'DM', returns ONLY that user's DM facts.
            2. If guild_id is a server, returns facts for THAT SERVER (shared context).
        """
        def _fetch_facts():
            with self._get_connection(use_row_factory=True) as conn:
                uid = str(user_id)
                gid = str(guild_id)
                
                if gid == "DM":
                    # Private DMs: Only facts from DMs for THIS user
                    query = "SELECT subject, predicate, object FROM facts WHERE user_id = ? AND guild_id = 'DM' ORDER BY timestamp DESC LIMIT 10"
                    params = (uid,)
                else:
                    # Public Servers: Shared facts for THIS guild
                    query = "SELECT subject, predicate, object FROM facts WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 10"
                    params = (gid,)
                
                cursor = conn.execute(query, params)
                return cursor.fetchall()

        loop = asyncio.get_event_loop()
        rows = await loop.run_in_executor(None, _fetch_facts)
        
        return [f"{r['subject']} {r['predicate']} {r['object']}" for r in rows]

    async def rerank_memories(self, query, raw_memories, llm_client=None, model_name=None):
        """
        Uses a local Cross-Encoder to re-rank memories by relevance.
        Much faster (~0.2s) and more accurate than LLM re-ranking.
        """
        if not raw_memories: return []
        
        # Lazy load CrossEncoder to avoid startup overhead
        if not hasattr(self, "_cross_encoder"):
            from sentence_transformers import CrossEncoder
            # Tiny model, very fast, high accuracy for ranking
            self._cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
            
        # Prepare pairs [query, doc]
        pairs = [[query, mem] for mem in raw_memories]
        
        # Predict scores
        scores = self._cross_encoder.predict(pairs)
        
        # Sort by score descending
        # Zip together (score, memory), sort, then extract memory
        scored_memories = sorted(zip(scores, raw_memories), key=lambda x: x[1], reverse=True)
        
        # Return top 3
        return [mem for score, mem in scored_memories[:3]]

    def store_memory(self, user_id, username, prompt, response, guild_id="DM", channel_id="DM", emotion="neutral"):
        """Stores interaction in ChromaDB."""
        # Use a more unique ID to prevent collisions during rapid interaction
        mem_id = f"mem_{datetime.now().timestamp()}_{user_id}"
        self.collection.add(
            documents=[f"{username} said: {prompt} | Tars replied: {response}"],
            ids=[mem_id],
            metadatas=[{
                "user_id": str(user_id),
                "username": str(username),
                "emotion": emotion,
                "guild_id": str(guild_id),
                "channel_id": str(channel_id)
            }]
        )

    def store_observation(self, user_id, username, text, guild_id="DM", channel_id="DM"):
        """Stores a passive observation (user message without bot reply)."""
        # Use a more unique ID to prevent collisions
        obs_id = f"obs_{datetime.now().timestamp()}_{user_id}"
        self.collection.add(
            documents=[f"{username} observed: {text}"],
            ids=[obs_id],
            metadatas=[{
                "user_id": str(user_id),
                "username": str(username),
                "type": "observation",
                "guild_id": str(guild_id),
                "channel_id": str(channel_id)
            }]
        )

    def store_knowledge(self, text, source, title):
        """Stores technical knowledge in the knowledge base."""
        self.knowledge_collection.add(
            documents=[text],
            ids=[f"{source}_{datetime.now().timestamp()}"],
            metadatas=[{"source": source, "title": title}]
        )

    def search_knowledge(self, query, n_results=3):
        """Retrieves technical knowledge relevant to the query."""
        results = self.knowledge_collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results.get('documents', [[]])[0]

    def get_recent_interactions(self, limit=50, hours=24):
        """Fetches recent interaction logs for the Dream Cycle."""
        with self._get_connection(use_row_factory=True) as conn:
            try:
                # Try audit_logs first (New Schema)
                cursor = conn.execute(f"""
                    SELECT prompt, response, mood, timestamp 
                    FROM audit_logs 
                    WHERE timestamp >= datetime('now', '-{hours} hours')
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                # Fallback to interactions (Old Schema)
                try:
                    cursor = conn.execute(f"""
                        SELECT prompt, response, mood, timestamp 
                        FROM interactions 
                        WHERE timestamp >= datetime('now', '-{hours} hours')
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (limit,))
                    rows = cursor.fetchall()
                except sqlite3.OperationalError:
                    rows = [] # Neither table exists?
        
        return rows

    async def get_recent_interactions_async(self, limit=50, hours=24):
         loop = asyncio.get_event_loop()
         return await loop.run_in_executor(None, lambda: self.get_recent_interactions(limit, hours))

    def search_memories(self, query, guild_id, user_id=None, n_results=5):
        """
        Searches memories.
        - If guild_id is "DM", RESTRICTS to user_id (Private).
        - If guild_id is valid, SEARCHES ALL users (Cross-User Context).
        """
        guild_id_str = str(guild_id)
        where_filter = {"guild_id": guild_id_str}
        
        # Enforce Privacy for DMs
        if guild_id_str == "DM" and user_id:
            where_filter = {"$and": [{"guild_id": "DM"}, {"user_id": str(user_id)}]}
            
        results = self.collection.query(
            query_texts=[query],
            where=where_filter,
            n_results=n_results
        )
        return results.get('documents', [[]])[0]
