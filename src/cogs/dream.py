import discord
from discord.ext import commands
import sqlite3
import json
import io
import logging
from src.bot_config import settings

class Dream(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def dream(self, ctx):
        """Triggers the Dream Cycle (Memory Consolidation + Art)."""
        status_msg = await ctx.send("🌙 Entering REM sleep... (Consolidating memories & Dreaming)")
        
        try:
            # STEP 1: Fetch last 24 hours of interactions via Memory Engine
            logging.info("🌙 Dream Cycle: Fetching recent interactions...")
            # Increase limit to 1000 to get as much as possible for the context window
            recent_logs = await self.bot.memory_engine.get_recent_interactions_async(limit=1000, hours=24)
            
            if not recent_logs:
                await status_msg.edit(content="💭 No recent memories to dream about. My mind is blank...")
                return
            
            # STEP 2: Analyze and summarize with LLM
            await status_msg.edit(content="🧠 Analyzing patterns in recent memories...")
            
            # Token-aware log construction (up to ~3000 tokens)
            log_entries = []
            total_tokens = 0
            MAX_LOG_TOKENS = 3000
            
            for log in recent_logs:
                entry = f"[{log[3]}] User: {log[0][:150]}... | Bot: {log[1][:150]}... | Mood: {log[2]}"
                tokens = self.bot.brain.count_tokens(entry)
                if total_tokens + tokens > MAX_LOG_TOKENS:
                    break
                log_entries.append(entry)
                total_tokens += tokens
            
            log_text = "\n".join(log_entries)
            
            consolidation_prompt = f"""Analyze these recent conversation logs and extract:
1. Main themes discussed
2. Dominant emotions
3. Recurring topics
4. Overall "vibe" of the day

Logs:
{log_text}

Respond in JSON format:
{{"themes": ["theme1"], "emotions": ["emotion1"], "vibe": "summary", "art_prompt": "art prompt"}}"""
            
            try:
                # Access ai_client from bot
                analysis_response = await self.bot.ai_client.chat.completions.create(
                    model=settings.MODEL_NAME,
                    messages=[
                        {"role": "system", "content": "You are a dream analyst extracting patterns from conversation logs."},
                        {"role": "user", "content": consolidation_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=settings.MAX_GENERATION,
                    timeout=20
                )
                
                analysis_text = analysis_response.choices[0].message.content
                if "```json" in analysis_text:
                    analysis_text = analysis_text.split("```json")[1].split("```")[0].strip()
                elif "```" in analysis_text:
                    analysis_text = analysis_text.split("```")[1].split("```")[0].strip()
                    
                analysis = json.loads(analysis_text)
            except Exception as e:
                logging.error(f"Dream analysis failed: {e}")
                analysis = {
                    "themes": ["chaos", "data"],
                    "emotions": ["curious", "confused"],
                    "vibe": "A day of digital wandering",
                    "art_prompt": "surreal dreamscape, abstract datastream, ethereal colors"
                }
            
            # STEP 3: Generate contextual dream art
            await status_msg.edit(content="🎨 Painting the dream...")
            
            dream_prompt = analysis.get("art_prompt", "surreal dreamscape")
            img = await self.bot.brain.call_comfyui(dream_prompt, None)
            
            # STEP 4: Store dream summary
            dream_summary = f"Dream Summary: {analysis.get('vibe', 'Unknown')}. Themes: {', '.join(analysis.get('themes', []))}. Emotions: {', '.join(analysis.get('emotions', []))}"
            
            self.bot.memory_engine.store_memory(
                user_id="SYSTEM_DREAM",
                username="TARS",
                prompt="Daily Dream Consolidation",
                response=dream_summary,
                guild_id=str(ctx.guild.id) if ctx.guild else "DM",
                channel_id=str(ctx.channel.id),
                emotion="reflective"
            )
            
            # STEP 5: Reply
            embed = discord.Embed(
                title="💤 Dream Cycle Complete",
                description=analysis.get("vibe", "A mysterious dream..."),
                color=0x9B59B6
            )
            embed.add_field(name="🎭 Themes", value=", ".join(analysis.get("themes", ["unknown"])), inline=False)
            embed.add_field(name="💫 Emotions", value=", ".join(analysis.get("emotions", ["neutral"])), inline=False)
            embed.set_footer(text=f"Analyzed {len(log_entries)} interactions from the last 24 hours")
            
            await status_msg.delete()
            await ctx.send(embed=embed)
            
            if img and isinstance(img, bytes):
                logging.info("🎨 Dream Cycle: Sending dream art...")
                await ctx.send(file=discord.File(io.BytesIO(img), filename="dream_cycle.png"))
            else:
                logging.warning(f"🎨 Dream Cycle: Art generation failed: {img}")
                await ctx.send(f"⚠️ Dream art generation failed: {img}")
                
        except Exception as e:
            logging.error(f"Dream cycle error: {e}")
            await ctx.send(f"❌ Woke up screaming: {e}")

async def setup(bot):
    await bot.add_cog(Dream(bot))
