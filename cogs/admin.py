import discord
from discord.ext import commands
import sqlite3
import os
from bot_config import settings

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="tools", description="List Tars's available tools and capabilities.")
    async def list_tools(self, ctx):
        """Show available tools."""
        # Access brain from bot instance
        if not hasattr(self.bot, 'brain'):
            await ctx.send("🧠 Brain not loaded.")
            return

        tools = self.bot.brain.get_tools_schema()
        
        embed = discord.Embed(
            title="🛠️ Tars Toolkit",
            description="I am equipped with the following cognitive modules:",
            color=0x4caf50
        )
        
        for tool in tools:
            fn = tool['function']
            name = fn['name']
            desc = fn['description']
            args = ", ".join([f"`{k}`" for k in fn['parameters']['properties'].keys()])
            embed.add_field(name=f"🦾 {name}", value=f"{desc}\n*Args: {args}*", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="vibe", description="Check your current emotional vibe with Tars.")
    async def vibe(self, ctx):
        conn = sqlite3.connect(settings.DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM emotional_state WHERE user_id = ?", (str(ctx.author.id),)).fetchone()
        conn.close()
        if not row:
            await ctx.send("I don't have a vibe for you yet. Talk to me!")
            return
        emotions = {k: v for k, v in dict(row).items() if k != 'user_id'}
        sorted_emos = sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:5]
        msg = [f"**Tars's Vibe Report for {ctx.author.display_name}:**"]
        for emo, val in sorted_emos:
            bar = "■" * int(val * 10) + "□" * (10 - int(val * 10))
            msg.append(f"`{emo.ljust(14)}` | {bar} | **{val:.2f}**")
        await ctx.send("\n".join(msg))

    @commands.hybrid_command(name="lobotomize", description="Wipe Tars's memory of a user.")
    @commands.has_permissions(administrator=True)
    async def lobotomize(self, ctx, target: discord.Member = None):
        target_user = target if target else ctx.author
        success = await self.bot.memory_engine.wipe_user(target_user.id)
        if success:
            await ctx.send(f"🧠 **LOBOTOMY COMPLETE.** Tars has forgotten everything about {target_user.display_name}.")
        else:
            await ctx.send(f"❌ **LOBOTOMY FAILED.** Check logs.")

async def setup(bot):
    await bot.add_cog(Admin(bot))
