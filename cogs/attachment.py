import asyncio
import logging
import os
import re
from typing import Optional

import aiofiles
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from tqdm.asyncio import tqdm

from db.database import Attachment, Base  # Assuming Base is the declarative base for SQLAlchemy models

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = os.getenv('DATA_DIR', 'data')
CONCURRENCY_LIMIT = int(os.getenv('CONCURRENCY_LIMIT', 5))
SUPPORTED_EXTENSIONS = os.getenv('SUPPORTED_EXTENSIONS', 'jpg,jpeg,png,gif,mp4,mov,avi,txt,pdf').split(',')
RATE_LIMIT = int(os.getenv('RATE_LIMIT', 5))  # Number of messages to process per second
DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', 60))  # Timeout in seconds for downloading attachments

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./kywins.db')
engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

class AttachmentCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize the filename to remove invalid characters."""
        return re.sub(r'[^\w\-_. ]', '', filename)

    async def download_attachment(self, session: aiohttp.ClientSession, attachment: discord.Attachment, file_path: str, pbar: Optional[tqdm] = None) -> None:
        """Download the attachment and save it to the specified file path."""
        async with self.semaphore:
            try:
                async with session.get(attachment.url, timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await resp.read())
                        logger.info(f"Attachment saved: {file_path}")
                    else:
                        logger.error(f"Failed to download attachment: {attachment.url} with status {resp.status}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout while downloading attachment: {attachment.url}")
            except aiohttp.ClientError as e:
                logger.error(f"Error downloading attachment {attachment.url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
            finally:
                if pbar:
                    pbar.update(1)

    async def save_to_database(self, channel_name: str, post_dir_name: str, filename: str, file_path: str) -> None:
        """Save the attachment metadata to the database."""
        async with SessionLocal() as session:
            async with session.begin():
                existing = await session.execute(
                    select(Attachment).filter_by(file_path=file_path)
                )
                if existing.scalars().first():
                    logger.info(f"Duplicate attachment found, skipping: {file_path}")
                    return

                attachment = Attachment(
                    channel_name=channel_name,
                    post_dir_name=post_dir_name,
                    filename=filename,
                    file_path=file_path
                )
                session.add(attachment)
            await session.commit()
            logger.info(f"Attachment metadata saved to database: {file_path}")

    async def ensure_directories(self, channel_name: str, post_dir_name: str) -> str:
        """Ensure the necessary directories exist and return the post directory path."""
        channel_dir = os.path.join(DATA_DIR, channel_name)
        post_dir = os.path.join(channel_dir, post_dir_name)
        os.makedirs(post_dir, exist_ok=True)
        return post_dir

    async def save_attachments_from_message(self, message: discord.Message, pbar: Optional[tqdm] = None) -> None:
        """Save all attachments from a given message."""
        attachments = message.attachments
        channel_name = message.channel.name
        post_dir_name = ''.join(re.findall(r'\w+', ' '.join(message.content.split(maxsplit=2)[:2]))).lower()
        post_dir = await self.ensure_directories(channel_name, post_dir_name)

        async with aiohttp.ClientSession() as session:
            tasks = []
            for index, attachment in enumerate(attachments, start=1):
                filename = attachment.filename
                safe_filename = self.sanitize_filename(filename)
                file_name_without_extension, extension = os.path.splitext(safe_filename)
                file_path = os.path.join(post_dir, f"{file_name_without_extension}_{index}{extension}")

                if not await self.async_file_exists(file_path):
                    tasks.append(self.download_attachment(session, attachment, file_path, pbar))
                    await self.save_to_database(channel_name, post_dir_name, filename, file_path)
                else:
                    logger.info(f"Skipping already saved attachment: {file_path}")

            await asyncio.gather(*tasks)

    @staticmethod
    async def async_file_exists(file_path: str) -> bool:
        """Asynchronously check if a file exists."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, os.path.exists, file_path)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listener to save new attachments as they get posted."""
        if message.attachments:
            await self.save_attachments_from_message(message)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Listener to start background tasks after the bot is ready."""
        await self.bot.wait_until_ready()
        self.bot.loop.create_task(self.fetch_past_attachments())

    @app_commands.command(name="save_all", description="Save all attachments from the entire server")
    @app_commands.default_permissions(administrator=True)
    async def save_all(self, interaction: discord.Interaction) -> None:
        """Command to save all past attachments from the entire server."""
        await interaction.response.send_message("Saving all attachments. This may take a while...", ephemeral=True)
        try:
            total_attachments = await self.count_all_attachments(interaction.guild)
            with tqdm(total=total_attachments, desc="Downloading attachments") as pbar:
                await self.download_all_attachments(interaction.guild, pbar)
            await interaction.followup.send("All attachments have been saved.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in save_all command: {e}")
            await interaction.followup.send("An error occurred while saving attachments.", ephemeral=True)

    async def count_all_attachments(self, guild: discord.Guild) -> int:
        """Count all attachments in the guild."""
        total_attachments = 0
        for channel in guild.text_channels:
            async for message in channel.history(limit=None):
                total_attachments += len(message.attachments)
        return total_attachments

    async def download_all_attachments(self, guild: discord.Guild, pbar: tqdm) -> None:
        """Download all attachments in the guild."""
        for channel in guild.text_channels:
            async for message in channel.history(limit=None):
                if message.attachments:
                    await self.save_attachments_from_message(message, pbar)
                await asyncio.sleep(1 / RATE_LIMIT)  # Rate limiting to avoid hitting API limits

    async def process_existing_files(self, directory: str) -> None:
        """Process existing files in the data directory and save their metadata to the database."""
        for root, _, files in os.walk(directory):
            for filename in files:
                if filename.endswith(tuple(SUPPORTED_EXTENSIONS)):
                    file_path = os.path.join(root, filename)
                    # Extract channel_name and post_dir_name from the file path
                    parts = file_path.split(os.sep)
                    if len(parts) >= 3:
                        channel_name = parts[-3]
                        post_dir_name = parts[-2]
                        await self.save_to_database(channel_name, post_dir_name, filename, file_path)

    @app_commands.command(name="fetch", description="Retroactively add attachments in the server to the database")
    @app_commands.default_permissions(administrator=True)
    async def fetch(self, interaction: discord.Interaction) -> None:
        """Command to retroactively add attachments in the server to the database."""
        await interaction.response.send_message("Fetching attachments. This may take a while...", ephemeral=True)
        try:
            await self.fetch_past_attachments_from_guild(interaction.guild)
            await self.process_existing_files(DATA_DIR)
            await interaction.followup.send("All attachments have been retroactively added to the database.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in fetch command: {e}")
            await interaction.followup.send("An error occurred while fetching attachments.", ephemeral=True)

    async def fetch_past_attachments_from_guild(self, guild: discord.Guild) -> None:
        """Fetch past attachments from all channels in the guild and save them to the database."""
        for channel in guild.text_channels:
            async for message in channel.history(limit=None):
                if message.attachments:
                    await self.save_attachments_metadata(message)
                await asyncio.sleep(1 / RATE_LIMIT)  # Rate limiting to avoid hitting API limits

    async def save_attachments_metadata(self, message: discord.Message) -> None:
        """Save metadata of all attachments from a given message to the database without downloading."""
        attachments = message.attachments
        channel_name = message.channel.name
        post_dir_name = ''.join(re.findall(r'\w+', ' '.join(message.content.split(maxsplit=2)[:2]))).lower()
        post_dir = await self.ensure_directories(channel_name, post_dir_name)

        for index, attachment in enumerate(attachments, start=1):
            filename = attachment.filename
            safe_filename = self.sanitize_filename(filename)
            file_name_without_extension, extension = os.path.splitext(safe_filename)
            file_path = os.path.join(post_dir, f"{file_name_without_extension}_{index}{extension}")

            await self.save_to_database(channel_name, post_dir_name, filename, file_path)

    @app_commands.command(name="view_attachments", description="View saved attachments from the database")
    async def view_attachments(self, interaction: discord.Interaction) -> None:
        """Command to view saved attachments from the database."""
        try:
            async with SessionLocal() as session:
                result = await session.execute(select(Attachment))
                attachments = result.scalars().all()

                if not attachments:
                    await interaction.response.send_message("No attachments found in the database.", ephemeral=True)
                    return

                embed = discord.Embed(title="Saved Attachments", color=discord.Color.blue())
                for attachment in attachments:
                    embed.add_field(name=f"{attachment.filename}",
                                    value=f"Channel: {attachment.channel_name}\nPath: {attachment.file_path}",
                                    inline=False)

                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in view_attachments command: {e}")
            await interaction.response.send_message("An error occurred while viewing attachments.", ephemeral=True)

    async def fetch_past_attachments(self) -> None:
        """Fetch past attachments from all channels and save them."""
        await self.bot.wait_until_ready()
        try:
            for guild in self.bot.guilds:
                await self.fetch_past_attachments_from_guild(guild)
            logger.info("All past attachments have been processed.")
        except Exception as e:
            logger.error(f"Error fetching past attachments: {e}")

async def setup(bot: commands.Bot):
    await init_db()  # Initialize the database
    cog = AttachmentCog(bot)
    await bot.add_cog(cog)
    # Remove command registration from setup to avoid re-registration issues
    # Commands are registered through the Cog itself now
