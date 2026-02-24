import os
import datetime
import threading
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
from .config import TRANSCRIPTION_HISTORY, TRANSCRIPTION_LOCK, TRANSCRIPT_FILE

app = Flask(__name__)
CORS(app)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Speaker ID Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Outfit', sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { font-weight: 600; color: #38bdf8; text-align: center; margin-bottom: 40px; }
        #transcript { background: #1e293b; border-radius: 16px; padding: 24px; min-height: 400px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid #334155; overflow-y: auto; max-height: 80vh; }
        .entry { margin-bottom: 16px; border-bottom: 1px solid #334155; padding-bottom: 12px; animation: fadeIn 0.4s ease-out; }
        .entry:last-child { border: none; }
        .time { font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px; }
        .speaker { font-weight: 600; color: #38bdf8; margin-right: 8px; }
        .text { color: #e2e8f0; line-height: 1.5; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎙️ Real-Time Speaker ID Dashboard</h1>
        <div id="transcript"></div>
    </div>
    <script>
        async function fetchUpdates() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                const container = document.getElementById('transcript');
                const atBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 100;
                
                container.innerHTML = data.map(e => `
                    <div class="entry">
                        <div class="time">${e.timestamp}</div>
                        <span class="speaker">${e.speaker}:</span>
                        <span class="text">${e.text}</span>
                    </div>
                `).join('');
                
                if(atBottom && data.length > 0) container.scrollTop = container.scrollHeight;
            } catch (e) {}
        }
        setInterval(fetchUpdates, 500);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/data')
def get_data():
    with TRANSCRIPTION_LOCK:
        return jsonify(TRANSCRIPTION_HISTORY[-50:]) # Send last 50 entries

def log_transcript(speaker, text):
    """Appends to the session transcript file and history."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    
    with TRANSCRIPTION_LOCK:
        TRANSCRIPTION_HISTORY.append({"speaker": speaker, "text": text, "timestamp": timestamp})
    
    mode = "a" if os.path.exists(TRANSCRIPT_FILE) else "w"
    with open(TRANSCRIPT_FILE, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("# Live Session Transcript\n\n")
        f.write(f"| {timestamp} | **{speaker}** | {text} |\n")

def run_dashboard():
    # Use 0.0.0.0 to allow external access if needed
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def start_dashboard():
    t = threading.Thread(target=run_dashboard, daemon=True)
    t.start()
    print("Dashboard active at http://localhost:5000")
    return t
