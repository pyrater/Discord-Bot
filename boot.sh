#!/bin/bash

# 1. Define paths
VENV_PATH="/app/applications/tars/venv"

echo "🔍 Checking environment..."

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

# 5. Start the Dashboard (Background)
echo "📊 Launching Dashboard..."
# Since the venv is active, 'streamlit' is directly in the PATH
streamlit run /app/applications/tars/dashboard.py \
    --global.developmentMode=false \
    --server.port 8514 \
    --server.address 0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType none &

# 6. Start the Bot (Foreground)
echo "🤖 Launching TARS..."
# -u keeps logs unbuffered so they show up in the log file immediately
python -u /app/applications/tars/script.py > /app/applications/tars/bot.log 2>&1