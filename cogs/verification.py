import logging
import os
import datetime
import asyncio
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
import pytz

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the guild ID and other settings from the environment variables
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
MUST_VERIFY_ROLE_NAME = os.getenv("MUST_VERIFY_ROLE_NAME", "MUST VERIFY")
MEMBER_ROLE_NAME = os.getenv("MEMBER_ROLE_NAME", "Member")
ADMIN_ROLE_NAME = os.getenv("ADMIN_ROLE_NAME", "Admin")
MODERATOR_ROLE_NAME = os.getenv("MODERATOR_ROLE_NAME", "Moderator")
VERIFICATION_PERIOD_HOURS = int(os.getenv("VERIFICATION_PERIOD_HOURS", "24"))
POST_ACTIVITY_PERIOD_HOURS = int(os.getenv("POST_ACTIVITY_PERIOD_HOURS", "24"))

# Set the timezone to Eastern Standard Time
EST = pytz.timezone('US/Eastern')

class Verification(commands.Cog):
    """
    A cog for verifying users by assigning and removing roles.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tree = bot.tree
        self.must_verify_role: Optional[discord.Role] = None
        self.member_role: Optional[discord.Role] = None
        self.admin_role: Optional[discord.Role] = None
        self.moderator_role: Optional[discord.Role] = None
        self.unverified_users: Dict[int, datetime.datetime] = {}  # To track users and their role assignment time
        self.recently_verified_users: Dict[int, datetime.datetime] = {}  # To track the verification time

        self.bot.loop.create_task(self.initialize_roles())
        self.check_unverified_users.start()
        self.check_verified_users_activity.start()

    async def initialize_roles(self):
        """
        Initialize the roles in the guild.
        Retries if initialization fails.
        """
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            logger.critical(f"Guild with ID {GUILD_ID} not found.")
            return

        if not self._has_manage_roles_permission(guild.me) or not self._has_kick_permission(guild.me):
            logger.critical("Bot lacks the necessary permissions to manage roles or kick members.")
            return

        for _ in range(3):
            try:
                await self._fetch_or_create_roles(guild)
                break  # Exit the loop if initialization succeeds
            except Exception as e:
                logger.error(f"Error initializing roles: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

    async def _fetch_or_create_roles(self, guild: discord.Guild):
        """
        Fetches existing roles or creates them if they do not exist.
        """
        logger.debug(f"Guild found: {guild.name} (ID: {guild.id})")

        self.must_verify_role = await self._get_or_create_role(guild, MUST_VERIFY_ROLE_NAME)
        self.member_role = await self._get_or_create_role(guild, MEMBER_ROLE_NAME)
        self.admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
        if not self.admin_role:
            logger.error(f"'{ADMIN_ROLE_NAME}' role not found.")
        self.moderator_role = discord.utils.get(guild.roles, name=MODERATOR_ROLE_NAME)
        if not self.moderator_role:
            logger.error(f"'{MODERATOR_ROLE_NAME}' role not found.")

    async def _get_or_create_role(self, guild: discord.Guild, role_name: str) -> discord.Role:
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            role = await guild.create_role(
                name=role_name,
                reason="Auto-created by bot",
                permissions=discord.Permissions(permissions=0)  # Customize permissions if needed
            )
            logger.info(f"Created '{role_name}' role: {role.name} (ID: {role.id})")
        else:
            logger.debug(f"'{role_name}' role found: {role.name} (ID: {role.id})")
        return role

    @staticmethod
    def is_admin_or_moderator():
        """
        Custom check to verify if the user has Admin or Moderator role.
        """
        async def predicate(interaction: discord.Interaction) -> bool:
            if not interaction.guild:
                return False
            user_roles = [role.name for role in interaction.user.roles]
            return ADMIN_ROLE_NAME in user_roles or MODERATOR_ROLE_NAME in user_roles

        return app_commands.check(predicate)

    @app_commands.command(name="verify_user", description="Verify a user to give them the Member role.")
    @app_commands.default_permissions()
    @app_commands.describe(member="The member to verify")
    @is_admin_or_moderator()
    async def verify_user(self, interaction: discord.Interaction, member: discord.Member):
        """
        Command to verify the user and assign the Member role.
        """
        await interaction.response.defer(ephemeral=True)  # Acknowledge the interaction immediately

        if not self.must_verify_role or not self.member_role:
            await interaction.followup.send(
                content="Roles are not set up correctly. Please contact an admin.",
                ephemeral=True
            )
            logger.critical("Roles are not initialized.")
            return

        if self.must_verify_role in member.roles:
            try:
                await member.remove_roles(self.must_verify_role)
                await member.add_roles(self.member_role)
                await interaction.followup.send(
                    content=f"{member.mention} has been verified and moved to the Member role!",
                    ephemeral=True
                )
                logger.info(f"User {member} has been verified by {interaction.user}.")
                self.unverified_users.pop(member.id, None)  # Remove user from tracking
                self.recently_verified_users[member.id] = datetime.datetime.now(EST)  # Track verification time in EST
            except discord.Forbidden:
                await interaction.followup.send(
                    content="Bot does not have permission to manage roles. Please contact an admin.",
                    ephemeral=True
                )
                logger.error(f"Bot does not have permission to manage roles for {member}.")
            except Exception as e:
                await interaction.followup.send(
                    content="An error occurred during verification. Please try again later.",
                    ephemeral=True
                )
                logger.error(f"Error in verify command: {e}", exc_info=True)
        else:
            await interaction.followup.send(
                content=f"{member.mention} does not have the MUST VERIFY role.",
                ephemeral=True
            )
            logger.warning(f"User {member} attempted to verify without the '{MUST_VERIFY_ROLE_NAME}' role.")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event listener that triggers when the bot is ready.
        """
        await self.initialize_roles()
        logger.info(f"Bot is ready. Logged in as {self.bot.user}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """
        Event listener that triggers when a member joins the guild.
        Assigns the 'MUST VERIFY' role to the new member and tracks the time.
        """
        if not self.must_verify_role:
            logger.critical(f"'{MUST_VERIFY_ROLE_NAME}' role is not initialized.")
            return

        if not self._has_manage_roles_permission(member.guild.me):
            logger.critical("Bot lacks the necessary permissions to manage roles.")
            return

        try:
            await member.add_roles(self.must_verify_role)
            self.unverified_users[member.id] = datetime.datetime.now(EST)  # Track join time in EST
            logger.info(f"Assigned \"{MUST_VERIFY_ROLE_NAME}\" role to {member.name}")
        except discord.Forbidden:
            logger.error(f"Bot does not have permission to assign roles to {member.name}.")
        except Exception as e:
            logger.error(f"Error in on_member_join event: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Event listener that triggers when a message is sent in the guild.
        Updates the last post time for verified users.
        """
        if message.guild and self.member_role in message.author.roles:
            self.recently_verified_users.pop(message.author.id, None)  # Remove user from recent verification tracking
            logger.info(f"User {message.author.name} posted a message, removed from recent verification tracking.")

    @tasks.loop(hours=24)
    async def check_unverified_users(self):
        """
        Background task that checks unverified users every 24 hours and kicks them if necessary.
        """
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            logger.critical(f"Guild with ID {GUILD_ID} not found.")
            return

        now = datetime.datetime.now(EST)
        to_kick = []

        for user_id, join_time in list(self.unverified_users.items()):
            member = guild.get_member(user_id)
            if not member:
                self.unverified_users.pop(user_id, None)  # Clean up if member is not found
                continue
            # Check if the member has been unverified for more than the allowed period
            if (now - join_time).total_seconds() > VERIFICATION_PERIOD_HOURS * 3600:
                to_kick.append(member)

        if not self._has_kick_permission(guild.me):
            logger.critical("Bot lacks the necessary permissions to kick members.")
            return

        for member in to_kick:
            try:
                await member.kick(reason="Failed to verify within the allowed period.")
                logger.info(f"Kicked {member.name} for not verifying within {VERIFICATION_PERIOD_HOURS} hours.")
                del self.unverified_users[member.id]
            except discord.Forbidden:
                logger.error(f"Bot does not have permission to kick {member.name}.")
            except Exception as e:
                logger.error(f"Error kicking user {member.name}: {e}", exc_info=True)

    @tasks.loop(hours=1)
    async def check_verified_users_activity(self):
        """
        Background task that checks verified users' activity every hour.
        """
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            logger.critical(f"Guild with ID {GUILD_ID} not found.")
            return

        now = datetime.datetime.now(EST)
        to_reverify = []

        for user_id, verify_time in list(self.recently_verified_users.items()):
            member = guild.get_member(user_id)
            if not member:
                self.recently_verified_users.pop(user_id, None)  # Clean up if member is not found
                continue
            # Check if the member has been verified and inactive for more than the allowed period
            if (now - verify_time).total_seconds() > POST_ACTIVITY_PERIOD_HOURS * 3600:
                to_reverify.append(member)

        if not self._has_manage_roles_permission(guild.me):
            logger.critical("Bot lacks the necessary permissions to manage roles.")
            return

        for member in to_reverify:
            try:
                await member.remove_roles(self.member_role)
                await member.add_roles(self.must_verify_role)
                await member.send(
                    f"You were verified but did not post within {POST_ACTIVITY_PERIOD_HOURS} hours, so you have been moved back to the '{MUST_VERIFY_ROLE_NAME}' role. Please post within 24 hours to be verified again."
                )
                logger.info(f"Moved {member.name} back to '{MUST_VERIFY_ROLE_NAME}' role for inactivity.")
                self.recently_verified_users.pop(member.id, None)
            except discord.Forbidden:
                logger.error(f"Bot does not have permission to manage roles for {member.name}.")
            except Exception as e:
                logger.error(f"Error moving user {member.name} back to verification: {e}", exc_info=True)

    @check_unverified_users.before_loop
    async def before_check_unverified_users(self):
        await self.bot.wait_until_ready()

    @check_verified_users_activity.before_loop
    async def before_check_verified_users_activity(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        """
        Event listener that triggers when a role is updated in the guild.
        Reinitializes roles if the monitored roles are updated.
        """
        if before.id == self.must_verify_role.id or before.id == self.member_role.id:
            await self.initialize_roles()
            logger.info(f"Reinitialized roles due to update: {before.name} -> {after.name}")

    def _has_manage_roles_permission(self, member: discord.Member) -> bool:
        """
        Check if the member has the Manage Roles permission.
        """
        return member.guild_permissions.manage_roles

    def _has_kick_permission(self, member: discord.Member) -> bool:
        """
        Check if the member has the Kick Members permission.
        """
        return member.guild_permissions.kick_members

    async def cog_unload(self):
        """
        Cleanup tasks when the cog is unloaded.
        """
        self.check_unverified_users.cancel()
        self.check_verified_users_activity.cancel()

async def setup(bot: commands.Bot):
    cog = Verification(bot)
    await bot.add_cog(cog)
