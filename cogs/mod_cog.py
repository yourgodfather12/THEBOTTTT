import asyncio
import logging
import os
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from logging.handlers import RotatingFileHandler

# Ensure the logs directory exists
os.makedirs( 'logs', exist_ok=True )

# Set up rotating logging
log_handler = RotatingFileHandler( 'logs/moderation.log', maxBytes=5 * 1024 * 1024, backupCount=2 )
log_formatter = logging.Formatter( '%(asctime)s:%(levelname)s:%(name)s: %(message)s' )
log_handler.setFormatter( log_formatter )
logger = logging.getLogger( __name__ )
logger.setLevel( logging.INFO )
logger.addHandler( log_handler )


class ModCog( commands.Cog ):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def check_permission(self, interaction: discord.Interaction, permission: str) -> bool:
        """Check if the user has the required permission."""
        has_permission = (
                getattr( interaction.user.guild_permissions, permission, False ) or
                discord.utils.get( interaction.user.roles, name="Admin" ) in interaction.user.roles or
                discord.utils.get( interaction.user.roles, name="Moderator" ) in interaction.user.roles
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

    async def send_embed_message(self, interaction: discord.Interaction, title: str, description: str,
                                 color: discord.Color = discord.Color.default()):
        """Send an embed message to the user."""
        embed = discord.Embed( title=title, description=description, color=color )
        if interaction.response.is_done():
            await interaction.followup.send( embed=embed, ephemeral=True )
        else:
            await interaction.response.send_message( embed=embed, ephemeral=True )

    async def kick_or_ban(self, interaction: discord.Interaction, user: discord.Member, action: str,
                          reason: Optional[str] = None):
        """Handle kick or ban actions."""
        if await self.check_permission( interaction, f"{action}_members" ):
            if reason is None:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    f"Please provide a reason for {action}ing {user.mention}.",
                    discord.Color.red()
                )
                return

            try:
                await getattr( user, action )( reason=reason )
                await self.send_embed_message(
                    interaction,
                    f"User {action.capitalize()}ed",
                    f"{user.mention} has been {action}ed for: {reason}.",
                    discord.Color.orange()
                )
                logger.info( f"User {user.name} has been {action}ed for: {reason}" )
            except discord.Forbidden:
                await self.send_embed_message(
                    interaction,
                    "Permission Denied",
                    f"I do not have permission to {action} {user.mention}.",
                    discord.Color.red()
                )
                logger.error( f"Failed to {action} {user.name}: Missing Permissions" )
            except discord.HTTPException as e:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    f"An error occurred while trying to {action} {user.mention}.",
                    discord.Color.red()
                )
                logger.error( f"Failed to {action} {user.name}: {e}" )

    @app_commands.command( name="warn", description="Warns a user." )
    @app_commands.describe( user="The user to warn", reason="The reason for the warning" )
    @app_commands.default_permissions( kick_members=True )
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Warn a user."""
        if await self.check_permission( interaction, "kick_members" ):
            if reason is None:
                await self.send_embed_message( interaction, "Warning",
                                               f"Please provide a reason for warning {user.mention}.",
                                               discord.Color.red() )
            else:
                await self.send_embed_message( interaction, "User Warned",
                                               f"{user.mention} has been warned for: {reason}.",
                                               discord.Color.orange() )
                logger.info( f"User {user.name} has been warned for: {reason}" )

    @app_commands.command( name="kick", description="Kicks a user from the server." )
    @app_commands.describe( user="The user to kick", reason="The reason for kicking" )
    @app_commands.default_permissions( kick_members=True )
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Kick a user."""
        await self.kick_or_ban( interaction, user, "kick", reason )

    @app_commands.command( name="ban", description="Bans a user from the server." )
    @app_commands.describe( user="The user to ban", reason="The reason for banning" )
    @app_commands.default_permissions( ban_members=True )
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Ban a user."""
        await self.kick_or_ban( interaction, user, "ban", reason )

    @app_commands.command( name="mute", description="Mutes a user, preventing them from sending messages." )
    @app_commands.describe( user="The user to mute", reason="The reason for muting" )
    @app_commands.default_permissions( manage_roles=True )
    async def mute(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Mute a user."""
        if await self.check_permission( interaction, "manage_roles" ):
            muted_role = discord.utils.get( interaction.guild.roles, name="Muted" )

            if muted_role is None:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    "The 'Muted' role does not exist. Please create it.",
                    discord.Color.red()
                )
                return

            if reason is None:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    f"Please provide a reason for muting {user.mention}.",
                    discord.Color.red()
                )
                return

            try:
                await user.add_roles( muted_role, reason=reason )
                await self.send_embed_message(
                    interaction,
                    "User Muted",
                    f"{user.mention} has been muted for: {reason}.",
                    discord.Color.orange()
                )
                logger.info( f"User {user.name} has been muted for: {reason}" )
            except discord.Forbidden:
                await self.send_embed_message(
                    interaction,
                    "Permission Denied",
                    "I do not have permission to add roles.",
                    discord.Color.red()
                )
                logger.error( f"Failed to mute {user.name}: Missing Permissions" )
            except discord.HTTPException as e:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    "An error occurred while trying to mute the user.",
                    discord.Color.red()
                )
                logger.error( f"Failed to mute {user.name}: {e}" )

    @app_commands.command( name="unmute", description="Unmutes a previously muted user." )
    @app_commands.describe( user="The user to unmute" )
    @app_commands.default_permissions( manage_roles=True )
    async def unmute(self, interaction: discord.Interaction, user: discord.Member):
        """Unmute a user."""
        if await self.check_permission( interaction, "manage_roles" ):
            muted_role = discord.utils.get( interaction.guild.roles, name="Muted" )
            if muted_role in user.roles:
                try:
                    await user.remove_roles( muted_role )
                    await self.send_embed_message(
                        interaction,
                        "User Unmuted",
                        f"{user.mention} has been unmuted.",
                        discord.Color.orange()
                    )
                    logger.info( f"User {user.name} has been unmuted" )
                except discord.Forbidden:
                    await self.send_embed_message(
                        interaction,
                        "Permission Denied",
                        "I do not have permission to remove roles.",
                        discord.Color.red()
                    )
                    logger.error( f"Failed to unmute {user.name}: Missing Permissions" )
                except discord.HTTPException as e:
                    await self.send_embed_message(
                        interaction,
                        "Error",
                        "An error occurred while trying to unmute the user.",
                        discord.Color.red()
                    )
                    logger.error( f"Failed to unmute {user.name}: {e}" )
            else:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    f"{user.mention} is not muted.",
                    discord.Color.red()
                )

    @app_commands.command( name="clear", description="Clears a specified number of messages from the current channel." )
    @app_commands.describe( amount="The number of messages to clear" )
    @app_commands.default_permissions( manage_messages=True )
    async def clear(self, interaction: discord.Interaction, amount: int):
        """Clear a number of messages from the channel."""
        if amount <= 0:
            await self.send_embed_message(
                interaction,
                "Error",
                "Please provide a valid number of messages to clear.",
                discord.Color.red()
            )
            return

        if await self.check_permission( interaction, "manage_messages" ):
            try:
                await interaction.channel.purge( limit=amount + 1 )
                await self.send_embed_message(
                    interaction,
                    "Messages Cleared",
                    f"{amount} messages cleared.",
                    discord.Color.green()
                )
                logger.info( f"Cleared {amount} messages in channel {interaction.channel.name}" )
            except discord.Forbidden:
                await self.send_embed_message(
                    interaction,
                    "Permission Denied",
                    "I don't have permission to delete messages.",
                    discord.Color.red()
                )
                logger.error( "Failed to clear messages: Missing Permissions" )
            except discord.HTTPException as e:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    "An error occurred while trying to clear messages.",
                    discord.Color.red()
                )
                logger.error( f"Failed to clear messages: {e}" )

    @app_commands.command( name="tempban", description="Temporarily bans a user for a specified duration." )
    @app_commands.describe( user="The user to temporarily ban", duration="The duration of the ban",
                            unit="The time unit for the duration (seconds, minutes, hours, days)",
                            reason="The reason for the ban" )
    @app_commands.default_permissions( ban_members=True )
    async def tempban(self, interaction: discord.Interaction, user: discord.Member, duration: int, unit: str,
                      reason: Optional[str] = None):
        """Temporarily ban a user for a specified duration."""
        if await self.check_permission( interaction, "ban_members" ):
            if reason is None:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    f"Please provide a reason for tempbanning {user.mention}.",
                    discord.Color.red()
                )
                return

            try:
                duration_in_seconds = self.convert_duration_to_seconds( duration, unit )
                if duration_in_seconds is None:
                    await self.send_embed_message(
                        interaction,
                        "Error",
                        "Invalid time unit specified. Please use seconds, minutes, hours, or days.",
                        discord.Color.red()
                    )
                    return

                await interaction.guild.ban( user, reason=reason )
                await self.send_embed_message(
                    interaction,
                    "User Temporarily Banned",
                    f"{user.mention} has been temporarily banned for {duration} {unit}(s).",
                    discord.Color.orange()
                )
                logger.info( f"User {user.name} has been temporarily banned for {duration} {unit}(s)" )

                await asyncio.sleep( duration_in_seconds )
                await interaction.guild.unban( user, reason="Tempban duration expired." )
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"{user.mention} has been unbanned after {duration} {unit}(s).",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
                logger.info( f"User {user.name} has been unbanned after {duration} {unit}(s)" )
            except discord.Forbidden:
                await self.send_embed_message(
                    interaction,
                    "Permission Denied",
                    "I do not have permission to ban this user.",
                    discord.Color.red()
                )
                logger.error( f"Failed to tempban {user.name}: Missing Permissions" )
            except discord.HTTPException as e:
                await self.send_embed_message(
                    interaction,
                    "Error",
                    "An error occurred while trying to tempban the user.",
                    discord.Color.red()
                )
                logger.error( f"Failed to tempban {user.name}: {e}" )

    def convert_duration_to_seconds(self, duration: int, unit: str) -> Optional[int]:
        """Convert duration to seconds based on the unit provided."""
        units_to_seconds = {
            "seconds": 1,
            "minutes": 60,
            "hours": 3600,
            "days": 86400
        }
        return duration * units_to_seconds.get( unit, None )


# Error handler for slash commands
@commands.Cog.listener()
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handle command errors."""
    if isinstance( error, app_commands.MissingPermissions ):
        await interaction.response.send_message( embed=discord.Embed(
            description="You do not have the required permissions to run this command.",
            color=discord.Color.red()
        ), ephemeral=True )
    elif isinstance( error, app_commands.BotMissingPermissions ):
        await interaction.response.send_message( embed=discord.Embed(
            description="I do not have the required permissions to run this command.",
            color=discord.Color.red()
        ), ephemeral=True )
    else:
        await interaction.response.send_message( embed=discord.Embed(
            description="An error occurred while executing the command.",
            color=discord.Color.red()
        ), ephemeral=True )
        logger.error( f"Error in command '{interaction.command.name}': {error}" )


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    cog = ModCog( bot )
    await bot.add_cog( cog )
    bot.tree.on_error = on_command_error
