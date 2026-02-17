#!/bin/bash

# Ensure System Dependencies
echo "🔧 Checking System Dependencies..."
if ! ldconfig -p | grep -q libopus; then
    echo "🔊 libopus not found. Attempting install..."
    apt-get update && apt-get install -y libopus0
fi

if ! command -v ffmpeg &> /dev/null; then
    echo "🎬 ffmpeg not found. It should be installed via imageio-ffmpeg or system."
    # imageio-ffmpeg provides a binary, but system ffmpeg is often better for discord.py
    # apt-get install -y ffmpeg
fi

# Ensure Python Dependencies
echo "📦 Checking Python Dependencies..."
pip install -r requirements.txt

# Run Bot
echo "🚀 Starting NoodleBot..."
python script.py
