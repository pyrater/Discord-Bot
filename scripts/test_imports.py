#!/usr/bin/env python3
"""Test imports after fixing."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

print("Testing imports...")
errors = []

try:
    print("  • Importing src.bot_config...")
    from src import bot_config
    print("    ✓ bot_config OK")
except Exception as e:
    errors.append(f"bot_config: {e}")
    print(f"    ❌ {e}")

try:
    print("  • Importing src.brain...")
    from src import brain
    print("    ✓ brain OK")
except Exception as e:
    errors.append(f"brain: {e}")
    print(f"    ❌ {e}")

try:
    print("  • Importing src.tts.config...")
    from src.tts import config as tts_config
    print("    ✓ tts.config OK")
except Exception as e:
    errors.append(f"tts.config: {e}")
    print(f"    ❌ {e}")

try:
    print("  • Importing src.tts.transcription_engine...")
    from src.tts import transcription_engine
    print("    ✓ tts.transcription_engine OK")
except Exception as e:
    errors.append(f"tts.transcription_engine: {e}")
    print(f"    ❌ {e}")

try:
    print("  • Importing src.script...")
    from src import script
    print("    ✓ script OK")
except Exception as e:
    errors.append(f"script: {e}")
    print(f"    ❌ {e}")

if errors:
    print(f"\n❌ {len(errors)} import errors found:")
    for err in errors:
        print(f"   - {err}")
    sys.exit(1)
else:
    print("\n✓ All imports successful!")
    sys.exit(0)
