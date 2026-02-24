import os
from dotenv import load_dotenv

load_dotenv()
import logging
import threading
import collections
import multiprocessing

# --- LOGGING SETUP ---
audio_logger = logging.getLogger("audio_debug")
audio_logger.setLevel(logging.INFO)
if not audio_logger.handlers:
    fh = logging.FileHandler("audio_debug.log")
    fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt="%d%H%M%b%y"))
    audio_logger.addHandler(fh)

# --- ENVIRONMENT & AUTH ---
HF_TOKEN = os.getenv("HF_TOKEN")
os.environ["HF_TOKEN"] = HF_TOKEN

# --- AUDIO SETTINGS ---
SAMPLE_RATE = 16000
DIART_LATENCY = 0.6 # Reduced from 1.0s
BUFFER_DURATION = 30
MAX_SAMPLES = BUFFER_DURATION * SAMPLE_RATE
VAD_THRESHOLD = float(os.getenv("NOISE_THRESHOLD", 0.005))
ADAPTIVE_VAD = True
INTERRUPTION_THRESHOLD = 0.02
NORMALIZATION_TARGET = -20.0 # dBFS
ENROLLED_SPEAKERS = {} # Stores { "Name": embedding_vector }

# --- MODEL SETTINGS ---
WHISPER_MODEL = "distil-small.en"
COMPUTE_TYPE = "int8"
EMBEDDING_DIM = 512 # Standard for pyannote/embedding

# --- PERSISTENCE ---
REGISTRY_FILE = "speaker_registry.json"
TRANSCRIPT_FILE = "transcript.md"

# --- GLOBAL STATE & LOCKS ---
TOTAL_SAMPLES_CAPTURED = 0
TRANSCRIPTION_HISTORY = [] # List of { "speaker": str, "text": str, "timestamp": str }
TRANSCRIPTION_LOCK = threading.Lock()

audio_buffer = collections.deque(maxlen=MAX_SAMPLES)
buffer_lock = threading.Lock()

known_id_map = {}    # { speaker_id: Name }
subagents = {}       # { speaker_id: VoiceSubagent }
speaker_lock = threading.Lock()

# Bridge for Multiprocessing
result_queue = multiprocessing.Queue()
