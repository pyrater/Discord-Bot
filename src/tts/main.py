import os
import traceback
import time
import threading
import numpy as np
import sounddevice as sd
import torch
import scipy.spatial.distance as dist
import collections

# Local Imports
from . import config
from .speaker_manager import VoiceSubagent, load_registry, enroll_speaker, save_registry
from .transcription_engine import TranscriptionEngine, transcription_queue
from .dashboard import start_dashboard, log_transcript

# Domain Imports
from diart import SpeakerDiarization
from diart.sources import MicrophoneAudioSource
from diart.inference import StreamingInference
from pyannote.audio import Inference, Model
from pyannote.audio.core.io import Audio

def run_realtime(pipeline, embedding_model, engine):
    """Main execution loop for real-time diarization and transcription."""
    print("Starting Live Transcription Engine...")
    
    # Device Selection Logic
    mic_device = os.getenv("AUDIO_DEVICE")
    if mic_device is None:
        mic_device = 2 # User preferred ID 2
        print(f"\n[!] Using User-Preferred Device: ID 2")

    try:
        mic = MicrophoneAudioSource(device=int(mic_device) if str(mic_device).isdigit() else mic_device)
    except Exception as e:
        config.audio_logger.error(f"Mic init failed: {e}")
        mic = MicrophoneAudioSource() # Fallback
    
    # RAW STREAM BUFFER HOOK
    class NoiseTracker:
        def __init__(self, window_size=50):
            self.history = collections.deque(maxlen=window_size)
        def update(self, vol): self.history.append(vol)
        def get_threshold(self):
            if not self.history: return config.VAD_THRESHOLD
            # Use a more conservative multiplier (1.2 instead of 1.5) to catch quieter voices
            return max(config.VAD_THRESHOLD, np.mean(self.history) * 1.2)

    noise_tracker = NoiseTracker()

    def fill_buffer(data):
        try:
            audio_chunk = data.ravel()
            volume = np.sqrt(np.mean(audio_chunk**2))
            noise_tracker.update(volume)
            
            with config.buffer_lock:
                config.audio_buffer.extend(audio_chunk.tolist())
                config.TOTAL_SAMPLES_CAPTURED += len(audio_chunk)
            
            # Throttle logging
            if not hasattr(fill_buffer, 'last_print'): fill_buffer.last_print = 0
            if config.TOTAL_SAMPLES_CAPTURED - fill_buffer.last_print >= config.SAMPLE_RATE * 2:
                config.audio_logger.info(f"Mic Active | Vol: {volume:.4f} | Dynamic VAD: {noise_tracker.get_threshold():.5f}")
                fill_buffer.last_print = config.TOTAL_SAMPLES_CAPTURED
        except Exception as e:
            config.audio_logger.error(f"Error in fill_buffer: {e}")

    mic.stream.subscribe(on_next=fill_buffer, on_error=lambda e: print(f"MICROPHONE STREAM ERROR: {e}"))

    def on_diarization_update(update):
        """Callback for diart diarization updates."""
        try:
            prediction, _ = update
            
            with config.buffer_lock:
                samples_now = config.TOTAL_SAMPLES_CAPTURED
                current_audio = np.array(config.audio_buffer, dtype=np.float32)

            buffer_start_time = max(0, (samples_now - len(current_audio)) / config.SAMPLE_RATE)
            active_ids = set()

            for turn, _, speaker_id in prediction.itertracks(yield_label=True):
                active_ids.add(speaker_id)
                
                # Identify speaker if new to this session instance
                if speaker_id not in config.subagents:
                    # Default name
                    name = config.known_id_map.get(speaker_id)
                    if not name:
                        name = f"Unknown_{speaker_id}"
                        
                        # Try to match with embedding if model is available
                        if embedding_model:
                            t_start = int((turn.start - buffer_start_time) * config.SAMPLE_RATE)
                            t_end = int((turn.end - buffer_start_time) * config.SAMPLE_RATE)
                            if 0 <= t_start < t_end <= len(current_audio) and (t_end - t_start) >= 1600:
                                feat = torch.from_numpy(current_audio[t_start:t_end]).float().unsqueeze(0)
                                try:
                                    emb = embedding_model({"waveform": feat, "sample_rate": config.SAMPLE_RATE})
                                    if hasattr(emb, "data"): emb = emb.data
                                    if len(emb.shape) > 1: emb = np.mean(emb, axis=0)
                                    emb = np.squeeze(emb)
                                    
                                    # Match against enrolled
                                    best_score = 0.8
                                    for enrolled_name, enrolled_emb in config.ENROLLED_SPEAKERS.items():
                                        if emb.shape == enrolled_emb.shape:
                                            score = 1 - dist.cosine(emb, enrolled_emb)
                                            if score > best_score:
                                                best_score = score
                                                name = enrolled_name
                                except Exception as e:
                                    config.audio_logger.error(f"Embedding failed: {e}")
                    
                    with config.speaker_lock:
                        config.known_id_map[speaker_id] = name
                        config.subagents[speaker_id] = VoiceSubagent(name)
                        if 'emb' in locals():
                            sa = config.subagents[speaker_id]
                            sa.last_embedding = emb
                            sa.embedding_history.append(emb)

                subagent = config.subagents[speaker_id]
                effective_start = max(turn.start, subagent.last_ts)
                if turn.end > (effective_start + 0.05):
                    start_idx = int((effective_start - buffer_start_time) * config.SAMPLE_RATE)
                    end_idx = int((turn.end - buffer_start_time) * config.SAMPLE_RATE)
                    
                    start_idx = max(0, start_idx)
                    end_idx = min(len(current_audio), end_idx)
                    
                    if start_idx < end_idx:
                        audio_slice = current_audio[start_idx:end_idx]
                        dynamic_threshold = noise_tracker.get_threshold()
                        
                        if np.sqrt(np.mean(audio_slice**2)) >= dynamic_threshold:
                            subagent.handle_speech(audio_slice, turn.end, transcription_queue, speaker_id)
                        subagent.last_ts = turn.end

            # Flush non-active speakers
            current_time = (samples_now / config.SAMPLE_RATE)
            for sid, sa in config.subagents.items():
                if sid not in active_ids:
                    sa.handle_speech(None, current_time, transcription_queue, sid, force_flush=True)

        except Exception as e:
            config.audio_logger.error(f"Diarization Error: {e}\n{traceback.format_exc()}")

    # Command Listener for Renaming
    def listener():
        print("\n[!] Command Listener: Type 'rename [Old] [New]' to re-label a speaker.\n")
        while True:
            try:
                line = input().strip()
                if line.startswith("rename"):
                    parts = line.split()
                    if len(parts) == 3:
                        old, new = parts[1], parts[2]
                        found = False
                        with config.speaker_lock:
                            for sid, name in config.known_id_map.items():
                                if name == old:
                                    config.known_id_map[sid] = new
                                    found = True
                            for sid, sa in config.subagents.items():
                                if sa.name == old:
                                    sa.name = new
                                    if sa.last_embedding is not None:
                                        config.ENROLLED_SPEAKERS[new] = sa.last_embedding
                                        save_registry()
                                    found = True
                            if found:
                                with config.TRANSCRIPTION_LOCK:
                                    for entry in config.TRANSCRIPTION_HISTORY:
                                        if entry['speaker'] == old: entry['speaker'] = new
                        if found: print(f"Success: Renamed {old} to {new}.")
                        else: print(f"Error: {old} not found.")
            except EOFError: break
            except Exception as e: print(f"CLI Error: {e}")

    threading.Thread(target=listener, daemon=True).start()
    
    # Result Bridge: Accumulate text until final flush
    def result_bridge():
        import queue
        from dashboard import log_transcript
        while True:
            try:
                # speaker_name, text, speaker_id, is_final
                name, text, sid, is_final = config.result_queue.get(timeout=1.0)
                
                with config.speaker_lock:
                    if sid in config.subagents:
                        sa = config.subagents[sid]
                        # Append to current utterance buffer
                        if sa.current_utterance:
                            sa.current_utterance += " " + text
                        else:
                            sa.current_utterance = text
                        
                        # Only commit to dashboard if it's the final part of a thought
                        if is_final:
                            log_transcript(name, sa.current_utterance)
                            sa.current_utterance = "" # Reset
            except queue.Empty:
                continue
            except Exception as e:
                config.audio_logger.error(f"Result bridge error: {e}")

    threading.Thread(target=result_bridge, daemon=True).start()
    inference = StreamingInference(pipeline, mic, do_plot=False)
    inference.attach_hooks(on_diarization_update)
    print("Inference loop started. Ctrl+C to quit.")
    try:
        inference()
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    load_registry()
    engine = TranscriptionEngine()
    engine.start(config.result_queue)
    start_dashboard()

    # Load Models
    print("Loading Diarization and Embedding models (HF)...")
    try:
        from diart import SpeakerDiarizationConfig
        sd_config = SpeakerDiarizationConfig(latency=config.DIART_LATENCY, step=0.5, duration=5)
        pipeline = SpeakerDiarization(config=sd_config)
        model = Model.from_pretrained("pyannote/embedding")
        model.audio = Audio(sample_rate=16000, mono="downmix")
        embedding = Inference(model, device=torch.device("cpu"))
    except Exception as e:
        print(f"\n[!] Model Loading Failed: {e}")
        print("Ensure HF_TOKEN is valid and you've accepted gated terms.")
        pipeline = None
        embedding = None

    if pipeline:
        # Enrollment check
        enrolled_lower = [n.lower() for n in config.ENROLLED_SPEAKERS.keys()]
        if "joe" not in enrolled_lower:
            enroll_speaker("Joe", embedding)
        
        run_realtime(pipeline, embedding, engine)
    else:
        print("Fatal: Cannot proceed without diarization pipeline.")