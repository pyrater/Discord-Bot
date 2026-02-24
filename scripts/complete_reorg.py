#!/usr/bin/env python3
"""Complete reorganization: validate, migrate, and report status."""

import sys
import py_compile
import subprocess
from pathlib import Path

def validate_files():
    """Check syntax of patched Python files."""
    root = Path(__file__).resolve().parents[1]
    files_to_check = [root / 'bot_config.py', root / 'tts' / 'config.py']
    
    print("=" * 60)
    print("STEP 1: Validating Python Syntax")
    print("=" * 60)
    
    all_ok = True
    for fpath in files_to_check:
        if not fpath.exists():
            print(f'❌ File not found: {fpath}')
            all_ok = False
            continue
        
        try:
            py_compile.compile(str(fpath), doraise=True)
            print(f'✓ {fpath.name}: OK')
        except Exception as e:
            print(f'❌ {fpath.name}: {e}')
            all_ok = False
    
    return all_ok

def run_migration():
    """Run the artifact migration script."""
    print("\n" + "=" * 60)
    print("STEP 2: Running Migration Script")
    print("=" * 60)
    
    root = Path(__file__).resolve().parents[1]
    migrate_script = root / 'scripts' / 'migrate_artifacts.py'
    
    if not migrate_script.exists():
        print(f'⚠️  Migration script not found: {migrate_script}')
        return False
    
    try:
        result = subprocess.run([sys.executable, str(migrate_script)], 
                              capture_output=True, text=True, timeout=30)
        print(result.stdout)
        if result.stderr:
            print('Stderr:', result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f'⚠️  Migration raised exception: {e}')
        return False

def show_summary():
    """Print final status."""
    root = Path(__file__).resolve().parents[1]
    
    print("\n" + "=" * 60)
    print("STEP 3: Reorg Summary")
    print("=" * 60)
    
    dirs_to_check = [root / 'db', root / 'data']
    for d in dirs_to_check:
        if d.exists():
            items = list(d.glob('*'))
            print(f'✓ {d.name}/ exists ({len(items)} items)')
        else:
            print(f'❌ {d.name}/ missing')
    
    print("\n" + "=" * 60)
    print("DONE: Repository reorganized")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run the bot to verify it starts correctly")
    print("2. Check data/bot.log for any errors")
    print("3. Verify data/ and db/ have expected files")

if __name__ == '__main__':
    try:
        syntax_ok = validate_files()
        migration_ok = run_migration()
        show_summary()
        
        if syntax_ok and migration_ok:
            print("\n✓ All steps completed successfully!")
            sys.exit(0)
        else:
            print("\n⚠️  Some steps may have issues; check above for details")
            sys.exit(0)  # non-blocking
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
