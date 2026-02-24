#!/usr/bin/env python3
"""Restructure repo: move Python files to src/, update imports."""

import os
import shutil
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'

# Files to move from root to src/
MOVE_TO_SRC = [
    'app.py',
    'brain.py',
    'bot_config.py',
    'conversation_manager.py',
    'memory_engine.py',
    'script.py',
    'tars_utils.py',
    'voice_bridge.py',
    'voice_engine.py',
]

# Directories to move
MOVE_DIRS = {
    'cogs': 'cogs',
    'tts': 'tts',
    'tabs': 'tabs',
}

# Files that import from these modules - need import updates
IMPORT_DEPS = {
    'bot_config': ['app', 'brain', 'conversation_manager', 'memory_engine', 'script', 'tars_utils', 'voice_bridge'],
    'brain': ['app', 'conversation_manager'],
    'conversation_manager': ['app'],
    'memory_engine': ['app', 'brain', 'conversation_manager'],
    'tars_utils': ['app'],
    'voice_bridge': ['script'],
    'tts': ['script', 'voice_bridge'],
}

def colorize(text, color):
    """Limited color output (no ANSI on all systems)."""
    return text

def step(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

def safe_backup(fpath):
    """Backup file if it exists."""
    if fpath.exists():
        bak = fpath.with_suffix(fpath.suffix + '.bak')
        shutil.copy2(fpath, bak)
        return bak
    return None

def create_src_structure():
    """Create src/ directory structure."""
    step("STEP 1: Creating src/ structure")
    SRC.mkdir(exist_ok=True)
    (SRC / '__init__.py').touch()
    print(f"✓ Created src/")
    
    for dir_name in MOVE_DIRS.values():
        new_dir = SRC / dir_name
        new_dir.mkdir(exist_ok=True)
        (new_dir / '__init__.py').touch()
        print(f"✓ Created src/{dir_name}/")

def move_files():
    """Move Python files to src/."""
    step("STEP 2: Moving Python files to src/")
    
    for fname in MOVE_TO_SRC:
        src_file = ROOT / fname
        dst_file = SRC / fname
        
        if src_file.exists():
            safe_backup(dst_file)
            shutil.move(str(src_file), str(dst_file))
            print(f"✓ Moved {fname} → src/{fname}")
        else:
            print(f"⚠️  {fname} not found (skipping)")

def move_directories():
    """Move directories to src/."""
    step("STEP 3: Moving directories to src/")
    
    for old_name, new_name in MOVE_DIRS.items():
        old_dir = ROOT / old_name
        new_dir = SRC / new_name
        
        if old_dir.exists():
            if new_dir.exists():
                print(f"⚠️  {new_name}/ already exists in src/ (backing up old)")
                shutil.move(str(new_dir), str(new_dir.with_name(new_name + '.bak')))
            shutil.move(str(old_dir), str(new_dir))
            print(f"✓ Moved {old_name}/ → src/{new_name}/")
        else:
            print(f"⚠️  {old_name}/ not found (skipping)")

def update_imports():
    """Update imports across files."""
    step("STEP 4: Updating imports")
    
    # Files that need import updates
    py_files_in_src = list(SRC.glob('*.py')) + list(SRC.glob('*/*.py'))
    
    import_patterns = [
        (r'^from bot_config import', 'from src.bot_config import'),
        (r'^from brain import', 'from src.brain import'),
        (r'^from conversation_manager import', 'from src.conversation_manager import'),
        (r'^from memory_engine import', 'from src.memory_engine import'),
        (r'^from tars_utils import', 'from src.tars_utils import'),
        (r'^from voice_bridge import', 'from src.voice_bridge import'),
        (r'^from voice_engine import', 'from src.voice_engine import'),
        (r'^from script import', 'from src.script import'),
        (r'^from cogs\.', 'from src.cogs.'),
        (r'^from tts\.', 'from src.tts.'),
        (r'^from tabs\.', 'from src.tabs.'),
        (r'^import bot_config', 'import src.bot_config'),
        (r'^import tts\.', 'import src.tts.'),
        (r'^import cogs\.', 'import src.cogs.'),
    ]
    
    updated_count = 0
    for fpath in py_files_in_src:
        text = fpath.read_text(encoding='utf-8', errors='ignore')
        orig = text
        
        for pattern, replacement in import_patterns:
            text = re.sub(pattern, replacement, text, flags=re.M)
        
        # Handle relative imports within src/ (convert to absolute)
        if fpath.parent == SRC:
            # Files in src/: relative imports become src.X
            text = re.sub(r'from \. import', 'from src import', text)
            text = re.sub(r'from \.bot_config', 'from src.bot_config', text)
            text = re.sub(r'from \.tts', 'from src.tts', text)
            text = re.sub(r'from \.cogs', 'from src.cogs', text)
        
        if text != orig:
            safe_backup(fpath)
            fpath.write_text(text, encoding='utf-8')
            updated_count += 1
            print(f"✓ Updated {fpath.relative_to(ROOT)}")
    
    print(f"\n✓ Updated {updated_count} files")

def update_boot_sh():
    """Update boot.sh to reference new structure."""
    step("STEP 5: Updating boot.sh")
    
    boot_file = ROOT / 'boot.sh'
    if boot_file.exists():
        text = boot_file.read_text(encoding='utf-8')
        orig = text
        
        # Update Python path if trying to run app.py directly
        text = re.sub(r'python app\.py', 'python -m src.app', text)
        text = re.sub(r'python script\.py', 'python -m src.script', text)
        
        # Ensure PYTHONPATH includes root
        if 'PYTHONPATH' not in text:
            text = 'export PYTHONPATH="${PYTHONPATH}:/app/applications/tars"\n' + text
        
        if text != orig:
            safe_backup(boot_file)
            boot_file.write_text(text, encoding='utf-8')
            print("✓ Updated boot.sh")
        else:
            print("ℹ️  boot.sh already correct")
    else:
        print("⚠️  boot.sh not found")

def verify_structure():
    """Show final structure."""
    step("STEP 6: Verifying structure")
    
    print(f"Root directory ({ROOT.name}/):")
    for item in sorted(ROOT.iterdir()):
        if item.name.startswith('.'):
            continue
        rel = item.relative_to(ROOT)
        marker = '📁' if item.is_dir() else '📄'
        print(f"  {marker} {rel}/") if item.is_dir() else print(f"  {marker} {rel}")
    
    print(f"\nSrc directory (src/):")
    if SRC.exists():
        for item in sorted(SRC.iterdir()):
            if item.name.startswith('_'):
                continue
            rel = item.relative_to(SRC)
            marker = '📁' if item.is_dir() else '📄'
            print(f"  {marker} {rel}/") if item.is_dir() else print(f"  {marker} {rel}")

def validate_python():
    """Quick syntax check."""
    step("STEP 7: Validating Python syntax")
    
    import py_compile
    py_files = list(SRC.glob('*.py')) + list(SRC.glob('*/*.py'))
    
    errors = 0
    for fpath in py_files:
        try:
            py_compile.compile(str(fpath), doraise=True)
            print(f"✓ {fpath.relative_to(ROOT)}")
        except Exception as e:
            print(f"❌ {fpath.relative_to(ROOT)}: {e}")
            errors += 1
    
    return errors == 0

if __name__ == '__main__':
    try:
        create_src_structure()
        move_files()
        move_directories()
        update_imports()
        update_boot_sh()
        verify_structure()
        
        if validate_python():
            print("\n" + "="*60)
            print("✓ RESTRUCTURING COMPLETE & VALIDATED")
            print("="*60)
            print("\nNext steps:")
            print("1. Test imports: python -c 'from src import app'")
            print("2. Update any remaining hardcoded paths in environment/configs")
            print("3. Restart the bot")
        else:
            print("\n⚠️  Some syntax errors detected; review above")
        
    except Exception as e:
        print(f"\n❌ Error during restructuring: {e}")
        import traceback
        traceback.print_exc()
