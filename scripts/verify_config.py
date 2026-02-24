#!/usr/bin/env python3
"""Verify bot_config paths are correct."""

import sys
from pathlib import Path

sys.path.insert(0, '/app/applications/tars')

from src.bot_config import settings

print("Bot Configuration Paths:")
print("=" * 60)
print(f"BASE_DIR:          {settings.BASE_DIR}")
print(f"DATA_DIR:          {settings.DATA_DIR}")
print(f"DB_PATH:           {settings.DB_PATH}")
print(f"CHROMA_PATH:       {settings.CHROMA_PATH}")
print(f"LOG_FILE:          {settings.LOG_FILE}")
print(f"TRANSCRIPT_FILE:   {settings.TRANSCRIPT_FILE}")
print(f"SPEAKER_REGISTRY:  {settings.SPEAKER_REGISTRY}")
print(f"AUDIO_DEBUG_LOG:   {settings.AUDIO_DEBUG_LOG}")
print("=" * 60)

# Verify paths exist
print("\nDirectory validation:")
required_dirs = [
    Path(settings.BASE_DIR),
    Path(settings.DATA_DIR),
    Path(settings.DB_PATH).parent,
    Path(settings.CHROMA_PATH).parent,
]

for d in required_dirs:
    exists = d.exists()
    print(f"  {'✓' if exists else '❌'} {d}")
    if not exists:
        print(f"     Creating {d}...")
        d.mkdir(parents=True, exist_ok=True)
        print(f"     ✓ Created")

print("\n✓ Configuration verified!")
