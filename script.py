# STANDARD IMPORTS
import sys
import os
import time
import json
import sqlite3
import logging
import logging.handlers
import asyncio
import base64
import random
import httpx
import io
import re  
import discord
import chromadb
import traceback 
import subprocess

# Voice Dependencies
import discord.ext.voice_recv as voice_recv

# Other Deps
import nacl

# Local Imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, 'deps'))

from voice_bridge import VoiceBridge 
from bot_config import settings
import memory_engine as mem_engine_module
import brain as brain_module
import voice_engine as v_engine

# Initialize Engines
memory_engine = mem_engine_module.MemoryEngine(
    db_path=settings.DB_PATH,
    chroma_path=settings.CHROMA_PATH
)

voice_engine = v_engine

# --- LOGGING SETUP ---
# Suppress noisy RTCP & Crypto logs
class NoCryptoErrorFilter(logging.Filter):
    def filter(self, record):
        return "CryptoError" not in record.getMessage()

logging.getLogger("discord.ext.voice_recv.reader").addFilter(NoCryptoErrorFilter())
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.ERROR)

# Configure Root Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE, mode='a')
    ]
)



# Ensure telemetry is disabled BEFORE chromadb initialization
os.environ['CHROMA_TELEMETRY'] = 'False' 

from discord.ext import commands
from openai import AsyncOpenAI
from datetime import datetime
from dotenv import load_dotenv
from llama_cpp import Llama
from transformers import pipeline
import tiktoken

# --- 1. CONFIG & SYSTEM SETUP ---
from bot_config import settings
# load_dotenv handled in bot_config.py

from functools import lru_cache

encoding = tiktoken.get_encoding("cl100k_base") 

@lru_cache(maxsize=2048)
def count_tokens(text):
    return len(encoding.encode(text))

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s]: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(settings.LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    ]
)

# Constants from Settings
# settings.DISCORD_TOKEN, etc are used directly below.

from memory_engine import MemoryEngine
from brain import CognitiveEngine
from conversation_manager import ConversationManager

# --- 2. INITIALIZE ENGINES ---
# conversation_history & last_bot_message_time moved to ConversationManager
# A. SETUP DISCORD BOT
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True # Needed for user lookup in voice channels
bot = commands.Bot(command_prefix="!", intents=intents)

# B. SETUP AI CLIENT
ai_client = AsyncOpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_TOKEN)

# C. SETUP ENGINES
logging.info("🧠 Loading Memory Engine...")
memory_engine = MemoryEngine()
# EAGER LOAD MEMORY MODEL
memory_engine.warmup()

logging.info("🧠 Loading Cognitive Brain...")
try:
    brain = CognitiveEngine(memory_engine, ai_client, settings.MODEL_NAME, settings.COMFY_URL, local_llm_path=settings.LOCAL_MODEL_PATH)
except NameError:
    logging.error("Brain init failed")
    sys.exit(1)

logging.info("🎭 Loading RoBERTa Emotion Engine onto CPU...")
emotion_classifier = pipeline(
    "text-classification", 
    model="SamLowe/roberta-base-go_emotions", 
    top_k=None, device=-1 
)

# --- VOICE ENGINE SETUP ---
from voice_engine import VoiceEngine
logging.info("🎤 Initializing Voice Engine...")
voice_engine = VoiceEngine()
# EAGER LOAD VOICE MODEL
voice_engine.load()

# --- VOICE BRIDGE SETUP ---
voice_bridge = VoiceBridge(bot)
voice_result_queue = None

# --- CONVERSATION MANAGER ---
logging.info("💬 Initializing Conversation Manager...")
conversation_manager = ConversationManager(
    bot=bot,
    brain=brain,
    memory_engine=memory_engine,
    voice_engine=voice_engine,
    ai_client=ai_client,
    emotion_classifier=emotion_classifier
)

# Construct base path for robust file loading
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# UPDATED: Point to TARS.json
CHAR_FILE = os.path.join(BASE_DIR, "TARS.json")

with open(CHAR_FILE, "r", encoding="utf-8") as f:
    char_data = json.load(f)

# --- 3. HELPER FUNCTIONS ---
# Functions moved to conversation_manager.py

# --- 4. DISCORD SETUP & COMMANDS ---

@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    
    # DEBUG: List Connected Guilds
    if not bot.guilds:
        logging.warning("⚠️ Bot is not connected to ANY guilds! Invite it using the Developer Portal.")
    else:
        logging.info(f"🏰 Connected to {len(bot.guilds)} Guilds:")
        for g in bot.guilds:
            logging.info(f" - {g.name} (ID: {g.id}) | Members: {g.member_count}")
    
    # Attach engines to bot for Cogs to access
    bot.memory_engine = memory_engine
    bot.brain = brain
    bot.voice_bridge = voice_bridge
    bot.ai_client = ai_client
    
    # Start Memory Engine Background Tasks
    await memory_engine.start()
    
    # Load Cogs
    # Only loading Voice as requested (Admin, Dream, Memory disabled)
    initial_extensions = ["cogs.voice"]
    for extension in initial_extensions:
        try:
            await bot.load_extension(extension)
            logging.info(f"🧩 Loaded Extension: {extension}")
        except Exception as e:
            logging.error(f"❌ Failed to load extension {extension}: {e}")

    # Start Voice Bridge Background Task
    global voice_result_queue
    if voice_bridge:
        voice_result_queue = voice_bridge.start_transcription_engine()
        bot.loop.create_task(process_voice_queue())
        logging.info("🗣️ Voice Bridge & Listener Task Started.")

async def process_voice_queue():
    """Background task to read from voice_bridge and trigger bot."""
    logging.info("👂 Voice Listener Validation Loop Running...")
    
    while True:
        if voice_result_queue is None:
            await asyncio.sleep(1)
            continue
            
        try:
            # (speaker_name, text, speaker_id, is_final)
            # Use run_in_executor to avoid blocking event loop with queue.get
            item = await bot.loop.run_in_executor(None, voice_result_queue.get)
            
            speaker_name, text, speaker_id, is_final = item
            
            if not is_final: 
                continue 
                
            text = text.strip()
            if not text: 
                continue

            # logging.info(f"🎤 HEARD [{speaker_name}]: {text}")
            
            # --- TRIGGER LOGIC ---
            # 1. Wake Words (Fast Path - Guaranteed)
            # UPDATED: Wake words for TARS
            wake_words = ["tars", "robot", "case", "computer", "hey tars", "ok tars", "listen", "can you", "yo tars"]
            is_wake = any(w in text.lower() for w in wake_words)
            
            # 2. Contextual Smarts (Slow Path - LLM Gatekeeper)
            should_reply = is_wake
            
            # Pre-lookup context
            found_channel_id = None
            recent_context = ""
            
            # Find which guild/channel the speaker is in
            target_guild = None
            target_channel = None
            target_member = None
            
            for guild in bot.guilds:
                # Naive search by display name (Weakness: duplicates)
                # Better: voice_bridge passes user_ID. We have speaker_id!
                member = guild.get_member(int(speaker_id)) if speaker_id.isdigit() else None
                if member and member.voice and member.voice.channel:
                    target_guild = guild
                    target_channel = member.voice.channel
                    target_member = member
                    found_channel_id = str(target_channel.id)
                    break
            
            if found_channel_id:
                # Get context to help the brain decide
                recent_context = conversation_manager.get_recent_history(found_channel_id, limit=3)
                
                # If not a wake word, ask the Brain's Gatekeeper
                if not should_reply:
                    should_reply = await brain.should_respond(text, False, recent_context)
                    if should_reply:
                        logging.info(f"🧠 Gatekeeper Check: PASSED for '{text}'")
                    else:
                        logging.info(f"🧠 Gatekeeper Check: IGNORED '{text}'")

            if should_reply and target_guild and target_channel and target_member:
                logging.info(f"🤖 Voice Triggered ({'Wake Word' if is_wake else 'Smart Context'}) by {speaker_name}: {text}")
                await conversation_manager.handle_interaction(target_member, text, target_channel, target_guild, is_voice=True)

        except Exception as e:
            logging.error(f"Voice Processor Error: {e}")
            await asyncio.sleep(1)

@bot.event
async def on_message(message):
    if message.author.bot: return

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    content_lower = message.clean_content.lower()
    channel_id = str(message.channel.id)
    now = datetime.now()

    # --- PASSIVE LOGGING ---
    # Log ALL messages to memory (except bot's own)
    await conversation_manager.passive_listen(message.author, message.clean_content, message.channel, message.guild)

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    is_reply = (message.reference and message.reference.resolved and message.reference.resolved.author.id == bot.user.id)
    
    # --- STRICT INTERACTION CHECK ---
    # Only reply to DMs, Mentions, or Replies
    if not (is_dm or is_mentioned or is_reply):
        return 

    # 0. COOLDOWN CHECK
    # Prevent spamming unless directly addressed
    # (Optional if strict mode is on, but good safety)
    if conversation_manager.check_cooldown(channel_id):
        return 

    # 1. BRAIN: SHOULD WE RESPOND?
    # Get recent history for context
    recent_context = conversation_manager.get_recent_history(channel_id, limit=2)
    
    # Even if mentioned, we can still ask the brain "should I respond?" (e.g. to filter nonsense)
    # But usually if mentioned, we MUST respond.
    # Let's force response if mentioned/DM
    should_reply = True 
    # should_reply = await brain.should_respond(message.clean_content, True, recent_history=recent_context)
    
    if not should_reply:
        return

    start_time = time.time()
    async with message.channel.typing():
        try:
            # 2. PROCESS INTERACTION VIA SHARED HANDLER
            
            # Multimodal Input Handling
            input_image_bytes = None
            for att in message.attachments:
                 if any(att.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'webp']):
                     input_image_bytes = await att.read()
                     break
            
            await conversation_manager.handle_interaction(
                message.author, 
                message.clean_content, 
                message.channel, 
                message.guild, 
                is_voice=False, 
                input_image_bytes=input_image_bytes,
                target_message=message
            )

            total_time = time.time() - start_time
            print(f"🏁 TOTAL REQUEST LATENCY: {total_time:.3f}s")
            print("--------------------------------------------------")

        except Exception as e:
            logging.error(f"Logic Error: {e}")

bot.run(settings.DISCORD_TOKEN)