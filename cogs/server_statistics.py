import logging
import discord
from discord.ext import commands
from discord import app_commands

# Initialize the logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class ServerStatisticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="serverstats", description="Show detailed statistics of the server")
    @app_commands.default_permissions()
    async def server_stats(self, interaction: discord.Interaction) -> None:
        """Show detailed statistics of the server"""
        try:
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check if the bot has permission to send messages and embeds
            permissions = interaction.channel.permissions_for(interaction.guild.me)
            if not (permissions.send_messages and permissions.embed_links):
                await interaction.response.send_message("I don't have permission to send messages or embeds in this channel.", ephemeral=True)
                logger.warning("Bot lacks permissions to send messages or embeds.")
                return

            # Example code for creating an embed with server statistics
            embed = discord.Embed(title=f"{guild.name} Statistics", description="Detailed server statistics", color=discord.Color.blue())
            embed.add_field(name="Member Count", value=guild.member_count)
            embed.add_field(name="Text Channels", value=len(guild.text_channels))
            embed.add_field(name="Voice Channels", value=len(guild.voice_channels))

            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)

            await interaction.response.send_message(embed=embed)
            logger.info(f"Server statistics displayed for {guild.name}.")
        except discord.Forbidden:
            logger.warning("Bot doesn't have permission to send messages.")
        except discord.NotFound:
            logger.warning("Interaction not found.")
        except Exception as e:
            logger.error(f"Error displaying server statistics: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while displaying the statistics. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = ServerStatisticsCog(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
