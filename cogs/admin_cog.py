import asyncio
import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

# Ensure the logs directory exists
if not os.path.exists('logs'):
    os.makedirs('logs')

# Set up logging
logging.basicConfig(
    filename='logs/admin.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tree = bot.tree

    async def check_permission(self, interaction: discord.Interaction, permission: str) -> bool:
        admin_role = discord.utils.get(interaction.guild.roles, name="Admin")
        has_permission = getattr(interaction.user.guild_permissions, permission, False) or (admin_role in interaction.user.roles if admin_role else False)
        if not has_permission:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You do not have permission to use this command.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        return has_permission

    @app_commands.command(name="lockdown", description="Locks down the entire server, preventing all messages except from administrators.")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message(
            embed=discord.Embed(
                description="Server locked down. Only administrators can send messages.",
                color=discord.Color.orange()
            )
        )
        logger.info("Server locked down")

    @app_commands.command(name="unlockdown", description="Unlocks the server after a lockdown.")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlockdown(self, interaction: discord.Interaction):
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(interaction.guild.default_role, send_messages=True)
        await interaction.response.send_message(
            embed=discord.Embed(
                description="Server unlocked.",
                color=discord.Color.green()
            )
        )
        logger.info("Server unlocked")

    @app_commands.command(name="delete_all", description="Delete all channels and categories recursively.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete_all(self, interaction: discord.Interaction):
        try:
            for category in interaction.guild.categories:
                for channel in category.channels:
                    await channel.delete()
                    await asyncio.sleep(1)  # Adding delay to prevent rate limiting
                await category.delete()
                await asyncio.sleep(1)  # Adding delay to prevent rate limiting
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="All categories and channels deleted successfully!",
                    color=discord.Color.green()
                )
            )
            logger.info("All categories and channels deleted")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="Error: I don't have permission to perform this action.",
                    color=discord.Color.red()
                )
            )
            logger.error("Failed to delete channels and categories: Missing Permissions")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Error: An unexpected error occurred: {e}",
                    color=discord.Color.red()
                )
            )
            logger.error(f"Failed to delete channels and categories: {e}")

    @app_commands.command(name="kick_users", description="Kicks all users with the Must Verify role")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_users(self, interaction: discord.Interaction):
        guild = interaction.guild
        must_verify_role = discord.utils.get(guild.roles, name="Must Verify")
        if must_verify_role is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="The 'Must Verify' role does not exist.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        kick_count = 0
        for member in guild.members:
            if must_verify_role in member.roles:
                try:
                    await member.kick(reason="User has not verified within the specified time")
                    kick_count += 1
                    await asyncio.sleep(1)  # Adding delay to prevent rate limiting
                except discord.Forbidden:
                    logger.error(f"Failed to kick {member.name}: Missing Permissions")
                except discord.HTTPException as e:
                    logger.error(f"Failed to kick {member.name}: {e}")

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"{kick_count} users with the 'Must Verify' role have been kicked.",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        logger.info(f"{kick_count} users with the 'Must Verify' role have been kicked")

    @app_commands.command(name="add_role", description="Adds a role to a user.")
    @app_commands.describe(user="The user to add the role to", role="The role to add")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        try:
            await user.add_roles(role)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Added {role.name} role to {user.mention}.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"Added {role.name} role to {user.name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="I do not have permission to add roles.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to add role {role.name} to {user.name}: Missing Permissions")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while trying to add the role.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to add role {role.name} to {user.name}: {e}")

    @app_commands.command(name="remove_role", description="Removes a role from a user.")
    @app_commands.describe(user="The user to remove the role from", role="The role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        try:
            await user.remove_roles(role)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Removed {role.name} role from {user.mention}.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"Removed {role.name} role from {user.name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="I do not have permission to remove roles.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to remove role {role.name} from {user.name}: Missing Permissions")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while trying to remove the role.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to remove role {role.name} from {user.name}: {e}")

    @app_commands.command(name="announce", description="Announces a message to a specific channel.")
    @app_commands.describe(channel="The channel to send the announcement to", message="The message to announce")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        try:
            await channel.send(message)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Announcement sent to {channel.mention}.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"Announcement sent to {channel.name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="I do not have permission to send messages to this channel.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to send announcement to {channel.name}: Missing Permissions")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while trying to send the announcement.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to send announcement to {channel.name}: {e}")

    @app_commands.command(name="change_server_name", description="Changes the server's name.")
    @app_commands.describe(name="The new name for the server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def change_server_name(self, interaction: discord.Interaction, name: str):
        try:
            await interaction.guild.edit(name=name)
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Server name changed to {name}.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )
            logger.info(f"Server name changed to {name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="I do not have permission to change the server name.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error("Failed to change the server name: Missing Permissions")
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="An error occurred while trying to change the server name.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            logger.error(f"Failed to change the server name: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
