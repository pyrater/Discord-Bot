import multiprocessing
import queue
import time
from faster_whisper import WhisperModel
from config import audio_logger, WHISPER_MODEL, COMPUTE_TYPE

# Global transcription queue (Now a Multiprocessing Queue)
transcription_queue = multiprocessing.Queue()

class TranscriptionEngine:
    def __init__(self):
        self.worker_process = None
        self.stop_event = multiprocessing.Event()

    def transcription_worker(self, q, res_q, stop_event):
        """Background worker process that transcribes audio chunks."""
        # Model must be loaded INSIDE the process to avoid memory sharing issues
        audio_logger.info(f"Worker Process: Loading Whisper model ({WHISPER_MODEL})...")
        transcriber = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=COMPUTE_TYPE)
        audio_logger.info("Worker Process: Whisper model loaded. Ready.")
        
        while not stop_event.is_set():
            try:
                # item: (speaker_name, audio_chunk, timestamp, sa_id, is_final)
                try:
                    item = q.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                speaker_name, audio_chunk, ts, sa_id, is_final = item
                audio_logger.info(f"Worker: Processing chunk from {speaker_name} (final={is_final})")
                print(f"Worker: Processing chunk from {speaker_name}")
                
                # Perform actual transcription
                segments, info = transcriber.transcribe(
                    audio_chunk, 
                    beam_size=1, # Speed Optimization: Greedy search
                    vad_filter=True, # Remove silence/noise
                    vad_parameters=dict(min_silence_duration_ms=800),
                    language="en"
                )
                
                for segment in segments:
                    text = segment.text.strip()
                    if text:
                        print(f"\n[TRANSCRIPTION] {speaker_name}: {text}")
                        audio_logger.info(f"TRANSCRIPTION [{speaker_name}]: {text}")
                        # Push back to main process via explicit shared queue
                        res_q.put((speaker_name, text, sa_id, is_final))
                        
            except Exception as e:
                audio_logger.error(f"Error in transcription_worker process: {e}")

    def start(self, res_q):
        self.worker_process = multiprocessing.Process(
            target=self.transcription_worker, 
            args=(transcription_queue, res_q, self.stop_event),
            daemon=True
        )
        self.worker_process.start()
        return self.worker_process

    def stop(self):
        self.stop_event.set()
        if self.worker_process:
            self.worker_process.join()
