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
                await interaction.response.send_message(
                    "I don't have permission to send messages or embeds in this channel.", ephemeral=True)
                logger.warning("Bot lacks permissions to send messages or embeds.")
                return

            # Gather detailed server statistics
            total_members = guild.member_count
            online_members = sum(member.status == discord.Status.online for member in guild.members)
            offline_members = sum(member.status == discord.Status.offline for member in guild.members)
            idle_members = sum(member.status == discord.Status.idle for member in guild.members)
            dnd_members = sum(member.status == discord.Status.dnd for member in guild.members)
            bots = sum(member.bot for member in guild.members)

            # Create an embed with server statistics
            embed = discord.Embed(title=f"{guild.name} Statistics", description="Detailed server statistics",
                                  color=discord.Color.blue())
            embed.add_field(name="Total Members", value=total_members)
            embed.add_field(name="Online Members", value=online_members)
            embed.add_field(name="Offline Members", value=offline_members)
            embed.add_field(name="Idle Members", value=idle_members)
            embed.add_field(name="Do Not Disturb Members", value=dnd_members)
            embed.add_field(name="Bots", value=bots)
            embed.add_field(name="Text Channels", value=len(guild.text_channels))
            embed.add_field(name="Voice Channels", value=len(guild.voice_channels))
            embed.add_field(name="Roles", value=len(guild.roles))
            embed.add_field(name="Emojis", value=len(guild.emojis))
            embed.add_field(name="Server Created At", value=guild.created_at.strftime("%B %d, %Y"))

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
            await interaction.response.send_message(
                "An error occurred while displaying the statistics. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStatisticsCog(bot))
