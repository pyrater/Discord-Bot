import discord
from discord.ext import commands
import logging

class MemoryInspector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="recall", description="Search Tars's memory about you.")
    async def recall(self, ctx, *, query: str = None):
        """
        Retrieves facts and memories.
        Usage: 
        !recall -> Shows your facts and recent context.
        !recall <text> -> Semantic search in your memories.
        """
        # Ensure MemoryEngine is available
        if not hasattr(self.bot, 'memory_engine'):
            await ctx.send("🧠 Memory Engine is offline.")
            return

        engine = self.bot.memory_engine
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id) if ctx.guild else "DM"
        
        await ctx.typing()

        embed = discord.Embed(
            title=f"🧠 Memory Recall: {ctx.author.display_name}",
            color=0x3498db
        )

        # 1. FACTS (Always show top facts)
        try:
            facts = await engine.get_facts(user_id, guild_id)
            if facts:
                embed.add_field(
                    name="🧩 Known Facts", 
                    value="\n".join([f"• {f}" for f in facts[:5]]), 
                    inline=False
                )
            else:
                embed.add_field(name="🧩 Known Facts", value="*No permanent facts extracted yet.*", inline=False)
        except Exception as e:
            logging.error(f"Error fetching facts: {e}")
            embed.add_field(name="🧩 Facts", value="error retrieving facts", inline=False)

        # 2. MEMORIES (Search or Recent)
        results_text = ""
        try:
            if query:
                # Semantic Search
                results = engine.collection.query(
                    query_texts=[query],
                    where={"$and": [{"user_id": user_id}, {"guild_id": guild_id}]},
                    n_results=3
                )
                docs = results.get('documents', [[]])[0]
                metas = results.get('metadatas', [[]])[0]
                
                if docs:
                    for i, doc in enumerate(docs):
                        # doc is the string content
                        doc_preview = (doc[:200] + '..') if len(doc) > 200 else doc
                        results_text += f"**{i+1}.** {doc_preview}\n\n"
                else:
                    results_text = "*No matching memories found.*"
                    
                embed.description = f"🔎 **Search:** \"{query}\""
            else:
                # Recent Context (using get_recent_interactions from DB is better for chronological)
                # But querying vector DB with empty query isn't standard.
                # Let's just pull from get_recent_interactions_async?
                # Wait, that method returns ALL interactions for the bot (for Dream). 
                # We need USER specific interactions.
                # Let's fallback to vector search with a generic "who am i" query or just skip.
                # Actually, let's just query for "recent conversation" or similar.
                
                # Better: Use the 'audit_logs' table directly via a new method or raw SQL?
                # To keep it clean, let's just show Facts for no-query, and maybe a tip.
                embed.description = "Here is what I know about you."
                results_text = "*Use `!recall <query>` to search past conversations.*"

            embed.add_field(name="🗂️ Memory Stream", value=results_text, inline=False)
            
        except Exception as e:
            logging.error(f"Error fetching memories: {e}")
            embed.add_field(name="🗂️ Memory Stream", value="error retrieving memories", inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="forget", description="Wipe all memories Tars has about YOU.")
    async def forget(self, ctx):
        """Standard User Command: Wipes your own memory."""
        user = ctx.author
        
        # Confirmation Dialog (Optional, but good UX. For now, direct action)
        if not hasattr(self.bot, 'memory_engine'):
            await ctx.send("🧠 Memory Engine offline.")
            return

        success = await self.bot.memory_engine.wipe_user(user.id)
        if success:
            await ctx.send(f"🧹 **Memory Wiped.** I have forgotten everything about you, {user.display_name}.")
        else:
            await ctx.send("❌ Error wiping memory.")

async def setup(bot):
    await bot.add_cog(MemoryInspector(bot))
