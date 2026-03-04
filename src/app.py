import os
# Disable telemetry BEFORE other imports
os.environ['CHROMA_TELEMETRY'] = 'False'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import hmac
import psutil
import subprocess
import signal
import chromadb
from src.tars_utils import (
    get_mood_metrics, get_audit_logs, get_mood_paths, 
    get_graph_data, get_knowledge_data, get_memories, get_total_counts,
    parse_prompt, BASE_DIR, DB_PATH, CHROMA_PATH
)
from src.brain import CognitiveEngine
from src.memory_engine import MemoryEngine
from src.bot_config import settings
import asyncio

# Flask app with explicit template folder (since app is in src/, we need to go up to root)
app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates'))
app.secret_key = "TARS_NEXUS_SECRET_KEY_2026" # Persistent key to avoid 401 on reboot

# Cache for Memory Engine only
_memory_engine = None

def get_memory_engine():
    global _memory_engine
    if _memory_engine is None:
        _memory_engine = MemoryEngine(db_path=DB_PATH, chroma_path=CHROMA_PATH)
    return _memory_engine

DASHBOARD_PASSWORD = settings.DASHBOARD_PASSWORD

def check_auth():
    return session.get("authenticated", False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password and hmac.compare_digest(password, DASHBOARD_PASSWORD):
            session['authenticated'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error="Access Denied")
    return render_template('login.html')

@app.route('/')
def index():
    if not check_auth(): return redirect(url_for('login'))
    
    stress, state = get_mood_metrics()
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    df_logs = get_audit_logs()
    v_path, a_path, a_fill = get_mood_paths(df_logs)
    
    nodes, links = get_graph_data()
    counts = get_total_counts()
    knowledge = get_knowledge_data()
    memories = get_memories()
    
    console_lines = [{"ts": row["timestamp"][-8:], "msg": f"{row['mood'].upper()[:10]} - LOG CAPTURED"} for _, row in df_logs.head(10).iterrows()]
    
    return render_template('index.html', 
                           cpu=cpu, ram=ram, stress=int(stress*100), state=state,
                           v_path=v_path, a_path=a_path, a_fill=a_fill,
                           graph_nodes=nodes, graph_links=links,
                           total_facts=counts["facts"], total_memories=counts["memories"], activity_24h=counts["activity"],
                           knowledge_rows=knowledge[:10], memories=memories,
                           console_lines=console_lines)

@app.route('/mobile')
def mobile_redirect():
    return redirect(url_for('index'))

@app.route('/api/graph')
def get_graph():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    nodes, links = get_graph_data()
    return jsonify({"nodes": nodes, "links": links})

@app.route('/api/stats')
def get_stats():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    stress, state = get_mood_metrics()
    counts = get_total_counts()
    return jsonify({
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "stress": int(stress*100),
        "state": state,
        "activity": counts["activity"],
        "facts": counts["facts"]
    })

@app.route('/api/system/<action>', methods=['POST'])
def system_action(action):
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    
    stop_flag_path = settings.STOP_FLAG
    
    if action == "reboot":
        # 1. Clear stop flag if it exists so bot can start again
        if os.path.exists(stop_flag_path):
            try: os.remove(stop_flag_path)
            except: pass
            
        # 2. Signal script.py and self to reboot
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = proc.info['cmdline'] or []
                cmd_str = " ".join(cmd).lower()
                if 'python' in proc.info['name'].lower() and ("src.script" in cmd_str or "src.app" in cmd_str):
                    if proc.pid != os.getpid():
                        proc.kill()
            except: pass
        
        # 3. Final kick to self
        os.kill(os.getpid(), signal.SIGTERM)
        return jsonify({"status": "reboot_sig_sent"})
        
    elif action == "shutdown":
        # 1. Write stop flag to prevent supervisor from restarting anything
        try:
            with open(stop_flag_path, "w") as f: f.write("STOP")
        except Exception as e:
            return jsonify({"error": f"Failed to write stop flag: {e}"}), 500

        # 2. Kill the bot process and any other dashboard instances
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = proc.info['cmdline'] or []
                cmd_str = " ".join(cmd).lower()
                # Target both the bot and dashboard apps
                if 'python' in proc.info['name'].lower() and ("src.script" in cmd_str or "src.app" in cmd_str):
                    if proc.pid != os.getpid():
                        proc.kill()
            except: pass

        # 3. Terminate self - boot.sh will now see the flag and NOT restart the dashboard
        os.kill(os.getpid(), signal.SIGTERM)
        return jsonify({"status": "shutdown_sig_sent"})
        
    return jsonify({"error": "invalid_action"}), 400

@app.route('/api/chat', methods=['POST'])
async def chat():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    data = request.json
    prompt = data.get("prompt")
    if not prompt: return jsonify({"error": "no prompt"}), 400
    
    # Use the Fresh Client/Brain pattern to avoid event loop conflicts
    from openai import AsyncOpenAI
    client = AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_TOKEN
    )
    
    mem = get_memory_engine()
    brain = CognitiveEngine(
        memory_engine=mem,
        llm_client=client,
        model_name=settings.MODEL_NAME,
        comfy_url=settings.COMFY_URL,
        lazy_load=True
    )
    
    try:
        response, _, _, _ = await brain.process_interaction(
            user_id="DASHBOARD",
            username="Admin",
            user_text=prompt
        )
        return jsonify({"response": response})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/facts/list')
def api_facts_list():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, user_id, subject, predicate, object FROM facts ORDER BY timestamp DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/facts/delete', methods=['POST'])
def api_facts_delete():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    try:
        fact_id = request.json.get("id")
        if not fact_id: return jsonify({"error": "no id"}), 400

        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/node/delete', methods=['POST'])
def api_node_delete():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    try:
        db_ref = request.json.get("db_ref")
        if not db_ref: return jsonify({"error": "no db_ref"}), 400

        if db_ref.startswith("fact:"):
            fact_id = db_ref.split(":", 1)[1]
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            conn.close()
            return jsonify({"status": "deleted", "type": "fact"})

        elif db_ref.startswith("reminder:"):
            reminder_id = db_ref.split(":", 1)[1]
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()
            conn.close()
            return jsonify({"status": "deleted", "type": "reminder"})

        elif db_ref.startswith("chroma:"):
            # Format: chroma:{collection_name}:{doc_id}
            parts = db_ref.split(":", 2)
            if len(parts) < 3: return jsonify({"error": "malformed chroma db_ref"}), 400
            col_name, doc_id = parts[1], parts[2]
            client = chromadb.PersistentClient(path=CHROMA_PATH)
            collection = client.get_collection(col_name)
            collection.delete(ids=[doc_id])
            return jsonify({"status": "deleted", "type": "chroma"})

        return jsonify({"error": "unknown db_ref type"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/facts/update', methods=['POST'])
def api_facts_update():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    try:
        data = request.json.get("facts", [])
        if not data: return jsonify({"status": "no data"}), 400
        
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for f in data:
            fid = f.get('id')
            s, p, o = f.get('subject'), f.get('predicate'), f.get('object')
            if fid:
                c.execute("UPDATE facts SET subject=?, predicate=?, object=? WHERE id=?", (s, p, o, fid))
        conn.commit()
        conn.close()
        return jsonify({"status": "updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/memories')
def api_memories():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_memories())

@app.route('/api/logs')
def api_logs():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    df = get_audit_logs()
    logs = [{"ts": row["timestamp"][-8:], "msg": f"{row['mood'].upper()[:10]} - LOG CAPTURED"} for _, row in df.head(30).iterrows()]
    return jsonify(logs)

@app.route('/api/system/broadcast', methods=['POST'])
def system_broadcast():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    msg = request.json.get("message")
    if not msg: return jsonify({"error": "no message"}), 400
    
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if webhook_url:
        import httpx
        try:
            httpx.post(webhook_url, json={"content": msg})
            return jsonify({"status": "sent"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "comms offline"}), 503

@app.route('/api/mood/analytics')
def api_mood_analytics():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    import pandas as pd
    df = get_audit_logs()
    result = {"mood_counts": {}, "timeline": [], "activity_by_hour": {}}
    if df.empty:
        return jsonify(result)
    
    # Mood counts (last 100 entries)
    if 'mood' in df.columns:
        moods = df['mood'].dropna().astype(str).head(100)
        # Clean mood strings - take the first word before parentheses
        cleaned = moods.apply(lambda x: x.split('(')[0].strip().split()[0] if x else 'unknown')
        counts = cleaned.value_counts().to_dict()
        result["mood_counts"] = counts
    
    # Timeline data (last 50 entries for scatter plot)
    if 'mood' in df.columns and 'timestamp' in df.columns:
        recent = df.head(50)
        timeline = []
        for _, row in recent.iterrows():
            mood_raw = str(row.get('mood', ''))
            mood_clean = mood_raw.split('(')[0].strip().split()[0] if mood_raw else 'unknown'
            timeline.append({
                "timestamp": str(row.get('timestamp', '')),
                "mood": mood_clean
            })
        result["timeline"] = timeline
    
    # Activity by hour (all entries)
    if 'timestamp' in df.columns:
        try:
            ts = pd.to_datetime(df['timestamp'], errors='coerce')
            hour_counts = ts.dropna().dt.hour.value_counts().sort_index()
            result["activity_by_hour"] = {str(int(h)): int(v) for h, v in hour_counts.items()}
        except:
            pass
    
    return jsonify(result)

@app.route('/api/debug/logs')
def api_debug_logs():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    df = get_audit_logs()
    
    # We want to return a list of logs with parsed prompt sections
    logs = []
    # limit to last 50 for performance
    for idx, row in df.head(50).iterrows():
        full_p = row.get('full_prompt', '')
        sections = parse_prompt(full_p)
        logs.append({
            "id": idx,
            "timestamp": row.get('timestamp', ''),
            "prompt": row.get('prompt', ''),
            "full_prompt": full_p,
            "sections": sections
        })
    return jsonify(logs)

@app.route('/api/cli/logs')
def api_cli_logs():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    try:
        import os
        # Use centralized log path from settings (placed under data/)
        log_path = settings.LOG_FILE
        if not os.path.exists(log_path):
            return jsonify({"lines": ["[SYSTEM] Log file not found."]})
            
        # Read the last 200 lines efficiently
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            tail_lines = lines[-200:]
            
        return jsonify({"lines": [line.strip() for line in tail_lines if line.strip()]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 TARS Dashboard booting on http://0.0.0.0:8514")
    app.run(host='0.0.0.0', port=8514, debug=True, use_reloader=False)
