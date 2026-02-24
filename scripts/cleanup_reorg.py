#!/usr/bin/env python3
"""Clean up: remove backups, move remaining utility scripts."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'

def cleanup():
    print("=" * 60)
    print("CLEANUP: Removing backups and reorganizing")
    print("=" * 60)
    
    # Remove .bak files and .bak directories
    for item in ROOT.glob('**/*.bak'):
        try:
            if item.is_file():
                item.unlink()
                print(f"✓ Removed {item.relative_to(ROOT)}")
            elif item.is_dir():
                shutil.rmtree(item)
                print(f"✓ Removed {item.relative_to(ROOT)}/")
        except Exception as e:
            print(f"⚠️  Failed to remove {item}: {e}")
    
    # Move remaining utility scripts to src/
    utility_scripts = [
        'diag_chroma.py',
        'diagnose_search.py',
        'ingest_codebase.py',
        'ingest_knowledge.py',
        'repair_chroma.py',
    ]
    
    print("\nMoving utility scripts to src/:")
    for fname in utility_scripts:
        src_file = ROOT / fname
        dst_file = SRC / fname
        
        if src_file.exists():
            shutil.move(str(src_file), str(dst_file))
            print(f"✓ Moved {fname} → src/{fname}")
            
            # Update imports in the moved file
            text = dst_file.read_text(encoding='utf-8', errors='ignore')
            orig = text
            
            # Add sys.path manipulation if needed
            import_adds = [
                (r'^(import|from) bot_config ', r'\1 src.bot_config '),
                (r'^(import|from) brain ', r'\1 src.brain '),
                (r'^(import|from) memory_engine ', r'\1 src.memory_engine '),
                (r'^(import|from) tars_utils ', r'\1 src.tars_utils '),
            ]
            
            for pattern, repl in import_adds:
                import re
                text = re.sub(pattern, repl, text, flags=re.M)
            
            if text != orig:
                dst_file.write_text(text, encoding='utf-8')
                print(f"  └─ Updated imports in {fname}")
        else:
            print(f"⚠️  {fname} not found")

def verify_final():
    print("\n" + "=" * 60)
    print("FINAL STRUCTURE")
    print("=" * 60)
    
    print(f"\nRoot ({ROOT.name}/):")
    root_items = sorted([x for x in ROOT.iterdir() if not x.name.startswith('.')])
    for item in root_items:
        rel = item.relative_to(ROOT)
        marker = '📁' if item.is_dir() else '📄'
        if item.is_dir():
            print(f"  {marker} {rel}/")
        else:
            print(f"  {marker} {rel}")
    
    print(f"\nSource (src/):")
    if SRC.exists():
        src_items = sorted([x for x in SRC.iterdir() if not x.name.startswith('_')])
        for item in src_items:
            rel = item.relative_to(SRC)
            marker = '📁' if item.is_dir() else '📄'
            if item.is_dir():
                print(f"  {marker} {rel}/")
            else:
                print(f"  {marker} {rel}")

if __name__ == '__main__':
    cleanup()
    verify_final()
    
    print("\n" + "=" * 60)
    print("✓ CLEANUP COMPLETE")
    print("=" * 60)
    print("\nReady to test:")
    print("  python -m src.app    # Dashboard")
    print("  python -m src.script # Bot")
