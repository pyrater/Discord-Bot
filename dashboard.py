import streamlit as st
import sqlite3
import pandas as pd
import os
import psutil
import chromadb
import httpx
import asyncio
import json
import html
import subprocess
import io
import hmac # For secure password comparison
import zipfile
import base64
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

# --- STYLING: NEXUS CORE AESTHETIC ---
def load_css():
    css_path = os.path.join(BASE_DIR, "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            return f"<style>{f.read()}</style>"
    return ""

def nexus_header():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Calculate Neural Stress from recent audit logs
    try:
        df = get_audit_logs().head(20)
        # GoEmotions Stress Labels + System Errors
        stress_labels = ['anger', 'annoyance', 'disappointment', 'disapproval', 'disgust', 'fear', 'grief', 'nervousness', 'remorse', 'sadness', 'error', 'fail', 'warn']
        error_count = len(df[df['mood'].str.lower().str.contains('|'.join(stress_labels), na=False)])
        neural_stress = min(1.0, error_count / 10.0)
        if not df.empty:
            raw_mood = df.iloc[0]['mood']
            # Take only the first word (emotion name) if it has a score or extra text
            last_mood = raw_mood.split('(')[0].strip() if '(' in raw_mood else raw_mood.split()[0] if ' ' in raw_mood else raw_mood
        else:
            last_mood = "STANDBY"
    except:
        neural_stress = 0.0
        last_mood = "UNKNOWN"

    stress_class = "orange" if neural_stress > 0.6 else ("orange" if neural_stress > 0.3 else "")
    
    st.markdown(f"""
        <style>
        .mobile-header {{
            position: relative;
            display: flex; justify-content: space-between; align-items: center;
            padding: 12px 16px 10px;
            border-bottom: 1px solid var(--panel-border);
            background: rgba(4, 6, 9, 0.98);
            backdrop-filter: blur(15px);
            margin-top: -3rem; /* Pull back into top padding */
            z-index: 100;
        }}
        .brand {{
            font-family: 'Rajdhani', sans-serif; font-size: 16px; font-weight: 700;
            color: var(--text-dim); letter-spacing: 2px;
        }}
        .brand span {{
            color: var(--tars-cyan); text-shadow: 0 0 8px var(--tars-cyan-glow);
        }}
        .header-metrics {{
            display: flex; align-items: center; gap: 12px;
            font-family: 'Share Tech Mono', monospace; font-size: 10px;
        }}
        .hm-item {{
            display: flex; flex-direction: column; align-items: flex-end;
            color: var(--text-secondary);
        }}
        .hm-val {{
            color: var(--text-primary); font-size: 12px; font-weight: bold;
        }}
        .hm-val.orange {{ color: var(--tars-amber); text-shadow: 0 0 8px var(--tars-amber-glow); }}
        .header-pulse {{
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--tars-cyan); box-shadow: 0 0 10px var(--tars-cyan);
            animation: pulseGlow 2s infinite;
        }}
        @keyframes pulseGlow {{
            0%,100% {{ opacity: 1; transform: scale(1); }}
            50%      {{ opacity: 0.4; transform: scale(0.7); }}
        }}
        </style>

        <header class="mobile-header">
            <div class="brand">TARS // <span>NEXUS</span></div>
            <div class="header-metrics">
                <div class="hm-item">CPU<span class="hm-val">{cpu}%</span></div>
                <div class="hm-item">RAM<span class="hm-val">{ram}%</span></div>
                <div class="hm-item">STATE<span class="hm-val {stress_class}">{last_mood.upper()[:7]}</span></div>
                <div class="header-pulse"></div>
            </div>
        </header>
    """, unsafe_allow_html=True)

    return neural_stress # Return this so we can override the sidebar calculation later

def render_command_deck():
    """Renders the system control buttons in a tech-card."""
    st.markdown('<div class="tech-card">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    
    with c1:
        if st.button("🟢 SYSTEM REBOOT", use_container_width=True):
            try:
                flag_path = "/app/stop_bot.flag"
                if os.path.exists(flag_path): os.remove(flag_path)
                killed = False
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmd = proc.info['cmdline'] or []
                        if 'python' in proc.info['name'].lower() and any("script.py" in arg for arg in cmd):
                            proc.kill()
                            killed = True
                    except: pass
                st.toast("REBOOT SIGNAL BROADCAST 🚀")
            except Exception as e:
                st.error(f"REBOOT FAILED: {e}")

    with c2:
        if st.button("🔴 EMERGENCY SHUTDOWN", use_container_width=True):
            try:
                with open("/app/stop_bot.flag", "w") as f: f.write("STOP")
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        cmd = proc.info['cmdline'] or []
                        if 'python' in proc.info['name'].lower() and any("script.py" in arg for arg in cmd):
                            proc.kill()
                    except: pass
                st.error("SYSTEM HALTED.")
            except Exception as e:
                st.error(f"HALT FAILED: {e}")

    with c3:
        if st.button("📦 ARCHIVE STATE", use_container_width=True):
            try:
                import shutil
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"tars_backup_{timestamp}"
                if not os.path.exists("backups"): os.makedirs("backups")
                
                with zipfile.ZipFile(f"backups/{backup_name}.zip", 'w') as zipf:
                    if os.path.exists(DB_PATH): zipf.write(DB_PATH, arcname="tars_state.db")
                    if os.path.exists("./TARS.json"): zipf.write("./TARS.json", arcname="TARS.json")
                    if os.path.exists("./.env"): zipf.write("./.env", arcname=".env")
                    if os.path.exists(CHROMA_PATH):
                        for root, _, files in os.walk(CHROMA_PATH):
                            for file in files:
                                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), os.path.join(CHROMA_PATH, '..')))
                
                st.success(f"ARCHIVED: {backup_name}")
                with open(f"backups/{backup_name}.zip", "rb") as f:
                    st.download_button("⬇️ DOWNLINK ARCHIVE", f, file_name=f"{backup_name}.zip", use_container_width=True)
            except Exception as e:
                st.error(f"ARCHIVE FAILED: {e}")
    st.markdown('</div>', unsafe_allow_html=True)

def repair_neural_collection(client, col_name):
    """Attempts to extract data, delete, and re-create a corrupted collection."""
    try:
        st.toast(f"⚡ Initializing Repair for {col_name}...")
        col = client.get_collection(col_name)
        data = col.get()
        
        # Backup
        ids = data['ids']
        documents = data['documents']
        metadatas = data['metadatas']
        
        # Reset
        client.delete_collection(col_name)
        new_col = client.create_collection(col_name)
        
        if ids:
            # Batch adds to avoid memory spikes
            batch_size = 50
            for i in range(0, len(ids), batch_size):
                new_col.add(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
        st.success(f"✅ Collection {col_name} Repaired Successfully!")
        st.rerun()
    except Exception as e:
        st.error(f"❌ Repair Failed: {e}")

# 1. DEFINE YOUR PASSWORD (Or pull from os.environ for better security)
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tars_state.db")
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")
MODELS_DIR = "/app/models/"
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

def check_password():
    if st.query_params.get("auth_success") == "1":
        st.session_state["password_correct"] = True
    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 TARS Nexus Access")
    with st.form("login_form"):
        entered_password = st.text_input("Enter Dashboard Password", type="password")
        if st.form_submit_button("Authenticate"):
            if hmac.compare_digest(entered_password, DASHBOARD_PASSWORD):
                st.session_state["password_correct"] = True
                st.query_params["auth_success"] = "1"
                st.rerun()
            else:
                st.error("😕 Access Denied")
    return False

if not check_password():
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(page_title="TARS Nexus Core", layout="wide", page_icon="🤖", initial_sidebar_state="collapsed")

# --- STYLING: CLEAN NEXUS UI ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    /* Pull app up slightly but keep tabs reachable */
    .stApp { top: -60px; } 
    #root > div:nth-child(1) > div > div > div > div > section > div {padding-top: 2rem;}
    
    /* Custom scanline overlay */
    .scanline-overlay {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0, 248, 255, 0.01) 2px, rgba(0, 248, 255, 0.01) 4px);
        pointer-events: none; z-index: 9999;
    }
    </style>
    <div class="scanline-overlay"></div>
""", unsafe_allow_html=True)

# --- DATA FETCHING ---
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

@st.cache_data(ttl=5)
def get_audit_logs():
    if not os.path.exists(DB_PATH): return pd.DataFrame()
    try:
        # Use Cached Resource with short TTL to keep dashboard reasonably live
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

# --- STATE INITIALIZATION ---
# Initialize session state for controls that are now in other tabs but needed globally
if 'link_strength' not in st.session_state: st.session_state['link_strength'] = 1.0
if 'charge_strength' not in st.session_state: st.session_state['charge_strength'] = 1.0
if 'grouping_mode' not in st.session_state: st.session_state['grouping_mode'] = "Temporal (Radial)"

# Pull values for use in visualizations
link_strength = st.session_state['link_strength']
charge_strength = st.session_state['charge_strength']
grouping_mode = st.session_state['grouping_mode']
is_spatial = (grouping_mode == "Semantic (Force)")

# --- TEMPLATE RENDERING LOGIC ---

def get_mood_paths(df):
    """Generates accurate SVG paths for Valence and Arousal based on GoEmotions."""
    if df is None or df.empty or 'mood' not in df.columns:
        return "M0,50 L100,50", "M0,80 L100,80", "M0,80 L100,80 L100,100 L0,100 Z"
    
    # Mapping GoEmotions to Valence (-1 to 1) and Arousal (-1 to 1)
    # Note: These are simplified heuristics for visualization
    v_a_map = {
        'joy': (0.8, 0.6), 'excitement': (0.7, 0.9), 'amusement': (0.6, 0.4), 'pride': (0.7, 0.5), 'gratitude': (0.9, 0.3),
        'love': (0.9, 0.3), 'caring': (0.8, 0.2), 'optimism': (0.7, 0.4), 'relief': (0.6, -0.3), 'curiosity': (0.5, 0.6),
        'approval': (0.4, 0.1), 'admiration': (0.6, 0.5), 'desire': (0.5, 0.5), 'surprise': (0.3, 0.9),
        'neutral': (0.0, 0.0), 'realization': (0.2, 0.4), 'confusion': (-0.1, 0.4), 'curious': (0.5, 0.6),
        'sadness': (-0.7, -0.4), 'grief': (-0.9, -0.5), 'remorse': (-0.6, -0.2), 'disappointment': (-0.6, -0.1),
        'annoyance': (-0.4, 0.4), 'anger': (-0.8, 0.8), 'disgust': (-0.7, 0.5), 'fear': (-0.6, 0.9),
        'nervousness': (-0.3, 0.7), 'disapproval': (-0.4, 0.2), 'embarrassment': (-0.3, 0.4)
    }

    recent_moods = df['mood'].tail(20).tolist()
    points_v = []
    points_a = []
    
    for i, m_str in enumerate(recent_moods):
        # Extract first word as emotion
        m = m_str.split('(')[0].strip().lower()
        v, a = v_a_map.get(m, (0.0, 0.0))
        
        # Map -1..1 to 0..100 for SVG (Y is inverted: 0 is top, 100 is bottom)
        # Valence: 0.8 -> 10 (High), -0.8 -> 90 (Low)
        x = (i / (len(recent_moods) - 1)) * 100 if len(recent_moods) > 1 else 0
        y_v = 50 - (v * 40)
        y_a = 50 - (a * 40)
        
        points_v.append(f"{x:.1f},{y_v:.1f}")
        points_a.append(f"{x:.1f},{y_a:.1f}")
    
    if not points_v:
        return "M0,50 L100,50", "M0,80 L100,80", "M0,80 L100,80 L100,100 L0,100 Z"

    path_v = "M" + " L".join(points_v)
    path_a = "M" + " L".join(points_a)
    fill_a = path_a + f" L100,100 L0,100 Z"
    
    return path_v, path_a, fill_a

def render_facts_html():
    if not os.path.exists(DB_PATH): return ""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        df = pd.read_sql_query("SELECT subject, predicate, object, timestamp FROM facts ORDER BY timestamp DESC LIMIT 5", conn)
        conn.close()
        rows = ""
        for _, row in df.iterrows():
            rows += f"<tr><td>{html.escape(row['subject'])}</td><td>{html.escape(row['predicate'])}</td><td class='num'>{html.escape(row['object'])}</td><td></td></tr>"
        return rows
    except: return ""

def render_console_html():
    if not os.path.exists(LOG_FILE): return "> Awaiting bot.log..."
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-8:]
        output = ""
        for line in lines:
            if "ERROR" in line or "CRITICAL" in line:
                output += f"<span style='color:#f85149;'>{html.escape(line.strip())}</span><br>"
            else:
                output += f"<span>{html.escape(line.strip())}</span><br>"
        return output
    except: return "> Error reading logs."

def generate_graph_layout(time_filter="ALL"):
    """Generates a 3D isometric graph layout from real SQLite facts for the NEXUS canvas."""
    import math
    
    hubs = [
        {"id": "cog", "x": 0, "y": 0, "r": 30, "h": 75, "hue": 300, "label": "COGNITIVE CORE",
         "meta": "Central processing hub\\nAll knowledge flows through here"}
    ]
    matrices = []
    links_list = []
    hub_hues = [190, 38, 120, 280, 60, 340, 160, 30, 210, 90, 330, 250, 15, 175, 75]
    
    if not os.path.exists(DB_PATH):
        hubs.append({"id": "empty", "x": 0, "y": 120, "r": 20, "h": 40, "hue": 190, "label": "NO DATA", "meta": "No database found"})
        links_list.append(["cog", "empty"])
        return json.dumps({"hubs": hubs, "matrices": matrices, "links": links_list})
    
    time_clause = ""
    if time_filter == "DAY": time_clause = "WHERE timestamp > datetime('now', '-1 day')"
    elif time_filter == "WEEK": time_clause = "WHERE timestamp > datetime('now', '-7 days')"
    elif time_filter == "MONTH": time_clause = "WHERE timestamp > datetime('now', '-30 days')"
    
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        df = pd.read_sql_query(f"SELECT subject, predicate, object, timestamp FROM facts {time_clause} ORDER BY timestamp DESC", conn)
        conn.close()
    except:
        return json.dumps({"hubs": hubs, "matrices": [], "links": []})
    
    if df.empty:
        return json.dumps({"hubs": hubs, "matrices": [], "links": []})
    
    subjects = df['subject'].str.strip().unique()
    total_hubs = len(subjects)
    radius = max(180, 100 + total_hubs * 25)
    
    for i, subj in enumerate(subjects):
        angle = (2 * math.pi * i / total_hubs) - math.pi / 2
        hx = int(math.cos(angle) * radius)
        hy = int(math.sin(angle) * radius)
        hue = hub_hues[i % len(hub_hues)]
        hub_id = f"s_{i}"
        subj_facts = df[df['subject'].str.strip() == subj]
        fact_count = len(subj_facts)
        hub_r = min(26, 14 + fact_count * 2)
        
        fact_lines = []
        for _, row in subj_facts.head(20).iterrows():
            fact_lines.append(f"{row['predicate']}: {row['object']}")
        meta_str = (f"Subject: {subj}\\nFacts: {fact_count}\\n" + "\\n".join(fact_lines)).replace('"', '\\"')
        
        hubs.append({"id": hub_id, "x": hx, "y": hy, "r": hub_r, "h": hub_r * 2,
                      "hue": hue, "label": subj.upper()[:18], "meta": meta_str})
        links_list.append(["cog", hub_id])
        
        if fact_count > 0:
            cols = min(fact_count, 10)
            rows = math.ceil(fact_count / cols)
            mat_x = hx + int(math.cos(angle) * 70)
            mat_y = hy + int(math.sin(angle) * 70)
            matrices.append({"startX": mat_x, "startY": mat_y, "rows": rows, "cols": cols,
                             "spacing": 18, "hue": hue, "parent": hub_id})
    
    for i in range(total_hubs):
        for j in range(i + 1, total_hubs):
            s1 = set(df[df['subject'].str.strip() == subjects[i]]['object'].str.strip().str.lower())
            s2 = set(df[df['subject'].str.strip() == subjects[j]]['object'].str.strip().str.lower())
            if s1 & s2: links_list.append([f"s_{i}", f"s_{j}"])
    
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collections = client.list_collections()
        for ci, col in enumerate(collections):
            ch_angle = (2 * math.pi * (total_hubs + ci) / (total_hubs + len(collections))) - math.pi / 2
            ch_x = int(math.cos(ch_angle) * (radius + 100))
            ch_y = int(math.sin(ch_angle) * (radius + 100))
            ch_id = f"vec_{ci}"
            try: vec_count = client.get_collection(col.name).count()
            except: vec_count = 0
            hubs.append({"id": ch_id, "x": ch_x, "y": ch_y, "r": min(22, 12 + vec_count // 10),
                          "h": 40, "hue": 190, "label": col.name.upper()[:14],
                          "meta": f"Vector Store: {col.name}\\nEntries: {vec_count}"})
            links_list.append(["cog", ch_id])
            if vec_count > 0:
                v_cols = min(vec_count, 8)
                v_rows = min(math.ceil(vec_count / v_cols), 6)
                matrices.append({"startX": ch_x + int(math.cos(ch_angle) * 60),
                                  "startY": ch_y + int(math.sin(ch_angle) * 60),
                                  "rows": v_rows, "cols": v_cols, "spacing": 16, "hue": 190, "parent": ch_id})
    except: pass
    
    return json.dumps({"hubs": hubs, "matrices": matrices, "links": links_list})



def render_dashboard_template():
    # Use interval=None for non-blocking if called frequently
    cpu = psutil.cpu_percent(interval=None) 
    ram = psutil.virtual_memory().percent
    # Neural Stress & Mood
    global neural_stress, current_state
    try:
        # Re-fetch during refresh for NEXUS
        df_logs_refresh = get_audit_logs()
        stress_labels = ['anger', 'annoyance', 'disappointment', 'disapproval', 'disgust', 'fear', 'grief', 'nervousness', 'remorse', 'sadness', 'error', 'fail', 'warn']
        recent_logs = df_logs_refresh.head(20)
        error_count = len(recent_logs[recent_logs['mood'].str.lower().str.contains('|'.join(stress_labels), na=False)])
        refresh_stress = min(1.0, error_count / 10.0)
        refresh_state = recent_logs.iloc[0]['mood'].upper() if not recent_logs.empty else "STANDBY"
    except:
        refresh_stress = neural_stress
        refresh_state = current_state

    v_path, a_path, a_fill = get_mood_paths(df_logs_refresh)
    
    # Read Template
    template_path = os.path.join(BASE_DIR, "assets", "example template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        tmpl = f.read()
    
    # Inject Data
    tmpl = tmpl.replace("__CPU__", str(f"{cpu:.1f}"))
    tmpl = tmpl.replace("__RAM__", str(ram))
    tmpl = tmpl.replace("__STRESS__", str(int(refresh_stress * 100)))
    tmpl = tmpl.replace("__STATE__", refresh_state[:12])
    # Firing rate could be based on message frequency in logs
    try:
        timestamps = pd.to_datetime(df_logs_refresh['timestamp'], errors='coerce')
        # If timestamps have timezone, remove it for comparison with naive now()
        if timestamps.dt.tz is not None:
            timestamps = timestamps.dt.tz_localize(None)
        fire_rate = len(df_logs_refresh[timestamps > (pd.Timestamp.now() - pd.Timedelta(minutes=5))]) / 5
    except Exception as e:
        fire_rate = 0.0 # Fallback
    tmpl = tmpl.replace("__SYNAPTIC_RATE__", str(f"{fire_rate:.2f}"))
    
    tmpl = tmpl.replace("__FACTS_TABLE__", render_facts_html())
    tmpl = tmpl.replace("__CONSOLE_OUTPUT__", render_console_html())
    tmpl = tmpl.replace("__VALENCE_PATH__", v_path)
    tmpl = tmpl.replace("__AROUSAL_PATH__", a_path)
    tmpl = tmpl.replace("__AROUSAL_FILL_PATH__", a_fill)
    
    # Inject the real knowledge graph data for the center canvas visualization
    tmpl = tmpl.replace("__GRAPH_DATA__", generate_graph_layout())
    
    # Inject live timestamp so user can confirm refresh
    from datetime import datetime
    tmpl = tmpl.replace("__UPDATED__", datetime.now().strftime("%H:%M:%S"))
    
    st.components.v1.html(tmpl, height=800, scrolling=False)

def render_mobile_template():
    """Renders the mobile-optimized NEXUS template with real data."""
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    global neural_stress, current_state
    try:
        df_logs_m = get_audit_logs()
        stress_labels = ['anger', 'annoyance', 'disappointment', 'disapproval', 'disgust', 'fear', 'grief', 'nervousness', 'remorse', 'sadness', 'error', 'fail', 'warn']
        recent_m = df_logs_m.head(20)
        err_ct = len(recent_m[recent_m['mood'].str.lower().str.contains('|'.join(stress_labels), na=False)])
        m_stress = min(1.0, err_ct / 10.0)
        m_state = recent_m.iloc[0]['mood'].upper()[:12] if not recent_m.empty else "STANDBY"
    except:
        m_stress = neural_stress
        m_state = current_state
        df_logs_m = pd.DataFrame()

    v_path, a_path, a_fill = get_mood_paths(df_logs_m)

    template_path = os.path.join(BASE_DIR, "assets", "tars-mobile.html")
    with open(template_path, "r", encoding="utf-8") as f:
        tmpl = f.read()

    # Core stats
    tmpl = tmpl.replace("__CPU__", str(f"{cpu:.1f}"))
    tmpl = tmpl.replace("__RAM__", str(ram))
    tmpl = tmpl.replace("__STRESS__", str(int(m_stress * 100)))
    tmpl = tmpl.replace("__STATE__", m_state)

    # Knowledge Graph rows (grouped by subject)
    kg_rows = ""
    total_facts = 0
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        df_facts = pd.read_sql_query("SELECT subject, predicate, object FROM facts", conn)
        conn.close()
        total_facts = len(df_facts)
        subjects = df_facts['subject'].str.strip().value_counts().head(8)
        max_count = subjects.max() if not subjects.empty else 1
        for subj, count in subjects.items():
            pct = int((count / max_count) * 100)
            kg_rows += f'<div class="k-row"><span class="k-label">{html.escape(subj[:20])}</span>'
            kg_rows += f'<span class="k-range">{count}</span>'
            kg_rows += f'<span class="k-num">{pct}.{count % 100:03d}</span>'
            kg_rows += f'<div class="k-bar-wrap"><div class="k-bar-bg"><div class="k-bar-fill" style="width:{pct}%"></div></div></div></div>'
    except:
        kg_rows = '<div class="k-row"><span class="k-label">No data</span></div>'
    tmpl = tmpl.replace("__KNOWLEDGE_ROWS__", kg_rows)

    # Console output
    tmpl = tmpl.replace("__CONSOLE_OUTPUT__", render_console_html())

    # Memory cards from audit logs
    mem_cards = ""
    total_memories = 0
    try:
        recent_entries = df_logs_m.head(6)
        total_memories = len(df_logs_m)
        for _, row in recent_entries.iterrows():
            ts = str(row.get('timestamp', ''))[:19].replace('T', ' // ').replace('-', '-')
            msg = html.escape(str(row.get('message', row.get('mood', '')))[:120])
            mem_cards += f'<div class="memory-card"><div class="memory-card-ts">{ts}</div><div class="memory-card-body">{msg}</div></div>'
    except:
        mem_cards = '<div class="memory-card"><div class="memory-card-body">No memories available.</div></div>'
    tmpl = tmpl.replace("__MEMORY_CARDS__", mem_cards)
    tmpl = tmpl.replace("__TOTAL_MEMORIES__", f"{total_memories:,}")
    tmpl = tmpl.replace("__TOTAL_FACTS__", f"{total_facts:,}")

    # 24h activity count
    try:
        timestamps_m = pd.to_datetime(df_logs_m['timestamp'], errors='coerce')
        if timestamps_m.dt.tz is not None:
            timestamps_m = timestamps_m.dt.tz_localize(None)
        activity_24h = len(df_logs_m[timestamps_m > (pd.Timestamp.now() - pd.Timedelta(hours=24))])
    except:
        activity_24h = 0
    tmpl = tmpl.replace("__ACTIVITY_24H__", f"{activity_24h:,}")

    # Mood chart paths
    tmpl = tmpl.replace("__VALENCE_PATH__", v_path)
    tmpl = tmpl.replace("__AROUSAL_PATH__", a_path)
    tmpl = tmpl.replace("__AROUSAL_FILL_PATH__", a_fill)

    # Mood tags from recent moods
    mood_tags = ""
    try:
        tag_colors = ['cyan', 'magenta', 'orange']
        recent_moods = df_logs_m['mood'].head(5).unique()
        for i, mood in enumerate(recent_moods[:5]):
            color = tag_colors[i % len(tag_colors)]
            clean_mood = mood.split('(')[0].strip() if '(' in mood else mood.split()[0] if ' ' in mood else mood
            mood_tags += f'<span class="mood-tag {color}">{html.escape(clean_mood[:12])}</span>'
    except:
        mood_tags = '<span class="mood-tag cyan">STANDBY</span>'
    tmpl = tmpl.replace("__MOOD_TAGS__", mood_tags)

    # Valence/Arousal numeric values
    try:
        mood_map = {'joy': (0.8, 0.6), 'curiosity': (0.5, 0.7), 'anger': (-0.7, 0.8), 'sadness': (-0.6, 0.2),
                    'neutral': (0.0, 0.3), 'approval': (0.6, 0.4), 'excitement': (0.7, 0.9)}
        last_mood_raw = df_logs_m.iloc[0]['mood'].lower().split('(')[0].strip() if not df_logs_m.empty else 'neutral'
        v_val, a_val = mood_map.get(last_mood_raw, (0.0, 0.3))
    except:
        v_val, a_val = 0.0, 0.3
    tmpl = tmpl.replace("__VALENCE_VAL__", f"{v_val:+.2f}")
    tmpl = tmpl.replace("__AROUSAL_VAL__", f"{a_val:+.2f}")
    # Cognitive Map (D3 force graph data - same format as Brain Explorer)
    cog_nodes = [
        {"id": "USER", "name": "USER INPUT", "color": "#00f0ff", "size": 20, "group": "core"},
        {"id": "BRAIN", "name": "COGNITIVE CORE", "color": "#bc13fe", "size": 32, "group": "core"},
        {"id": "LLM", "name": "LLM API", "color": "#5865f2", "size": 18, "group": "core"}
    ]
    cog_links = [
        {"source": "USER", "target": "BRAIN", "value": "core"},
        {"source": "BRAIN", "target": "LLM", "value": "core"}
    ]
    try:
        if os.path.exists(DB_PATH):
            hub_id = "hub_facts"
            cog_nodes.append({"id": hub_id, "name": "KNOWLEDGE BASE", "color": "#3fb950", "size": 22, "group": "hub"})
            cog_links.append({"source": "BRAIN", "target": hub_id, "value": "hub"})
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            df_cog = pd.read_sql_query("SELECT subject, predicate, object FROM facts ORDER BY rowid DESC", conn)
            conn.close()
            subjects_seen = {}
            for i, row in df_cog.iterrows():
                subj = row['subject'].strip()
                obj = row['object'].strip()
                pred = row['predicate'].strip()
                # Subject nodes (deduplicated)
                if subj not in subjects_seen:
                    sid = f"s_{subj.replace(' ','_')}"
                    cog_nodes.append({"id": sid, "name": subj.upper()[:16], "color": "#1f6feb", "size": 12, "group": "user"})
                    cog_links.append({"source": hub_id, "target": sid, "value": "category"})
                    subjects_seen[subj] = sid
                # Object/fact nodes
                oid = f"o_{i}"
                cog_nodes.append({"id": oid, "name": obj[:20], "color": "#3fb950", "size": 6, "group": "data"})
                cog_links.append({"source": subjects_seen[subj], "target": oid, "value": "fact"})
        try:
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            collections = client.list_collections()
            colors = ["#ffca28", "#58a6ff", "#f85149", "#d29922"]
            for idx, col in enumerate(collections):
                cid = f"vec_{col.name}"
                cog_nodes.append({"id": cid, "name": f"VEC:{col.name.upper()[:10]}", "color": colors[idx % len(colors)], "size": 16, "group": "hub"})
                cog_links.append({"source": "BRAIN", "target": cid, "value": "hub"})
                try:
                    collection = client.get_collection(col.name)
                    peek = collection.peek(limit=50)
                    if peek and 'ids' in peek:
                        for j, doc_id in enumerate(peek['ids']):
                            did = f"d_{col.name}_{j}"
                            doc_text = peek['documents'][j][:20] if j < len(peek['documents']) else doc_id[:20]
                            cog_nodes.append({"id": did, "name": doc_text, "color": colors[idx % len(colors)], "size": 5, "group": "data"})
                            cog_links.append({"source": cid, "target": did, "value": "data"})
                except: pass
        except: pass
    except: pass
    tmpl = tmpl.replace("__COG_NODES__", json.dumps(cog_nodes))
    tmpl = tmpl.replace("__COG_LINKS__", json.dumps(cog_links))

    st.components.v1.html(tmpl, height=800, scrolling=True)

# --- GLOBAL STATE ---
# Neural Stress & Mood (Shared across tabs)
df_logs_global = get_audit_logs()
try:
    stress_labels = ['anger', 'annoyance', 'disappointment', 'disapproval', 'disgust', 'fear', 'grief', 'nervousness', 'remorse', 'sadness', 'error', 'fail', 'warn']
    recent_logs_global = df_logs_global.head(20)
    error_count_global = len(recent_logs_global[recent_logs_global['mood'].str.lower().str.contains('|'.join(stress_labels), na=False)])
    neural_stress = min(1.0, error_count_global / 10.0)
    current_state = recent_logs_global.iloc[0]['mood'].upper() if not recent_logs_global.empty else "STANDBY"
except:
    neural_stress = 0.0
    current_state = "UNKNOWN"

# Physics Calculation
neural_speed = 0.0006 * (1 + neural_stress * 2)

# --- MAIN UI LAYOUT ---
tab_nexus, tab_mobile, tab_brain_explorer, tab_knowledge, tab_mem, tab_analytics, tab_models, tab_play, tab_logs, tab_cli, tab_debug, tab_conf = st.tabs([
    "🛰️ NEXUS", "📱 Nexus_mobile", "🧠 Brain Explorer", "🕸️ Knowledge Graph", "🧠 Memories", "📈 Mood", "🤖 Models", "💬 Playground", "📜 Logs", "🖥️ CLI", "🔍 Debug", "⚙️ Config"
])

with tab_nexus:
    render_dashboard_template()

with tab_mobile:
    render_mobile_template()

# TAB 1: DATABASE LOGS (MOVED DOWN)
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
                search_term = st.text_input("Search Logs", placeholder="Type a keyword...")
            
            # Apply Filters
            if filter_mood != "All":
                df = df[df['mood'] == filter_mood]
            if search_term:
                df = df[df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)]

            st.dataframe(df, use_container_width=True, height=600)
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
                mtime = os.path.getmtime(LOG_FILE)
                if 'last_log_mtime' not in st.session_state or mtime > st.session_state['last_log_mtime']:
                    st.session_state['last_log_mtime'] = mtime
                    with open(LOG_FILE, "rb") as f:
                        raw_bytes = f.read()
                    
                    if raw_bytes.startswith(b'\xff\xfe') or b'\x00' in raw_bytes[:100]:
                        content = raw_bytes.decode('utf-16', errors='replace')
                    else:
                        content = raw_bytes.decode('utf-8', errors='replace')
                        
                    lines = content.splitlines()
                    st.session_state['log_tail'] = "\n".join(lines[-50:])
                
                tail = st.session_state.get('log_tail', "Waiting for logs...")
                
                st.markdown(f"""
                    <div style="
                        background-color: #0d1117;
                        color: #58a6ff;
                        font-family: 'JetBrains Mono', monospace;
                        font-size: 9px !important;
                        line-height: 1.25 !important;
                        padding: 10px !important;
                        border-radius: 8px !important;
                        height: 500px !important;
                        overflow-y: auto !important;
                        white-space: pre-wrap !important;
                        border: 1px solid rgba(0, 240, 255, 0.15) !important;
                        box-shadow: inset 0 0 10px rgba(0,0,0,0.5) !important;
                    ">
                        {tail}
                    </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Console Stream Error: {e}")
        else:
            st.info("Waiting for bot.log...")
    update_console()

# TAB 4: BRAIN EXPLORER
with tab_brain_explorer: # Renamed from tab_brain_explorer to tab_brain in instruction, but original code uses tab_brain_explorer. Sticking to original tab name.
    st.markdown("### 🧠 Neural Core Explorer") # Changed from st.subheader and st.caption
    
    # Phase 3: Cognitive Control Layer
    # On mobile landscape, a 2:1 ratio can squish the slider too much. Using equal or removing ratios is safer if not strictly needed, but 2:1 is usually okay if the container is wide enough.
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        time_range = st.select_slider(
            "🕒 Memory Time Travel (Historical Perspective)",
            options=["ALL", "MONTH", "WEEK", "DAY"],
            value="ALL",
            help="Filter TARS's cognitive map by temporal depth."
        )
    with col_ctrl2:
        # Phase 3: Mutation Bridge (Handling signals from JS)
        if "delete_node" in st.query_params:
            del_id = st.query_params["delete_node"]
            if st.button(f"🗑️ CONFIRM DELETION OF {del_id}", type="primary"):
                # Real deletion logic would go here (ChromaDB or SQLite)
                st.info(f"Purging node {del_id} from long-term memory...")
                # ... (Actual purge logic) ...
                st.query_params.clear()
                st.rerun()
            if st.button("Cancel"):
                st.query_params.clear()
                st.rerun()

    # 1. FETCH DATA FOR HIERARCHICAL VISUALIZATION
    # Core architecture nodes (always present)
    nodes = [
        {"id": "USER", "name": "USER INPUT", "color": "#00f0ff", "size": 20, "group": "core"},
        {"id": "BRAIN", "name": "COGNITIVE CORE", "color": "#bc13fe", "size": 32, "group": "core"},
        {"id": "LLM", "name": "LLM API", "color": "#5865f2", "size": 18, "group": "core"}
    ]
    links = [
        {"source": "USER", "target": "BRAIN", "value": "core"},
        {"source": "BRAIN", "target": "LLM", "value": "core"}
    ]

    try:
        # Time Filter Thresholds
        threshold_days = 9999
        if time_range == "DAY": threshold_days = 1
        elif time_range == "WEEK": threshold_days = 7
        elif time_range == "MONTH": threshold_days = 30

        # =============================================
        # PRIMARY DATA SOURCE: SQLite Knowledge Graph
        # (Same source as the Knowledge Graph tab)
        # =============================================
        if os.path.exists(DB_PATH):
            hub_id = "hub_facts"
            nodes.append({
                "id": hub_id,
                "name": "HUB: KNOWLEDGE BASE",
                "color": "#3fb950",
                "size": 24,
                "group": "hub",
                "details": "Source: SQLite Facts Database",
                "time_score": 1
            })
            links.append({"source": "BRAIN", "target": hub_id, "value": "hub", "strength": 0.9})
            
            try:
                conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
                df_facts = pd.read_sql_query("SELECT id, subject, predicate, object, timestamp FROM facts ORDER BY timestamp DESC", conn)
                conn.close()
                
                # Group by Subject for Hierarchy (KNOWLEDGE BASE -> Subject Entity -> Facts)
                subjects_map = {}
                objects_map = {}  # Track unique objects for cross-linking

                for i, row in df_facts.iterrows():
                    subj = row['subject'].strip()
                    obj = row['object'].strip()
                    pred = row['predicate'].strip()
                    
                    # Temporal scoring & filtering
                    time_score = 1
                    days_old = 0
                    try:
                        dt = pd.to_datetime(row['timestamp'])
                        days_old = (pd.Timestamp.now() - dt.tz_localize(None)).days
                        if days_old <= 1: time_score = 1
                        elif days_old <= 7: time_score = 2
                        else: time_score = 3
                    except: pass

                    if days_old > threshold_days:
                        continue
                    
                    # 1. Create Subject Entity Node if needed
                    if subj not in subjects_map:
                        subj_id = f"subj_{subj.replace(' ', '_')}"
                        nodes.append({
                            "id": subj_id,
                            "name": subj.upper(),
                            "color": "#1f6feb",
                            "size": 16,
                            "group": "user",
                            "details": f"ENTITY: {subj}\nTYPE: Subject\nFacts: {len(df_facts[df_facts['subject'].str.strip() == subj])}",
                            "time_score": 1
                        })
                        links.append({"source": hub_id, "target": subj_id, "value": "category", "strength": 0.6})
                        subjects_map[subj] = subj_id
                    
                    # 2. Create Object Node if unique enough (avoid duplicates)
                    obj_key = obj.lower().strip()
                    if obj_key not in objects_map:
                        obj_id = f"obj_{obj_key.replace(' ', '_')}_{i}"
                        nodes.append({
                            "id": obj_id,
                            "name": obj[:30],
                            "color": "#3fb950",
                            "size": 8,
                            "group": "data",
                            "details": f"FACT: {subj} {pred} {obj}\nLEARNED: {row['timestamp']}",
                            "time_score": time_score
                        })
                        objects_map[obj_key] = obj_id
                    
                    # 3. Link Subject -> Object with Predicate as relationship
                    links.append({
                        "source": subjects_map[subj], 
                        "target": objects_map[obj_key], 
                        "value": "fact", 
                        "strength": 0.4,
                        "label": pred
                    })

            except Exception as db_e:
                st.sidebar.warning(f"Skipping fact engine: {db_e}")
        
        # =============================================
        # SECONDARY DATA SOURCE: ChromaDB Vector Store
        # (Optional - gracefully fails without breaking)
        # =============================================
        try:
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            collections = client.list_collections()
            
            hub_colors = ["#ffca28", "#58a6ff", "#f85149", "#d29922", "#8b949e"]
            
            for idx, col in enumerate(collections):
                hub_id = f"hub_{col.name}"
                color = hub_colors[idx % len(hub_colors)]
                
                nodes.append({
                    "id": hub_id,
                    "name": f"VEC: {col.name.upper()}",
                    "color": color,
                    "size": 18,
                    "group": "hub",
                    "details": f"Vector Collection: {col.name}",
                    "time_score": 1
                })
                links.append({"source": "BRAIN", "target": hub_id, "value": "hub"})
                
                try:
                    collection = client.get_collection(col.name)
                    peek = collection.peek(limit=30)
                    
                    if not peek or 'ids' not in peek: continue
                    
                    for i, doc_id in enumerate(peek['ids']):
                        full_text = peek['documents'][i] if i < len(peek['documents']) else "No Content"
                        metadata = peek['metadatas'][i] if (peek['metadatas'] and i < len(peek['metadatas'])) else {}
                        
                        # Temporal filtering
                        days_old = 0
                        time_score = 1
                        if "timestamp" in metadata:
                            try:
                                dt = pd.to_datetime(metadata["timestamp"])
                                days_old = (pd.Timestamp.now() - dt.tz_localize(None)).days
                                if days_old <= 1: time_score = 1
                                elif days_old <= 7: time_score = 2
                                else: time_score = 3
                            except: pass
                        
                        if days_old > threshold_days:
                            continue

                        # Sentiment coloring
                        sentiment_color = color
                        if "error" in full_text.lower() or "fail" in full_text.lower():
                            sentiment_color = "#f85149"
                        elif "success" in full_text.lower() or "done" in full_text.lower():
                            sentiment_color = "#7ee787"
                        
                        display_name = full_text[:35] + "…" if len(full_text) > 35 else full_text
                        node_id = f"mem_{col.name}_{i}"
                        nodes.append({
                            "id": node_id,
                            "name": display_name,
                            "color": sentiment_color,
                            "size": 6,
                            "group": "data",
                            "details": full_text,
                            "metadata": str(metadata),
                            "time_score": time_score
                        })
                        links.append({"source": hub_id, "target": node_id, "value": "data", "strength": 0.8})
                        
                        # Cross-link: if memory text mentions a known subject, connect them
                        for subj_name, subj_node_id in subjects_map.items():
                            if subj_name.lower() in full_text.lower():
                                links.append({"source": node_id, "target": subj_node_id, "value": "cross", "strength": 0.15})
                                break  # Only one cross-link per memory
                                
                except Exception as inner_e:
                    pass  # Silently skip corrupted collections
        except Exception as chroma_e:
            pass  # ChromaDB entirely unavailable - that's fine, facts are primary

        # Calculate Global Brain Sentiment for Background Pulse
        active_data_nodes = [n for n in nodes if n['group'] == 'data']
        avg_sentiment = 0
        if active_data_nodes:
            # Simple heuristic: positive color has high green/blue, negative high red
            # But we already have colors, let's just use a simplified pulse index
            # Or better, look at the mean of time_scores/colors
            avg_sentiment = sum(1 if n['color'] == '#3fb950' else (-1 if n['color'] == '#f85149' else 0) for n in active_data_nodes) / len(active_data_nodes)
        
        pulse_color = "#3fb950" if avg_sentiment > 0.1 else ("#f85149" if avg_sentiment < -0.1 else "#58a6ff")
        pulse_alpha = 0.05 + (abs(avg_sentiment) * 0.1)

    except Exception as e:
        st.sidebar.error(f"Brain Viz Mapping Error: {e}")
        pulse_color = "#58a6ff"
        pulse_alpha = 0.05

    # Serialize and Inject with Guards
    try:
        nodes_json = json.dumps(nodes)
        links_json = json.dumps(links)
    except Exception as e:
        st.error(f"Brain Data Serialization Error: {e}")
        nodes_json = "[]"
        links_json = "[]"

    BRAIN_EXPLORER_CODE = f"""
    <div id="brain-viz-container" style="width:100%; height:min(900px, 80vh); background:transparent; position:relative; overflow:hidden;">
        <svg id="brain-viz" style="width:100%; height:100%; cursor:move;"></svg>
        
        <div id="brain-search-container" style="position:absolute; top:80px; left:20px; z-index:50; display:flex; gap:10px;">
            <input type="text" id="node-search" placeholder="Search cognitive map..." 
                style="background: rgba(15,15,15,0.85); border: 1px solid rgba(88,166,255,0.4); border-radius: 6px; padding: 10px 15px; color: #fff; font-family: monospace; width: 250px; max-width: 80vw; backdrop-filter: blur(10px); outline: none;">
        </div>

        <div id="brain-details" style="position:absolute; top:70px; right:5%; width:90%; max-width:350px; background: rgba(10,10,10,0.95); border: 1px solid rgba(0,248,255,0.3); padding:15px; border-radius:10px; font-family: monospace; font-size:11px; backdrop-filter:blur(15px); z-index:1000; box-shadow: 0 10px 40px rgba(0,0,0,0.8); transition: all 0.3s; display:none;">
            <div style="color:#7dd3fc; font-weight:bold; border-bottom:1px solid #333; padding-bottom:8px; margin-bottom:10px; letter-spacing:1px; display:flex; justify-content:space-between;">
                <span>NEURAL TELEMETRY</span>
                <span id="close-details" style="cursor:pointer; color:#777; font-size:24px; line-height:0.5; padding:5px;" onclick="document.getElementById('brain-details').style.display='none'">×</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div id="unit-status" style="color: #7dd3fc;">Stress: <span style="font-weight:bold;">{int(neural_stress*100)}%</span></div>
                <div id="pulse-indicator" style="width:10px; height:10px; border-radius:50%; background: #444; box-shadow: 0 0 8px #444; animation: heartbeat {1.5 - neural_stress}s infinite;"></div>
            </div>
            <div id="node-info" style="margin-top:8px; color: #7dd3fc; font-weight:bold; font-size:12px;">Target: STANDBY</div>
            
            <div style="margin-top:12px; border-top:1px solid #222; padding-top:10px;">
                <div style="color: #58a6ff; font-size:10px; margin-bottom:5px; text-transform:uppercase;">Metadata Content:</div>
                <div id="multimodal-preview" style="display:none; margin-bottom:10px; border-radius:4px; overflow:hidden; border:1px solid #333;"></div>
                <div id="full-content" style="color: #7dd3fc; font-size:11px; line-height:1.4; max-height:250px; overflow-y:auto; word-break:break-word; scrollbar-width:thin;">Select a node to view metadata...</div>
                <div id="node-meta" style="color: #7dd3fc; font-size:9px; margin-top:10px; border-top: 1px dashed #333; padding-top:8px; display:none;"></div>
            </div>

            <div id="button-bridge" style="margin-top:15px; display:none; gap:5px;">
                <button id="del-btn" style="flex:1; background:rgba(248,81,73,0.1); border:1px solid #f85149; color:#f85149; padding:5px; font-size:9px; cursor:pointer; border-radius:4px;">[PURGE MEMORY]</button>
                <button id="edit-btn" style="flex:1; background:rgba(88,166,255,0.1); border:1px solid #58a6ff; color:#58a6ff; padding:5px; font-size:9px; cursor:pointer; border-radius:4px;">[RE-VECTOR]</button>
            </div>

            <div id="diag-info" style="color: #7dd3fc; margin-top:15px; font-size:9px; border-top: 1px solid #222; padding-top:10px;">Mapped: {len(nodes)} Neural Points</div>
            <div style="color: #7dd3fc; font-size:9px; margin-top:5px;">SHIFT+CLICK TO UNPIN • ENTER TO SEARCH</div>
        </div>

        <style>
            @keyframes heartbeat {{
                0% {{ transform: scale(1); opacity: 0.8; }}
                50% {{ transform: scale(1.4); opacity: 1; }}
                100% {{ transform: scale(1); opacity: 0.8; }}
            }}
            
            /* Velocity Flow Animation */
            .packet-flow {{
                stroke-dasharray: 4, 12;
                stroke-dashoffset: 100;
                animation: flowForward 3s linear infinite;
                stroke-opacity: 0.8 !important;
            }}

            @keyframes flowForward {{
                to {{ stroke-dashoffset: 0; }}
            }}

            /* Security Ripple */
            .core-ripple {{
                fill: none;
                stroke: rgba(88, 166, 255, 0.4);
                stroke-width: 1px;
                animation: nexus-ripple 4s cubic-bezier(0, 0.2, 0.8, 1) infinite;
            }}

            @keyframes nexus-ripple {{
                0% {{ r: 10; opacity: 1; }}
                100% {{ r: 120; opacity: 0; }}
            }}

            /* Responsive Brain Explorer */
            @media (max-width: 768px) {{
                #brain-viz-container {{
                    height: 400px !important;
                }}
                #brain-details {{
                    position: relative !important;
                    top: auto !important;
                    right: auto !important;
                    width: 100% !important;
                    max-width: 100% !important;
                    margin-top: 10px;
                    border-radius: 8px !important;
                }}
                #brain-search-container {{
                    flex-direction: column;
                    gap: 5px;
                }}
                #brain-search-container input {{
                    width: 100% !important;
                }}
            }}
        </style>
    </div>
    
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script>
    (function() {{
        const raw_nodes = {nodes_json};
        const raw_links = {links_json};
        console.log("Brain Viz: Data Loaded. Nodes:", raw_nodes.length, "Links:", raw_links.length);
        
        let is3D = false;
        let g, zoom, svg_root, simulation;
        
        window.runBrainViz = function() {{ if (typeof d3 !== 'undefined') init(); }};
        window.toggle3D = function() {{
            is3D = !is3D;
            document.getElementById("toggle-3d").innerText = is3D ? "[2D MODE]" : "[3D MODE]";
            init();
        }};

        const container = document.getElementById("brain-viz-container");
        const svg = d3.select("#brain-viz");

        function init() {{
            const width = container.offsetWidth || 800;
            const height = container.offsetHeight || 900;
            svg.selectAll("*").remove();
            svg_root = svg;
            g = svg.append("g");
            
            zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", (e) => {{
                g.attr("transform", e.transform);
                // Dynamic LOD: Fade out small nodes when zoomed out
                g.selectAll(".data-node").style("opacity", e.transform.k < 0.4 ? 0.3 : 1);
                g.selectAll(".data-label").style("opacity", e.transform.k > 1.8 ? 1 : 0);
            }});
            svg.call(zoom);

            simulation = d3.forceSimulation(raw_nodes).alphaDecay(0.05)
                .force("link", d3.forceLink(raw_links).id(d => d.id).distance(d => d.value === 'core' ? 300 : 150).strength({link_strength}))
                .force("charge", d3.forceManyBody().strength(d => {{
                    if (d.group === 'core') return -8000 * {charge_strength};
                    if (d.group === 'hub') return -2000 * {charge_strength};
                    return -150 * {charge_strength};
                }}))
                .force("collide", d3.forceCollide().radius(d => d.size + 10));

            if (is3D) {{
                // Refined Spherical Projection
                simulation.force("r", d3.forceRadial(d => d.group === 'core' ? 0 : 350, width/2, height/2).strength(0.8));
            }} else if ({'true' if is_spatial else 'false'}) {{
                // Force-Directed Semantic Grouping
                simulation.force("center", d3.forceCenter(width/2, height/2))
                    .force("collide", d3.forceCollide().radius(d => d.size + 15));
            }} else {{
                // Radial Temporal
                simulation.force("center", d3.forceCenter(width/2, height/2))
                    .force("r", d3.forceRadial(d => {{
                        if (d.group === 'core') return 0;
                        if (d.group === 'hub') return 300;
                        return 300 + (d.time_score * 180);
                    }}, width/2, height/2).strength(0.4));
            }}

            const link = g.append("g").selectAll("line").data(raw_links).enter().append("line")
                .attr("class", d => d.value === 'core' ? "packet-flow" : "")
                .attr("stroke", d => d.value === 'cross' ? "#58a6ff" : (d.value === 'core' ? "#58a6ff" : "#333"))
                .attr("stroke-width", d => d.value === 'core' ? 2 : 1)
                .attr("stroke-opacity", d => (d.strength || 0.4));

            // Central Node Ripple (Security Ripple)
            const coreNode = raw_nodes.find(n => n.id === 'BRAIN');
            if (coreNode) {{
                g.append("circle").attr("class", "core-ripple").attr("cx", coreNode.x).attr("cy", coreNode.y).attr("r", 10);
                g.append("circle").attr("class", "core-ripple").style("animation-delay", "2s").attr("cx", coreNode.x).attr("cy", coreNode.y).attr("r", 10);
            }}

            const node = g.append("g").selectAll("g").data(raw_nodes).enter().append("g")
                .attr("class", d => d.group === 'data' ? "data-node" : "")
                .style("cursor", "pointer")
                .on("mouseover", (e, d) => {{
                    d3.select(e.currentTarget).select("circle").attr("stroke-width", 4);
                    d3.select(e.currentTarget).select("text").style("opacity", 1);
                }})
                .on("mouseout", (e, d) => {{
                    d3.select(e.currentTarget).select("circle").attr("stroke-width", d.group === 'data' ? 1 : 2.5);
                    const currentK = d3.zoomTransform(svg.node()).k;
                    d3.select(e.currentTarget).select("text").style("opacity", d.group === 'data' ? (currentK > 1.8 ? 1 : 0) : 1);
                }})
                .on("click", (e, d) => focusNode(d, e.currentTarget))
                .call(d3.drag()
                    .on("start", (e, d) => {{ if (!e.active) simulation.alphaTarget(0.1).restart(); d.fx = d.x; d.fy = d.y; }})
                    .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
                    .on("end", (e, d) => {{ if (!e.active) simulation.alphaTarget(0); }}));

            node.append("circle").attr("r", d => d.size).attr("fill", "#050505").attr("stroke", d => d.color)
                .attr("stroke-width", d => d.group === 'data' ? 1 : 2.5)
                .style("filter", d => d.group !== 'data' ? "drop-shadow(0 0 12px " + d.color + "66)" : "none");

            node.append("text").attr("class", d => d.group === 'data' ? "data-label" : "")
                .attr("dy", d => d.size + 16).attr("text-anchor", "middle").attr("fill", "#eee")
                .style("font-size", "10px").style("font-family", "monospace").style("pointer-events", "none")
                .style("opacity", d => d.group === 'data' ? 0 : 1).text(d => d.name);

            const packets = g.append("g").selectAll("circle").data(raw_links).enter().append("circle")
                .attr("r", 1.5).attr("fill", "#fff").style("filter", "blur(1px)");

            function focusNode(d, element) {{
                const details = document.getElementById("brain-details");
                details.style.display = "block";
                details.style.zIndex = "1000"; // Above normal content
                document.getElementById("node-info").innerText = "Target: " + d.name.toUpperCase();
                document.getElementById("full-content").innerText = d.details || "No content.";
                const metaDiv = document.getElementById("node-meta");
                metaDiv.innerText = d.metadata ? "REF: " + d.metadata : "";
                metaDiv.style.display = d.metadata ? "block" : "none";
                
                // Multimodal Previews (Item 5)
                const preview = document.getElementById("multimodal-preview");
                const imgMatch = d.details?.match(/(https?:\\/\\/\\S+\\.(?:png|jpg|jpeg|gif|webp))/i);
                if (imgMatch) {{
                    preview.innerHTML = `<img src="${{imgMatch[0]}}" style="width:100%; height:auto; display:block;">`;
                    preview.style.display = "block";
                }} else {{
                    preview.style.display = "none";
                }}

                const bridge = document.getElementById("button-bridge");
                if (d.group === 'data') {{
                    bridge.style.display = "flex";
                    document.getElementById("del-btn").onclick = () => {{
                         const url = new URL(window.parent.location);
                         url.searchParams.set("delete_node", d.id);
                         window.parent.location.href = url.href;
                    }};
                }} else {{ bridge.style.display = "none"; }}

                triggerPulse(d);
                if (element) {{ d.fx = d.x; d.fy = d.y; }}
                svg_root.transition().duration(1000).call(zoom.transform, d3.zoomIdentity.translate(width/2, height/2).scale(1.5).translate(-d.x, -d.y));
            }}

            function triggerPulse(targetNode) {{
                const indicator = document.getElementById("pulse-indicator");
                if (indicator) {{
                    indicator.style.background = targetNode.color;
                    indicator.style.boxShadow = "0 0 10px " + targetNode.color;
                    setTimeout(() => {{ indicator.style.background = "#444"; indicator.style.boxShadow = "none"; }}, 300);
                }}

                const pulse = g.append("circle").attr("cx", width/2).attr("cy", height/2).attr("r", 5)
                    .attr("fill", "none").attr("stroke", targetNode.color).attr("stroke-width", 2).style("opacity", 1);
                pulse.transition().duration(1200).attr("r", 1000).style("opacity", 0).remove();
            }}

            document.getElementById("node-search").addEventListener("keypress", (e) => {{
                if (e.key === "Enter") {{
                    const q = e.target.value.toLowerCase();
                    const match = raw_nodes.find(n => n.name.toLowerCase().includes(q) || n.details?.toLowerCase().includes(q));
                    if (match) focusNode(match);
                }}
            }});
            
            // Drag-Drop Emulation
            // const zone = document.getElementById("upload-zone");
            // zone.addEventListener("dragover", (e) => {{ e.preventDefault(); zone.style.border = "1px dashed #58a6ff"; zone.style.color = "#58a6ff"; }});
            // zone.addEventListener("dragleave", (e) => {{ zone.style.border = "1px dashed #333"; zone.style.color = "#444"; }});
            // zone.addEventListener("drop", (e) => {{ e.preventDefault(); console.log("Neutral Injection Triggered"); }});

            simulation.on("tick", () => {{
                link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
                node.attr("transform", d => "translate(" + d.x + "," + d.y + ")");
                // Update Ripple Positions
                if (coreNode) {{
                    g.selectAll(".core-ripple").attr("cx", coreNode.x).attr("cy", coreNode.y);
                }}
            }});

            const pSpeed = {neural_speed};
            d3.timer(() => {{
                packets.attr("cx", d => {{
                    const t = (Date.now() * (d.value === 'core' ? pSpeed*2 : pSpeed) + raw_links.indexOf(d) * 0.1) % 1;
                    return d.source.x + (d.target.x - d.source.x) * t;
                }}).attr("cy", d => {{
                    const t = (Date.now() * (d.value === 'core' ? pSpeed*2 : pSpeed) + raw_links.indexOf(d) * 0.1) % 1;
                    return d.source.y + (d.target.y - d.source.y) * t;
                }});
            }});
        }}
        if (raw_nodes.length > 0) setTimeout(window.runBrainViz, 300);
        window.addEventListener('resize', init);
    }})();
    </script>
    """
    st.components.v1.html(BRAIN_EXPLORER_CODE, height=950)

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
    
    # Shout Tool Integration
    with st.expander("📣 BROADCAST SYSTEM", expanded=False):
        c_shout1, c_shout2 = st.columns([4, 1])
        with c_shout1:
            shout_msg = st.text_input("Broadcast Message:", placeholder="System Alert...", label_visibility="collapsed")
        with c_shout2:
            if st.button("SEND", use_container_width=True):
                if DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL != "YOUR_WEBHOOK_URL_HERE":
                    try:
                        httpx.post(DISCORD_WEBHOOK_URL, json={"content": shout_msg})
                        st.toast("Transmission Sent!")
                    except Exception as e:
                        st.error(f"Failed: {e}")
                else:
                    st.warning("Comms Offline.")

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
    tars_json_path = os.path.join(BASE_DIR, "chars", "TARS.json")
    if os.path.exists(tars_json_path):
        try:
            with open(tars_json_path, "r", encoding="utf-8") as f:
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
                    
                    with open(tars_json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    st.success("Persona updated via Form!")
        except Exception as e:
            st.error(f"Error loading JSON: {e}")
    else:
        st.error("TARS.json not found.")

    st.divider()
    st.subheader("🧠 Neural Hyperparameters")
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        st.session_state['link_strength'] = st.slider("Synapse Strength (Gravity)", 0.1, 2.5, st.session_state['link_strength'], 0.1)
    with col_h2:
        st.session_state['charge_strength'] = st.slider("Repulsion Force", 0.1, 5.0, st.session_state['charge_strength'], 0.1)

# --- BOTTOM WIDGETS ---
st.divider()

def _mini_bar_svg(pairs):
    safe_pairs = [(str(k), float(v)) for k, v in pairs if v is not None]
    if not safe_pairs:
        return ""
    max_v = max(v for _, v in safe_pairs) or 1.0
    rows = []
    for k, v in safe_pairs[:6]:
        w = int((v / max_v) * 100)
        rows.append(
            f"<div style='display:flex; align-items:center; gap:10px; margin:6px 0;'>"
            f"<div style='width:86px; font-size:11px; letter-spacing:1px; text-transform:uppercase; color: var(--text-dim); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;'>{k}</div>"
            f"<div style='flex:1; height:8px; border-radius:999px; background: rgba(0,248,255,0.08); border:1px solid rgba(0,248,255,0.12); overflow:hidden;'>"
            f"<div style='width:{w}%; height:100%; background: linear-gradient(90deg, rgba(0,248,255,0.9), rgba(168,85,247,0.75)); box-shadow: 0 0 14px rgba(0,248,255,0.28);'></div>"
            f"</div>"
            f"<div style='width:32px; text-align:right; font-family: Orbitron, sans-serif; font-size:12px; color: var(--cyan);'>{int(v)}</div>"
            f"</div>"
        )
    return "".join(rows)

def _card(title, icon, body_html):
    return (
        f"<div style=\"background: linear-gradient(135deg, rgba(15,18,28,0.92) 0%, rgba(10,12,18,0.86) 100%); "
        f"border: 1px solid rgba(0,248,255,0.18); border-radius: 16px; padding: 18px 18px 16px; "
        f"backdrop-filter: blur(28px); box-shadow: 0 10px 40px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);\">"
        f"<div style=\"display:flex; align-items:center; gap:10px; padding-bottom: 12px; margin-bottom: 14px; "
        f"border-bottom: 1px solid rgba(0,248,255,0.10);\">"
        f"<div style=\"width:34px; height:34px; border-radius: 10px; display:flex; align-items:center; justify-content:center; "
        f"background: rgba(0,248,255,0.08); border: 1px solid rgba(0,248,255,0.22);\">{icon}</div>"
        f"<div style=\"font-family: Space Grotesk, sans-serif; font-size: 13px; letter-spacing: 1.5px; text-transform: uppercase; "
        f"color: var(--text); font-weight: 700;\">{title}</div>"
        f"</div>"
        f"{body_html}"
        f"</div>"
    ).strip()

def _mood_timeline_svg(df):
    """Optimized SVG timeline instead of heavy matplotlib."""
    if df is None or getattr(df, 'empty', True): return ""
    if 'timestamp' not in df.columns or 'mood' not in df.columns: return ""
    
    # Use native Streamlit chart for interactivity inside the card-like container
    # But since we are inside an HTML card, we might prefer a micro-chart.
    # Let's use st.vega_lite_chart if we want it perfect, but for speed let's just 
    # use a simple sparkline-style SVG if matplotlib was the bottleneck.
    return "<!-- Interactive Timeline Placeholder -->"

# Create 2x2 grid layout for bottom widgets (Row 1)
bw_col1, bw_col2 = st.columns(2)

# Widget 1: Knowledge Graph (pure HTML)
with bw_col1:
    try:
        fact_count = entity_count = relation_count = 0
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM facts")
            fact_count = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(DISTINCT subject) FROM facts")
            entity_count = int(cursor.fetchone()[0] or 0)
            cursor.execute("SELECT COUNT(DISTINCT predicate) FROM facts")
            relation_count = int(cursor.fetchone()[0] or 0)
            conn.close()
        density = min(100, int((fact_count / 1000) * 100)) if fact_count else 0
        body = f"""
          <div style='display:flex; flex-direction:column; gap:10px;'>
            <div style='display:flex; justify-content:space-between;'><span style='color: var(--text-dim); font-size:12px;'>Total Facts</span><span style='font-family: Orbitron, sans-serif; color: var(--cyan);'>{fact_count}</span></div>
            <div style='display:flex; justify-content:space-between;'><span style='color: var(--text-dim); font-size:12px;'>Entities</span><span style='font-family: Orbitron, sans-serif; color: var(--cyan);'>{entity_count}</span></div>
            <div style='display:flex; justify-content:space-between;'><span style='color: var(--text-dim); font-size:12px;'>Relations</span><span style='font-family: Orbitron, sans-serif; color: var(--cyan);'>{relation_count}</span></div>
            <div style='margin-top:8px;'>
              <div style='font-size:10px; letter-spacing:1.5px; text-transform:uppercase; color: var(--text-dim); margin-bottom:8px;'>Graph Density: {density}%</div>
              <div style='height:10px; border-radius:999px; background: rgba(0,248,255,0.08); border:1px solid rgba(0,248,255,0.14); overflow:hidden;'>
                <div style='width:{density}%; height:100%; background: linear-gradient(90deg, rgba(0,248,255,0.95), rgba(168,85,247,0.7)); box-shadow: 0 0 18px rgba(0,248,255,0.22);'></div>
              </div>
            </div>
          </div>
        """
        st.markdown(_card("Knowledge Graph", "🧠", body), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(_card("Knowledge Graph", "🧠", f"<div style='color:#ff6b6b; font-size:12px;'>Error: {str(e)}</div>"), unsafe_allow_html=True)

# Widget 2: CLI Output (pure HTML)
with bw_col2:
    try:
        log_output = ""
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                log_output = "".join(f.readlines()[-10:]).strip()
        if not log_output:
            log_output = "[SYSTEM] Awaiting console output…"
        safe_log = html.escape(log_output)
        body = f"""
          <pre style='margin:0; max-height: 180px; overflow:auto; padding: 8px; border-radius: 8px; background: rgba(0,0,0,0.35); border: 1px solid rgba(0,248,255,0.1); color: #7dd3fc; font-size: 8px !important; line-height: 1.2 !important; font-family: JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;'>\n{safe_log}\n</pre>
        """
        st.markdown(_card("CLI Output", "💻", body), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(_card("CLI Output", "💻", f"<div style='color:#ff6b6b; font-size:12px;'>Error: {str(e)}</div>"), unsafe_allow_html=True)

# Bottom widgets Row 2
bw_col3, bw_col4 = st.columns(2)

# Widget 3: Mood Analytics (pure HTML)
with bw_col3:
    try:
        df = get_audit_logs()
        if df is None or getattr(df, 'empty', True):
            body = "<div style='color: var(--text-dim); font-size:12px;'>No audit logs found</div>"
        else:
            if 'mood' in df.columns:
                moods = df['mood'].dropna().astype(str)
                tail = moods.tail(100)
                counts = tail.value_counts().head(5)
                current = (moods.iloc[-1] if len(moods) else "UNKNOWN")
                bars = _mini_bar_svg(list(zip(counts.index.tolist(), counts.values.tolist())))
                body = f"""
                  <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom: 10px;'>
                    <span style='color: var(--text-dim); font-size:12px;'>Current State</span>
                    <span style='font-family: Orbitron, sans-serif; color: var(--cyan); font-size:12px;'>{html.escape(str(current)).upper()}</span>
                  </div>
                  <div style='margin-top: 10px;'>{bars}</div>
                """
                # Enhanced Vega-Lite Mood History Graph
                with st.expander("Mood History", expanded=False):
                    mood_data = df.tail(100).copy()
                    mood_data['timestamp'] = pd.to_datetime(mood_data['timestamp'])
                    
                    vega_spec = {
                        "mark": {"type": "circle", "size": 60, "opacity": 0.8, "stroke": "white", "strokeWidth": 0.5},
                        "encoding": {
                            "x": {
                                "field": "timestamp", 
                                "type": "temporal", 
                                "title": "Time",
                                "axis": {"grid": True, "gridColor": "rgba(0,248,255,0.1)", "labelColor": "#a0a0a0", "titleColor": "#e0e0e0"}
                            },
                            "y": {
                                "field": "mood", 
                                "type": "nominal", 
                                "title": "Mood",
                                "sort": "ascending",
                                "axis": {"grid": True, "gridColor": "rgba(0,248,255,0.1)", "labelColor": "#a0a0a0", "titleColor": "#e0e0e0"}
                            },
                            "color": {
                                "field": "mood", 
                                "type": "nominal", 
                                "scale": {"scheme": "spectral"},
                                "legend": None
                            },
                            "tooltip": [
                                {"field": "timestamp", "type": "temporal", "title": "Time"},
                                {"field": "mood", "type": "nominal", "title": "Mood"}
                            ]
                        },
                        "config": {
                            "background": "transparent",
                            "view": {"stroke": "transparent"}
                        },
                        "height": 250
                    }
                    st.vega_lite_chart(mood_data, vega_spec, use_container_width=True)
            else:
                body = "<div style='color: var(--text-dim); font-size:12px;'>No mood column found</div>"
        st.markdown(_card("Mood Analytics", "📈", body.strip()), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(_card("Mood Analytics", "📈", f"<div style='color:#ff6b6b; font-size:12px;'>Error: {str(e)}</div>"), unsafe_allow_html=True)

# Widget 4: Activity Volume (pure HTML)
with bw_col4:
    try:
        df = get_audit_logs()
        total = 0
        last_24h = None
        hour_counts = []
        if df is not None and not getattr(df, 'empty', True):
            total = len(df)
            if 'timestamp' in df.columns:
                ts = pd.to_datetime(df['timestamp'], errors='coerce')
                # Use UTC-aware or naive based on data, usually sqlite is naive
                now = pd.Timestamp.now()
                mask = ts > (now - pd.Timedelta(hours=24))
                last_24h = int(mask.sum())
                hrs = ts.dropna().dt.hour.value_counts().sort_index()
                hour_counts = [(str(int(h)).zfill(2), int(v)) for h, v in hrs.tail(6).items()]
        level = "LOW"
        level_color = "#00f8ff"
        if last_24h is not None:
            if last_24h > 50:
                level, level_color = "HIGH", "#ff4444"
            elif last_24h > 20:
                level, level_color = "MED", "#ffca28"
        bars = _mini_bar_svg(hour_counts) if hour_counts else "<div style='color: var(--text-dim); font-size:12px;'>No timestamp data available</div>"
        body = f"""
          <div style='display:flex; flex-direction:column; gap:10px;'>
            <div style='display:flex; justify-content:space-between;'><span style='color: var(--text-dim); font-size:12px;'>Total Activities</span><span style='font-family: Orbitron, sans-serif; color: var(--cyan);'>{total}</span></div>
            <div style='display:flex; justify-content:space-between;'><span style='color: var(--text-dim); font-size:12px;'>Last 24h</span><span style='font-family: Orbitron, sans-serif; color: var(--cyan);'>{'' if last_24h is None else last_24h}</span></div>
            <div style='font-size:10px; letter-spacing:1.5px; text-transform:uppercase; color: {level_color};'>Activity Level: {level}</div>
            <div style='margin-top:4px;'>{bars}</div>
          </div>
        """
        st.markdown(_card("Activity Volume", "📊", body), unsafe_allow_html=True)
    except Exception as e:
        st.markdown(_card("Activity Volume", "📊", f"<div style='color:#ff6b6b; font-size:12px;'>Error: {str(e)}</div>"), unsafe_allow_html=True)

# --- COMMAND DECK ---
st.divider()
with st.expander("☢️ COMMAND DECK", expanded=False):
    render_command_deck()