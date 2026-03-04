import os
# Disable telemetry BEFORE other imports
os.environ['CHROMA_TELEMETRY'] = 'False'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

import sqlite3
import pandas as pd
import psutil
import json
import html
import chromadb
from dotenv import load_dotenv
from src.bot_config import settings

# Absolute paths (prefer central settings)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Use configured paths from settings so they reflect the reorganized layout
DB_PATH = settings.DB_PATH
CHROMA_PATH = settings.CHROMA_PATH
LOG_FILE = settings.LOG_FILE

def get_audit_logs():
    if not os.path.exists(DB_PATH): return pd.DataFrame()
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
        df = pd.read_sql_query("SELECT * FROM audit_logs ORDER BY timestamp DESC", conn)
        conn.close()
        return df
    except: return pd.DataFrame()

# Sentiment/Arousal Mapping for GoEmotions
# Format: label: (valence [-1 to 1], arousal [0 to 1])
# Higher arousal = higher "Neural Stress"
EMOTION_PROPERTIES = {
    'admiration': (0.8, 0.3), 'amusement': (0.8, 0.4), 'anger': (-0.8, 0.9), 'annoyance': (-0.4, 0.6),
    'approval': (0.6, 0.2), 'caring': (0.7, 0.2), 'confusion': (-0.2, 0.5), 'curiosity': (0.5, 0.5),
    'desire': (0.5, 0.6), 'disappointment': (-0.6, 0.3), 'disapproval': (-0.5, 0.4), 'disgust': (-0.7, 0.6),
    'embarrassment': (-0.4, 0.7), 'excitement': (0.8, 0.8), 'fear': (-0.9, 0.9), 'gratitude': (0.9, 0.2),
    'grief': (-0.9, 0.2), 'joy': (0.9, 0.6), 'love': (1.0, 0.5), 'nervousness': (-0.4, 0.8),
    'optimism': (0.7, 0.4), 'pride': (0.7, 0.5), 'realization': (0.3, 0.4), 'relief': (0.6, 0.1),
    'remorse': (-0.6, 0.4), 'sadness': (-0.8, 0.2), 'surprise': (0.6, 0.8), 'neutral': (0.0, 0.1),
    'unknown': (0.0, 0.0)
}

def get_mood_metrics():
    """Calculates neural stress (volatility/arousal) and the dominant system state."""
    try:
        # Get the very latest log
        df = get_audit_logs().head(1)
        if df.empty:
            return 0.0, "STANDBY"
            
        latest = df.iloc[0]
        raw_mood = str(latest.get('mood', 'neutral'))
        ts_str = str(latest.get('timestamp', ''))
        
        # 1. Parse emotion name and confidence
        if '(' in raw_mood and ')' in raw_mood:
            emo_name = raw_mood.split('(')[0].strip().lower()
            try:
                conf = float(raw_mood.split('(')[1].split(')')[0])
            except:
                conf = 0.5
        else:
            emo_name = raw_mood.strip().lower()
            conf = 1.0

        # 2. Calculate Base Stress (Arousal * Confidence)
        emo_data = EMOTION_PROPERTIES.get(emo_name, EMOTION_PROPERTIES['unknown'])
        valence, arousal = emo_data
        
        # Neural Stress is primarily linked to Arousal
        # We also boost it slightly if valence is very negative
        base_stress = arousal
        if valence < -0.4:
            base_stress = max(base_stress, abs(valence) * 0.8)
        
        stress_val = base_stress * conf

        # 3. Apply Time-based Decay
        try:
            # Assumes format "2024-..." or ISO
            last_time = pd.to_datetime(ts_str)
            diff_sec = (datetime.now() - last_time).total_seconds()
        except:
            diff_sec = 0

        # State Heuristics
        if diff_sec > 600: # 10 mins
            return 0.0, "IDLE"
        elif diff_sec > 120: # 2 mins
            return stress_val * 0.2, "STANDBY"
        
        # 4. Final state name logic
        if stress_val > 0.6 and valence < 0:
            state = "DISTURBED"
        elif stress_val > 0.4 and valence < 0:
            state = "ALERT"
        elif stress_val > 0.5 and valence > 0.5:
            state = "EXCITED"
        elif valence > 0.3:
            state = "STABLE"
        elif emo_name == "neutral":
            state = "NORMAL"
        else:
            state = emo_name.upper()

        return stress_val, state

    except Exception as e:
        print(f"Error in get_mood_metrics: {e}")
        return 0.0, "ERROR"

def get_mood_paths(df):
    """Generates SVG paths for Valence and Arousal visualizations."""
    if df is None or df.empty or 'mood' not in df.columns:
        return "M0,50 L100,50", "M0,80 L100,80", "M0,80 L100,80 L100,100 L0,100 Z"
    
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
        m = m_str.split('(')[0].strip().lower()
        v, a = v_a_map.get(m, (0.0, 0.0))
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

def parse_prompt(full_prompt):
    """Parses system prompts into structured sections."""
    sections = {"Persona": "Not found", "Context": "Not found", "Memories": "None retrieved", "Instructions": "Not found"}
    if not full_prompt or not isinstance(full_prompt, str): return sections
    parts = {
        "Persona": "### SYSTEM PERSONA ###", "Examples": "### EXAMPLE DIALOGUE ###",
        "Facts": "### KNOWN FACTS ###", "Context": "### INTERACTION CONTEXT ###",
        "Memories": "### RETRIEVED MEMORIES ###", "History": "### RECENT HISTORY ###",
        "Instructions": "### INSTRUCTIONS ###"
    }
    lines = full_prompt.split("\n")
    current_key = None
    buffer = []
    for line in lines:
        matched = False
        for key, header in parts.items():
            if header in line:
                if current_key: sections[current_key] = "\n".join(buffer).strip()
                current_key = key
                buffer = []
                matched = True
                break
        if not matched and current_key: buffer.append(line)
    if current_key: sections[current_key] = "\n".join(buffer).strip()
    return sections

def get_graph_data():
    """Generates d3-compatible graph data from SQLite facts and Chroma indices, replicating the legacy nested structure."""
    nodes = [
        {"id": "USER", "name": "USER INPUT", "color": "#00f0ff", "size": 20, "group": "core"},
        {"id": "BRAIN", "name": "COGNITIVE CORE", "color": "#bc13fe", "size": 32, "group": "core"},
        {"id": "LLM", "name": "LLM API", "color": "#5865f2", "size": 18, "group": "core"}
    ]
    links = [
        {"source": "USER", "target": "BRAIN", "value": "core"},
        {"source": "BRAIN", "target": "LLM", "value": "core"}
    ]
    
    hub_memory = "hub_memory"
    hub_knowledge = "hub_knowledge"
    hub_facts = "hub_facts"
    hub_reminders = "hub_reminders"
    
    nodes.extend([
        {"id": hub_memory, "name": "USER MEMORY", "color": "#ffca28", "size": 24, "group": "hub", "details": "Episodic user conversations"},
        {"id": hub_knowledge, "name": "KNOWLEDGE", "color": "#3fb950", "size": 24, "group": "hub", "details": "Ingested general knowledge"},
        {"id": hub_facts, "name": "FACTS", "color": "#58a6ff", "size": 24, "group": "hub", "details": "General Facts"},
        {"id": hub_reminders, "name": "REMINDERS", "color": "#f85149", "size": 24, "group": "hub", "details": "Tasks and Alerts"}
    ])
    
    links.extend([
        {"source": "BRAIN", "target": hub_memory, "value": "hub", "strength": 0.9},
        {"source": "BRAIN", "target": hub_knowledge, "value": "hub", "strength": 0.9},
        {"source": "BRAIN", "target": hub_facts, "value": "hub", "strength": 0.9},
        {"source": "BRAIN", "target": hub_reminders, "value": "hub", "strength": 0.9}
    ])
    
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            # Exhaustive sweep of FACTS
            df_facts = pd.read_sql_query("SELECT id, subject, predicate, object, timestamp FROM facts ORDER BY timestamp DESC", conn)

            # Exhaustive sweep of REMINDERS
            try:
                df_reminders = pd.read_sql_query("SELECT id, note, due_time FROM reminders", conn)
                for i, row in df_reminders.iterrows():
                    rid = f"rem_{i}"
                    nodes.append({
                        "id": rid,
                        "name": str(row['note'])[:20] + "...",
                        "color": "#f85149",
                        "size": 10,
                        "group": "data",
                        "db_ref": f"reminder:{row['id']}",
                        "details": f"TASK: {row['note']}\nDUE: {row['due_time']}"
                    })
                    links.append({"source": hub_reminders, "target": rid, "value": "data", "strength": 0.4})
            except: pass

            conn.close()
            
            subjects_map = {}
            objects_map = {}
            
            for i, row in df_facts.iterrows():
                subj = row['subject'].strip()
                obj = row['object'].strip()
                pred = row['predicate'].strip()
                
                # Subject Hub
                if subj not in subjects_map:
                    subj_id = f"subj_{hash(subj) % 100000}"
                    
                    # Subjects from facts link directly to FACTS hub
                    nodes.append({
                        "id": subj_id,
                        "name": subj.upper()[:20],
                        "color": "#1f6feb",
                        "size": 16,
                        "group": "user",
                        "details": f"ENTITY: {subj}\nFACTS: {len(df_facts[df_facts['subject'].str.strip() == subj])}"
                    })
                    links.append({"source": hub_facts, "target": subj_id, "value": "category", "strength": 0.6})
                    subjects_map[subj] = subj_id
                
                # Object Leaf
                obj_key = obj.lower().strip()
                if obj_key not in objects_map:
                    obj_id = f"obj_{hash(obj_key) % 100000}_{i}"
                    nodes.append({
                        "id": obj_id,
                        "name": obj[:30],
                        "color": "#58a6ff",
                        "size": 8,
                        "group": "data",
                        "db_ref": f"fact:{row['id']}",
                        "details": f"FACT: {subj} {pred} {obj}\nLEARNED: {row['timestamp']}"
                    })
                    objects_map[obj_key] = obj_id
                    links.append({"source": subjects_map[subj], "target": obj_id, "value": "data", "strength": 0.2})
        except:
            pass

    # 2. VECTOR MEMORIES SUB-GRAPH
    try:
        colors = ["#ffca28", "#58a6ff", "#f85149", "#d29922"]
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collections = client.list_collections()
        
        user_nodes = {}  # Track created user memory hubs
        
        for idx, col in enumerate(collections):
            # Route based on collection name
            name_lower = col.name.lower()
            if "know" in name_lower or "doc" in name_lower or "code" in name_lower:
                parent_hub = hub_knowledge
            else:
                parent_hub = hub_memory
                
            try:
                collection = client.get_collection(col.name)
                # UNIVERSAL RETRIEVAL: collection.get() instead of peek()
                data = collection.get()
                
                # Create a VEC:COL_NAME hub for non-user memory collections
                if col.name != "user_memories":
                    cid = f"vec_{col.name}"
                    nodes.append({
                        "id": cid, 
                        "name": f"VEC:{col.name.upper()[:10]}", 
                        "color": colors[idx % len(colors)], 
                        "size": 16, 
                        "group": "hub",
                        "details": f"Collection: {col.name}"
                    })
                    links.append({"source": parent_hub, "target": cid, "value": "hub"})
                
                if data and 'ids' in data:
                    for j, doc_id in enumerate(data['ids']):
                        did = f"d_{col.name}_{j}"
                        full_doc = data['documents'][j] if j < len(data['documents']) else doc_id
                        meta = data.get('metadatas', [])
                        meta_dict = meta[j] if meta and j < len(meta) and meta[j] else {}
                        
                        if col.name == "user_memories":
                            user = meta_dict.get('username', 'Unknown User').upper()
                            uid = f"vec_user_{hash(user) % 100000}"
                            if user not in user_nodes:
                                user_nodes[user] = uid
                                nodes.append({
                                    "id": uid,
                                    "name": user[:20],
                                    "color": colors[idx % len(colors)],
                                    "size": 16,
                                    "group": "user",
                                    "details": f"USER MEMORY: {user}"
                                })
                                links.append({"source": parent_hub, "target": uid, "value": "category"})
                            
                            is_observed = full_doc.startswith("[Observed]")
                            sub_type = "OBSERVED" if is_observed else "DIRECT"
                            sub_id = f"{uid}_{sub_type}"
                            sub_key = f"{user}_{sub_type}"
                            
                            if sub_key not in user_nodes:
                                user_nodes[sub_key] = sub_id
                                nodes.append({
                                    "id": sub_id,
                                    "name": sub_type,
                                    "color": colors[idx % len(colors)],
                                    "size": 12,
                                    "group": "category",
                                    "details": f"{sub_type} interactions for {user}"
                                })
                                links.append({"source": uid, "target": sub_id, "value": "category"})
                                
                            parent_for_doc = sub_id
                        else:
                            parent_for_doc = f"vec_{col.name}"

                        nodes.append({
                            "id": did,
                            "name": full_doc[:25].strip() + "...",
                            "color": colors[idx % len(colors)],
                            "size": 5,
                            "group": "data",
                            "db_ref": f"chroma:{col.name}:{doc_id}",
                            "details": full_doc
                        })
                        links.append({"source": parent_for_doc, "target": did, "value": "data"})
            except: pass
    except:
        pass
            
    return nodes, links

def get_knowledge_data():
    if not os.path.exists(DB_PATH): return []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        df = pd.read_sql_query("SELECT subject, predicate, object, timestamp FROM facts ORDER BY timestamp DESC LIMIT 50", conn)
        conn.close()
        return df.to_dict(orient='records')
    except: return []

def get_memories():
    if not os.path.exists(DB_PATH): return []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        df = pd.read_sql_query("SELECT timestamp, content FROM observed_messages ORDER BY timestamp DESC LIMIT 20", conn)
        conn.close()
        return df.to_dict(orient='records')
    except: return []

def get_total_counts():
    counts = {"facts": 0, "memories": 0, "activity": 0}
    if not os.path.exists(DB_PATH): return counts
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        c = conn.cursor()
        
        # 1. Total Facts
        try:
            counts["facts"] = c.execute("SELECT count(*) FROM facts").fetchone()[0]
        except: pass
        
        # 2. Memories (Placeholder for now, or count Chroma if possible)
        # SQLite doesn't have basic memories table, so we use reminders or just 0
        try:
            counts["memories"] = c.execute("SELECT count(*) FROM reminders").fetchone()[0]
        except: pass
        
        # 3. 24h Activity
        try:
            from datetime import datetime, timedelta
            # Use Python threshold to match system time
            threshold = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')
            res = c.execute("SELECT count(*) FROM audit_logs WHERE timestamp >= ?", (threshold,)).fetchone()
            counts["activity"] = res[0] if res else 0
        except Exception as activity_err:
            print(f"Activity count error: {activity_err}")
        
        conn.close()
    except Exception as e:
        print(f"[ERROR] get_total_counts: {e}")
        
    return counts

