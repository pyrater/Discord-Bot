import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
print('Repo root:', ROOT)

# Patch bot_config.py
bot_cfg = ROOT / 'bot_config.py'
if bot_cfg.exists():
    text = bot_cfg.read_text(encoding='utf-8')
    bak = bot_cfg.with_suffix('.py.bak')
    bak.write_text(text, encoding='utf-8')
    old = 'self.LOG_FILE = os.path.join(base_dir, "data", "bot.log")'
    new = (
        'self.DATA_DIR = os.path.join(base_dir, "data")\n'
        '        os.makedirs(self.DATA_DIR, exist_ok=True)\n'
        '        self.LOG_FILE = os.path.join(self.DATA_DIR, "bot.log")\n'
        '        # Common runtime artifact paths\n'
        '        self.TRANSCRIPT_FILE = os.path.join(self.DATA_DIR, "transcript.md")\n'
        '        self.SPEAKER_REGISTRY = os.path.join(self.DATA_DIR, "speaker_registry.json")\n'
        '        self.AUDIO_DEBUG_LOG = os.path.join(self.DATA_DIR, "audio_debug.log")'
    )
    if old in text:
        text = text.replace(old, new)
        bot_cfg.write_text(text, encoding='utf-8')
        print('Patched bot_config.py')
    else:
        # fallback: insert after ART_FILENAME line
        marker = 'self.ART_FILENAME = "tars_art.png"'
        if marker in text:
            text = text.replace(marker, marker + '\n        # Log and other runtime artifacts go into `data/`\n        ' + new)
            bot_cfg.write_text(text, encoding='utf-8')
            print('Inserted data settings into bot_config.py (fallback)')
        else:
            print('Could not patch bot_config.py: pattern not found')
else:
    print('bot_config.py not found')

# Patch tts/config.py
tts_cfg = ROOT / 'tts' / 'config.py'
if tts_cfg.exists():
    text = tts_cfg.read_text(encoding='utf-8')
    bak = tts_cfg.with_suffix('.py.bak')
    bak.write_text(text, encoding='utf-8')
    old_block = (
        '    if not audio_logger.handlers:\n'
        '        # Place audio debug logs in project `data/` directory\n'
        '        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
        '        data_dir = os.path.join(base_dir, "data")\n'
        '        os.makedirs(data_dir, exist_ok=True)\n'
        '        fh = logging.FileHandler(os.path.join(data_dir, "audio_debug.log"))\n'
        '        fh.setFormatter(logging.Formatter(\"%(asctime)s - %(message)s\", datefmt=\"%d%H%M%b%y\"))\n'
        '        audio_logger.addHandler(fh)'
    )
    new_block = (
        '    if not audio_logger.handlers:\n'
        '        from bot_config import settings\n'
        '        os.makedirs(settings.DATA_DIR, exist_ok=True)\n'
        '        fh = logging.FileHandler(settings.AUDIO_DEBUG_LOG)\n'
        '        fh.setFormatter(logging.Formatter(\"%(asctime)s - %(message)s\", datefmt=\"%d%H%M%b%y\"))\n'
        '        audio_logger.addHandler(fh)'
    )
    if old_block in text:
        text = text.replace(old_block, new_block)
        tts_cfg.write_text(text, encoding='utf-8')
        print('Patched tts/config.py')
    else:
        # try simpler replacement
        if 'data_dir = os.path.join(base_dir, "data")' in text:
            text = text.replace('data_dir = os.path.join(base_dir, "data")', 'from bot_config import settings\n    os.makedirs(settings.DATA_DIR, exist_ok=True)\n    fh = logging.FileHandler(settings.AUDIO_DEBUG_LOG)')
            tts_cfg.write_text(text, encoding='utf-8')
            print('Patched tts/config.py (alt)')
        else:
            print('Could not patch tts/config.py: pattern not found')
else:
    print('tts/config.py not found')
