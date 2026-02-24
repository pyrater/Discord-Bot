import discord
from discord.ext import commands
import asyncio
import logging
import re
import time
import io
import os
import imageio_ffmpeg
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Union, Tuple
from bot_config import settings
from voice_engine import AudioManager
from memory_engine import MemoryEngine
from brain import CognitiveEngine

class AudioQueue:
    """
    Manages sequential playback of audio sources for a VoiceClient.
    Required for streaming sentence-by-sentence.
    """
    MAX_PLAY_RETRIES = 8  # Max 8 × 150ms = 1.2s before giving up waiting for vc to stop

    def __init__(self, voice_client: discord.VoiceClient):
        self.vc: discord.VoiceClient = voice_client
        self.queue: asyncio.Queue[Tuple[discord.AudioSource, Optional[Callable[[Optional[Exception]], None]]]] = asyncio.Queue()
        self.is_playing: bool = False
        self._stopped: bool = False
        self._play_retries: int = 0
        self.loop = asyncio.get_event_loop()

    async def add(self, source: discord.AudioSource, cleanup: Optional[Callable[[Optional[Exception]], None]] = None) -> None:
        await self.queue.put((source, cleanup))
        if not self.is_playing:
            self.play_next()

    def play_next(self) -> None:
        if self._stopped or self.queue.empty():
            self.is_playing = False
            self._play_retries = 0
            return

        # If vc is still finishing a previous ffmpeg process, defer briefly.
        # Hard cap at MAX_PLAY_RETRIES to avoid an infinite spin if vc never clears.
        if self.vc.is_playing():
            self._play_retries += 1
            if self._play_retries > self.MAX_PLAY_RETRIES:
                logging.warning(f"⚠️ AudioQueue: vc still playing after {self.MAX_PLAY_RETRIES} retries — forcing stop.")
                # Force-stop multiple times to ensure it actually stops
                self.vc.stop()
                import time
                time.sleep(0.01)
                if self.vc.is_playing():
                    self.vc.stop()  # Call stop() again if still playing
                self._play_retries = 0
            else:
                logging.debug(f"⚠️ AudioQueue: vc still playing, deferring play_next (attempt {self._play_retries}/{self.MAX_PLAY_RETRIES}).")
                self.loop.call_soon_threadsafe(
                    lambda: self.loop.call_later(0.15, self.play_next)
                )
            return

        self._play_retries = 0
        self.is_playing = True
        try:
            source, cleanup = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            self.is_playing = False
            return

        def after_play(e: Optional[Exception]) -> None:
            if e: logging.error(f"Playback Error: {e}")
            if cleanup: cleanup(e)
            self.loop.call_soon_threadsafe(self.play_next)

        try:
            if self.vc.is_connected():
                self.vc.play(source, after=after_play)
            else:
                self.is_playing = False
        except discord.errors.ClientException as e:
            logging.error(f"AudioQueue ClientException: {e}")
            if cleanup: cleanup(e)
            self.is_playing = False
            self.play_next()
        except Exception as e:
            logging.error(f"AudioQueue Error: {e}")
            if cleanup: cleanup(e)
            self.is_playing = False
            self.play_next()

    def stop(self):
        """Stop all playback and clear pending items."""
        self._stopped = True
        self._play_retries = 0
        while not self.queue.empty():
            try:
                _, cleanup = self.queue.get_nowait()
                if cleanup: cleanup(None)
            except asyncio.QueueEmpty:
                break
        self.is_playing = False

class ConversationManager:
    def __init__(self, bot: commands.Bot, brain: CognitiveEngine, memory_engine: MemoryEngine, voice_engine: Any, ai_client: Any, emotion_classifier: Any):
        self.bot = bot
        self.brain = brain
        self.memory_engine = memory_engine
        self.voice_engine = voice_engine
        self.ai_client = ai_client
        self.emotion_classifier = emotion_classifier
        
        # State
        self.conversation_history: Dict[str, List[str]] = {}
        self.last_bot_message_time: Dict[str, datetime] = {}
        self.ffmpeg_path: str = imageio_ffmpeg.get_ffmpeg_exe()
        self.active_audio_queue = None  # Current voice AudioQueue (for barge-in access)

    def check_cooldown(self, channel_id: str, seconds: int = 8) -> bool:
        """Returns True if the bot is on cooldown for this channel."""
        if channel_id in self.last_bot_message_time:
            time_since_last = (datetime.now() - self.last_bot_message_time[channel_id]).total_seconds()
            if time_since_last < seconds:
                logging.info(f"🛑 Cooldown active ({time_since_last:.1f}s < {seconds}s). Ignoring.")
                return True
        return False
        
    def get_recent_history(self, channel_id: str, limit: int = 2) -> str:
        """Returns the recent conversation history for context."""
        hist = self.conversation_history.get(str(channel_id), [])
        return "\n".join(hist[-limit:]) if hist else ""

    async def handle_interaction(self, 
                                 user: Union[discord.Member, discord.User], 
                                 user_text: str, 
                                 channel: Union[discord.abc.Messageable, discord.Thread, discord.TextChannel], 
                                 guild: Optional[discord.Guild], 
                                 is_voice: bool = False, 
                                 input_image_bytes: Optional[bytes] = None, 
                                 target_message: Optional[discord.Message] = None) -> None:
        """
        Centralized handler for both text and voice interactions using STREAMING.
        """
        try:
            # 1. Setup Context
            guild_id = str(guild.id) if guild else "DM"
            channel_id = str(channel.id) if hasattr(channel, 'id') else ("v_" + guild_id)
            username = user.display_name
            user_id = str(user.id)
            
            # 2. Short Term History
            if channel_id not in self.conversation_history: self.conversation_history[channel_id] = []
            short_term = self.conversation_history.get(channel_id, [])

            # 3. Reminder Callback
            async def schedule_reminder(minutes: float, note: str) -> None:
                cog = self.bot.get_cog("Reminders")
                if cog:
                    await cog.create_reminder(user_id, channel_id, minutes, note)

            # 4. Stream Results
            full_response_text = ""
            sentence_buffer = ""
            system_prompt = "Streamed"
            interaction_memories = []
            audio_queue = None
            
            if is_voice and guild.voice_client:
                audio_queue = AudioQueue(guild.voice_client)
                self.active_audio_queue = audio_queue  # Expose for barge-in access
                # Play "Computing..." acknowledgment immediately as first queue item
                try:
                    ack_audio = await asyncio.to_thread(self.voice_engine.synthesize, "Computing...")
                    if ack_audio:
                        tmp_path, cleanup_fn = AudioManager.create_async_audio_file(ack_audio.read())
                        await audio_queue.add(discord.FFmpegPCMAudio(tmp_path, executable=self.ffmpeg_path), cleanup_fn)
                except Exception as ack_err:
                    logging.warning(f"⚠️ Voice ack failed (non-critical): {ack_err}")

            async for kind, data in self.brain.process_interaction_stream(
                user_id=user_id,
                username=username,
                user_text=user_text,
                channel_id=channel_id,
                guild_id=guild_id,
                conversation_history=self.conversation_history.get(channel_id, []),
                input_image_bytes=input_image_bytes,
                reminder_callback=schedule_reminder,
                is_voice=is_voice
            ):
                if kind == "meta":
                    system_prompt = data.get("system_prompt", "Streamed")
                    interaction_memories = data.get("memories", [])
                    if "clean_response" in data:
                        # Overwrite the raw accumulation with the purified version
                        full_response_text = data["clean_response"]
                
                elif kind == "text":
                    token = str(data)
                    full_response_text += token
                    sentence_buffer += token
                    
                    # Check for sentence boundary for voice
                    if is_voice and audio_queue:
                         if any(token.endswith(p) for p in [".", "?", "!", "\n"]):
                               to_speak = sentence_buffer.strip()
                               clean_text = re.sub(r'http\S+|```.*?```|`.*?`|[*_>~]', '', to_speak).strip()
                               if clean_text:
                                    # Synthesize and add to queue
                                    stream = await asyncio.to_thread(self.voice_engine.synthesize, clean_text)
                                    if stream:
                                        tmp_path, cleanup_fn = AudioManager.create_async_audio_file(stream.read())
                                        await audio_queue.add(discord.FFmpegPCMAudio(tmp_path, executable=self.ffmpeg_path), cleanup_fn)
                               sentence_buffer = ""

                    # Send to Discord (Regular Text)
                    # Note: For non-voice we'd ideally buffer for rate limits, but for now we rely on the bot's chunking
                    pass

                elif kind == "image":
                    if hasattr(channel, 'send') and isinstance(data, bytes):
                         await channel.send(file=discord.File(io.BytesIO(data), filename=settings.ART_FILENAME))
                
            # 5. Final Flush
            if full_response_text:
                logging.info(f"📤 Final Text: {repr(full_response_text[:50])}...")
                
                # Send Text
                if not is_voice:
                     chunks = [full_response_text[i:i+2000] for i in range(0, len(full_response_text), 2000)]
                     for chunk in chunks:
                        if target_message:
                            await target_message.reply(chunk)
                        elif hasattr(channel, 'send'):
                            await channel.send(chunk)

                # Flush remaining audio
                if sentence_buffer and audio_queue:
                      to_speak = sentence_buffer.strip()
                      clean_text = re.sub(r'http\S+|```.*?```|`.*?`|[*_>~]', '', to_speak).strip()
                      if clean_text:
                           stream = await asyncio.to_thread(self.voice_engine.synthesize, clean_text)
                           if stream:
                               tmp_path, cleanup_fn = AudioManager.create_async_audio_file(stream.read())
                               await audio_queue.add(discord.FFmpegPCMAudio(tmp_path, executable=self.ffmpeg_path), cleanup_fn)

            # 6. Update History
            if full_response_text:
                # Use sanitized version for history/persistence if possible
                clean_response = getattr(self.brain, 'sanitize_response', lambda x: x)(full_response_text)
                short_term.append(f"{username}: {user_text}")
                short_term.append(f"Tars: {clean_response}")
                if len(short_term) > 20: 
                    self.conversation_history[channel_id] = short_term[-20:]
                
                # Run emotion classifier on user text
                emo_results = []
                try:
                    emo_results = self.emotion_classifier(user_text[:512])[0]  # Truncate for model limit
                except Exception as e:
                    logging.warning(f"Emotion classification failed: {e}")
                    
                # Persist
                asyncio.create_task(self._persist_interaction(
                   user_id=user_id,
                   username=username,
                   prompt=user_text,
                   response=clean_response,
                   guild_id=guild_id,
                   channel_id=channel_id,
                   full_prompt=system_prompt,
                   memories=interaction_memories,
                   emo_results=emo_results
                ))
                
                # Recency
                self.last_bot_message_time[channel_id] = datetime.now()

        except asyncio.CancelledError:
            logging.info("🛑 Voice interaction cancelled (barge-in).")
            # Stop the AudioQueue so queued sentences don't keep playing
            if audio_queue:
                audio_queue.stop()
            self.active_audio_queue = None
            return
        except Exception as e:
            logging.error(f"Handle Interaction Error: {e}")
        finally:
            # Always clear the active queue reference when done
            if self.active_audio_queue is audio_queue:
                self.active_audio_queue = None

    async def _persist_interaction(self, user_id, username, prompt, response, guild_id, channel_id, full_prompt, memories, emo_results=None):
        """Persists the interaction to the database and vector store."""
        try:
            # 1. Extract and store facts from THIS response
            # (Ensuring memories retrieved previously are also linked)
            await self.memory_engine.store_interaction(
                user_id=user_id,
                username=username,
                prompt=prompt,
                response=response,
                guild_id=guild_id,
                channel_id=channel_id,
                llm_client=self.ai_client,
                model_name=self.brain.model_name,
                emo_results=emo_results,
                full_prompt=full_prompt,
                memories=memories
            )
            logging.info(f"✅ Interaction persisted for {username}")
        except Exception as e:
            logging.error(f"Persistence Error: {e}")

    async def passive_listen(self, user, user_text, channel, guild):
        """
        Logs a user message to memory without responding.
        Only stores the prompt in ChromaDB (no response to avoid polluting RAG).
        """
        try:
             guild_id = str(guild.id) if guild else "DM"
             channel_id = str(channel.id) if hasattr(channel, 'id') else "DM"
             user_id = str(user.id)
             
             # Store observation in ChromaDB (prompt only, no response)
             self.memory_engine.store_observation(
                user_id=user_id,
                username=user.display_name,
                text=user_text,
                guild_id=guild_id,
                channel_id=channel_id
             )
        except Exception as e:
            logging.error(f"Passive Listen Error: {e}")
