#!/usr/bin/env python3
"""Ensure directories exist with proper permissions."""

import os
from pathlib import Path

ROOT = Path('/app/applications/tars')
print(f"Working directory: {ROOT}")

# Create and verify directories
dirs = [
    ROOT / 'db',
    ROOT / 'data',
]

for d in dirs:
    d.mkdir(parents=True, exist_ok=True)
    # Make sure they're writable
    os.chmod(d, 0o777)
    print(f"✓ {d.relative_to(ROOT)}/ exists (mode: {oct(d.stat().st_mode)})")

# List what's in db/
print(f"\nContents of db/:")
for f in (ROOT / 'db').iterdir():
    print(f"  - {f.name}")

print("\n✓ Directories ready for bot startup!")
