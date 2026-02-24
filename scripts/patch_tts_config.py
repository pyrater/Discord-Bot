from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / 'tts' / 'config.py'
print('Patching', p)
text = p.read_text(encoding='utf-8')
orig = text

if 'from bot_config import settings' not in text:
    text = text.replace('load_dotenv()\nimport logging', 'load_dotenv()\nimport logging\nfrom bot_config import settings')

# Replace the audio logger handler block
text = re.sub(r"if not audio_logger.handlers:.*?audio_logger.addHandler\(fh\)\s*", (
    "if not audio_logger.handlers:\n"
    "    os.makedirs(settings.DATA_DIR, exist_ok=True)\n"
    "    fh = logging.FileHandler(settings.AUDIO_DEBUG_LOG)\n"
    "    fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt=\"%d%H%M%b%y\"))\n"
    "    audio_logger.addHandler(fh)\n"
), text, flags=re.S)

# Replace registry and transcript paths
text = text.replace('REGISTRY_FILE = os.path.join(data_dir, "speaker_registry.json")', 'REGISTRY_FILE = settings.SPEAKER_REGISTRY')
text = text.replace('TRANSCRIPT_FILE = os.path.join(data_dir, "transcript.md")', 'TRANSCRIPT_FILE = settings.TRANSCRIPT_FILE')

if text != orig:
    p.write_text(text, encoding='utf-8')
    print('Patched tts/config.py')
else:
    print('No changes applied to tts/config.py')
