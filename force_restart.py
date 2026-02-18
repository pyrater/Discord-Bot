import psutil
import os
import signal
import time

def kill_bot():
    print("🎯 Searching for bot process (script.py)...")
    killed = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline'] or []
            if 'python' in proc.info['name'].lower() and any("script.py" in arg for arg in cmd):
                print(f"🛑 Found bot process {proc.info['pid']}. Terminating...")
                os.kill(proc.info['pid'], signal.SIGTERM)
                killed = True
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if killed:
        print("✅ Bot terminated. Supervisor should restart it in 2 seconds.")
    else:
        print("❓ No bot process found. It might be already down.")

if __name__ == "__main__":
    kill_bot()
