import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from db.database import handle_database_operations  # Ensure this import is correct

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

    async def update_channel_permissions(self, guild, role, send_messages: bool):
        for channel in guild.text_channels:
            await channel.set_permissions(role, send_messages=send_messages)
            await asyncio.sleep(0.5)  # Adding delay to prevent rate limiting

    async def batch_update_permissions(self, guild, role, send_messages: bool):
        tasks = [self.update_channel_permissions(guild, role, send_messages)]
        await asyncio.gather(*tasks)

    async def send_error_message(self, interaction, message):
        await interaction.followup.send(
            embed=discord.Embed(
                description=message,
                color=discord.Color.red()
            ),
            ephemeral=True
        )

    async def send_success_message(self, interaction, message):
        await interaction.followup.send(
            embed=discord.Embed(
                description=message,
                color=discord.Color.green()
            ),
            ephemeral=True
        )

    async def send_info_message(self, interaction, message):
        await interaction.followup.send(
            embed=discord.Embed(
                description=message,
                color=discord.Color.orange()
            ),
            ephemeral=True
        )

    @app_commands.command(name="lockdown", description="Locks down the entire server, preventing all messages except from administrators.")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.batch_update_permissions(interaction.guild, interaction.guild.default_role, send_messages=False)
        await self.send_info_message(interaction, "Server locked down. Only administrators can send messages.")
        logger.info(f"Server locked down by {interaction.user.name} in {interaction.guild.name}")

    @app_commands.command(name="unlockdown", description="Unlocks the server after a lockdown.")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlockdown(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.batch_update_permissions(interaction.guild, interaction.guild.default_role, send_messages=True)
        await self.send_success_message(interaction, "Server unlocked.")
        logger.info(f"Server unlocked by {interaction.user.name} in {interaction.guild.name}")

    @app_commands.command(name="delete_all", description="Delete all channels and categories recursively.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete_all(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            for category in interaction.guild.categories:
                for channel in category.channels:
                    await channel.delete()
                    await asyncio.sleep(0.5)  # Adding delay to prevent rate limiting
                await category.delete()
                await asyncio.sleep(0.5)  # Adding delay to prevent rate limiting
            await self.send_success_message(interaction, "All categories and channels deleted successfully!")
            logger.info(f"All categories and channels deleted by {interaction.user.name} in {interaction.guild.name}")
        except discord.Forbidden:
            await self.send_error_message(interaction, "Error: I don't have permission to perform this action.")
            logger.error(f"Failed to delete channels and categories by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
        except discord.HTTPException as e:
            await self.send_error_message(interaction, f"Error: An unexpected error occurred: {e}")
            logger.error(f"Failed to delete channels and categories by {interaction.user.name} in {interaction.guild.name}: {e}")

    @app_commands.command(name="kick_users", description="Kicks all users with the MUST VERIFY role")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick_users(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        must_verify_role = discord.utils.get(guild.roles, name="MUST VERIFY")
        if must_verify_role is None:
            await self.send_error_message(interaction, "The 'MUST VERIFY' role does not exist.")
            return

        kick_count = 0
        for member in guild.members:
            if must_verify_role in member.roles:
                try:
                    await member.kick(reason="User has not verified within the specified time")
                    kick_count += 1
                    await asyncio.sleep(0.5)  # Adding delay to prevent rate limiting
                except discord.Forbidden:
                    logger.error(f"Failed to kick {member.name} by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
                except discord.HTTPException as e:
                    logger.error(f"Failed to kick {member.name} by {interaction.user.name} in {interaction.guild.name}: {e}")

        await self.send_success_message(interaction, f"{kick_count} users with the 'MUST VERIFY' role have been kicked.")
        logger.info(f"{kick_count} users with the 'MUST VERIFY' role have been kicked by {interaction.user.name} in {interaction.guild.name}")

    @app_commands.command(name="add_role", description="Adds a role to a user.")
    @app_commands.describe(user="The user to add the role to", role="The role to add")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role in user.roles:
            await self.send_error_message(interaction, f"{user.mention} already has the {role.name} role.")
            return
        try:
            await user.add_roles(role)
            await self.send_success_message(interaction, f"Added {role.name} role to {user.mention}.")
            logger.info(f"Added {role.name} role to {user.name} by {interaction.user.name} in {interaction.guild.name}")
        except discord.Forbidden:
            await self.send_error_message(interaction, "I do not have permission to add roles.")
            logger.error(f"Failed to add role {role.name} to {user.name} by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
        except discord.HTTPException as e:
            await self.send_error_message(interaction, "An error occurred while trying to add the role.")
            logger.error(f"Failed to add role {role.name} to {user.name} by {interaction.user.name} in {interaction.guild.name}: {e}")

    @app_commands.command(name="remove_role", description="Removes a role from a user.")
    @app_commands.describe(user="The user to remove the role from", role="The role to remove")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if role not in user.roles:
            await self.send_error_message(interaction, f"{user.mention} does not have the {role.name} role.")
            return
        try:
            await user.remove_roles(role)
            await self.send_success_message(interaction, f"Removed {role.name} role from {user.mention}.")
            logger.info(f"Removed {role.name} role from {user.name} by {interaction.user.name} in {interaction.guild.name}")
        except discord.Forbidden:
            await self.send_error_message(interaction, "I do not have permission to remove roles.")
            logger.error(f"Failed to remove role {role.name} from {user.name} by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
        except discord.HTTPException as e:
            await self.send_error_message(interaction, "An error occurred while trying to remove the role.")
            logger.error(f"Failed to remove role {role.name} from {user.name} by {interaction.user.name} in {interaction.guild.name}: {e}")

    @app_commands.command(name="announce", description="Announces a message to a specific channel.")
    @app_commands.describe(channel="The channel to send the announcement to", message="The message to announce")
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.send(message)
            await self.send_success_message(interaction, f"Announcement sent to {channel.mention}.")
            logger.info(f"Announcement sent to {channel.name} by {interaction.user.name} in {interaction.guild.name}")
        except discord.Forbidden:
            await self.send_error_message(interaction, "I do not have permission to send messages to this channel.")
            logger.error(f"Failed to send announcement to {channel.name} by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
        except discord.HTTPException as e:
            await self.send_error_message(interaction, "An error occurred while trying to send the announcement.")
            logger.error(f"Failed to send announcement to {channel.name} by {interaction.user.name} in {interaction.guild.name}: {e}")

    @app_commands.command(name="populate_db", description="Retroactively populate all database tables.")
    async def populate_db(self, interaction: discord.Interaction):
        await interaction.response.send_message("Starting database population. This may take a while...", ephemeral=True)
        try:
            await handle_database_operations(self.bot)
            await self.send_success_message(interaction, "Database population completed successfully.")
        except Exception as e:
            logger.error(f"Error during database population: {e}")
            await self.send_error_message(interaction, f"An error occurred: {e}")

    @app_commands.command(name="change_server_name", description="Changes the server's name.")
    @app_commands.describe(name="The new name for the server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def change_server_name(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.guild.edit(name=name)
            await self.send_success_message(interaction, f"Server name changed to {name}.")
            logger.info(f"Server name changed to {name} by {interaction.user.name} in {interaction.guild.name}")
        except discord.Forbidden:
            await self.send_error_message(interaction, "I do not have permission to change the server name.")
            logger.error(f"Failed to change the server name by {interaction.user.name} in {interaction.guild.name}: Missing Permissions")
        except discord.HTTPException as e:
            await self.send_error_message(interaction, "An error occurred while trying to change the server name.")
            logger.error(f"Failed to change the server name by {interaction.user.name} in {interaction.guild.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
