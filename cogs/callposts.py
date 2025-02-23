import logging
import os
from datetime import datetime, timedelta, time
import asyncio

import discord
import pytz
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, DBAPIError

from db.database import AsyncSessionLocal, MessageCount, Base

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set the timezone to Eastern Standard Time
EST = pytz.timezone('US/Eastern')

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./kywins.db')
engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def init_db():
    for _ in range(5):  # Try to initialize the database connection up to 5 times
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully.")
            return
        except (SQLAlchemyError, DBAPIError) as e:
            logger.error(f"Error initializing database: {e}")
            await asyncio.sleep(5)
    logger.critical("Failed to initialize database after several attempts.")

class CallPosts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kick_day = 4  # Friday
        self.kick_time = time(23, 30)  # 11:30 PM EST
        self.track_messages.start()

    def cog_unload(self):
        self.track_messages.cancel()

    async def update_attachment_count(self, guild_id: int, member_id: int, attachment_count: int):
        async with AsyncSessionLocal() as db_session:
            try:
                result = await db_session.execute(select(MessageCount).filter_by(guild_id=guild_id, member_id=member_id))
                message_count = result.scalars().first()
                if message_count:
                    message_count.count += attachment_count
                else:
                    message_count = MessageCount(guild_id=guild_id, member_id=member_id, count=attachment_count)
                    db_session.add(message_count)
                await db_session.commit()
                logger.debug(f"Updated attachment count for member {member_id} in guild {guild_id}.")
            except Exception as e:
                logger.error(f"Error updating attachment count: {e}", exc_info=True)

    async def reset_message_counts(self):
        async with AsyncSessionLocal() as db_session:
            try:
                await db_session.execute(MessageCount.__table__.delete())
                await db_session.commit()
                logger.info("Message counts reset successfully.")
            except Exception as e:
                logger.error(f"Error resetting message counts: {e}", exc_info=True)

    async def get_message_counts(self, guild_id: int):
        async with AsyncSessionLocal() as db_session:
            try:
                result = await db_session.execute(select(MessageCount).filter_by(guild_id=guild_id))
                return result.scalars().all()
            except Exception as e:
                logger.error(f"Error retrieving message counts: {e}", exc_info=True)
                return []

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return

        attachment_count = len(message.attachments)
        if attachment_count > 0:
            guild_id = message.guild.id
            member_id = message.author.id

            logger.info(f"Updating attachment count for member {member_id} in guild {guild_id} with {attachment_count} attachments.")
            await self.update_attachment_count(guild_id, member_id, attachment_count)

    @tasks.loop(hours=24)
    async def track_messages(self):
        now = datetime.now(pytz.UTC).astimezone(EST)
        kick_datetime = datetime.combine(now.date(), self.kick_time).replace(tzinfo=EST)
        if now.weekday() == self.kick_day and now >= kick_datetime:
            logger.info("Resetting message counts.")
            await self.reset_message_counts()

    @track_messages.before_loop
    async def before_track_messages(self):
        await self.bot.wait_until_ready()

    async def kick_low_activity_members(self, guild: discord.Guild):
        member_role = discord.utils.get(guild.roles, name="Member")
        if not member_role:
            logger.warning(f"Role 'Member' not found in guild {guild.name}.")
            return

        kicked_members = []
        message_counts = await self.get_message_counts(guild.id)
        for message_count in message_counts:
            if message_count.count < 5:
                member = guild.get_member(message_count.member_id)
                if member and member_role in member.roles:
                    try:
                        await member.kick(reason="Less than 5 attachments in the last 7 days")
                        kicked_members.append(member.display_name)
                    except discord.Forbidden:
                        logger.warning(f"Bot doesn't have permission to kick {member.display_name} in guild {guild.name}. Skipping...")
                    except Exception as e:
                        logger.error(f"Error kicking member {member.display_name}: {e}", exc_info=True)

        if kicked_members:
            kicked_list = "\n".join(kicked_members)
            logger.info(f"Kicked the following members in guild {guild.name} for having less than 5 attachments in the last 7 days:\n{kicked_list}")

    @app_commands.command(name="callposts", description="List attachment counts for users with the Member role for the last 7 days")
    @app_commands.default_permissions(administrator=True)
    async def callposts(self, interaction: discord.Interaction):
        await interaction.response.send_message("Processing attachment counts. This may take a moment...", ephemeral=True)
        try:
            message_counts = await self.get_message_counts(interaction.guild.id)
            if not message_counts:
                await interaction.followup.send("No members found with the 'Member' role.", ephemeral=True)
                return

            sorted_counts = sorted(message_counts, key=lambda item: item.count, reverse=True)
            result = "\n".join([
                f"{interaction.guild.get_member(message_count.member_id).display_name}: {message_count.count} attachments"
                for message_count in sorted_counts if interaction.guild.get_member(message_count.member_id)
            ])

            now = datetime.now(pytz.UTC).astimezone(EST)
            kick_datetime = datetime.combine(now.date(), self.kick_time).replace(tzinfo=EST)
            if now.weekday() > self.kick_day or (now.weekday() == self.kick_day and now >= kick_datetime):
                next_kick_date = now + timedelta(days=(7 - now.weekday() + self.kick_day) % 7)
            else:
                next_kick_date = now + timedelta(days=(self.kick_day - now.weekday()))

            kick_datetime = datetime.combine(next_kick_date.date(), self.kick_time).replace(tzinfo=EST)
            time_left = kick_datetime - now
            days, remainder = divmod(time_left.total_seconds(), 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            result += f"\n\n**Kick day is Friday night at 11:30pm EST.**\nThose who don't have an attachment count of 5 will be kicked. No exceptions."
            result += f"\n**Time left until kick:** {int(days)} days, {int(hours)} hours, {int(minutes)} minutes, and {int(seconds)} seconds."

            if len(result) > 2000:
                result = result[:1997] + "..."

            await interaction.followup.send(f"**Attachment counts from Saturday 5am to Friday 11:30pm EST:**\n{discord.utils.escape_mentions(result)}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in callposts: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while retrieving attachment counts: {e}", ephemeral=True)

    @app_commands.command(name="kicklowposts", description="Kick users with the Member role who have less than 5 attachments in the last 7 days")
    @app_commands.default_permissions(administrator=True)
    async def kicklowposts(self, interaction: discord.Interaction):
        await interaction.response.send_message("Starting kicking process. This may take a moment...", ephemeral=True)
        try:
            await self.kick_low_activity_members(interaction.guild)
            await interaction.followup.send("Kicking process completed.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in kicklowposts: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while kicking members: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await init_db()  # Initialize the database
    await bot.add_cog(CallPosts(bot))
