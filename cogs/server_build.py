import asyncio
import logging
from typing import List, Dict

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

# Constants for category names and roles
CATEGORY_NAMES = {
    "rules_verify": "Rules & Verify",
    "misc": "Misc",
    "admin_mod": "Admin & Mod",
}

ROLES_PERMISSIONS = {
    "Bot": {"permissions": discord.Permissions.none(), "color": discord.Color(0x0019ff)},
    "Admin": {"permissions": discord.Permissions(administrator=True), "color": discord.Color(0xff0000)},
    "Mod": {"permissions": discord.Permissions(
        read_message_history=True,
        manage_messages=True,
        mention_everyone=True,
        add_reactions=True,
        attach_files=True,
        embed_links=True,
        send_messages=True,
        create_instant_invite=True,
        view_channel=True
    ), "color": discord.Color(0xff8b00)},
    "VIP": {"permissions": discord.Permissions(
        read_message_history=True,
        mention_everyone=True,
        add_reactions=True,
        attach_files=True,
        embed_links=True,
        send_messages=True,
        view_channel=True
    ), "color": discord.Color(0xe8ff00)},
    "Member": {"permissions": discord.Permissions(
        read_message_history=True,
        mention_everyone=True,
        add_reactions=True,
        attach_files=True,
        embed_links=True,
        send_messages=True,
        view_channel=True
    ), "color": discord.Color(0x17ff00)},
    "Must Verify": {"permissions": discord.Permissions.none(), "color": discord.Color(0xffffff)}
}

STATE_FIPS_CODES: Dict[str, str] = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05", "California": "06",
    "Colorado": "08", "Connecticut": "09", "Delaware": "10", "Florida": "12", "Georgia": "13",
    "Hawaii": "15", "Idaho": "16", "Illinois": "17", "Indiana": "18", "Iowa": "19",
    "Kansas": "20", "Kentucky": "21", "Louisiana": "22", "Maine": "23", "Maryland": "24",
    "Massachusetts": "25", "Michigan": "26", "Minnesota": "27", "Mississippi": "28",
    "Missouri": "29", "Montana": "30", "Nebraska": "31", "Nevada": "32", "New Hampshire": "33",
    "New Jersey": "34", "New Mexico": "35", "New York": "36", "North Carolina": "37",
    "North Dakota": "38", "Ohio": "39", "Oklahoma": "40", "Oregon": "41", "Pennsylvania": "42",
    "Rhode Island": "44", "South Carolina": "45", "South Dakota": "46", "Tennessee": "47",
    "Texas": "48", "Utah": "49", "Vermont": "50", "Virginia": "51", "Washington": "53",
    "West Virginia": "54", "Wisconsin": "55", "Wyoming": "56"
}

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServerBuilder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def create_roles(self, guild: discord.Guild) -> None:
        """Create roles in the guild based on predefined permissions and colors."""
        existing_roles = {role.name: role for role in guild.roles}
        for role_name, details in ROLES_PERMISSIONS.items():
            if role_name not in existing_roles:
                permissions = details["permissions"]
                color = details["color"]
                try:
                    await guild.create_role(name=role_name, permissions=permissions, color=color)
                    logger.info(f"Role {role_name} created with permissions: {permissions}")
                except discord.HTTPException as e:
                    logger.error(f"Failed to create role {role_name}: {e}")

    async def create_category(self, guild: discord.Guild, category_name: str) -> discord.CategoryChannel:
        """Create a category in the guild if it doesn't already exist."""
        existing_category = discord.utils.get(guild.categories, name=category_name)
        if not existing_category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            try:
                category = await guild.create_category(category_name, overwrites=overwrites)
                logger.info(f"Category {category_name} created.")
                return category
            except discord.HTTPException as e:
                logger.error(f"Failed to create category {category_name}: {e}")
                raise
        logger.info(f"Category {category_name} already exists.")
        return existing_category

    async def create_channels(self, guild: discord.Guild) -> None:
        """Create predefined channels under respective categories in the guild."""
        categories_to_channels = {
            CATEGORY_NAMES["rules_verify"]: ["rules", "verify"],
            CATEGORY_NAMES["admin_mod"]: ["admin", "mod", "logs"],
            CATEGORY_NAMES["misc"]: ["chat", "requests", "mega-dropbox"]
        }

        for category_name, channels in categories_to_channels.items():
            category = await self.create_category(guild, category_name)
            for channel_name in channels:
                existing_channel = discord.utils.get(category.channels, name=channel_name)
                if not existing_channel:
                    try:
                        await guild.create_text_channel(channel_name, category=category)
                        logger.info(f"Channel {channel_name} created under category {category_name}.")
                    except discord.HTTPException as e:
                        logger.error(f"Failed to create channel {channel_name} under category {category_name}: {e}")

    async def fetch_counties(self, state_fips_code: str) -> List[str]:
        """Fetch counties for a given state using the Census API."""
        url = f'https://api.census.gov/data/2019/pep/population?get=NAME&for=county:*&in=state:{state_fips_code}'
        async with self.session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                counties = [item[0].replace(" County", "") for item in data[1:]]  # Skip the header row and remove "County"
                logger.info(f"Fetched counties for state FIPS code {state_fips_code}.")
                return counties
            else:
                logger.error(f"Failed to fetch counties: HTTP {response.status}")
                return []

    async def create_county_channels(self, guild: discord.Guild, state_name: str) -> None:
        """Create text channels for each county in a given state."""
        state_fips_code = STATE_FIPS_CODES.get(state_name)
        if not state_fips_code:
            raise ValueError(f"Invalid state name: {state_name}")

        counties = await self.fetch_counties(state_fips_code)
        if not counties:
            raise ValueError(f"No counties found for state: {state_name}")

        max_channels_per_category = 50
        for i in range(0, len(counties), max_channels_per_category):
            category_name = f"Counties ({counties[i]} - {counties[min(i + max_channels_per_category - 1, len(counties) - 1)]})"
            category = await self.create_category(guild, category_name)
            for county in counties[i:i + max_channels_per_category]:
                existing_channel = discord.utils.get(category.channels, name=county)
                if not existing_channel:
                    try:
                        await guild.create_text_channel(county, category=category)
                        logger.info(f"Channel {county} created under category {category_name}.")
                        await asyncio.sleep(1)  # Add delay to prevent rate limits
                    except discord.HTTPException as e:
                        logger.error(f"Failed to create channel {county} under category {category_name}: {e}")

    async def has_permissions(self, interaction: discord.Interaction, permissions: List[str]) -> bool:
        """Check if the bot has the required permissions."""
        guild = interaction.guild
        if not guild:
            return False

        missing_permissions = [perm for perm in permissions if not getattr(guild.me.guild_permissions, perm)]
        if missing_permissions:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"Error: I don't have permission to {', '.join(missing_permissions)}.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="build", description="Build the server by creating roles, categories, and channels for a specified state.")
    @app_commands.describe(state_name="The name of the state to build channels for.")
    @app_commands.default_permissions(manage_roles=True, manage_channels=True)
    async def build(self, interaction: discord.Interaction, state_name: str) -> None:
        """Build the server by creating roles, categories, and channels for a specified state."""
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                embed=discord.Embed(description="Error: This command can only be used in a guild.", color=discord.Color.red()),
                ephemeral=True
            )

        required_permissions = ['manage_roles', 'manage_channels']
        if not await self.has_permissions(interaction, required_permissions):
            return

        try:
            await self.create_roles(guild)
            await self.create_channels(guild)
            await self.create_county_channels(guild, state_name)

            await interaction.response.send_message(
                embed=discord.Embed(description="Server built successfully!", color=discord.Color.green())
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=discord.Embed(description="Error: I don't have permission to perform this action.", color=discord.Color.red()),
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"Error: An unexpected error occurred: {e}", color=discord.Color.red()),
                ephemeral=True
            )
        except ValueError as e:
            await interaction.response.send_message(
                embed=discord.Embed(description=str(e), color=discord.Color.red()),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            await interaction.response.send_message(
                embed=discord.Embed(description="An unexpected error occurred. Please try again later.", color=discord.Color.red()),
                ephemeral=True
            )

    def cog_unload(self):
        asyncio.create_task(self.session.close())

async def setup(bot: commands.Bot) -> None:
    cog = ServerBuilder(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
