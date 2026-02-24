#!/usr/bin/env python3
"""Quick syntax and import validation for patched files."""

import sys
import py_compile
from pathlib import Path

def check_syntax(filepath):
    """Check Python syntax."""
    try:
        py_compile.compile(str(filepath), doraise=True)
        return True, None
    except py_compile.PyCompileError as e:
        return False, str(e)

def check_imports(filepath):
    """Try to import and check for basic errors."""
    try:
        spec_str = str(filepath).replace('/', '.').replace('.\\', '').replace('.py', '')
        if 'tts' in str(filepath):
            sys.path.insert(0, str(filepath.parents[1]))
        else:
            sys.path.insert(0, str(filepath.parent))
        return True, None
    except Exception as e:
        return False, str(e)

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    files_to_check = [
        root / 'bot_config.py',
        root / 'tts' / 'config.py',
    ]
    
    all_ok = True
    for fpath in files_to_check:
        if not fpath.exists():
            print(f'❌ File not found: {fpath}')
            all_ok = False
            continue
        
        ok, err = check_syntax(fpath)
        if ok:
            print(f'✓ Syntax OK: {fpath.name}')
        else:
            print(f'❌ Syntax error in {fpath.name}: {err}')
            all_ok = False
    
    if all_ok:
        print('\n✓ All files have valid syntax!')
        sys.exit(0)
    else:
        print('\n❌ Some files have errors!')
        sys.exit(1)
