import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve the Discord token from environment variables
DISCORD_TOKEN = os.getenv( "DISCORD_TOKEN" )

if not DISCORD_TOKEN:
    raise ValueError( "No Discord token found in environment variables." )

# Initialize the bot with intents and command prefix
intents = discord.Intents.default()
intents.messages = True  # Enable message intent to listen for messages
intents.guilds = True
intents.message_content = True  # Enable message content intent for processing message contents

bot = commands.Bot( command_prefix="!", intents=intents )


@bot.event
async def on_ready():
    print( f'Logged in as {bot.user}' )
    guild_id = 123456789012345678  # Replace with your actual guild ID
    guild = bot.get_guild( guild_id )

    if guild is None:
        print( f"Bot is not a member of the guild with ID {guild_id}." )
        return

    try:
        await bot.tree.sync( guild=discord.Object( id=guild_id ) )  # Synchronize slash commands with the specific guild
        print( f'Slash commands synced with guild: {guild_id}' )
    except discord.Forbidden:
        print( f"Error: Missing access to guild {guild_id}" )
    except discord.HTTPException as e:
        print( f"HTTP error occurred while syncing commands with guild {guild_id}: {e}" )


async def setup_extensions():
    # Load extensions (cogs)
    extensions = [
        'cogs.admin_cog',
        'cogs.attachment',
        'cogs.backup_and_restore',
        'cogs.callposts',
        'cogs.currency_system',
        'cogs.donation',
        'cogs.mod_cog',
        'cogs.report_cog',
        'cogs.server_build',
        'cogs.server_rules',
        'cogs.server_statistics',
        'cogs.store',
        'cogs.trading',
        'cogs.upload',
        'cogs.user_info',
        'cogs.utility_cog',
        'cogs.verification'
    ]

    for extension in extensions:
        try:
            await bot.load_extension( extension )
            print( f'Loaded extension: {extension}' )
        except commands.ExtensionNotFound:
            print( f'Extension {extension} not found.' )
        except commands.ExtensionAlreadyLoaded:
            print( f'Extension {extension} is already loaded.' )
        except commands.NoEntryPointError:
            print( f'Extension {extension} does not have a setup function.' )
        except commands.ExtensionFailed as e:
            print( f'Extension {extension} failed to load. Error: {e.__class__.__name__}: {e}' )


async def main():
    async with bot:
        await setup_extensions()
        await bot.start( DISCORD_TOKEN )


if __name__ == "__main__":
    asyncio.run( main() )
