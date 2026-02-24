import discord
import discord.ext.voice_recv as voice_recv
import numpy as np
import scipy.signal
import asyncio
import logging
import time
import os
import sys
import threading
import multiprocessing

# Add the tts folder to path so we can import its modules
# Imports
# We rely on 'tts' being a proper package or in path
TTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tts')
if TTS_DIR not in sys.path:
    sys.path.insert(0, TTS_DIR)

# Ensure dependencies are loaded
import tts.transcription_engine
import tts.speaker_manager
import tts.config as tts_config
from tts.transcription_engine import TranscriptionEngine, transcription_queue
from tts.speaker_manager import VoiceSubagent

# Constants
DISCORD_SAMPLE_RATE = 48000
WHISPER_SAMPLE_RATE = 16000
CHANNELS = 2 # Discord sends stereo

# Barge-in constants - IMPROVED SENSITIVITY & RELIABILITY
BARGE_IN_RMS_THRESHOLD = 0.030  # Increased to 0.030 (was 0.025, 0.015) - further reduce false positives
BARGE_IN_CONSECUTIVE_PACKETS = 7  # Increased from 5 (210ms validation vs 100ms) - require longer speech  
BARGE_IN_COOLDOWN = 0.5  # Increased from 0.3 (0.5s between re-triggers) - prevent rapid re-detection
BARGE_IN_TIMEOUT = 2.0  # Force-reset flag if cleanup stuck > 2 seconds

class DiscordAudioSink(voice_recv.AudioSink):
    """
    Receives audio from Discord, resamples it, and routes it to the specific
    VoiceSubagent for that user (identified by user_id).
    Includes barge-in detection: if TARS is playing audio and a user speaks,
    TARS stops playback so the new speech can be captured.
    """
    def __init__(self, bot=None):
        self.bot = bot
        self.user_buffers = {} # Maps user_id -> bytearray
        self.resample_ratio = WHISPER_SAMPLE_RATE / DISCORD_SAMPLE_RATE
        # Barge-in state
        self._barge_in_counter = 0       # Consecutive loud packets
        self._last_barge_in_time = 0.0   # Timestamp of last barge-in
        self._barge_in_in_progress = False  # True while _barge_in_stop() is running
        self._barge_in_stop_start_time = None  # Track when cleanup started for timeout protection
        # Initialize Subagents if not already
        if not hasattr(tts_config, 'subagents'):
            tts_config.subagents = {}
        
        logging.info("🎧 DiscordAudioSink initialized (barge-in enabled).")

    def wants_opus(self):
        return False # We want PCM

    def write(self, user, data):
        """
        Callback from discord-ext-voice-recv.
        process audio packet for a specific user.
        """
        if user is None:
            return

        # 0. Debug Log (Optional)
        # logging.debug(f"📥 [AudioSink] Packet from {user.display_name} (len: {len(data.pcm)})")

        try:
            # 1. Convert PCM bytes to numpy array (Int16)
            # Discord sends 16-bit signed PCM, 48kHz, Stereo
            audio_data = np.frombuffer(data.pcm, dtype=np.int16)
            
            # 2. Convert Stereo to Mono (average channels)
            if CHANNELS == 2:
                audio_data = audio_data.reshape(-1, 2)
                audio_data = audio_data.mean(axis=1) # Shape: (Samples,)
            
            # 3. Resample 48k -> 16k
            # Calculate target number of samples
            target_samples = int(len(audio_data) * (WHISPER_SAMPLE_RATE / DISCORD_SAMPLE_RATE))
            
            # Use scipy.signal.resample (Fourier method) for better quality
            # This avoids aliasing that happens with simple slicing [::3]
            # audio_data is likely float64 from mean(), resample returns float
            audio_16k = scipy.signal.resample(audio_data, target_samples).astype(np.float32)
            
            # Normalize to float32 [-1.0, 1.0] as expected by our VoiceSubagent/Whisper
            audio_16k /= 32768.0

            # 3.5 BARGE-IN DETECTION
            # If TARS is currently playing audio and a user speaks, stop playback
            if self.bot and len(audio_16k) > 0:
                rms = float(np.sqrt(np.mean(audio_16k ** 2)))
                current_time = time.time()
                
                # Check if any guild voice client is playing
                is_tars_speaking = False
                active_vc = None
                for guild in self.bot.guilds:
                    vc = guild.voice_client
                    if vc and vc.is_playing():
                        is_tars_speaking = True
                        active_vc = vc
                        break
                
                # Check if we're stuck in barge-in and force-reset if timeout exceeded
                if (self._barge_in_in_progress and 
                    self._barge_in_stop_start_time and
                    (current_time - self._barge_in_stop_start_time) > BARGE_IN_TIMEOUT):
                    logging.warning(f"🛑 BARGE-IN STUCK >{BARGE_IN_TIMEOUT}s, force-resetting state")
                    self._barge_in_in_progress = False
                    self._barge_in_stop_start_time = None
                
                if is_tars_speaking and rms > BARGE_IN_RMS_THRESHOLD:
                    self._barge_in_counter += 1
                    if (self._barge_in_counter >= BARGE_IN_CONSECUTIVE_PACKETS and
                            (current_time - self._last_barge_in_time) > BARGE_IN_COOLDOWN and
                            not self._barge_in_in_progress):

                        # Atomically claim this barge-in before any other packet can
                        self._barge_in_in_progress = True
                        self._barge_in_stop_start_time = current_time  # Record start time for timeout protection
                        self._barge_in_counter = 0
                        self._last_barge_in_time = current_time

                        logging.info(f"🛑 BARGE-IN detected from {user.display_name} (RMS: {rms:.4f}). Stopping playback.")

                        captured_vc = active_vc
                        bot_ref = self.bot
                        sink_ref = self
                        start_cleanup_time = time.time()
                        
                        # ========== INSTANT STOP (synchronous) ==========
                        # Stop the voice client IMMEDIATELY without waiting
                        if captured_vc and captured_vc.is_playing():
                            captured_vc.stop()
                            logging.debug("🛑 Voice client stopped (instant)")
                        
                        # Drain AudioQueue immediately
                        if (hasattr(bot_ref, 'conversation_manager') and
                                bot_ref.conversation_manager.active_audio_queue):
                            bot_ref.conversation_manager.active_audio_queue.stop()
                            logging.debug("📋 AudioQueue drained (instant)")

                        async def _barge_in_cleanup():
                            """Background cleanup - verify stop and re-attach sink"""
                            try:
                                # Quick verification and additional stops if needed
                                if captured_vc and captured_vc.is_playing():
                                    logging.debug("🛑 Voice client still playing, additional stop")
                                    captured_vc.stop()
                                    await asyncio.sleep(0.02)
                                    
                                    # Final check with short timeout
                                    for _ in range(20):  # 200ms max
                                        if not captured_vc.is_playing():
                                            break
                                        await asyncio.sleep(0.01)

                                # Re-attach the sink
                                if hasattr(bot_ref, 'voice_bridge'):
                                    await bot_ref.voice_bridge.reattach_sink()
                                    
                                cleanup_duration = (time.time() - start_cleanup_time) * 1000
                                logging.info(f"✅ Barge-in cleanup complete ({cleanup_duration:.0f}ms)")
                            finally:
                                # Always clear the flags so the next barge-in can fire
                                sink_ref._barge_in_in_progress = False
                                sink_ref._barge_in_stop_start_time = None

                        # Fire cleanup in background (don't wait for it)
                        asyncio.run_coroutine_threadsafe(_barge_in_cleanup(), self.bot.loop)

                        # Drop trigger packet — don't feed it into the transcription pipeline
                        return
                else:
                    self._barge_in_counter = 0

            # 4. Route to VoiceSubagent
            user_id = str(user.id)
            username = user.display_name

            with tts_config.speaker_lock:
                if user_id not in tts_config.subagents:
                    # Create new subagent for this discord user
                    # We map User ID as the unique key
                    logging.info(f"🆕 New Voice Subagent: {username} ({user_id})")
                    tts_config.subagents[user_id] = VoiceSubagent(username)
                    # Also register in known_id_map just in case
                    tts_config.known_id_map[user_id] = username
                
                agent = tts_config.subagents[user_id]
            
            # 5. Feed audio to agent
            # We calculate a 'timestamp' just based on current time
            # VoiceSubagent expects (audio_chunk, end_time, queue, sa_id)
            # It handles VAD internally.
            
            # VoiceSubagent logic checks: if np.sqrt(np.mean(audio_slice**2)) >= dynamic_threshold
            # So we pass it the chunk.
            
            current_time = time.time()
            if len(audio_16k) > 0:
                logging.debug(f"Packet from {username} ({len(audio_16k)} samples)")
            agent.handle_speech(
                audio_chunk=audio_16k,
                end_time=current_time,
                transcription_queue=transcription_queue,
                sa_id=user_id,
                force_flush=False
            )

        except Exception as e:
            logging.error(f"Audio Sink Error: {e}")

    def cleanup(self):
        logging.info("🧹 Cleaning up DiscordAudioSink")

class VoiceBridge:
    def __init__(self, bot):
        self.bot = bot
        self.sink = DiscordAudioSink(bot=bot)
        self.transcription_engine = None
        self.active_vc = None # Track the current VoiceRecvClient
        self.response_queue = multiprocessing.Queue() # Queue for text results back to main thread
        self._reattach_lock = asyncio.Lock()

    async def reattach_sink(self, attempt=0, max_attempts=3):
        """Safely re-attaches the sink with retry logic and exponential backoff."""
        # Lazily initialize lock to ensure it's on the right loop
        if not hasattr(self, '_reattach_lock'):
            self._reattach_lock = asyncio.Lock()
        
        if not self.active_vc:
            logging.warning("⚠️ Cannot reattach sink: No active voice client tracked in VoiceBridge.")
            return False
        
        async with self._reattach_lock:
            try:
                # Exponential backoff: 0.1s → 0.2s → 0.4s
                delay = 0.1 * (2 ** attempt)
                await asyncio.sleep(delay)
                
                if not hasattr(self.active_vc, 'listen'):
                    logging.error("❌ Voice client missing .listen() method")
                    return False
                
                logging.info(f"🎤 Re-attaching sink (attempt {attempt+1}/{max_attempts})...")
                self.active_vc.listen(self.sink)
                
                # Brief verification
                await asyncio.sleep(0.05)
                
                logging.info("✅ Sink re-attached successfully.")
                return True
                
            except Exception as e:
                logging.error(f"❌ Re-attach failed (attempt {attempt+1}): {e}")
                
                if attempt < max_attempts - 1:
                    logging.info(f"🔄 Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                    return await self.reattach_sink(attempt=attempt+1, max_attempts=max_attempts)
                
                logging.error(f"❌ All {max_attempts} re-attach attempts failed")
                return False

    def start_transcription_engine(self):
        """Starts the separate process for Whisper."""
        import multiprocessing
        
        # We need a new queue for results to come back to the bot
        # existing engine uses 'transcription_queue' for input, and takes a 'result_queue' for output
        
        logging.info("🚀 Starting Transcription Engine Process...")
        self.transcription_engine = TranscriptionEngine()
        self.transcription_engine.start(self.response_queue)
        
        # Start Silence Monitor (Thread)
        self.monitor_thread = threading.Thread(target=self._silence_monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        return self.response_queue

    def _silence_monitor_loop(self):
        """Monitors subagents for inactivity and forces flush."""
        logging.info("🔇 Silence Monitor Started.")
        import time
        while True:
            time.sleep(0.2) # Check 5 times a second
            try:
                 # Check all agents
                with tts_config.speaker_lock:
                    current_time = time.time()
                    for user_id, agent in tts_config.subagents.items():
                        # If agent has data in buffer
                        if len(agent.audio_buffer) > 0:
                            # If no new audio for > 1.2s (silence/pause)
                            if (current_time - agent.last_ts) > 1.2:
                                # Force FLUSH
                                logging.info(f"⏳ Silence detected for {agent.name} after 1.2s. Flushing buffer.")
                                agent.handle_speech(
                                    audio_chunk=np.array([], dtype=np.float32), # Empty chunk just to trigger flush logic
                                    end_time=current_time,
                                    transcription_queue=transcription_queue,
                                    sa_id=user_id,
                                    force_flush=True
                                )
                                # EMERGENCY GUARD: If handle_speech didn't clear the buffer (e.g. too small)
                                # we must clear it here or it will loop forever.
                                if len(agent.audio_buffer) > 0:
                                    # logging.debug(f"🗑️ Clearing leftover small buffer ({len(agent.audio_buffer)} samples) for {agent.name}")
                                    agent.audio_buffer = []
            except Exception as e:
                logging.error(f"SilenceMonitor Error: {e}")

    def stop(self):
        if self.transcription_engine:
            self.transcription_engine.stop()
