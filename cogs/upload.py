import asyncio
import hashlib
import json
import logging
import os
from typing import Set

import aiofiles
import discord
from discord.ext import commands
from discord import app_commands

# Constants
RATE_LIMIT = int(os.getenv("RATE_LIMIT", 1))  # Rate limit between file uploads per channel in seconds
FILE_SIZE_LIMIT = int(os.getenv("FILE_SIZE_LIMIT", 50 * 1024 * 1024))  # 50 MB limit
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 8 * 1024 * 1024))  # 8 MB chunks
CONCURRENT_UPLOADS = int(os.getenv("CONCURRENT_UPLOADS", 3))  # Limit concurrent uploads

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UploadCog(commands.Cog):
    def __init__(self, bot: commands.Bot, folder_path: str):
        self.bot = bot
        self.tree = bot.tree
        self.folder_path = folder_path
        self.uploaded_files: Set[str] = set()
        self.resume_state_file = "logs/upload_resume_state.json"
        self.ensure_db_path_exists()
        self.upload_semaphore = asyncio.Semaphore(CONCURRENT_UPLOADS)

    async def cog_load(self):
        await self.load_state()

    def ensure_db_path_exists(self) -> None:
        """Ensure the directory for the resume state file exists."""
        os.makedirs(os.path.dirname(self.resume_state_file), exist_ok=True)

    async def save_state(self) -> None:
        """Save the current upload state to a file."""
        try:
            async with aiofiles.open(self.resume_state_file, "w") as f:
                await f.write(json.dumps(list(self.uploaded_files)))
            logger.info("Upload state saved.")
        except Exception as e:
            logger.error(f"Failed to save upload state: {e}")

    async def load_state(self) -> None:
        """Load the upload state from a file."""
        if os.path.exists(self.resume_state_file):
            try:
                async with aiofiles.open(self.resume_state_file, "r") as f:
                    self.uploaded_files = set(json.loads(await f.read()))
                logger.info("Upload state loaded.")
            except Exception as e:
                logger.error(f"Failed to load upload state: {e}")

    async def enqueue_files(self, file_queue: asyncio.Queue) -> None:
        """Enqueue files for processing."""
        for county_folder in os.listdir(self.folder_path):
            county_folder_path = os.path.join(self.folder_path, county_folder)
            if not os.path.isdir(county_folder_path):
                continue

            for sub_dir_name in os.listdir(county_folder_path):
                sub_dir_path = os.path.join(county_folder_path, sub_dir_name)
                if not os.path.isdir(sub_dir_path):
                    continue

                normalized_sub_dir_name = sub_dir_name.lower().replace(" ", "_")

                for file_name in os.listdir(sub_dir_path):
                    file_path = os.path.join(sub_dir_path, file_name)
                    if not os.path.isfile(file_path):
                        continue

                    await file_queue.put((county_folder, normalized_sub_dir_name, file_name, file_path))

    async def process_queue(self, interaction: discord.Interaction, file_queue: asyncio.Queue) -> None:
        """Process the file queue."""
        while not file_queue.empty():
            county_folder, sub_dir_name, file_name, file_path = await file_queue.get()

            channel = discord.utils.get(interaction.guild.channels, name=county_folder)
            if not channel:
                await self.send_warning(interaction, f"No channel found with the name '{county_folder}'")
                continue

            permissions = channel.permissions_for(interaction.guild.me)
            if not (permissions.send_messages and permissions.attach_files):
                await self.send_warning(interaction, f"The bot lacks permissions to upload files to '{county_folder}' channel.")
                continue

            await self.upload_file(interaction, channel, sub_dir_name, file_name, file_path)
            await asyncio.sleep(RATE_LIMIT)

    async def upload_file(self, interaction: discord.Interaction, channel: discord.TextChannel, sub_dir_name: str, file_name: str, file_path: str) -> None:
        async with self.upload_semaphore:
            try:
                file_identifier = await self.get_file_identifier(file_path)
                if file_identifier in self.uploaded_files:
                    logger.info(f"File {file_name} already uploaded, skipping.")
                    return

                if os.path.getsize(file_path) > FILE_SIZE_LIMIT:
                    await self.upload_large_file(interaction, channel, sub_dir_name, file_name, file_path)
                else:
                    await self.upload_small_file(interaction, channel, sub_dir_name, file_name, file_path)

                self.uploaded_files.add(file_identifier)
                await self.save_state()
            except FileNotFoundError:
                await self.send_error(interaction, f"File not found: {file_path}")
            except PermissionError:
                await self.send_error(interaction, f"Permission denied: {file_path}")
            except discord.errors.HTTPException as e:
                await self.send_error(interaction, f"Discord HTTP error uploading file {file_path}: {e}")
            except Exception as e:
                logger.error(f"Error uploading file {file_path}: {e}", exc_info=True)
                await self.send_error(interaction, f"Error uploading file {file_path}: {e}")

    async def upload_small_file(self, interaction: discord.Interaction, channel: discord.TextChannel, sub_dir_name: str, file_name: str, file_path: str) -> None:
        """Upload small files directly."""
        try:
            async with aiofiles.open(file_path, 'rb') as file:
                file_to_send = discord.File(await file.read(), filename=file_name)
                await channel.send(f"{sub_dir_name}\n", file=file_to_send)
                await self.send_success(interaction, f"Uploaded file {file_name} to '{sub_dir_name}' successfully.")
                logger.info(f"File {file_name} uploaded to '{sub_dir_name}' channel successfully.")
        except Exception as e:
            await self.send_error(interaction, f"Failed to upload small file {file_name}: {e}")

    async def upload_large_file(self, interaction: discord.Interaction, channel: discord.TextChannel, sub_dir_name: str, file_name: str, file_path: str) -> None:
        """Upload large files in chunks."""
        base_name, ext = os.path.splitext(file_name)
        chunk_index = 0

        try:
            async with aiofiles.open(file_path, 'rb') as file:
                while chunk := await file.read(CHUNK_SIZE):
                    chunk_file_name = f"{base_name}_part{chunk_index}{ext}"
                    chunk_file_path = f"{file_path}_part{chunk_index}"
                    async with aiofiles.open(chunk_file_path, 'wb') as chunk_file:
                        await chunk_file.write(chunk)

                    await self.upload_small_file(interaction, channel, sub_dir_name, chunk_file_name, chunk_file_path)
                    os.remove(chunk_file_path)
                    chunk_index += 1

            await self.send_success(interaction, f"Uploaded large file {file_name} to '{sub_dir_name}' in chunks.")
        except Exception as e:
            await self.send_error(interaction, f"Failed to upload large file {file_name} in chunks: {e}")

    async def send_error(self, interaction: discord.Interaction, message: str) -> None:
        """Send an error message to the interaction."""
        logger.error(message)
        await interaction.followup.send(embed=discord.Embed(description=message, color=discord.Color.red()), ephemeral=True)

    async def send_warning(self, interaction: discord.Interaction, message: str) -> None:
        """Send a warning message to the interaction."""
        logger.warning(message)
        await interaction.followup.send(embed=discord.Embed(description=message, color=discord.Color.orange()), ephemeral=True)

    async def send_success(self, interaction: discord.Interaction, message: str) -> None:
        """Send a success message to the interaction."""
        logger.info(message)
        await interaction.followup.send(embed=discord.Embed(description=message, color=discord.Color.green()), ephemeral=True)

    async def get_file_identifier(self, file_path: str) -> str:
        """Generate a unique identifier for the file based on its content."""
        hasher = hashlib.sha1()
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(4096):
                hasher.update(chunk)
        return hasher.hexdigest()

    async def cog_unload(self) -> None:
        """Save the upload state when the cog is unloaded."""
        await self.save_state()

    @app_commands.command(name="upload", description="Upload files to respective channels.")
    @app_commands.default_permissions()
    async def upload_command(self, interaction: discord.Interaction) -> None:
        """Command to trigger the file upload process."""
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        bot_permissions = interaction.guild.me.guild_permissions
        if not (bot_permissions.manage_roles and bot_permissions.manage_channels and bot_permissions.send_messages):
            await interaction.response.send_message("Bot does not have the required permissions to execute this command.", ephemeral=True)
            return

        await interaction.response.send_message("File upload process started.", ephemeral=True)
        file_queue = asyncio.Queue()
        await self.enqueue_files(file_queue)
        await self.process_queue(interaction, file_queue)

async def setup(bot: commands.Bot) -> None:
    """Setup function to add the cog to the bot."""
    folder_path = os.getenv("FOLDER_PATH")
    if folder_path:
        cog = UploadCog(bot, folder_path)
        await bot.add_cog(cog)
