import logging
from datetime import datetime, timedelta, time

import discord
import pytz
from discord import app_commands
from discord.ext import commands, tasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from db.database import AsyncSessionLocal, MessageCount

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set the timezone to Eastern Standard Time
EST = pytz.timezone('US/Eastern')

class CallPosts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.kick_day = 4  # Friday
        self.kick_time = time(23, 30)  # 11:30 PM EST
        self.track_messages.start()

    def cog_unload(self):
        self.track_messages.cancel()

    async def update_attachment_count(self, db_session: AsyncSession, guild_id: int, member_id: int, attachment_count: int):
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

    async def reset_message_counts(self, db_session: AsyncSession):
        try:
            await db_session.execute(MessageCount.__table__.delete())
            await db_session.commit()
            logger.info("Message counts reset successfully.")
        except Exception as e:
            logger.error(f"Error resetting message counts: {e}", exc_info=True)

    async def get_message_counts(self, db_session: AsyncSession, guild_id: int):
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

            async with AsyncSessionLocal() as db_session:
                await self.update_attachment_count(db_session, guild_id, member_id, attachment_count)

    @tasks.loop(hours=24)
    async def track_messages(self):
        now = datetime.now(pytz.UTC).astimezone(EST)
        kick_datetime = datetime.combine(now.date(), self.kick_time).replace(tzinfo=EST)
        if now.weekday() == self.kick_day and now >= kick_datetime:
            async with AsyncSessionLocal() as db_session:
                await self.reset_message_counts(db_session)

    @track_messages.before_loop
    async def before_track_messages(self):
        await self.bot.wait_until_ready()

    async def kick_low_activity_members(self, db_session: AsyncSession, guild: discord.Guild):
        member_role = discord.utils.get(guild.roles, name="Member")
        if not member_role:
            logger.warning(f"Role 'Member' not found in guild {guild.name}.")
            return

        kicked_members = []
        message_counts = await self.get_message_counts(db_session, guild.id)
        for message_count in message_counts:
            if message_count.count < 5:
                member = guild.get_member(message_count.member_id)
                if member and member_role in member.roles:
                    try:
                        await member.kick(reason="Less than 5 attachments in the last 7 days")
                        kicked_members.append(member.display_name)
                    except discord.Forbidden:
                        logger.warning(f"Bot doesn't have permission to kick {member.display_name} in guild {guild.name}. Skipping...")

        if kicked_members:
            kicked_list = "\n".join(kicked_members)
            logger.info(f"Kicked the following members in guild {guild.name} for having less than 5 attachments in the last 7 days:\n{kicked_list}")

    @app_commands.command(name="callposts", description="List attachment counts for users with the Member role for the last 7 days")
    @app_commands.default_permissions(administrator=True)
    async def callposts(self, interaction: discord.Interaction):
        await interaction.response.send_message("Processing attachment counts. This may take a moment...", ephemeral=True)
        try:
            async with AsyncSessionLocal() as db_session:
                message_counts = await self.get_message_counts(db_session, interaction.guild.id)
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
            async with AsyncSessionLocal() as db_session:
                await self.kick_low_activity_members(db_session, interaction.guild)
            await interaction.followup.send("Kicking process completed.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in kicklowposts: {e}", exc_info=True)
            await interaction.followup.send(f"An error occurred while kicking members: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CallPosts(bot))
    # Removed duplicate cog registration and command registration
