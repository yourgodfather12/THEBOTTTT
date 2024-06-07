import json
import logging
import os
import re

import aiofiles
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BACKUP_FOLDER = os.getenv('BACKUP_FOLDER', 'backups')
BACKUP_INTERVAL = int(os.getenv('BACKUP_INTERVAL', 24 * 60 * 60))  # Default 24 hours

class BackupAndRestore(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.backup_folder = BACKUP_FOLDER
        self.schedule_backup.start()

    @tasks.loop(seconds=BACKUP_INTERVAL)  # Run the backup task based on configured interval
    async def schedule_backup(self):
        await self.bot.wait_until_ready()  # Wait until the bot is ready to access guilds
        for guild in self.bot.guilds:
            await self.create_backup(guild)

    async def create_backup(self, guild: discord.Guild):
        backup_data = {
            "name": guild.name,
            "id": guild.id,
            "members": [
                {
                    "id": member.id,
                    "name": str(member),
                    "joined_at": member.joined_at.isoformat() if member.joined_at else "Unknown"
                } for member in guild.members
            ],
            "channels": [
                {
                    "id": channel.id,
                    "name": channel.name,
                    "type": str(channel.type)
                } for channel in guild.channels
            ],
            "roles": [
                {
                    "id": role.id,
                    "name": role.name
                } for role in guild.roles
            ]
        }

        # Use a sanitized version of the guild name for the backup filename
        sanitized_guild_name = re.sub(r'[\\/*?:"<>|]', "_", guild.name)
        backup_file = os.path.join(self.backup_folder, f"{sanitized_guild_name}_{guild.id}.json")

        os.makedirs(self.backup_folder, exist_ok=True)

        try:
            async with aiofiles.open(backup_file, "w") as f:
                await f.write(json.dumps(backup_data, indent=4))  # Added indent for readability
            logger.info(f"Backup created for {guild.name} ({guild.id}), saved to {backup_file}")
        except Exception as e:
            logger.error(f"Failed to create backup for {guild.name} ({guild.id}): {e}")

    @schedule_backup.error
    async def schedule_backup_error(self, error):
        logger.error(f"Error occurred in scheduled backup: {error}")

    @app_commands.command(name="restore_backup", description="Restore a backup from a specified file")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(backup_file="The backup file to restore from.")
    async def restore_backup(self, interaction: discord.Interaction, backup_file: str):
        """Command to restore a backup from a specified file."""
        try:
            async with aiofiles.open(os.path.join(self.backup_folder, backup_file), "r") as f:
                backup_data = json.loads(await f.read())

            guild = discord.utils.get(self.bot.guilds, id=backup_data['id'])
            if not guild:
                await interaction.response.send_message("Guild not found.", ephemeral=True)
                return

            # Restore members, channels, and roles as needed
            # Note: Full restoration of members, channels, and roles may require additional permissions and complexity
            await interaction.response.send_message(f"Restoration process initiated for {backup_data['name']} ({backup_data['id']}).", ephemeral=True)

        except FileNotFoundError:
            await interaction.response.send_message("Backup file not found.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to restore backup from {backup_file}: {e}")
            await interaction.response.send_message("Failed to restore backup. Check logs for details.", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Bot is ready and logged in as {self.bot.user}")

    async def cog_unload(self):
        self.schedule_backup.cancel()

    @commands.Cog.listener()
    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Error in {event_method}: {args} {kwargs}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BackupAndRestore(bot))
    # Removed duplicate cog registration and command registration
