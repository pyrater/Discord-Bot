#!/bin/bash
# 1. Update the system and install the missing compiler (GCC)
apt-get update && apt-get install -y build-essential gcc cmake

# 2. Run your original requirements install
pip install -r /app/applications/noodlebrain/requirements.txt

# 3. Start your bot
python /app/applications/noodlebrain/script.py