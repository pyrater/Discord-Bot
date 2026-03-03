import discord
from discord.ext import commands
import sqlite3
import os
import asyncio
import logging
from src.bot_config import settings

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help", description="Show this message.")
    async def help_command(self, ctx, command_name: str = None):
        """Custom Help Command."""
        if command_name:
            # Detailed help for a specific command
            cmd = self.bot.get_command(command_name)
            if not cmd:
                await ctx.send(f"❓ Command `{command_name}` not found.")
                return
            
            embed = discord.Embed(title=f"📖 Help: !{cmd.name}", color=0x2196f3)
            embed.add_field(name="Description", value=cmd.help or cmd.description or "No description.", inline=False)
            if cmd.aliases:
                embed.add_field(name="Aliases", value=", ".join([f"`!{a}`" for a in cmd.aliases]), inline=True)
            
            sig = f"!{cmd.name} {cmd.signature}" if cmd.signature else f"!{cmd.name}"
            embed.add_field(name="Usage", value=f"`{sig}`", inline=True)
            await ctx.send(embed=embed)
            return

        # Overview help
        embed = discord.Embed(
            title="🤖 Tars Central Command",
            description="Use `!help <command>` for detailed info on a specific module.",
            color=0x2196f3
        )
        
        # Categorization
        categories = {
            "🛠️ Core": ["vibe", "reset", "nuke", "ingest", "ingest_remove", "cmd", "log"],
            "⏰ Reminders": ["timers", "kill"],
            "🎤 Voice": ["join", "leave"],
            "🦾 AI Tools": ["tools", "recall"] # recall is in memory_cog but feels like a tool
        }
        
        # Dynamic tools from tools_cog (if loaded)
        dynamic_tools = []
        if hasattr(self.bot, 'brain'):
            tools = self.bot.brain.get_tools_schema()
            dynamic_tools = [t['function']['name'] for t in tools]
        
        for cat_name, cmd_names in categories.items():
            valid_cmds = []
            for name in cmd_names:
                cmd = self.bot.get_command(name)
                if cmd:
                    valid_cmds.append(f"`!{cmd.name}`")
            
            if valid_cmds:
                embed.add_field(name=cat_name, value=" ".join(valid_cmds), inline=False)

        if dynamic_tools:
            # Only show first 10 or so to avoid clutter, or just a summary
            tool_str = " ".join([f"`!{t}`" for t in dynamic_tools[:12]])
            if len(dynamic_tools) > 12:
                tool_str += f" ... (+{len(dynamic_tools)-12} more)"
            embed.add_field(name="🧠 Direct Tool Access", value=tool_str, inline=False)

        embed.set_footer(text="Tars v2.4 | System Status: ONLINE")
        await ctx.send(embed=embed)

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

    def is_admin(self, ctx):
        """Checks if the user is the configured admin."""
        if not settings.ADMIN_USER:
            return False # No admin configured -> No access
        # Check username (handle) or ID if you want to support IDs
        return ctx.author.name == settings.ADMIN_USER

    @commands.hybrid_command(name="reset", description="Clear the bot's short-term memory of this channel.")
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        """Clears conversation history (Admin Only)."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return
            
        # Access ConversationManager
        # It's not directly on bot, but likely bot.conversation_manager if properly attached...
        # Wait, in script.py: conversation_manager is NOT attached to bot! 
        # But 'bot.brain' IS attached.
        
        # We need to reach conversation_manager. 
        # In script.py, conversation_manager handles interactions but isn't explicitly attached to 'bot' as a property 
        # in the same way 'bot.brain' is?
        # Let's check script.py lines 182-187... 
        # It assumes we can't access it easily unless we attach it.
        # But wait, cogs usually need access.
        
        # Let's assume we can attach it in script.py OR just wipe it from here if we can find it.
        # Actually, conversation_history is in ConversationManager.
        
        # I need to update script.py to attach conversation_manager to bot before I can use it here.
        # For now, I'll mark this as TODO or try to implement if possible.
        
        # RE-READING script.py...
        # It doesn't seem to attach conversation_manager to bot.
        # "bot.memory_engine = memory_engine", "bot.brain = brain".
        
        # I will handle the attach in script.py in a separate step. 
        # For now I will code the command assuming `bot.conversation_manager` exists.
        
        if hasattr(self.bot, 'conversation_manager'):
            channel_id = str(ctx.channel.id)
            if channel_id in self.bot.conversation_manager.conversation_history:
                del self.bot.conversation_manager.conversation_history[channel_id]
                await ctx.send("🧹 **Short-term memory cleared.**")
            else:
                await ctx.send("🧹 Memory was already empty.")
        else:
            await ctx.send("❌ Error: Conversation Manager not accessible.")

    @commands.hybrid_command(name="nuke", description="⚠️ GLOBAL RESET: Wipes ALL memory of EVERYTHING. (Admin Only)")
    @commands.has_permissions(administrator=True)
    async def nuke(self, ctx):
        """
        !nuke -> Wipes the ENTIRE database and vector store.
        """
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return
            
        if hasattr(self.bot, 'memory_engine'):
            # Double confirmation would be nice, but user asked for "nuke" 
            await ctx.send("☢️ **INITIATING GLOBAL WIPE...** Stand by.")
            
            success = await self.bot.memory_engine.wipe_all()
            if success:
                await ctx.send(f"💥 **NUKE COMPLETE.** Tars has been reset to factory settings (memory-wise).")
            else:
                await ctx.send(f"❌ **NUKE FAILED.** Check logs.")
        else:
             await ctx.send("🧠 Memory Engine offline.")
    
    @commands.hybrid_command(name="restart", description="Restarts the bot (Admin Only).")
    @commands.has_permissions(administrator=True)
    async def restart(self, ctx):
        """Kills the bot process, supervisor loop will restart it."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return
            
        await ctx.send("🔄 **Restarting TARS service...** See you in a few seconds.")
        # Note: Supervisor loop in boot.sh will restart the process
        # os._exit ignores exception handlers in the event loop and forcefully terminates
        os._exit(0)

    @commands.hybrid_command(name="log", description="Wipes all .log files in the data directory. (Admin Only)")
    @commands.has_permissions(administrator=True)
    async def log_cleanup(self, ctx):
        """Deletes or clears all .log files in the data folder."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return
            
        import glob
        log_pattern = os.path.join(settings.DATA_DIR, "*.log")
        files = glob.glob(log_pattern)
        
        if not files:
            await ctx.send("📂 No log files found to clean.")
            return

        deleted = []
        cleared = []
        errors = []

        for f in files:
            try:
                # If it's the active log, we just truncate it
                if os.path.abspath(f) == os.path.abspath(settings.LOG_FILE):
                    with open(f, 'w') as log_file:
                        log_file.truncate(0)
                    cleared.append(os.path.basename(f))
                else:
                    os.remove(f)
                    deleted.append(os.path.basename(f))
            except Exception as e:
                errors.append(f"{os.path.basename(f)}: {str(e)}")

        report = "🧹 **Log Cleanup Report:**\n"
        if deleted: report += f"✅ Deleted: {', '.join(deleted)}\n"
        if cleared: report += f"📝 Cleared (Active): {', '.join(cleared)}\n"
        if errors: report += f"❌ Errors: {', '.join(errors)}"
        
        await ctx.send(report)
    
    @commands.hybrid_command(name="ingest_remove", description="Selectively clear ingested data: !ingest_remove [code|knowledge|all]. (Admin Only)")
    @commands.has_permissions(administrator=True)
    async def ingest_remove(self, ctx, target: str = "all"):
        """Clears specific types of ingested data from the knowledge base."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return
            
        target = target.lower()
        if target not in ["code", "knowledge", "all"]:
            await ctx.send("❓ Invalid target. Use `!ingest_remove code`, `!ingest_remove knowledge`, or `!ingest_remove all`.")
            return

        await ctx.send(f"🧹 **Clearing {target.capitalize()} Ingested Data...** stand by.")
        
        if hasattr(self.bot, 'memory_engine'):
            success = self.bot.memory_engine.wipe_knowledge(kb_type=target)
            if success:
                await ctx.send(f"✅ **Wipe Complete.** {target.capitalize()} data has been removed from the knowledge base.")
            else:
                await ctx.send(f"❌ **Wipe Failed.** Please check the system logs.")
        else:
            await ctx.send("🧠 Memory Engine offline.")

    @commands.hybrid_command(name="ingest", description="Run ingestion: !ingest [code|knowledge|all] [github_url]. (Admin Only)")
    @commands.has_permissions(administrator=True)
    async def ingest(self, ctx, target: str = "knowledge", url: str = None):
        """Manually trigger ingestion (code, knowledge, or all). Optionally pass a GitHub URL for code ingestion."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return

        target = target.lower()
        if target not in ["code", "knowledge", "all"]:
            await ctx.send("❓ Invalid target. Use `!ingest code [github_url]`, `!ingest knowledge`, or `!ingest all`.")
            return

        status_msg = await ctx.send(f"📥 **Starting {target.capitalize()} Ingestion...** This may take a moment.")
        asyncio.create_task(self._run_ingest(status_msg, target, url))

    async def _run_ingest(self, status_msg, target, url):
        """Background task: runs ingestion and edits the status message when done."""
        from src.ingest_knowledge import ingest as ingest_knowledge
        from src.ingest_codebase import ingest_github, DEFAULT_GITHUB_URL

        try:
            if target in ["knowledge", "all"]:
                await ingest_knowledge()
            if target in ["code", "all"]:
                await ingest_github(url or DEFAULT_GITHUB_URL)

            await status_msg.edit(content=f"✅ **{target.capitalize()} Ingestion Complete.**")
        except Exception as e:
            logging.error(f"Ingest task failed: {e}")
            await status_msg.edit(content=f"❌ **Ingestion failed:** {e}")

    @commands.hybrid_command(name="cmd", description="List EVERYTHING Tars can do. (Admin Only)")
    @commands.has_permissions(administrator=True)
    async def cmd(self, ctx):
        """Comprehensive list of commands and tools."""
        if not self.is_admin(ctx):
            await ctx.send(f"🚫 Access Denied. You are not {settings.ADMIN_USER}.")
            return

        embed = discord.Embed(
            title="📜 Tars Full Capability Report",
            description="Comprehensive list of all registered commands and cognitive tools.",
            color=0x9c27b0
        )
        
        # 1. Grouped Commands
        categories = {
            "🔴 ADMIN (Priority)": ["nuke", "ingest", "ingest_remove", "cmd", "vibe", "reset", "forget", "log"],
            "🎤 VOICE": ["join", "leave"],
            "⏰ REMINDERS": ["timers", "kill"],
            "🧠 AI COGNITIVE TOOLS": [] # Filled dynamically
        }

        # Handle commands first
        for cat_name, cmd_names in categories.items():
            if cat_name == "🧠 AI COGNITIVE TOOLS": continue
            
            valid_cmds = []
            for name in cmd_names:
                cmd = self.bot.get_command(name)
                if cmd:
                    desc = cmd.description or cmd.help or "*No description.*"
                    if len(desc) > 80: desc = desc[:77] + "..."
                    valid_cmds.append(f"!{cmd.name.ljust(10)} | {desc}")
            
            if valid_cmds:
                chunk = "\n".join(valid_cmds)
                embed.add_field(name=cat_name, value=f"```\n{chunk}\n```", inline=False)
        
        # Handle AI Tools separately for dynamic discovery
        if hasattr(self.bot, 'brain'):
            tools = sorted(self.bot.brain.get_tools_schema(), key=lambda x: x['function']['name'])
            tool_info = []
            for t in tools:
                name = t['function']['name']
                desc = t['function']['description']
                if len(desc) > 80: desc = desc[:77] + "..."
                tool_info.append(f"🦾 !{name.ljust(15)} | {desc}")
            
            if tool_info:
                chunk = "\n".join(tool_info)
                embed.add_field(name="🧠 AI COGNITIVE TOOLS", value=f"```\n{chunk}\n```", inline=False)
            
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
