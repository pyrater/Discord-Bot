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
                vc = ctx.voice_client
            else:
                vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
            
            # Wait for connection to stabilize to avoid ClientException: Not connected to voice.
            for _ in range(10): 
                if vc and vc.is_connected():
                    break
                await asyncio.sleep(0.5)

            # Attach the sink
            if hasattr(self.bot, 'voice_bridge') and vc:
                try:
                    vc.listen(self.bot.voice_bridge.sink)
                    # Register with VoiceBridge so reattach_sink() knows which client to use
                    self.bot.voice_bridge.active_vc = vc
                    await ctx.send(f"🎤 Connected to **{channel.name}**. I'm listening...")
                except discord.ClientException as e:
                    logging.error(f"Failed to start listening: {e}")
                    await ctx.send(f"⚠️ Connected to **{channel.name}**, but had trouble starting the ears. Try again?")
            else:
                await ctx.send(f"⚠️ Connected to **{channel.name}**, but VoiceBridge is not attached.")
        else:
            await ctx.send("❌ You need to be in a voice channel first.")

    @commands.command(name="leave", description="Disconnects from the current voice channel.")
    async def leave(self, ctx):
        """Leaves the voice channel."""
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            if hasattr(self.bot, 'voice_bridge'):
                self.bot.voice_bridge.active_vc = None
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
