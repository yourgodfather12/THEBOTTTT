import os
import logging
import json
from datetime import datetime, timezone
from typing import Optional

import aiofiles
import discord
from discord import app_commands
from discord.ext import commands

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tree = bot.tree
        self.message_counts = {}
        self.voice_times = {}
        self.voice_start_times = {}
        self.state_file = os.path.join("database", "user_info_state.json")
        self.ensure_db_path_exists()
        self.bot.loop.create_task(self.load_state())

    def ensure_db_path_exists(self) -> None:
        """Ensure the directory for the state file exists."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

    async def save_state(self) -> None:
        """Save the current state to a file."""
        try:
            state = {
                "message_counts": self.message_counts,
                "voice_times": self.voice_times
            }
            async with aiofiles.open(self.state_file, "w") as f:
                await f.write(json.dumps(state))
            logger.info("User info state saved.")
        except Exception as e:
            logger.error(f"Failed to save user info state: {e}")

    async def load_state(self) -> None:
        """Load the state from a file."""
        if os.path.exists(self.state_file):
            try:
                async with aiofiles.open(self.state_file, "r") as f:
                    content = await f.read()
                    if content:
                        state = json.loads(content)
                        self.message_counts = state.get("message_counts", {})
                        self.voice_times = state.get("voice_times", {})
                        logger.info("User info state loaded.")
                    else:
                        logger.warning("User info state file is empty.")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to load user info state: Invalid JSON format. {e}")
            except Exception as e:
                logger.error(f"Failed to load user info state: {e}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Load state when the bot is ready."""
        await self.load_state()
        logger.info(f"Bot is ready. Loaded state from {self.state_file}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Update message count when a message is sent."""
        if message.author.bot:
            return
        try:
            self.message_counts[message.author.id] = self.message_counts.get(message.author.id, 0) + 1
        except Exception as e:
            logger.error(f"Error updating message count for {message.author.id}: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        """Update voice time when a user joins or leaves a voice channel."""
        current_time = datetime.now(timezone.utc).timestamp()
        try:
            if before.channel is None and after.channel is not None:
                self.voice_start_times[member.id] = current_time
            elif before.channel is not None and after.channel is None:
                start_time = self.voice_start_times.pop(member.id, None)
                if start_time is not None:
                    duration = current_time - start_time
                    self.voice_times[member.id] = self.voice_times.get(member.id, 0) + duration
        except Exception as e:
            logger.error(f"Error updating voice time for {member.id}: {e}")

    @app_commands.command(name='userinfo', description='Displays information about a user.')
    @app_commands.describe(member="The member to display information for.")
    async def user_info(self, interaction: discord.Interaction, member: Optional[discord.Member] = None) -> None:
        """Display user information."""
        member = member or interaction.user
        messages = self.message_counts.get(member.id, 0)
        voice_time = self.voice_times.get(member.id, 0)
        voice_hours = round(voice_time / 3600, 2)

        embed = discord.Embed(
            title=f"User Information - {member.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        avatar_url = member.avatar.url if member.avatar else member.default_avatar.url
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="User ID", value=member.id, inline=False)
        embed.add_field(name="Display Name", value=member.display_name, inline=False)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%B %d, %Y"), inline=False)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%B %d, %Y"), inline=False)
        embed.add_field(name="Roles", value=", ".join([role.name for role in member.roles if role.name != "@everyone"]), inline=False)
        embed.add_field(name="Messages Sent", value=messages, inline=False)
        embed.add_field(name="Time in Voice Channels (hours)", value=voice_hours, inline=False)

        await interaction.response.send_message(embed=embed)
        logger.info(f"Displayed user info for {member.display_name} ({member.id}).")

    async def cog_unload(self) -> None:
        """Save the state when the cog is unloaded."""
        await self.save_state()

    @commands.Cog.listener()
    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        """Handle errors in listeners."""
        logger.error(f"An error occurred in the event listener {event_method}: {args} {kwargs}")

    async def cog_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Handle errors within the cog."""
        error_msg = f"Error in command '{interaction.command}': {error}"
        logger.error(error_msg)
        await interaction.response.send_message(embed=discord.Embed(description=error_msg, color=discord.Color.red()), ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    cog = UserInfoCog(bot)
    await bot.add_cog(cog)
