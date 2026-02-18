import discord
from discord.ext import commands
import logging
import io

class ToolBridge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._register_dynamic_commands()

    def _register_dynamic_commands(self):
        """Dynamically creates discord commands from the Brain's tool schema."""
        if not hasattr(self.bot, 'brain'):
            logging.warning("⚠️ ToolBridge: Brain not found on bot. Dynamic command registration skipped.")
            return

        tools = self.bot.brain.get_tools_schema()
        for tool in tools:
            fn = tool['function']
            name = fn['name']
            desc = fn['description']
            params = fn['parameters']['properties']
            
            # Create the command callback
            # We use a factory function to capture the tool name and metadata
            command = self._make_tool_command(name, desc, params)
            
            # Register with the bot
            # Note: We use bot.add_command because we're outside a normal class-based command decorator
            self.bot.add_command(command)
            logging.info(f"🦾 ToolBridge: Registered tool command !{name}")

    def _make_tool_command(self, tool_name, description, params):
        """Factory for creating a Discord command for a specific tool."""
        
        @commands.command(name=tool_name, help=description)
        async def tool_callback(ctx, *, args_str: str = ""):
            if not hasattr(self.bot, 'brain'):
                await ctx.send("🧠 Brain offline.")
                return

            # Construct arguments for the tool
            # Logic: If tool has 1 param, pass the whole string. 
            # If complex (like set_reminder), it might be tricky.
            param_keys = list(params.keys())
            
            tool_args = {}
            if len(param_keys) == 1:
                # Standard tools like search_web(query) or urban_dict(term)
                tool_args[param_keys[0]] = args_str
            elif tool_name == "set_reminder":
                # Special case or parse 'minutes message'
                parts = args_str.split(" ", 1)
                if len(parts) < 2:
                    await ctx.send("❌ Usage: `!set_reminder <minutes> <message>`")
                    return
                try:
                    tool_args = {"minutes": float(parts[0]), "message": parts[1]}
                except ValueError:
                    await ctx.send("❌ Minutes must be a number.")
                    return
            else:
                # Generic fallback for multiple params: just pass the string to the first one?
                if param_keys:
                    tool_args[param_keys[0]] = args_str

            await ctx.send(f"⚙️ **Executing {tool_name}...**")
            
            # Execute
            result = await self.bot.brain.execute_tool(tool_name, tool_args)
            
            # Handle results (images vs text)
            if isinstance(result, str):
                # Check if it looks like a confirm or data
                if len(result) > 1950:
                    result = result[:1950] + "... (truncated)"
                await ctx.send(f"📄 **Tool Response:**\n{result}")
            elif isinstance(result, bytes):
                # Direct image/file result
                file = discord.File(fp=io.BytesIO(result), filename="result.png")
                await ctx.send(file=file)
            elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], bytes):
                # Image result (legacy or multi-image)
                file = discord.File(fp=io.BytesIO(result[0]), filename="result.png")
                await ctx.send(file=file)
            else:
                await ctx.send(f"✅ **Tool Executed.** Result: `{result}`")

        return tool_callback

async def setup(bot):
    await bot.add_cog(ToolBridge(bot))
