import os
import logging
import discord
from discord import app_commands
from discord.ext import commands

# Ensure the logs directory exists
if not os.path.exists('logs'):
    os.makedirs('logs')

# Set up logging
logging.basicConfig(filename='logs/utility.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

class UtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_permission(self, interaction: discord.Interaction, permission: str) -> bool:
        """Check if the user has the specified permission or Admin/Mod role."""
        try:
            has_permission = (
                getattr(interaction.user.guild_permissions, permission, False) or
                any(role.name in ["Admin", "Mod"] for role in interaction.user.roles)
            )
            if not has_permission:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="You do not have permission to use this command.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
            return has_permission
        except Exception as e:
            logger.error(f"Error checking permission: {e}", exc_info=True)
            return False

    @app_commands.command(name="listroles", description="Lists all roles available in the server.")
    async def listroles(self, interaction: discord.Interaction):
        """List all roles available in the server."""
        try:
            roles = [role.name for role in interaction.guild.roles]
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Server Roles",
                    description=', '.join(roles),
                    color=discord.Color.blue()
                )
            )
            logger.info(f"Listed all roles in server {interaction.guild.name}")
        except Exception as e:
            logger.error(f"Error listing roles: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while listing roles.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

    @app_commands.command(name="clearchat", description="Clears all messages from the current channel.")
    async def clearchat(self, interaction: discord.Interaction):
        """Clear all messages from the current channel."""
        if await self.check_permission(interaction, "manage_messages"):
            try:
                await interaction.channel.purge()
                embed = discord.Embed(
                    description="All messages cleared.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                logger.info(f"All messages cleared in channel {interaction.channel.name}")
            except Exception as e:
                logger.error(f"Error clearing chat: {e}", exc_info=True)
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description="An error occurred while clearing the chat.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
        else:
            logger.warning(f"User {interaction.user.name} attempted to clear messages without permission in channel {interaction.channel.name}")

    @app_commands.command(name="list_commands", description="Lists all commands available in the bot, organized by cog.")
    async def list_commands(self, interaction: discord.Interaction):
        """List all commands available in the bot, organized by cog."""
        try:
            embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
            for cog_name, cog in self.bot.cogs.items():
                command_names = [command.name for command in cog.get_app_commands()]
                if command_names:
                    embed.add_field(
                        name=cog_name,
                        value=", ".join(command_names),
                        inline=False
                    )
            # List commands not associated with any cog
            no_cog_commands = [command.name for command in self.bot.tree.walk_commands() if command.parent is None]
            if no_cog_commands:
                embed.add_field(
                    name="No Category",
                    value=", ".join(no_cog_commands),
                    inline=False
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Listed all commands for guild {interaction.guild.name}")
        except Exception as e:
            logger.error(f"Error listing commands: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while listing commands.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
