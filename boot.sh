export PYTHONPATH="${PYTHONPATH}:/app/applications/tars"
#!/bin/bash

# 1. Define paths
VENV_PATH="/app/applications/tars/venv"

echo "🔍 Checking environment..."

# 1.5 System Dependencies (Merged from start.sh/run.sh)
if command -v apt-get &> /dev/null; then
    echo "🔧 Checking System Dependencies..."
    
    # Check for libopus (Required for Voice)
    if ! ldconfig -p | grep -q libopus; then
        echo "🔊 libopus not found. Installing..."
        apt-get update && apt-get install -y libopus0
    fi
    
    # Check for build tools (Required for chroma/llama.cpp)
    if ! command -v gcc &> /dev/null || ! command -v cmake &> /dev/null; then
         echo "🛠️ Build tools not found. Installing build-essential gcc cmake..."
         apt-get update && apt-get install -y build-essential gcc cmake
    fi
    
    # Check for FFMPEG (System level is preferred)
    if ! command -v ffmpeg &> /dev/null; then
         echo "🎬 ffmpeg not found. Installing..."
         apt-get install -y ffmpeg
    fi
fi

# 2. Create venv if it doesn't exist
if [ ! -d "$VENV_PATH" ]; then
    echo "🛠️ Creating new virtual environment in $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
fi

# 3. Activate the virtual environment
# This automatically sets your PATH so 'python' and 'pip' point to the venv
source "$VENV_PATH/bin/activate"

# 4. Smart Dependency Check
# We check for the package folder inside the venv's site-packages
# Note: Streamlit folder name is 'streamlit', psutil is 'psutil'
SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")

if [ ! -d "$SITE_PACKAGES/psutil" ] || [ ! -d "$SITE_PACKAGES/chromadb" ] || [ ! -d "$SITE_PACKAGES/discord" ] || [ ! -d "$SITE_PACKAGES/llama_cpp" ]; then
    echo "🚀 Installing dependencies into venv..."
    pip install --upgrade pip
    pip install -r /app/applications/tars/requirements.txt
    echo "✅ Dependencies updated!"
else
    #pip install -r /app/applications/tars/requirements.txt
    echo "✨ Venv looks good. Skipping install!"
fi

# 5. Start the Dashboard (Supervisor Loop - Background)
echo "📊 Launching Dashboard Supervisor..."
(
while true; do
    echo "🚀 Starting Dashboard Process..."
    python -m src.app
    echo "⚠️ Dashboard exited. Restarting in 2s..."
    sleep 2
done
) &

# 6. Start the Bot (Supervisor Loop)
echo "🤖 Launching TARS Supervisor..."
while true; do
    if [ -f "/app/stop_bot.flag" ]; then
        echo "🛑 'stop_bot.flag' detected. Bot is paused."
        sleep 5
    else
        echo "🚀 Starting Bot Process..."
        # -u keeps logs unbuffered so they show up in the log file immediately
        # Redirect runtime logs into the `data/` directory
        python -u -m src.script >> /app/applications/tars/data/bot.log 2>&1
        
        EXIT_CODE=$?
        echo "⚠️ Bot process exited with code $EXIT_CODE."
        
        # If exit code was 0 (clean exit), maybe we want to stop? 
        # For now, we assume we always want to restart unless the flag is present.
        echo "🔄 Restarting in 2 seconds..."
        sleep 2
    fi
done