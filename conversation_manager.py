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
    def __init__(self, voice_client: discord.VoiceClient):
        self.vc: discord.VoiceClient = voice_client
        self.queue: asyncio.Queue[Tuple[discord.AudioSource, Optional[Callable[[Optional[Exception]], None]]]] = asyncio.Queue()
        self.is_playing: bool = False
        self.loop = asyncio.get_event_loop()

    async def add(self, source: discord.AudioSource, cleanup: Optional[Callable[[Optional[Exception]], None]] = None) -> None:
        await self.queue.put((source, cleanup))
        if not self.is_playing:
            self.play_next()

    def play_next(self) -> None:
        if self.queue.empty():
            self.is_playing = False
            return
        
        self.is_playing = True
        try:
            source, cleanup = self.queue.get_nowait()
        except asyncio.QueueEmpty:
            self.is_playing = False
            return
        
        def after_play(e: Optional[Exception]) -> None:
            if e: logging.error(f"Playback Error: {e}")
            if cleanup: cleanup(e)
            # Schedule next
            self.loop.call_soon_threadsafe(self.play_next)
            
        try:
            if self.vc.is_connected():
                self.vc.play(source, after=after_play)
            else:
                self.is_playing = False
        except Exception as e:
            logging.error(f"AudioQueue Error: {e}")
            if cleanup: cleanup(e)
            self.play_next()

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
                else:
                    # Fallback to ephemeral if cog fails to load
                    async def _wait_and_send() -> None:
                        await asyncio.sleep(minutes * 60)
                        if channel and hasattr(channel, 'send'):
                             await channel.send(f"⏰ **REMINDER:** {user.mention} - {note}")
                    asyncio.create_task(_wait_and_send())

            # 4. STREAMING BRAIN CALL
            # Initialize AudioQueue if needed
            audio_queue: Optional[AudioQueue] = None
            if (is_voice or (guild and guild.voice_client and guild.voice_client.is_connected())) and guild:
                audio_queue = AudioQueue(guild.voice_client)

            full_response_text = ""
            sentence_buffer = ""
            system_prompt = "Streamed"
            interaction_memories = []
            
            # Consume Generator
            async for kind, data in self.brain.process_interaction_stream(
                user_id=user_id,
                username=username,
                user_text=user_text,
                channel_id=channel_id,
                guild_id=guild_id,
                conversation_history=short_term,
                input_image_bytes=input_image_bytes,
                reminder_callback=schedule_reminder
            ):
                if kind == "meta":
                    system_prompt = data.get("system_prompt", "Streamed")
                    interaction_memories = data.get("memories", [])
                
                elif kind == "text":
                    token = str(data)
                    full_response_text += token
                    sentence_buffer += token
                    
                    # Check for sentence boundary
                    if re.search(r'[.!?\n]\s*$', sentence_buffer):
                        to_speak = sentence_buffer.strip()
                        sentence_buffer = ""
                        
                        if to_speak and audio_queue:
                             logging.info(f"🗣️ Queueing Sentence: {repr(to_speak[:30])}...")
                             clean_text = re.sub(r'http\S+|```.*?```|`.*?`|[*_>~]', '', to_speak).strip()
                             if clean_text:
                                 stream = await asyncio.to_thread(self.voice_engine.synthesize, clean_text)
                                 if stream:
                                     tmp_path, cleanup_fn = AudioManager.create_async_audio_file(stream.read())
                                     await audio_queue.add(discord.FFmpegPCMAudio(tmp_path, executable=self.ffmpeg_path), cleanup_fn)
                
                elif kind == "image":
                    if hasattr(channel, 'send') and isinstance(data, bytes):
                         await channel.send(file=discord.File(io.BytesIO(data), filename="noodle_art.png"))
                
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
                 short_term.append(f"{username}: {user_text}")
                 short_term.append(f"Tars: {full_response_text}")
                 if len(short_term) > 20: 
                     self.conversation_history[channel_id] = short_term[-20:]
                     
                 # Persist
                 asyncio.create_task(self._persist_interaction(
                    user_id=user_id,
                    username=username,
                    prompt=user_text,
                    response=full_response_text,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    full_prompt=system_prompt,
                    memories=interaction_memories 
                 ))
                 
                 # Recency
                 self.last_bot_message_time[channel_id] = datetime.now()

        except Exception as e:
            logging.error(f"Handle Interaction Error: {e}")

    async def passive_listen(self, user, user_text, channel, guild):
        """
        Logs a user message to memory without responding.
        """
        try:
             guild_id = str(guild.id) if guild else "DM"
             channel_id = str(channel.id) if hasattr(channel, 'id') else "DM"
             user_id = str(user.id)
             
             # Store in ChromaDB as an 'observation'
             # Run in executor to avoid blocking main loop with DB writes
             loop = asyncio.get_event_loop()
             await loop.run_in_executor(
                 None, 
                 lambda: self.memory_engine.store_observation(user_id, user.display_name, user_text, guild_id, channel_id)
             )

             # Queue fact extraction for observations too
             await self.memory_engine.queue_fact_extraction(
                 user_id, 
                 user.display_name, 
                 user_text, 
                 self.ai_client, 
                 settings.MODEL_NAME,
                 guild_id
             )

             guild_name = guild.name if guild else "DM"
             logging.info(f"💾 [{guild_name}] {user.display_name} (Observed): {user_text}")
             
        except Exception as e:
            logging.error(f"Passive Listen Error: {e}")

    async def _persist_interaction(self, user_id: str, username: str, prompt: str, response: str, guild_id: str, channel_id: str, full_prompt: str = "", memories: Union[List[str], str] = "") -> None:
        """
        Saves the interaction to the database and ChromaDB with location metadata.
        """
        try:
            logging.info(f"💾 Background task started for {username}")
            
            primary_emo = "neutral"
            emo_results = []
            try:
                 loop = asyncio.get_event_loop()
                 # Use self.emotion_classifier
                 if self.emotion_classifier:
                    emo_results = await loop.run_in_executor(None, lambda: self.emotion_classifier(response)[0])
                    top_score = 0
                    for res in emo_results:
                        if res['score'] > top_score:
                            primary_emo, top_score = res['label'], res['score']
            except Exception: pass

            async def save_sqlite() -> None:
                success = await self.memory_engine.log_interaction(
                    user_id=str(user_id),
                    prompt=prompt,
                    response=response,
                    mood=primary_emo,
                    full_prompt=full_prompt,
                    memories=memories,
                    emo_results=emo_results
                )
                if success:
                    logging.info(f"✅ SQLite saved for {username}")

            async def save_chroma() -> None:
                try:
                    self.memory_engine.store_memory(
                        user_id=str(user_id),
                        username=username,
                        prompt=prompt,
                        response=response,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        emotion=primary_emo
                    )
                    
                    # Check for facts (Background Queue)
                    await self.memory_engine.queue_fact_extraction(
                        str(user_id), 
                        username,
                        prompt, 
                        self.ai_client, 
                        settings.MODEL_NAME,
                        guild_id
                    )
                    
                    logging.info(f"✅ ChromaDB and Fact Extraction queued for {username}")
                except Exception as e:
                    logging.error(f"background_tasks_chroma Error: {e}")

            await asyncio.gather(save_sqlite(), save_chroma())
            logging.info(f"✅ Background tasks completed for {username}")
        except Exception as e:
            logging.error(f"❌ Background Task Error: {e}")
