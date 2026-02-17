import streamlit as st
import sqlite3
import pandas as pd
import os
import psutil
import chromadb
import httpx
import asyncio
import json
import subprocess
import io
import hmac # For secure password comparison
import zipfile
try:
    from graphviz import Digraph # For Knowledge Graph Viz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))  # This specifically looks for the .env file and loads it

from memory_engine import MemoryEngine
from brain import CognitiveEngine
from openai import AsyncOpenAI

# 1. DEFINE YOUR PASSWORD (Or pull from os.environ for better security)
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def check_password():
    """Returns True if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        # Check against the .env password
        entered_password = st.session_state.get("password", "")
        if hmac.compare_digest(entered_password, DASHBOARD_PASSWORD):
            st.session_state["password_correct"] = True
            # Clearing the password safely
            st.session_state["password"] = ""
        else:
            st.session_state["password_correct"] = False

    # 1. If already logged in, show the dashboard
    if st.session_state.get("password_correct", False):
        return True

    # 2. Show the login form
    st.title("🔒 TARS Secure Access")
    st.text_input(
        "Enter Dashboard Password", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    # 3. Handle incorrect attempts
    if st.session_state.get("password_correct") == False:
        st.error("😕 Password incorrect")
        
    return False

# 2. ONLY RUN THE REST IF PASSWORD IS CORRECT
if not check_password():
    st.stop()  # Stop execution here if not logged in
    
# --- PAGE CONFIG ---
st.set_page_config(page_title="TARS Command Center", layout="wide", page_icon="🤖")

# --- CUSTOM CSS (CYBERPUNK THEME) ---
# --- CUSTOM CSS (TARS SCI-FI THEME) ---
# --- CUSTOM CSS (TARS SCI-FI THEME V2) ---
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
if os.path.exists(css_path):
    load_css(css_path)
else:
    st.warning("⚠️ Theme file not found. Falling back to default.")

# Scanline Overlay (HTML injection)
st.markdown('<div class="scanline-overlay"></div>', unsafe_allow_html=True)


# Absolute paths for Docker/Unraid
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tars_state.db")
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
MODELS_DIR = "/app/models/"
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

@st.cache_resource
def get_db_connection():
    """Singleton connection pool"""
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)

@st.cache_resource
def get_tars_brain():
    """Initializes the Brain for the Dashboard"""
    mem = MemoryEngine(db_path=DB_PATH, chroma_path=CHROMA_PATH)
    client = AsyncOpenAI(
        base_url=os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1"),
        api_key=os.getenv("LLM_TOKEN")
    )
    return CognitiveEngine(
        memory_engine=mem,
        llm_client=client,
        model_name=os.getenv("MODEL_NAME", "google/gemma-3-27b-it"),
        comfy_url=os.getenv("COMFY_URL"),
        local_llm_path="/app/models/google_gemma-3-270m-it-Q8_0.gguf",
        lazy_load=True
    )

# --- DATA FETCHING ---
def get_audit_logs():
    if not os.path.exists(DB_PATH): return pd.DataFrame()
    try:
        # Use Cached Resource if possible, but for logs we need fresh data often.
        # However, connecting repeatedly is slow. 
        # Better approach: Open temp connection for read
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
        df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
        conn.close()
        return df
    except: return pd.DataFrame()

def parse_prompt(full_prompt):
    """Parses the structured prompt into sections."""
    sections = {
        "Persona": "Not found",
        "Context": "Not found",
        "Memories": "None retrieved",
        "Instructions": "Not found"
    }
    if not full_prompt or not isinstance(full_prompt, str):
        return sections
    
    parts = {
        "Persona": "### SYSTEM PERSONA ###",
        "Examples": "### EXAMPLE DIALOGUE ###",
        "Facts": "### KNOWN FACTS ###",
        "Context": "### INTERACTION CONTEXT ###",
        "Memories": "### RETRIEVED MEMORIES ###",
        "History": "### RECENT HISTORY ###",
        "Instructions": "### INSTRUCTIONS ###"
    }
    
    # Simple parsing logic
    lines = full_prompt.split("\n")
    current_key = None
    buffer = []
    
    for line in lines:
        matched = False
        for key, header in parts.items():
            if header in line:
                if current_key:
                    sections[current_key] = "\n".join(buffer).strip()
                current_key = key
                buffer = []
                matched = True
                break
        if not matched and current_key:
            buffer.append(line)
            
    if current_key:
        sections[current_key] = "\n".join(buffer).strip()
        
    return sections

# --- SIDEBAR: HARDWARE, CONTROLS & TERMINAL ---
st.sidebar.title("🚀 System Monitor")
cpu_usage = psutil.cpu_percent(interval=1)
ram_usage = psutil.virtual_memory().percent

st.sidebar.metric("CPU Usage", f"{cpu_usage}%")
st.sidebar.progress(cpu_usage / 100)
st.sidebar.metric("RAM Usage", f"{ram_usage}%")
st.sidebar.progress(ram_usage / 100)

st.sidebar.divider()
st.sidebar.divider()
st.sidebar.subheader("⚙️ Bot Control")


if st.sidebar.button("🟢 Restart Bot", type="secondary"):
    # 1. Kill existing
    killed = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline'] or []
            if 'python' in proc.info['name'].lower() and any("script.py" in arg for arg in cmd):
                proc.kill()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # 2. Start new
    try:
        if os.name == 'nt':
            # Open in new visible window
            subprocess.Popen(["start", "cmd", "/k", "python script.py"], shell=True)
        else:
            subprocess.Popen(["nohup", "python", "script.py", "&"], shell=True)
        st.toast("Bot Restarted! 🚀")
    except Exception as e:
        st.sidebar.error(f"Failed to start: {e}")

if st.sidebar.button("🔴 Stop Bot", type="primary"):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline'] or []
            if 'python' in proc.info['name'].lower() and any("script.py" in arg for arg in cmd):
                proc.kill()
        except: pass
    st.sidebar.error("Bot Process Terminated")

st.sidebar.divider()
st.sidebar.subheader("� Backup System")
if st.sidebar.button("📦 Create Backup"):
    try:
        import shutil
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"tars_backup_{timestamp}"
        
        # specific files to backup
        # Create a temp dir
        if not os.path.exists("backups"): os.makedirs("backups")
        
        # Copy DB
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, f"backups/{backup_name}.db")
            
        # Zip Chroma - This is heavy, maybe just zip the whole backups folder? 
        # Actually simpler: Zip the current state to a download buffer
        shutil.make_archive(f"backups/{backup_name}", 'zip', root_dir='.', base_dir='chroma_db')
        # Also add the db to that zip? shutil make_archive is directory based.
        # Let's just zip the essential files into one zip
        
        with zipfile.ZipFile(f"backups/{backup_name}.zip", 'w') as zipf:
            if os.path.exists(DB_PATH):
                zipf.write(DB_PATH, arcname="tars_state.db")
            if os.path.exists(os.path.join(BASE_DIR, "./TARS.json")):
                zipf.write(os.path.join(BASE_DIR, "./TARS.json"), arcname="TARS.json")
            if os.path.exists(os.path.join(BASE_DIR, ".env")):
                zipf.write(os.path.join(BASE_DIR, ".env"), arcname=".env")
            # Walk chroma
            if os.path.exists(CHROMA_PATH):
                for root, dirs, files in os.walk(CHROMA_PATH):
                    for file in files:
                        zipf.write(os.path.join(root, file), 
                                   os.path.relpath(os.path.join(root, file), os.path.join(CHROMA_PATH, '..')))
        
        st.sidebar.success(f"Backup created: backups/{backup_name}.zip")
        with open(f"backups/{backup_name}.zip", "rb") as f:
            st.sidebar.download_button("⬇️ Download Zip", f, file_name=f"{backup_name}.zip")
            
    except Exception as e:
        st.sidebar.error(f"Backup failed: {e}")

st.sidebar.divider()
st.sidebar.subheader("📣 Shout Tool")
shout_msg = st.sidebar.text_input("Message:", placeholder="Hello from the void...")
if st.sidebar.button("Send to Discord"):
    if DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL != "YOUR_WEBHOOK_URL_HERE":
        try:
            httpx.post(DISCORD_WEBHOOK_URL, json={"content": shout_msg})
            st.sidebar.success("Sent!")
        except Exception as e:
            st.sidebar.error(f"Failed: {e}")
    else:
        st.sidebar.warning("Webhook URL not set.")

# --- MAIN UI TABS ---
# tab_debugger, tab_config to the list of variables and "🔍 Prompt Debugger", "⚙️ Config Editor" to the tab labels
# tab_debugger, tab_config to the list of variables and "🔍 Prompt Debugger", "⚙️ Config Editor" to the tab labels
tab_logs, tab_cli, tab_mem, tab_knowledge, tab_analytics, tab_models, tab_play, tab_debug, tab_conf = st.tabs([
    "📜 Logs", "🖥️ CLI", "🧠 Memories", "🕸️ Knowledge Graph", "📈 Mood", "🤖 Models", "💬 Playground", "🔍 Debug", "⚙️ Config"
])

# TAB 1: DATABASE LOGS
with tab_logs:
    st.subheader("Latest Database Entries")
    
    @st.fragment(run_every=5)
    def show_logs_tab():
        df = get_audit_logs()
        if not df.empty:
            
            # Filters
            col_f1, col_f2 = st.columns([1, 2])
            with col_f1:
                moods = ["All"] + list(df['mood'].unique()) if 'mood' in df.columns else ["All"]
                filter_mood = st.selectbox("Filter by Mood/Status", moods)
            with col_f2:
                search_term = st.text_input("Search Logs", placeholder="Type a keyword (e.g. error, user name)...")
            
            # Apply Filters
            if filter_mood != "All":
                df = df[df['mood'] == filter_mood]
            
            if search_term:
                # Convert all columns to string and search
                df = df[df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)]

            st.dataframe(df, width='stretch', height=600)
        else:
            st.info("No database logs found.")
    show_logs_tab()

# TAB 2: LIVE CLI CONSOLE
with tab_cli:
    st.subheader("🖥️ Real-time Bot Output")
    
    @st.fragment(run_every=2)
    def update_console():
        if os.path.exists(LOG_FILE):
            try:
                # OPTIMIZATION: Check mtime before reading
                mtime = os.path.getmtime(LOG_FILE)
                
                # If cached and file hasn't changed, skip read
                if 'last_log_mtime' not in st.session_state or mtime > st.session_state['last_log_mtime']:
                    st.session_state['last_log_mtime'] = mtime
                    
                    # Robust reading
                    with open(LOG_FILE, "rb") as f:
                        raw_bytes = f.read()
                    
                    if raw_bytes.startswith(b'\xff\xfe') or b'\x00' in raw_bytes[:100]:
                        content = raw_bytes.decode('utf-16', errors='replace')
                    else:
                        content = raw_bytes.decode('utf-8', errors='replace')
                        
                    lines = content.splitlines()
                    st.session_state['log_tail'] = "\n".join(lines[-50:])
                
                tail = st.session_state.get('log_tail', "Waiting for logs...")
                
                # Custom CSS for terminal look
                st.markdown(f"""
                    <div style="
                        background-color: #1e1e1e;
                        color: #00ff00;
                        font-family: 'Consolas', 'Courier New', monospace;
                        font-size: 12px;
                        line-height: 1.2;
                        padding: 10px;
                        border-radius: 5px;
                        height: 500px;
                        overflow-y: auto;
                        white-space: pre-wrap;
                        border: 1px solid #333;
                    ">
                        {tail}
                    </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error reading log file: {e}")
        else:
            st.info("Waiting for bot.log... Bot might be offline.")
    update_console()

# TAB 3: RAG MEMORY BROWSER
with tab_mem:
    st.subheader("ChromaDB Vector Explorer")
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collections = client.list_collections()
        if collections:
            selected_col_name = st.selectbox("Select Collection", [c.name for c in collections])
            collection = client.get_collection(selected_col_name)
            
            # Search functionality
            search_q = st.text_input("Search Memories:")
            if search_q:
                results = collection.query(query_texts=[search_q], n_results=10)
                df_mem = pd.DataFrame({
                    "ID": results['ids'][0],
                    "Document": results['documents'][0],
                    "Metadata": [str(m) for m in results['metadatas'][0]]
                })
                st.write("Search Results:")
                st.dataframe(df_mem, width='stretch')
                
                # Delete functionality
                to_delete = st.multiselect("Select IDs to Delete:", results['ids'][0])
                if st.button("Delete Selected Memories", type="primary"):
                    collection.delete(ids=to_delete)
                    st.success("Deleted!")
                    st.rerun()
            else:
                st.write("Recent Memories (Peek):")
                st.json(collection.peek())
        else:
            st.warning("No memory collections found.")
    except Exception as e:
        st.error(f"Could not connect to ChromaDB: {e}")

# TAB 3.5: KNOWLEDGE GRAPH
with tab_knowledge:
    st.subheader("🕸️ Semantic Knowledge Graph")
    
    col_k1, col_k2 = st.columns([1, 2])
    
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=rw", uri=True, timeout=30)
        try:
            df_facts = pd.read_sql_query("SELECT * FROM facts ORDER BY timestamp DESC", conn)
            
            with col_k1:
                st.write("### 📋 Fact Table")
                if not df_facts.empty:
                    # Make it editable!
                    # We hide ID but keep it for tracking updates
                    edited_df = st.data_editor(
                        df_facts, 
                        column_config={
                            "id": st.column_config.NumberColumn(disabled=True),
                            "timestamp": st.column_config.DatetimeColumn(disabled=True),
                        },
                        num_rows="dynamic",
                        width='stretch',
                        key="fact_editor"
                    )
                    
                    if st.button("💾 Save Changes", type="primary"):
                        try:
                            # 1. Identification
                            # Existing IDs in DB
                            curr_ids = set(df_facts['id'].dropna().tolist())
                            # IDs in Editor
                            new_ids = set(edited_df['id'].dropna().tolist())
                            
                            # 2. Deletions (In DB but not in Editor)
                            to_delete = curr_ids - new_ids
                            if to_delete:
                                placeholders = ",".join("?" * len(to_delete))
                                conn.execute(f"DELETE FROM facts WHERE id IN ({placeholders})", list(to_delete))
                            
                            # 3. Updates & Inserts
                            # Iterate rows
                            for index, row in edited_df.iterrows():
                                if pd.isna(row['id']): 
                                    # Insert (New Row)
                                    # Default user_id to 'dashboard_user' or first row's user_id if smart
                                    uid = row['user_id'] if 'user_id' in row and row['user_id'] else "dashboard_admin"
                                    conn.execute("INSERT INTO facts (user_id, subject, predicate, object, timestamp) VALUES (?, ?, ?, ?, datetime('now'))",
                                                 (uid, row['subject'], row['predicate'], row['object']))
                                else:
                                    # Update
                                    conn.execute("UPDATE facts SET subject=?, predicate=?, object=? WHERE id=?",
                                                 (row['subject'], row['predicate'], row['object'], row['id']))
                            
                            conn.commit()
                            st.success("Knowledge Graph Updated!")
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                else:
                    st.info("No facts extracted yet.")
            
            with col_k2:
                st.write("### 🔗 Interactive Graph")
                if not df_facts.empty:
                    if HAS_GRAPHVIZ:
                        # Create Graphviz DOT
                        dot = Digraph(comment='Knowledge Graph')
                        dot.attr(bgcolor='#0e1117', rankdir='LR')
                        dot.attr('node', shape='box', style='filled', color='#4caf50', fontcolor='black', fontname='Consolas')
                        dot.attr('edge', color='white', fontcolor='white', fontname='Consolas', fontsize='10')
                        
                        # Limit to last 20 facts to prevent spaghetti
                        for _, row in df_facts.head(20).iterrows():
                            s, p, o = row['subject'].replace(":", ""), row['predicate'], row['object'].replace(":", "")
                            dot.edge(s, o, label=p)
                        
                        st.graphviz_chart(dot)
                    else:
                        st.warning("Graphviz library not found. Run `pip install graphviz`.")
                else:
                    st.caption("Add facts to see the graph.")

        except Exception as e:
            st.warning(f"Could not read facts table: {e}")
        finally:
            conn.close()

# TAB 4: MOOD & FEAR ANALYTICS
with tab_analytics:
    st.subheader("TARS's Emotional Stability")
    df = get_audit_logs()
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Mood Distribution
        # Mood Distribution
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            st.write("### 📊 Mood Counts")
            st.bar_chart(df['mood'].value_counts())
        
        with col_a2:
            st.write("### 📈 Mood Timeline (Drill-Down)")
            # Interactive Timeline
            st.scatter_chart(df, x='timestamp', y='mood', color='mood', height=300)

        # Activity Heatmap (Simple aggregation)
        st.divider()
        st.write("### 🕒 Activity Volume")
        # Bin by hour
        df['hour'] = df['timestamp'].dt.hour
        activity_by_hour = df.groupby('hour').size()
        st.bar_chart(activity_by_hour)
    else:
        st.info("Insufficient data for analytics.")

# TAB 5: MODEL SWAPPER
with tab_models:
    st.subheader("Local Model Management")
    if os.path.exists(MODELS_DIR):
        model_files = [f for f in os.listdir(MODELS_DIR) if f.endswith(".gguf")]
        selected_model = st.selectbox("Active Brain (GGUF)", model_files)
        if st.button("Apply & Restart Bot"):
            with open(os.path.join(BASE_DIR, ".active_model"), "w", encoding="utf-8") as f:
                f.write(selected_model)
            st.success(f"Configured for {selected_model}. Restarting bot...")
            os.system("pkill -f script.py") 
    else:
        st.error("Models directory not found.")

# TAB 5.5: PLAYGROUND
with tab_play:
    st.subheader("💬 Direct Neural Link (Playground)")
    st.caption("Talk directly to the local model logic, bypassing Discord.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Message TARS..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)


        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            try:
                # Use REAL Brain (cached memory, fresh client for thread loop)
                # brain = get_tars_brain()  <-- CAUSES EVENT LOOP MISMATCH with AsyncOpenAI
                
                # 1. Get Cached Memory Engine (heavy)
                cached_brain = get_tars_brain()
                memory_engine = cached_brain.memory_engine
                
                # 2. Create FRESH Client (light, bound to new loop)
                from openai import AsyncOpenAI
                client = AsyncOpenAI(
                    base_url=os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1"),
                    api_key=os.getenv("LLM_TOKEN")
                )
                
                # 3. Create FRESH Brain (light if lazy_load=True)
                from brain import CognitiveEngine
                temp_brain = CognitiveEngine(
                    memory_engine=memory_engine,
                    llm_client=client,
                    model_name=os.getenv("MODEL_NAME", "google/gemma-3-27b-it"),
                    comfy_url=os.getenv("COMFY_URL"),
                    local_llm_path="/app/models/google_gemma-3-270m-it-Q8_0.gguf",
                    lazy_load=True
                )
                
                # Prepare history in main thread to avoid session_state thread-safety issues
                history = [m["content"] for m in st.session_state.messages[-10:]]

                # Run Async in Streamlit
                async def run_interaction(conv_hist):
                    # We use a dummy user ID for dashboard to separate from main bot if desired, 
                    # or use "DASHBOARD_ADMIN"
                    return await temp_brain.process_interaction(
                        user_id="DASHBOARD_1",
                        username="Admin",
                        user_text=prompt,
                        channel_id="DASHBOARD",
                        conversation_history=conv_hist
                    )

                # Run in a separate thread to avoid "asyncio.run() cannot be called from a running event loop"
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                     text_resp, img_bytes, sys_prompt, mems = executor.submit(asyncio.run, run_interaction(history)).result()
                
                full_response = text_resp
                message_placeholder.markdown(full_response)
                
                if img_bytes:
                    st.image(io.BytesIO(img_bytes), caption="Generated via Playground")
                
                with st.expander("🔍 Debug Context"):
                    st.text(f"System Prompt Size: {len(sys_prompt)} chars")
                    st.json(mems)

            except Exception as e:
                message_placeholder.error(f"Brain Failure: {e}")
                
            st.session_state.messages.append({"role": "assistant", "content": full_response})

# --- TAB 6: PROMPT VISUALIZER ---
with tab_debug:
    st.subheader("🕵️ Live Prompt Debugger")
    st.caption("Visualizes the last generated prompt composition based on selected log entry.")

    df = get_audit_logs()
    if not df.empty:
        # Let the user pick which interaction to debug
        log_selection = st.selectbox("Select Interaction to Debug", 
                                    df.index, 
                                    format_func=lambda x: f"{df.iloc[x]['timestamp']} - {df.iloc[x]['prompt'][:50]}...")
        
        selected_row = df.iloc[log_selection]

        # Parse the actual prompt data
        full_p = selected_row.get('full_prompt', '')
        p_sections = parse_prompt(full_p)

        def debug_card(title, content):
            st.markdown(f"""
            <div class='debug-label'>{title}</div>
            <div class='debug-box'>{content or "None"}</div>
            """, unsafe_allow_html=True)

        if HAS_GRAPHVIZ:
            st.divider()
            st.subheader("🧠 Prompt Synthesis Flow")
            
            # Helper to wrap text for graph labels (Show ALL text)
            def clean_label(text, width=40):
                text = text or "None"
                # Naive wrap: insert newline every 'width' characters
                return "\\n".join([text[i:i+width] for i in range(0, len(text), width)])

            # Create Flow Chart
            flow = Digraph(comment='Prompt Flow')
            flow.attr(bgcolor='#0e1117', rankdir='LR') # Left to Right flow
            flow.attr('node', shape='box', style='filled', fontname='Consolas')
            flow.attr('edge', color='white', fontname='Consolas', fontsize='10')

            # Nodes with ACTUAL DATA - ALL TEXT
            p_label = f"Persona\\n({clean_label(p_sections.get('Persona', ''))})"
            c_label = f"Context\\n({clean_label(p_sections.get('Context', ''))})"
            i_label = f"Instructions\\n({clean_label(p_sections.get('Instructions', ''))})"
            u_label = f"User Input\\n({clean_label(selected_row['prompt'])})"
            h_label = f"History\\n({clean_label(p_sections.get('History', ''))})"
            m_label = f"Memories\\n({clean_label(p_sections.get('Memories', ''))})"
            f_label = f"Facts\\n({clean_label(p_sections.get('Facts', ''))})"
            
            flow.node('P', p_label, color='#1a237e', fontcolor='white')
            flow.node('C', c_label, color='#1a237e', fontcolor='white')
            flow.node('I', i_label, color='#b71c1c', fontcolor='white')
            
            flow.node('U', u_label, color='#1b5e20', fontcolor='white')
            flow.node('H', h_label, color='#f57f17', fontcolor='black')
            flow.node('M', m_label, color='#4a148c', fontcolor='white')
            flow.node('F', f_label, color='#006064', fontcolor='white')
            
            flow.node('LLM', 'Context Window\n(LLM)', shape='doubleoctagon', color='#212121', fontcolor='#00ff41')

            # Edges with counts/length hint
            flow.edge('P', 'LLM')
            flow.edge('C', 'LLM')
            flow.edge('I', 'LLM')
            flow.edge('U', 'LLM')
            flow.edge('H', 'LLM')
            flow.edge('M', 'LLM')
            flow.edge('F', 'LLM')
            
            st.graphviz_chart(flow)


        # Row 1: System & Context
        col1, col2, col3 = st.columns(3)
        with col1:
            debug_card("System Persona", p_sections.get("Persona", ""))
        with col2:
            debug_card("Interaction Context", p_sections.get("Context", ""))
        with col3:
            debug_card("Instructions", p_sections.get("Instructions", ""))

        # Row 2: Inputs & Memories
        col4, col5, col6 = st.columns(3)
        with col4:
            debug_card("User Input", selected_row['prompt'])
        with col5:
            debug_card("Retrieved Memory", p_sections.get("Memories", "None"))
        with col6:
            debug_card("Recent History", p_sections.get("History", "None"))
            
        facts_text = p_sections.get("Facts", "None")
        debug_card("Known Facts Used", facts_text)
        
        # Mini-Graph for Used Facts
        if HAS_GRAPHVIZ and facts_text and facts_text != "None":
            st.caption("🕸️ Graph of facts used in this specific prompt:")
            dot = Digraph(comment='Debug Graph')
            dot.attr(bgcolor='#0e1117', rankdir='LR')
            dot.attr('node', shape='box', style='filled', color='#4caf50', fontcolor='black', fontname='Consolas')
            dot.attr('edge', color='white', fontcolor='white', fontname='Consolas', fontsize='10')
            
            lines = facts_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith("- "):
                    payload = line[2:]
                    parts = payload.split(" ")
                    if len(parts) >= 3:
                        # Heuristic: Subject Predicate Object...
                        # This is imperfect on flat strings but better than nothing
                        s, p, o = parts[0], parts[1], " ".join(parts[2:])
                        dot.edge(s, o, label=p)
                    else:
                        dot.edge("Context", payload)
            
            st.graphviz_chart(dot)

        # Row 2: Full Prompt Preview
        st.divider()
        st.subheader("Raw GPT Prompt Sent:")
        st.text_area("Final string sent to LLM:", value=full_p, height=400)
    else:
        st.warning("No logs found to visualize.")

# --- TAB 7: CONFIG EDITOR ---
with tab_conf:
    st.subheader("⚙️ System Configuration")
    
    st.write("**TARS Persona UI**")
    nb_json_path = os.path.join(BASE_DIR, "TARS.json")
    if os.path.exists(nb_json_path):
        try:
            with open(nb_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            with st.form("persona_form"):
                new_name = st.text_input("Char Name", data.get("char_name", "TARS"))
                new_persona = st.text_area("Persona Description", data.get("char_persona", ""), height=150)
                new_scenario = st.text_area("World Scenario", data.get("world_scenario", ""), height=100)
                new_examples = st.text_area("Example Dialogue", data.get("example_dialogue", ""), height=150)
                
                if st.form_submit_button("💾 Save Persona"):
                    data["char_name"] = new_name
                    data["char_persona"] = new_persona
                    data["world_scenario"] = new_scenario
                    data["example_dialogue"] = new_examples
                    
                    with open(nb_json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    st.success("Persona updated via Form!")
        except Exception as e:
            st.error(f"Error loading JSON: {e}")
    else:
        st.error("TARS.json not found.")