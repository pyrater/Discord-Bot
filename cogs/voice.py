import discord
from discord.ext import commands
import discord.ext.voice_recv as voice_recv
import logging
import asyncio

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="join", description="Joins your current voice channel so I can listen and speak.")
    async def join(self, ctx):
        """Joins the user's voice channel."""
        if not ctx.guild:
            await ctx.send("❌ Voice commands only work in servers, not DMs.")
            return

        if ctx.author.voice:
            channel = ctx.author.voice.channel
            # USE VoiceRecvClient to enable listening
            if ctx.voice_client:
                await ctx.voice_client.move_to(channel)
            else:
                await channel.connect(cls=voice_recv.VoiceRecvClient)
            
            # Attach the sink
            # Ensure bot.voice_bridge is set in main script
            if hasattr(self.bot, 'voice_bridge'):
                # Store reference for robust re-attachment
                self.bot.voice_bridge.active_vc = ctx.voice_client
                ctx.voice_client.listen(self.bot.voice_bridge.sink)
                await ctx.send(f"🎤 Connected to **{channel.name}**. I'm listening...")
            else:
                await ctx.send(f"⚠️ Connected to **{channel.name}**, but VoiceBridge is not attached. I can't hear you.")
                logging.error("VoiceBridge not attached to bot instance.")
        else:
            await ctx.send("❌ You need to be in a voice channel first.")

    @commands.command(name="leave", description="Disconnects from the current voice channel.")
    async def leave(self, ctx):
        """Leaves the voice channel."""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("👋 Disconnected.")
        else:
            await ctx.send("❌ I'm not in a voice channel.")

    # Removed summon and voice_debug commands as requested.


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Log voice state changes for debugging."""
        if member.bot: return
        
        if before.channel != after.channel:
            if after.channel:
                logging.info(f"🎤 [Voice Monitor] {member.display_name} joined {after.channel.name}")
            else:
                logging.info(f"🎤 [Voice Monitor] {member.display_name} left voice.")

async def setup(bot):
    await bot.add_cog(Voice(bot))
