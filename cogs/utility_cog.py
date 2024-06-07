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

    @app_commands.command(name="listroles", description="Lists all roles available in the server.")
    async def listroles(self, interaction: discord.Interaction):
        roles = [role.name for role in interaction.guild.roles]
        await interaction.response.send_message(
            embed=discord.Embed(
                description=', '.join(roles),
                color=discord.Color.blue()
            )
        )

    @app_commands.command(name="clearchat", description="Clears all messages from the current channel.")
    async def clearchat(self, interaction: discord.Interaction):
        if await self.check_permission(interaction, "manage_messages"):
            await interaction.channel.purge()
            embed = discord.Embed(
                description="All messages cleared.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"All messages cleared in channel {interaction.channel.name}")
        else:
            embed = discord.Embed(
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list_commands", description="Lists all commands in every cog.")
    async def list_commands(self, interaction: discord.Interaction):
        commands_list = []
        for cog in self.bot.cogs.values():
            for command in cog.get_app_commands():
                commands_list.append(command.name)
        commands_str = ', '.join(commands_list)
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Commands: {commands_str}",
                color=discord.Color.blue()
            ),
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(UtilityCog(bot))
