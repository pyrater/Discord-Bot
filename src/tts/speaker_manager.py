import json
import os
import numpy as np
try:
    import sounddevice as sd
    import torch
except ImportError:
    sd = None
    torch = None
from .config import audio_logger, SAMPLE_RATE, REGISTRY_FILE, ENROLLED_SPEAKERS, speaker_lock, subagents, TRANSCRIPTION_HISTORY, known_id_map, EMBEDDING_DIM, NORMALIZATION_TARGET

class VoiceSubagent:
    def __init__(self, name):
        self.name = name
        self.history = []
        self.audio_buffer = [] # Accumulate audio samples
        self.last_ts = 0.0     # Absolute timestamp of last processed sample
        self.last_embedding = None # Store most recent voice signature
        self.embedding_history = [] # Rolling average for better ID
        self.current_utterance = "" # Buffer for text until flush

    def normalize_audio(self, audio_chunk):
        """Applies peak normalization to the audio chunk."""
        max_val = np.max(np.abs(audio_chunk))
        if max_val > 0:
            target = 10 ** (NORMALIZATION_TARGET / 20)
            return audio_chunk * (target / max_val)
        return audio_chunk

    def get_stable_embedding(self):
        """Returns the average of last few embeddings for robustness."""
        if not self.embedding_history:
            return self.last_embedding
        return np.mean(self.embedding_history[-5:], axis=0)

    def handle_speech(self, audio_chunk, end_time, transcription_queue, sa_id, force_flush=False):
        """Buffers audio and pushes to the background queue when ready."""
        if audio_chunk is not None and len(audio_chunk) > 0:
            # Apply individual user normalization
            norm_chunk = self.normalize_audio(audio_chunk)
            self.audio_buffer.extend(norm_chunk.tolist() if isinstance(norm_chunk, np.ndarray) else norm_chunk)
            self.last_ts = end_time # Update timestamp for silence detection
            
        buffer_len_sec = len(self.audio_buffer) / SAMPLE_RATE
        # We handle intermediate chunks (every 4s) vs final flushes
        if buffer_len_sec >= 4.0 or (force_flush and buffer_len_sec > 0.1):
            audio_to_send = np.array(self.audio_buffer, dtype=np.float32)
            self.audio_buffer = [] # Clear buffer
            
            # Non-blocking: Push to queue
            audio_logger.debug(f"Queueing {buffer_len_sec:.2f}s (flush={force_flush}) for {self.name}")
            # Pass name, audio, end_time, id, and the flush status as 'is_final'
            transcription_queue.put((self.name, audio_to_send, end_time, sa_id, force_flush))

def save_registry():
    """Saves ENROLLED_SPEAKERS to a JSON file."""
    data_to_save = {name: emb.tolist() for name, emb in ENROLLED_SPEAKERS.items()}
    with open(REGISTRY_FILE, "w") as f:
        json.dump(data_to_save, f)
    print(f"Registry saved to {REGISTRY_FILE}")

def load_registry():
    """Loads ENROLLED_SPEAKERS from a JSON file."""
    global ENROLLED_SPEAKERS
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                data = json.load(f)
            # Update the reference in the shared ENROLLED_SPEAKERS dict
            ENROLLED_SPEAKERS.clear()
            for name, emb in data.items():
                arr = np.array(emb)
                if arr.shape == (EMBEDDING_DIM,):
                    ENROLLED_SPEAKERS[name] = arr
                else:
                    print(f"Warning: Skipping {name} due to dimension mismatch ({arr.shape})")
            print(f"Loaded {len(ENROLLED_SPEAKERS)} speakers from registry.")
        except Exception as e:
            print(f"Error loading registry: {e}")
    else:
        print("No registry found. Starting fresh.")

def enroll_speaker(name, embedding_model, duration=5):
    """Records audio, extracts embedding, and saves to ENROLLED_SPEAKERS."""
    print(f"Recording {name} for {duration} seconds. Please speak naturally...")
    recording = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
    sd.wait()
    
    # Pre-process for embedding
    audio_data = recording.T # Shape [1, samples]
    
    if embedding_model:
        try:
            # Use the model directly or via Inference object
            waveform = torch.from_numpy(audio_data).float()
            embedding = embedding_model({"waveform": waveform, "sample_rate": SAMPLE_RATE})
            if hasattr(embedding, "data"): embedding = embedding.data
            if len(embedding.shape) > 1:
                embedding = np.mean(embedding, axis=0)
            embedding = np.squeeze(embedding)
            ENROLLED_SPEAKERS[name] = embedding
            print(f"Enrollment for {name} complete.")
        except Exception as e:
            print(f"Error during embedding extraction: {e}")
            ENROLLED_SPEAKERS[name] = np.random.rand(EMBEDDING_DIM)
    else:
        print("Warning: Embedding model not available. Using random signature for enrollment.")
        ENROLLED_SPEAKERS[name] = np.random.rand(EMBEDDING_DIM)
    
    save_registry()
