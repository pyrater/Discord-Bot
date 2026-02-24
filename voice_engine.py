import os
import sys
import subprocess
import asyncio
import logging
import io
import json

import soundfile as sf
from piper.voice import PiperVoice

class VoiceEngine:
    def __init__(self, model_input_path=None):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.models_dir = "/app/models"
        if not os.path.exists(self.models_dir): os.makedirs(self.models_dir)
        
        # Default Model: TARS V3 (Custom Voice)
        self.model_name = "TARS-v3"
        self.onnx_path = os.path.join(self.models_dir, f"{self.model_name}.onnx")
        self.conf_path = os.path.join(self.models_dir, f"{self.model_name}.onnx.json")
        
        self.voice = None
        
    def _ensure_model_exists(self):
        """Downloads the Piper model if missing."""
        if not os.path.exists(self.onnx_path) or not os.path.exists(self.conf_path):
            logging.info(f"⬇️ Downloading Voice Model: {self.model_name}...")
            try:
                # TARS V3 Model from GitHub
                onnx_url = "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx"
                json_url = "https://github.com/TARS-AI-Community/TARS-AI/raw/refs/heads/V3/src/character/TARS/voice/TARS.onnx.json"
                
                import requests
                # Download ONNX
                logging.info(f"   Downloading .onnx from {onnx_url}...")
                r = requests.get(onnx_url)
                r.raise_for_status()
                with open(self.onnx_path, "wb") as f: f.write(r.content)
                
                # Download JSON Config
                logging.info(f"   Downloading .json from {json_url}...")
                r = requests.get(json_url)
                r.raise_for_status()
                with open(self.conf_path, "wb") as f: f.write(r.content)
                
                logging.info("✅ Voice Model Downloaded.")
            except Exception as e:
                logging.error(f"❌ Failed to download voice model: {e}")

    def load(self):
        """Loads the Piper model into memory."""
        self._ensure_model_exists()
        try:
            self.voice = PiperVoice.load(self.onnx_path, config_path=self.conf_path)
            logging.info(f"🎤 Voice Loaded: {self.model_name}")
        except Exception as e:
            logging.error(f"❌ Voice Load Failed: {e}")

    def synthesize(self, text):
        """
        Synthesizes text to a WAV BytesIO object.
        Returns: BytesIO object containing WAV data, or None.
        """
        if not self.voice: self.load()
        if not self.voice: return None
        
        try:
            # Create a WAV file in memory
            wav_buffer = io.BytesIO()
            with import_wave_module().open(wav_buffer, 'wb') as wav_file:
                # Piper writes directly to a wave file object
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit samples
                wav_file.setframerate(self.voice.config.sample_rate)
                
                # Robust Method Call (Some versions use synthesize_wav, others synthesize)
                if hasattr(self.voice, "synthesize_wav"):
                    self.voice.synthesize_wav(text, wav_file)
                else:
                    self.voice.synthesize(text, wav_file)
            
            # Check buffer size
            wav_buffer.seek(0)
            size = wav_buffer.getbuffer().nbytes
            logging.debug(f"🗣️ Generated Audio Size: {size} bytes")
            
            if size < 100:
                logging.warning("⚠️ Audio buffer suspiciously small!")
            
            return wav_buffer
        except Exception as e:
            logging.error(f"🗣️ Synthesis Error: {e}")
            return None


def import_wave_module():
    import wave
    return wave


import tempfile
import contextlib

class AudioManager:
    """
    Manages temporary audio files with guaranteed cleanup using context managers.
    Prevents disk bloat from crashed/interrupted TTS processes.
    """
    
    @staticmethod
    @contextlib.contextmanager
    def scoped_audio_file(suffix=".wav", dir=None):
        """
        Yields a path to a temporary file. 
        Guarantees deletion when the context exits, even on error.
        """
        fd, path = tempfile.mkstemp(suffix=suffix, dir=dir)
        os.close(fd)
        try:
            logging.debug(f"🔉 Created scoped audio file: {path}")
            yield path
        finally:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logging.debug(f"🗑️ Cleaned up audio file: {path}")
                except Exception as e:
                    logging.error(f"❌ Failed to cleanup audio file {path}: {e}")

    @staticmethod
    def create_async_audio_file(data: bytes, suffix=".wav"):
        """
        Creates a temp file for async usage (e.g. AudioQueue).
        Returns (path, cleanup_callback).
        The caller MUST call cleanup_callback() when done.
        """
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.write(fd, data)
        os.close(fd)
        
        def cleanup(error=None):
            if error: logging.warning(f"⚠️ Audio Cleanup Triggered by Error: {error}")
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logging.debug(f"🗑️ Async Audio Cleanup: {path}")
            except Exception as e:
                logging.error(f"❌ Async Cleanup Failed {path}: {e}")
                
        return path, cleanup
