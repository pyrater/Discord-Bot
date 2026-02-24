import discord
from discord.ext import commands
import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from src.bot_config import settings

class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_tasks = {} # id -> asyncio.Task
        self.bot.loop.create_task(self.load_reminders())

    async def load_reminders(self):
        """Reschedules pending reminders from the database on startup."""
        await self.bot.wait_until_ready()
        logging.info("⏰ Reminders: Loading pending reminders from DB...")
        
        with self.bot.memory_engine._get_connection(use_row_factory=True) as conn:
            now = datetime.now().isoformat()
            cursor = conn.execute("SELECT * FROM reminders WHERE due_time > ?", (now,))
            rows = cursor.fetchall()
            
        for row in rows:
            self.schedule_task(dict(row))
            
        logging.info(f"⏰ Reminders: Rescheduled {len(rows)} reminders.")

    def schedule_task(self, data):
        """Starts a background task for a reminder."""
        reminder_id = data['id']
        due_time = datetime.fromisoformat(data['due_time'])
        
        async def _run():
            delay = (due_time - datetime.now()).total_seconds()
            if delay > 0:
                await asyncio.sleep(delay)
            
            # Send Reminder
            channel = self.bot.get_channel(int(data['channel_id']))
            if channel:
                user_mention = f"<@{data['user_id']}>"
                await channel.send(f"⏰ **REMINDER:** {user_mention} - {data['note']}")
            
            # Cleanup
            self.remove_from_db(reminder_id)
            if reminder_id in self.active_tasks:
                del self.active_tasks[reminder_id]

        task = self.bot.loop.create_task(_run())
        self.active_tasks[reminder_id] = task

    def remove_from_db(self, reminder_id):
        with self.bot.memory_engine._get_connection() as conn:
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()

    async def create_reminder(self, user_id, channel_id, minutes, note):
        """Creates and schedules a new reminder."""
        due_time = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        
        with self.bot.memory_engine._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (user_id, channel_id, due_time, note) VALUES (?, ?, ?, ?)",
                (str(user_id), str(channel_id), due_time, note)
            )
            reminder_id = cursor.lastrowid
            conn.commit()
            
        data = {
            'id': reminder_id,
            'user_id': user_id,
            'channel_id': channel_id,
            'due_time': due_time,
            'note': note
        }
        self.schedule_task(data)
        return reminder_id

    @commands.hybrid_command(name="timers", aliases=["reminders"], description="List your active reminders.")
    async def timers(self, ctx):
        """Lists active reminders for the user."""
        user_id = str(ctx.author.id)
        with self.bot.memory_engine._get_connection(use_row_factory=True) as conn:
            cursor = conn.execute("SELECT * FROM reminders WHERE user_id = ? ORDER BY due_time ASC", (user_id,))
            rows = cursor.fetchall()

        if not rows:
            await ctx.send("⏰ You have no active reminders.")
            return

        embed = discord.Embed(title="⏰ Your Active Reminders", color=0x3498db)
        for row in rows:
            due = datetime.fromisoformat(row['due_time'])
            time_left = due - datetime.now()
            
            if time_left.total_seconds() < 0:
                status = "Due now!"
            else:
                mins = int(time_left.total_seconds() // 60)
                status = f"In {mins}m" if mins > 0 else "In < 1m"

            embed.add_field(
                name=f"ID: {row['id']} | {status}",
                value=f"📝 {row['note']}",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="kill", aliases=["cancel"], description="Remove a reminder by ID.")
    async def kill(self, ctx, reminder_id: int):
        """Cancels a specific reminder."""
        user_id = str(ctx.author.id)
        
        # Check ownership and existence
        with self.bot.memory_engine._get_connection(use_row_factory=True) as conn:
            row = conn.execute("SELECT * FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)).fetchone()
            
        if not row:
            await ctx.send(f"❌ Reminder ID `{reminder_id}` not found or doesn't belong to you.")
            return

        # Cancel task
        if reminder_id in self.active_tasks:
            self.active_tasks[reminder_id].cancel()
            del self.active_tasks[reminder_id]

        # Remove from DB
        self.remove_from_db(reminder_id)
        await ctx.send(f"✅ Reminder `{reminder_id}` cancelled.")

async def setup(bot):
    await bot.add_cog(Reminders(bot))
