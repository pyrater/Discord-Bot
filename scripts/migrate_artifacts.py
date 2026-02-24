import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, 'db')
DATA_DIR = os.path.join(BASE_DIR, 'data')

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Files and dirs to move (source -> dest)
MAP = [
    (os.path.join(BASE_DIR, 'tars_state.db'), os.path.join(DB_DIR, 'tars_state.db')),
    (os.path.join(BASE_DIR, 'chroma_db'), os.path.join(DB_DIR, 'chroma_db')),
    (os.path.join(BASE_DIR, 'bot.log'), os.path.join(DATA_DIR, 'bot.log')),
    (os.path.join(BASE_DIR, 'audio_debug.log'), os.path.join(DATA_DIR, 'audio_debug.log')),
    (os.path.join(BASE_DIR, 'transcript.md'), os.path.join(DATA_DIR, 'transcript.md')),
    (os.path.join(BASE_DIR, 'speaker_registry.json'), os.path.join(DATA_DIR, 'speaker_registry.json')),
]

moved = []
for src, dst in MAP:
    if os.path.exists(src):
        try:
            # Directory move
            if os.path.isdir(src):
                if os.path.exists(dst):
                    print(f"Destination exists, renaming old dst: {dst}")
                    os.rename(dst, dst + ".backup")
                shutil.move(src, dst)
            else:
                # File move
                if os.path.exists(dst):
                    print(f"Destination file exists, backing up: {dst}")
                    os.rename(dst, dst + ".backup")
                shutil.move(src, dst)
            moved.append((src, dst))
            print(f"Moved {src} -> {dst}")
        except Exception as e:
            print(f"Failed to move {src} -> {dst}: {e}")
    else:
        print(f"Not found (skipping): {src}")

print('\nMigration complete.\nMoved items:')
for s, d in moved:
    print(f" - {s} -> {d}")

print('\nIf you run this in a container ensure file permissions are correct and restart the bot.')
