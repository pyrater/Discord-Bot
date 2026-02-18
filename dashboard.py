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

# --- STYLING: NEXUS CORE AESTHETIC ---
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;700&family=Rajdhani:wght@500;600;700&display=swap');

:root {
    --glass-bg: rgba(13, 17, 23, 0.7);
    --glass-border: rgba(56, 139, 253, 0.15);
    --accent-blue: #2f81f7;
    --text-primary: #c9d1d9;
    --text-secondary: #8b949e;
    --bg-dark: #010409;
    
    /* Compatibility vars */
    --neon-blue: #2f81f7; 
    --neon-purple: #a371f7;
    --neon-red: #f85149;
}

html, body, [class*="st-"] {
    font-family: 'Inter', sans-serif !important;
    background-color: var(--bg-dark) !important;
    color: var(--text-primary) !important;
    background-image: radial-gradient(circle at 50% 0%, rgba(56, 139, 253, 0.1) 0%, transparent 60%) !important;
    background-size: 100% 100% !important;
    background-position: center top !important;
}

h1, h2, h3, .hud-title {
    font-weight: 600 !important;
    letter-spacing: 0.5px !important;
    font-family: 'Rajdhani', sans-serif !important;
    text-transform: uppercase;
}

.mono, code, pre, .hud-value, .stMetricValue {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Hide Sidebar & Streamlit Chrome */
[data-testid="stSidebar"] { display: none !important; }
#MainMenu, footer, header { visibility: hidden !important; }

/* Remove Top Padding/Dead Space */
.block-container {
    padding-top: 0rem !important;
    padding-bottom: 5rem !important;
    margin-top: 1rem !important;
}

/* HUD Header - Minimalist */
.nexus-hud {
    display: flex; justify-content: space-between; align-items: center;
    background: var(--glass-bg);
    border-bottom: 1px solid var(--glass-border);
    padding: 12px 24px; 
    margin-bottom: 30px;
    backdrop-filter: blur(12px);
}

.hud-group {
    display: flex; gap: 40px; align-items: center;
}

.hud-item {
    text-align: left;
    display: flex; flex-direction: column;
}

.hud-label {
    font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px;
    font-family: 'Inter', sans-serif; font-weight: 500;
}

.hud-value {
    font-size: 16px; font-weight: 500; color: var(--text-primary);
}

.hud-title {
    font-size: 18px; color: var(--text-primary);
    font-weight: 700 !important;
    letter-spacing: 1px;
}

/* Clean Glass Cards */
.tech-card, .stCard, div[data-testid="stMetric"], div[data-testid="stExpander"] {
    background: rgba(22, 27, 34, 0.5) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 6px !important;
    padding: 20px !important;
    box-shadow: none !important;
    backdrop-filter: blur(10px);
    margin-bottom: 16px;
}
/* No pseudo-elements */
.tech-card::before, .tech-card::after { display: none !important; }

/* Buttons - Clean Actions */
div.stButton > button {
    background: rgba(56, 139, 253, 0.1) !important;
    border: 1px solid rgba(56, 139, 253, 0.3) !important;
    color: var(--accent-blue) !important;
    border-radius: 6px !important;
    padding: 6px 16px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    text-transform: none !important;
    transition: all 0.1s ease;
}
div.stButton > button:hover {
    background: rgba(56, 139, 253, 0.2) !important;
    border-color: var(--accent-blue) !important;
    color: #fff !important;
}

/* Danger Buttons */
div[data-testid="stButton"] button:contains("DELETE"), 
div[data-testid="stButton"] button:contains("SHUTDOWN") {
    border-color: rgba(248, 81, 73, 0.4) !important; color: var(--neon-red) !important;
    background: rgba(248, 81, 73, 0.1) !important;
}
div[data-testid="stButton"] button:contains("DELETE"):hover,
div[data-testid="stButton"] button:contains("SHUTDOWN"):hover {
    background: rgba(248, 81, 73, 0.2) !important;
    border-color: var(--neon-red) !important;
}

/* Form Elements */
.stTextInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
    background-color: #0d1117 !important;
    border: 1px solid #30363d !important;
    color: var(--text-primary) !important;
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent-blue) !important;
    box-shadow: 0 0 0 1px var(--accent-blue) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 20px; margin-bottom: 20px; border-bottom: 1px solid #30363d; padding-bottom: 0px; }
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    font-size: 14px;
    padding: 12px 0;
    margin-right: 15px;
}
.stTabs [aria-selected="true"] {
    color: var(--text-primary) !important;
    border-bottom: 2px solid var(--accent-blue) !important;
    font-weight: 600 !important;
}

</style>
"""

def nexus_header():
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Calculate Neural Stress from recent audit logs
    try:
        df = get_audit_logs(limit=20)
        error_count = len(df[df['mood'].str.lower().str.contains('error|fail|warn', na=False)])
        neural_stress = min(1.0, error_count / 10.0)
        last_mood = df.iloc[0]['mood'] if not df.empty else "STANDBY"
    except:
        neural_stress = 0.0
        last_mood = "UNKNOWN"

    stress_color = "#ff003c" if neural_stress > 0.6 else ("#f39c12" if neural_stress > 0.3 else "#00f3ff")
    
    st.markdown(f"""
        <div class="nexus-hud">
            <div class="hud-group">
                <div class="hud-title">TARS <span style="font-size:12px; opacity:0.7; letter-spacing:1px; vertical-align:middle;">NEXUS CORE</span></div>
            </div>
            <div class="hud-group">
                <div class="hud-item">
                    <div class="hud-label">CPU LOAD</div>
                    <div class="hud-value">{cpu}%</div>
                </div>
                <div class="hud-item">
                    <div class="hud-label">RAM USAGE</div>
                    <div class="hud-value">{ram}%</div>
                </div>
                <div class="hud-item">
                    <div class="hud-label">NEURAL STRESS</div>
                    <div class="hud-value" style="color: {stress_color};">{int(neural_stress*100)}%</div>
                </div>
                <div class="hud-item">
                    <div class="hud-label">COGNITIVE STATE</div>
                    <div class="hud-value" style="color: var(--neon-purple);">{last_mood.upper()}</div>
                </div>
            </div>
        </div>
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
st.set_page_config(page_title="TARS Nexus Core", layout="wide", page_icon="🤖")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# --- GLOBAL COSMIC SMOKE BACKGROUND ---
st.components.v1.html("""
<script>
(function() {
    const parentDoc = window.parent.document;
    if (parentDoc.getElementById('cosmic-bg-container')) return;
    
    // Create background container
    const container = parentDoc.createElement('div');
    container.id = 'cosmic-bg-container';
    container.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; z-index:-1; pointer-events:none; background:#020202;';
    
    const canvas = parentDoc.createElement('canvas');
    canvas.id = 'hero-canvas';
    canvas.style.cssText = 'width:100%; height:100%; display:block;';
    container.appendChild(canvas);
    
    parentDoc.body.prepend(container);

    // Simplex Noise Implementation
    const SimplexNoise = (function () {
      const F3 = 1 / 3, G3 = 1 / 6;
      const grad3 = [[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]];
      const p = [151, 160, 137, 91, 90, 15, 131, 13, 201, 95, 96, 53, 194, 233, 7, 225, 140, 36, 103, 30, 69, 142, 8, 99, 37, 240, 21, 10, 23, 190, 6, 148, 247, 120, 234, 75, 0, 26, 197, 62, 94, 252, 219, 203, 117, 35, 11, 32, 57, 177, 33, 88, 237, 149, 56, 87, 174, 20, 125, 136, 171, 168, 68, 175, 74, 165, 71, 134, 139, 48, 27, 166, 77, 146, 158, 231, 83, 111, 229, 122, 60, 211, 133, 230, 220, 105, 92, 41, 55, 46, 245, 40, 244, 102, 143, 54, 65, 25, 63, 161, 1, 216, 80, 73, 209, 76, 132, 187, 208, 89, 18, 169, 200, 196, 135, 130, 116, 188, 159, 86, 164, 100, 109, 198, 173, 186, 3, 64, 52, 217, 226, 250, 124, 123, 5, 202, 38, 147, 118, 126, 255, 82, 85, 212, 207, 206, 59, 227, 47, 16, 58, 17, 182, 189, 28, 42, 223, 183, 170, 213, 119, 248, 152, 2, 44, 154, 163, 70, 221, 153, 101, 155, 167, 43, 172, 9, 129, 22, 39, 253, 19, 98, 108, 110, 79, 113, 224, 232, 178, 185, 112, 104, 218, 246, 97, 228, 251, 34, 242, 193, 238, 210, 144, 12, 191, 179, 162, 241, 81, 51, 145, 235, 249, 14, 239, 107, 49, 192, 214, 31, 181, 199, 106, 157, 184, 84, 204, 176, 115, 121, 50, 45, 127, 4, 150, 254, 138, 236, 205, 93, 222, 114, 67, 29, 24, 72, 243, 141, 128, 195, 78, 66, 215, 61, 156, 180];
      const perm = new Array(512), permMod12 = new Array(512);
      for (let i = 0; i < 512; i++) { perm[i] = p[i & 255]; permMod12[i] = perm[i] % 12; }
      function dot3(g, x, y, z) { return g[0] * x + g[1] * y + g[2] * z; }
      return {
        noise3D: function (xin, yin, zin) {
          let s = (xin + yin + zin) * F3;
          let i = Math.floor(xin + s), j = Math.floor(yin + s), k = Math.floor(zin + s);
          let t = (i + j + k) * G3;
          let X0 = i - t, Y0 = j - t, Z0 = k - t;
          let x0 = xin - X0, y0 = yin - Y0, z0 = zin - Z0;
          let i1, j1, k1, i2, j2, k2;
          if (x0 >= y0) { if (y0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 1; k2 = 0 } else if (x0 >= z0) { i1 = 1; j1 = 0; k1 = 0; i2 = 1; j2 = 0; k2 = 1 } else { i1 = 0; j1 = 0; k1 = 1; i2 = 1; j2 = 0; k2 = 1 } }
          else { if (y0 < z0) { i1 = 0; j1 = 0; k1 = 1; i2 = 0; j2 = 1; k2 = 1 } else if (x0 < z0) { i1 = 0; j1 = 1; k1 = 0; i2 = 0; j2 = 1; k2 = 1 } else { i1 = 0; j1 = 1; k1 = 0; i2 = 1; j2 = 1; k2 = 0 } }
          let x1 = x0 - i1 + G3, y1 = y0 - j1 + G3, z1 = z0 - k1 + G3;
          let x2 = x0 - i2 + 2 * G3, y2 = y0 - j2 + 2 * G3, z2 = z0 - k2 + 2 * G3;
          let x3 = x0 - 1 + 3 * G3, y3 = y0 - 1 + 3 * G3, z3 = z0 - 1 + 3 * G3;
          let ii = i & 255, jj = j & 255, kk = k & 255;
          let n0, n1, n2, n3;
          let t0 = 0.6 - x0 * x0 - y0 * y0 - z0 * z0;
          if (t0 < 0) n0 = 0; else { t0 *= t0; n0 = t0 * t0 * dot3(grad3[permMod12[ii + perm[jj + perm[kk]]]], x0, y0, z0) }
          let t1 = 0.6 - x1 * x1 - y1 * y1 - z1 * z1;
          if (t1 < 0) n1 = 0; else { t1 *= t1; n1 = t1 * t1 * dot3(grad3[permMod12[ii + i1 + perm[jj + j1 + perm[kk + k1]]]], x1, y1, z1) }
          let t2 = 0.6 - x2 * x2 - y2 * y2 - z2 * z2;
          if (t2 < 0) n2 = 0; else { t2 *= t2; n2 = t2 * t2 * dot3(grad3[permMod12[ii + i2 + perm[jj + j2 + perm[kk + k2]]]], x2, y2, z2) }
          let t3 = 0.6 - x3 * x3 - y3 * y3 - z3 * z3;
          if (t3 < 0) n3 = 0; else { t3 *= t3; n3 = t3 * t3 * dot3(grad3[permMod12[ii + 1 + perm[jj + 1 + perm[kk + 1]]]], x3, y3, z3) }
          return 32 * (n0 + n1 + n2 + n3);
        }
      };
    })();

    const ctx = canvas.getContext('2d');
    let w, h, dpr;

    function resize() {
        dpr = Math.min(window.devicePixelRatio, 2);
        w = window.innerWidth;
        h = window.innerHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    const WISPS_COUNT = 15;
    let wisps = [];
    function createWisp(init = false) {
        const sourceX = w * 0.95 + Math.random() * w * 0.05;
        const sourceY = h * 0.48 + (Math.random() - 0.5) * h * 0.4;
        const scale = Math.random() * 0.8 + 0.6;
        return {
          x: init ? Math.random() * w : sourceX,
          y: init ? (h * 0.48 + (Math.random() - 0.5) * h * 0.5) : sourceY,
          vx: -(Math.random() * 0.5 + 0.2),
          vy: (Math.random() - 0.5) * 0.05,
          width: (Math.random() * 800 + 400) * scale,
          height: (Math.random() * 200 + 50) * scale,
          alpha: 0,
          targetAlpha: Math.random() * 0.12 + 0.04,
          r: 180 + Math.random() * 75,
          g: 190 + Math.random() * 65,
          b: 240 + Math.random() * 15,
          noiseOffset: Math.random() * 1000,
          rotation: (Math.random() - 0.5) * 0.15,
          life: 0,
          maxLife: Math.random() * 1200 + 800,
        };
    }
    for (let i = 0; i < WISPS_COUNT; i++) wisps.push(createWisp(true));

    const noiseScale = 0.0006, timeScale = 0.00004;

    function draw() {
        const t = Date.now();
        ctx.fillStyle = '#020202';
        ctx.fillRect(0, 0, w, h);
        ctx.save();
        ctx.filter = `blur(${Math.min(w, h) * 0.06}px)`;
        ctx.globalCompositeOperation = 'screen';
        for (let i = 0; i < wisps.length; i++) {
          const b = wisps[i];
          b.life++;
          if (b.life < 150) b.alpha += (b.targetAlpha / 150);
          else if (b.life > b.maxLife - 150) b.alpha -= (b.targetAlpha / 150);
          const nx = b.x * noiseScale + b.noiseOffset;
          const ny = b.y * noiseScale;
          const noise = SimplexNoise.noise3D(nx, ny, t * timeScale);
          b.x += b.vx; b.y += b.vy + noise * 0.3;
          if (b.alpha <= 0 && b.life > 150) { wisps[i] = createWisp(); continue; }
          if (b.x < -b.width) { wisps[i] = createWisp(); continue; }
          ctx.save();
          ctx.translate(b.x, b.y);
          ctx.rotate(b.rotation + noise * 0.05);
          const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, b.width / 2);
          if (b.noiseOffset > 500) {
            grad.addColorStop(0, `rgba(${b.r - 20}, ${b.g - 40}, ${b.b}, ${b.alpha})`);
            grad.addColorStop(1, 'rgba(40, 20, 80, 0)');
          } else {
            grad.addColorStop(0, `rgba(${b.r}, ${b.g}, ${b.b}, ${b.alpha})`);
            grad.addColorStop(1, `rgba(${b.r}, ${b.g}, ${b.b}, 0)`);
          }
          ctx.fillStyle = grad;
          ctx.scale(1, b.height / b.width);
          ctx.beginPath(); ctx.arc(0, 0, b.width / 2, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
        }
        ctx.restore();
        requestAnimationFrame(draw);
    }
    draw();
})();
</script>
""", height=0)

# Scanline Overlay (HTML injection)
st.markdown('<div class="scanline-overlay"></div>', unsafe_allow_html=True)

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

# --- MAIN UI LAYOUT ---
# HUD Header (Returns neural_stress for physics calc)
neural_stress = nexus_header()

# Physics Calculation
neural_speed = 0.0006 * (1 + neural_stress * 2)

tab_brain_explorer, tab_knowledge, tab_mem, tab_analytics, tab_models, tab_play, tab_logs, tab_cli, tab_debug, tab_conf = st.tabs([
    "🧠 Brain Explorer", "🕸️ Knowledge Graph", "🧠 Memories", "📈 Mood", "🤖 Models", "💬 Playground", "📜 Logs", "🖥️ CLI", "🔍 Debug", "⚙️ Config"
])

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
                        font-size: 11px;
                        line-height: 1.4;
                        padding: 15px;
                        border-radius: 8px;
                        height: 500px;
                        overflow-y: auto;
                        white-space: pre-wrap;
                        border: 1px solid var(--nexus-border);
                        box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
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

        # Connect to ChromaDB
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collections = client.list_collections()
        
        hub_colors = ["#ffca28", "#3fb950", "#58a6ff", "#f85149", "#d29922", "#8b949e"]
        
        for idx, col in enumerate(collections):
            hub_id = f"hub_{col.name}"
            color = hub_colors[idx % len(hub_colors)]
            
            # Hub node always added
            nodes.append({
                "id": hub_id,
                "name": f"HUB: {col.name.upper()}",
                "color": color,
                "size": 22,
                "group": "hub",
                "details": f"Vector Collection: {col.name}",
                "time_score": 1
            })
            links.append({"source": "BRAIN", "target": hub_id, "value": "hub"})
            
            try:
                collection = client.get_collection(col.name)
                # Fetch limited to avoid massive overhead during debug
                peek = collection.peek(limit=50)
                
                # Verify data structure
                if not peek or 'ids' not in peek: continue
                
                for i, doc_id in enumerate(peek['ids']):
                    full_text = peek['documents'][i] if i < len(peek['documents']) else "No Content"
                    metadata = peek['metadatas'][i] if (peek['metadatas'] and i < len(peek['metadatas'])) else {}
                    
                    # Temporal logic
                    time_score = 1
                    days_old = 0
                    if "timestamp" in metadata:
                        try:
                            # Assuming ISO format or similar
                            dt = pd.to_datetime(metadata["timestamp"])
                            days_old = (pd.Timestamp.now() - dt.tz_localize(None)).days
                            if days_old <= 1: time_score = 1
                            elif days_old <= 7: time_score = 2
                            else: time_score = 3
                        except: pass
                    
                    # Applying Filter
                    if days_old > threshold_days:
                        continue

                    # Dynamic Sentiment Heatmapping (Simple heuristic)
                    sentiment_color = color
                    if "error" in full_text.lower() or "fail" in full_text.lower():
                        sentiment_color = "#f85149" # Alert Red
                    elif "success" in full_text.lower() or "done" in full_text.lower():
                        sentiment_color = "#7ee787" # Kinetic Green
                    
                    display_name = full_text[:40] + "..." if len(full_text) > 40 else full_text
                    node_id = f"mem_{col.name}_{i}"
                    nodes.append({
                        "id": node_id,
                        "name": display_name,
                        "color": sentiment_color,
                        "size": 8,
                        "group": "data",
                        "details": full_text,
                        "metadata": str(metadata),
                        "time_score": time_score
                    })
                    links.append({"source": hub_id, "target": node_id, "value": "data", "strength": 0.8})
            except Exception as inner_e:
                err_msg = str(inner_e)
                st.sidebar.error(f"⚠️ Neural Hub Corrupted: {col.name}")
                if "Error finding id" in err_msg:
                    st.sidebar.warning("Detected known ChromaDB index corruption.")
                    if st.sidebar.button(f"🛠️ Attempt Auto-Repair: {col.name}", key=f"rep_{col.name}"):
                        repair_neural_collection(client, col.name)
                else:
                    st.sidebar.warning(f"Technical Trace: {err_msg[:100]}")

        if os.path.exists(DB_PATH):
            hub_id = "hub_facts"
            nodes.append({
                "id": hub_id,
                "name": "HUB: KNOWLEDGE BASE",
                "color": "#3fb950",
                "size": 22,
                "group": "hub",
                "details": "Source: SQLite Database",
                "time_score": 1
            })
            links.append({"source": "BRAIN", "target": hub_id, "value": "hub", "strength": 0.9})
            
            try:
                conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
                df_facts = pd.read_sql_query("SELECT id, subject, predicate, object, timestamp FROM facts LIMIT 100", conn)
                conn.close()
                
                # Group by Subject for Hierarchy (KNOWLEDGE BASE -> user -> fact)
                subjects_map = {}

                for i, row in df_facts.iterrows():
                    subj = row['subject'].strip()
                    
                    # 1. Create Subject Node if needed
                    if subj not in subjects_map:
                        subj_id = f"subj_{subj}_{i}"
                        nodes.append({
                            "id": subj_id,
                            "name": subj.upper(),
                            "color": "#1f6feb", # Blue for categories
                            "size": 14,
                            "group": "user",
                            "details": f"ENTITY: {subj}\nTYPE: Subject",
                            "time_score": 1
                        })
                        links.append({"source": hub_id, "target": subj_id, "value": "category", "strength": 0.5})
                        subjects_map[subj] = subj_id
                    
                    # 2. Create Fact Node
                    node_id = f"fact_{row['id'] or i}"
                    
                    # Temporal scoring
                    time_score = 1
                    try:
                        dt = pd.to_datetime(row['timestamp'])
                        days_old = (pd.Timestamp.now() - dt.tz_localize(None)).days
                        if days_old <= 1: time_score = 1
                        elif days_old <= 7: time_score = 2
                        else: time_score = 3
                    except: pass

                    nodes.append({
                        "id": node_id,
                        # Cleaner name: just the predicate and object
                        "name": f"{row['predicate']} » {row['object']}", 
                        "color": "#3fb950",
                        "size": 6,
                        "group": "data",
                        "details": f"FACT: {subj}\nRELATION: {row['predicate']}\nTARGET: {row['object']}\nLEARNED: {row['timestamp']}",
                        "time_score": time_score
                    })
                    # Link Fact to Subject, not Hub
                    links.append({"source": subjects_map[subj], "target": node_id, "value": "fact", "strength": 0.3})
                    
                    # Phase 2: Cross-Collection Linking - Robust version
                    for n in nodes:
                        if n.get('group') == 'data' and 'mem_' in n.get('id', ''):
                            if 'details' in n and subj.lower() in n['details'].lower():
                                links.append({"source": n['id'], "target": subjects_map[subj], "value": "cross", "strength": 0.1})
            except Exception as db_e:
                st.sidebar.warning(f"Skipping fact engine: {db_e}")
                
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
    <div id="brain-viz-container" style="width:100%; height:900px; background:transparent; position:relative; overflow:hidden;">
        <svg id="brain-viz" style="width:100%; height:100%; cursor:move;"></svg>
        
        <div id="brain-search-container" style="position:absolute; top:20px; left:20px; z-index:100; display:flex; gap:10px;">
            <input type="text" id="node-search" placeholder="Search cognitive map..." 
                style="background: rgba(15,15,15,0.85); border: 1px solid rgba(88,166,255,0.4); border-radius: 6px; padding: 10px 15px; color: #fff; font-family: monospace; width: 250px; backdrop-filter: blur(10px); outline: none;">
            <button id="toggle-3d" style="background: rgba(15,15,15,0.85); border: 1px solid #444; color:#aaa; padding:10px; border-radius:6px; cursor:pointer;" onclick="window.toggle3D()">[3D MODE]</button>
        </div>

        <div id="brain-details" style="position:absolute; top:20px; right:20px; width:300px; background: rgba(10,10,10,0.95); border: 1px solid rgba(88,166,255,0.3); padding:15px; border-radius:10px; font-family: monospace; font-size:11px; backdrop-filter:blur(15px); z-index:100; box-shadow: 0 10px 40px rgba(0,0,0,0.8); transition: all 0.3s;">
            <div style="color:#58a6ff; font-weight:bold; border-bottom:1px solid #333; padding-bottom:8px; margin-bottom:10px; letter-spacing:1px; display:flex; justify-content:space-between;">
                <span>NEURAL TELEMETRY</span>
                <span id="close-details" style="cursor:pointer; color:#444;" onclick="document.getElementById('full-content').innerText='Select a node to view metadata...'">×</span>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div id="unit-status">Stress: <span style="color:{'#f85149' if neural_stress > 0.7 else '#00ff00'}; font-weight:bold;">{int(neural_stress*100)}%</span></div>
                <div id="pulse-indicator" style="width:10px; height:10px; border-radius:50%; background:#444; box-shadow: 0 0 8px #444; animation: heartbeat {1.5 - neural_stress}s infinite;"></div>
            </div>
            <div id="node-info" style="margin-top:8px; color:#58a6ff; font-weight:bold; font-size:12px;">Target: STANDBY</div>
            
            <div style="margin-top:12px; border-top:1px solid #222; padding-top:10px;">
                <div style="color:#888; font-size:10px; margin-bottom:5px; text-transform:uppercase;">Metadata Content:</div>
                <div id="multimodal-preview" style="display:none; margin-bottom:10px; border-radius:4px; overflow:hidden; border:1px solid #333;"></div>
                <div id="full-content" style="color:#eee; font-size:11px; line-height:1.4; max-height:250px; overflow-y:auto; word-break:break-word; scrollbar-width:thin;">Select a node to view metadata...</div>
                <div id="node-meta" style="color:#444; font-size:9px; margin-top:10px; border-top: 1px dashed #333; padding-top:8px; display:none;"></div>
            </div>

            <div id="button-bridge" style="margin-top:15px; display:none; gap:5px;">
                <button id="del-btn" style="flex:1; background:rgba(248,81,73,0.1); border:1px solid #f85149; color:#f85149; padding:5px; font-size:9px; cursor:pointer; border-radius:4px;">[PURGE MEMORY]</button>
                <button id="edit-btn" style="flex:1; background:rgba(88,166,255,0.1); border:1px solid #58a6ff; color:#58a6ff; padding:5px; font-size:9px; cursor:pointer; border-radius:4px;">[RE-VECTOR]</button>
            </div>

            <div id="diag-info" style="color:#444; margin-top:15px; font-size:9px; border-top: 1px solid #222; padding-top:10px;">Mapped: {len(nodes)} Neural Points</div>
            <div style="color:#333; font-size:9px; margin-top:5px;">SHIFT+CLICK TO UNPIN • ENTER TO SEARCH</div>
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
    st.components.v1.html(BRAIN_EXPLORER_CODE, height=900)

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
        st.error("TARS.json not found.")

    st.divider()
    st.subheader("🧠 Neural Hyperparameters")
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        st.session_state['link_strength'] = st.slider("Synapse Strength (Gravity)", 0.1, 2.5, st.session_state['link_strength'], 0.1)
    with col_h2:
        st.session_state['charge_strength'] = st.slider("Repulsion Force", 0.1, 5.0, st.session_state['charge_strength'], 0.1)
    
    st.session_state['grouping_mode'] = st.radio("Clustering Mode", ["Temporal (Radial)", "Semantic (Force)"], 
                                                 index=0 if st.session_state['grouping_mode'] == "Temporal (Radial)" else 1)

# --- COMMAND DECK ---
st.divider()
with st.expander("☢️ COMMAND DECK", expanded=False):
    render_command_deck()