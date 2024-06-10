import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from typing import Optional
import logging
import aiofiles

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 5
SEARCH_COOLDOWN = 3600  # 1 hour in seconds
KENTUCKY_BLUE = discord.Color.from_rgb(0, 84, 164)

class SearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.search_cooldown = commands.CooldownMapping.from_cooldown(5, SEARCH_COOLDOWN, commands.BucketType.user)

    async def cog_check(self, interaction: discord.Interaction) -> bool:
        allowed_roles = {'Admin', 'Mod', 'VIP', 'Member'}
        return any(role.name in allowed_roles for role in interaction.user.roles)

    async def send_dm(self, user: discord.User, content: Optional[str] = None, embed: Optional[discord.Embed] = None):
        try:
            if content:
                await user.send(content=content)
            if embed:
                await user.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot send DM to user {user.name}")

    def get_search_cooldown_message(self, retry_after: float) -> str:
        minutes = int(retry_after // 60)
        seconds = int(retry_after % 60)
        time_unit = "minute" if minutes == 1 else "minutes" if minutes > 0 else "second"
        retry_after_str = f"{minutes} {time_unit}" if minutes > 0 else f"{seconds} seconds"
        return f"You are on cooldown. Please wait {retry_after_str} before using the command again."

    async def search_images(self, folder_path: str, keyword: str) -> list:
        try:
            return [filename for filename in os.listdir(folder_path) if keyword.lower() in filename.lower()]
        except Exception as e:
            logger.error(f"Error searching images in folder '{folder_path}': {e}")
            return []

    async def get_paginated_images(self, found_images: list, page_num: int) -> list:
        start_index = (page_num - 1) * RESULTS_PER_PAGE
        end_index = min(start_index + RESULTS_PER_PAGE, len(found_images))
        return found_images[start_index:end_index]

    @app_commands.command(name="search_image", description="Search for images in local storage")
    @app_commands.describe(keyword="Keyword to search for images")
    async def search_image(self, interaction: discord.Interaction, keyword: str):
        """Search for images in local storage"""
        if not keyword.strip():
            await interaction.response.send_message( "Please provide a valid keyword to search.", ephemeral=True )
            return

        bucket = self.search_cooldown.get_bucket( interaction )
        retry_after = bucket.update_rate_limit()
        if retry_after:
            cooldown_message = self.get_search_cooldown_message( retry_after )
            await interaction.response.send_message( cooldown_message, ephemeral=True )
            return

        folder_path = os.getenv( "IMAGE_FOLDER_PATH", "C:/Users/joshu/PycharmProjects/BOT-4-26-2024/database/data" )
        if not os.path.exists( folder_path ):
            await interaction.response.send_message( "Folder not found.", ephemeral=True )
            logger.error( f"Folder not found: {folder_path}" )
            return

        found_images = await self.search_images( folder_path, keyword )
        total_images = len( found_images )
        if total_images == 0:
            await interaction.response.send_message( "No images found matching the keyword.", ephemeral=True )
            return

        total_pages = (total_images + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE

        for page_num in range( 1, total_pages + 1 ):
            paginated_images = await self.get_paginated_images( found_images, page_num )

            embeds = []
            files = []
            for image_name in paginated_images:
                file_path = os.path.join( folder_path, image_name )
                try:
                    async with aiofiles.open( file_path, "rb" ) as file:
                        file_data = discord.File( await file.read(), filename=image_name )
                        embed = discord.Embed( title=f"Search Results for '{keyword}'", color=KENTUCKY_BLUE )
                        embed.set_footer( text=f"Page {page_num}/{total_pages}" )
                        embed.set_image( url=f"attachment://{image_name}" )
                        files.append( file_data )
                        embeds.append( embed )
                except Exception as e:
                    logger.error( f"Error opening file {file_path}: {e}" )
                    continue

            tasks = [interaction.followup.send( embed=embed, file=file ) for embed, file in zip( embeds, files )]
            await asyncio.gather( *tasks )

        remaining_searches = max( 0, 5 - bucket._tokens )
        remaining_message = f"Check your DMs for more information. You have {remaining_searches} searches remaining for the hour."
        await interaction.followup.send( remaining_message )
        await self.send_dm( interaction.user, remaining_message )

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info("Bot is ready. Syncing commands...")
        await self.bot.tree.sync()

async def setup(bot: commands.Bot):
    await bot.add_cog(SearchCog(bot))
