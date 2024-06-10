import asyncio
import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Retrieve necessary environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not DISCORD_TOKEN:
    raise ValueError("No Discord token found in environment variables.")
if not GUILD_ID:
    raise ValueError("No Guild ID found in environment variables.")

# Initialize the bot with a command prefix and intents
intents = discord.Intents.all()
intents.members = True  # Enable the members intent
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Flag to ensure on_ready tasks are only run once
bot.synced = False

@bot.event
async def on_ready():
    if not bot.synced:
        logger.info(f'Logged in as {bot.user}')
        try:
            guild = discord.Object(id=int(GUILD_ID))  # Ensure you use the correct guild ID
            await bot.tree.sync(guild=guild)  # Synchronize slash commands with the specific guild
            logger.info(f'Slash commands synced with guild: {GUILD_ID}')
        except discord.Forbidden:
            logger.error(f"Error: Missing access to guild {GUILD_ID}")
        except discord.HTTPException as e:
            logger.error(f"HTTP error occurred while syncing commands with guild {GUILD_ID}: {e}")
        bot.synced = True
        logger.info('Bot is ready and slash commands are synced.')
    else:
        logger.info('Bot reconnected.')

@bot.event
async def on_resumed():
    logger.info('Bot has resumed the session.')

@bot.event
async def on_disconnect():
    logger.warning('Bot has disconnected from Discord.')

@bot.event
async def on_guild_join(guild):
    logger.info(f"Bot joined guild: {guild.name} (ID: {guild.id})")

@bot.event
async def on_guild_remove(guild):
    logger.info(f"Bot removed from guild: {guild.name} (ID: {guild.id})")

# Error handling for command errors
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CommandNotFound):
        await ctx.send("This command does not exist.")
        logger.warning(f"Command not found: {ctx.message.content}")
    else:
        await ctx.send("An error occurred.")
        logger.error(f"An error occurred: {error}", exc_info=True)

# Load all extensions in the cogs directory
async def load_extensions():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            extension = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}.", exc_info=True)

async def main():
    logger.info("Starting bot...")
    async with bot:
        await load_extensions()
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Critical error in bot startup: {e}", exc_info=True)
