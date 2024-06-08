import logging
import os

import discord
from discord.ext import commands
from discord import app_commands

# Ensure the logs directory exists
if not os.path.exists('logs'):
    os.makedirs('logs')

# Set up logging
logging.basicConfig(filename='logs/report.log', level=logging.INFO,
                    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

class ReportCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_permission(self, interaction: discord.Interaction, permission: str) -> bool:
        admin_role = discord.utils.get(interaction.guild.roles, name="Admin")
        mod_role = discord.utils.get(interaction.guild.roles, name="Mod")
        has_permission = (
            getattr(interaction.user.guild_permissions, permission, False) or
            (admin_role in interaction.user.roles if admin_role else False) or
            (mod_role in interaction.user.roles if mod_role else False)
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

    @app_commands.command(name="report", description="Allows users to report other users for rule violations.")
    @app_commands.describe(user="The user to report", reason="The reason for reporting the user")
    @app_commands.default_permissions(manage_messages=True)
    async def report(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        report_channel = discord.utils.get(interaction.guild.channels, name="reports")
        if report_channel:
            await report_channel.send(
                embed=discord.Embed(
                    description=f"{interaction.user.mention} reported {user.mention} for: {reason}.",
                    color=discord.Color.orange()
                )
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Report submitted successfully.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"{interaction.user.name} reported {user.name} for: {reason}")
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Report channel not found. Please contact an administrator.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error("Report channel not found")

    @app_commands.command(name="checkwarns", description="Checks the number of warnings a user has received.")
    @app_commands.describe(user="The user to check warnings for")
    async def checkwarns(self, interaction: discord.Interaction, user: discord.Member):
        warnings = 0  # Placeholder value
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{user.mention} has {warnings} warnings.",
                color=discord.Color.orange()
            )
        )

    @app_commands.command(name="checkbans", description="Checks if a user is banned from the server.")
    @app_commands.describe(user="The user to check ban status for")
    async def checkbans(self, interaction: discord.Interaction, user: discord.Member):
        bans = await interaction.guild.bans()
        if user in [ban.user for ban in bans]:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{user.mention} is banned.",
                    color=discord.Color.red()
                )
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{user.mention} is not banned.",
                    color=discord.Color.green()
                )
            )

    @report.error
    async def report_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You do not have the required permissions to use this command.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )

# Error handler for slash commands
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(embed=discord.Embed(
            description="You do not have the required permissions to run this command.",
            color=discord.Color.red()
        ), ephemeral=True)
    elif isinstance(error, app_commands.BotMissingPermissions):
        await interaction.response.send_message(embed=discord.Embed(
            description="I do not have the required permissions to run this command.",
            color=discord.Color.red()
        ), ephemeral=True)
    else:
        await interaction.response.send_message(embed=discord.Embed(
            description="An error occurred while executing the command.",
            color=discord.Color.red()
        ), ephemeral=True)
        logger.error(f"Error in command '{interaction.command.name}': {error}")

async def setup(bot: commands.Bot):
    cog = ReportCog(bot)
    await bot.add_cog(cog)
    bot.tree.on_error = on_command_error
