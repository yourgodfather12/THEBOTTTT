import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import List, Tuple

import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import County, RecentPurchase, AsyncSessionLocal

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StoreCog(commands.Cog):
    REACTION_TIMEOUT = 60.0

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.county_lock = asyncio.Lock()
        logger.info("StoreCog initialized.")

    async def cog_load(self):
        await self.initialize()

    async def initialize(self) -> None:
        """Initialize the cog by ensuring the database is set up."""
        async with self.county_lock:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(County))
                counties = result.scalars().all()
                if not counties:
                    await self.load_default_counties(session)

    async def load_default_counties(self, session: AsyncSession) -> None:
        """Load default county data into the database."""
        config_path = Path(__file__).parent.parent / 'config' / 'county_config.py'
        logger.debug(f"Looking for configuration file at {config_path}")
        if not config_path.exists():
            logger.error(f"Configuration file not found at {config_path}")
            return

        try:
            spec = importlib.util.spec_from_file_location("county_config", config_path)
            county_config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(county_config)
            county_data = county_config.get_county_folder_counts()
            if not county_data:
                logger.warning("No county data found in the configuration.")
                return

            for county_name, folder_count in county_data.items():
                county = County(name=county_name, folder_count=folder_count)
                session.add(county)
            await session.commit()
            logger.info("County data loaded successfully.")
            logger.debug(f"County data: {county_data}")
        except (ImportError, AttributeError, FileNotFoundError) as e:
            logger.error(f"Error loading county configuration: {e}")

    async def save_recent_purchase(self, session: AsyncSession, username: str, county_name: str, price: int) -> None:
        """Save a recent purchase to the database."""
        purchase = RecentPurchase(username=username, county_name=county_name, price=price)
        session.add(purchase)
        await session.commit()

    def calculate_price(self, num_folders: int) -> int:
        """Calculate the price based on the number of folders."""
        if num_folders < 10:
            return 5
        elif 10 <= num_folders <= 20:
            return 10
        elif 21 <= num_folders <= 50:
            return 20
        else:
            return 50

    @app_commands.command(name="shop", description="Displays the shop with available county folders.")
    @app_commands.default_permissions()
    async def shop(self, interaction: discord.Interaction):
        """Display the shop with available county folders."""
        async with self.county_lock:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(County))
                counties = result.scalars().all()
                if not counties:
                    await interaction.response.send_message("County data is not available.", ephemeral=True)
                    return

                try:
                    counties_sorted = sorted((county.name, county.folder_count) for county in counties)
                    logger.debug(f"Counties sorted for shop: {counties_sorted}")
                    embed = self.create_shop_embed(counties_sorted)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logger.error(f"Error in 'shop' command: {e}")
                    await interaction.response.send_message("An error occurred while fetching the shop. Please try again later.", ephemeral=True)

    def create_shop_embed(self, counties_sorted: List[Tuple[str, int]]) -> discord.Embed:
        """Create a single embed for the shop command."""
        embed = discord.Embed(title="Kentucky County Folders Shop", color=discord.Color.blue())
        county_list = "\n".join([f"{county}: {num_folders} folders - ${self.calculate_price(num_folders)} KyBucks" for county, num_folders in counties_sorted])
        if not county_list:
            county_list = "No available counties at the moment."
        embed.add_field(name="Available Counties", value=county_list, inline=False)
        logger.debug(f"Embed created with counties: {county_list}")
        return embed

    @app_commands.command(name="buy", description="Buy a county folder from the shop.")
    @app_commands.default_permissions()
    @app_commands.describe(county_name="The name of the county folder to buy")
    async def buy(self, interaction: discord.Interaction, county_name: str):
        """Allow users to buy a county folder from the shop."""
        async with self.county_lock:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(County).filter_by(name=county_name))
                county = result.scalars().first()
                if county is None:
                    await interaction.response.send_message("Invalid county name. Please check the county name and try again.", ephemeral=True)
                    return

                currency_cog = self.bot.get_cog('CurrencySystemCog')
                if currency_cog is None:
                    await interaction.response.send_message("Currency system is not available.", ephemeral=True)
                    return

                try:
                    balance = await currency_cog.get_balance(interaction.user.id)
                    price = self.calculate_price(county.folder_count)
                    if balance < price:
                        await interaction.response.send_message(
                            f"{interaction.user.mention}, you do not have enough KyBucks to buy this county folder. Your balance is {balance} KyBucks, but you need {price} KyBucks.", ephemeral=True
                        )
                        return

                    await self.send_confirmation(interaction, county_name, price, currency_cog, session)
                except Exception as e:
                    logger.error(f"Error in 'buy' command: {e}")
                    await interaction.response.send_message("An error occurred while processing your purchase. Please try again later.", ephemeral=True)

    async def send_confirmation(self, interaction: discord.Interaction, county_name: str, price: int, currency_cog, session: AsyncSession) -> None:
        """Send a purchase confirmation message."""
        try:
            confirmation_view = ConfirmationView(interaction.user, county_name, price, currency_cog, session, self)
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Confirmation",
                    description=f"Are you sure you want to buy {county_name} for ${price} KyBucks?",
                    color=discord.Color.green()
                ),
                view=confirmation_view,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in send_confirmation: {e}")
            await interaction.followup.send("An error occurred during the confirmation process. Please try again later.", ephemeral=True)

    @app_commands.command(name="topspenders", description="Display the top spenders leaderboard.")
    @app_commands.default_permissions()
    async def topspenders(self, interaction: discord.Interaction):
        """Display the top spenders leaderboard."""
        currency_cog = self.bot.get_cog('CurrencySystemCog')
        if currency_cog is None:
            await interaction.response.send_message("Currency system is not available.", ephemeral=True)
            return

        try:
            top_spenders = await currency_cog.get_top_spenders()
            embed = discord.Embed(title="Top Spenders Leaderboard", color=discord.Color.gold())
            for user_id, amount in top_spenders:
                user = self.bot.get_user(user_id)
                if user:
                    embed.add_field(name=user.name, value=f"{amount} KyBucks", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in 'topspenders' command: {e}")
            await interaction.response.send_message("An error occurred while fetching the leaderboard. Please try again later.", ephemeral=True)

    @app_commands.command(name="recentpurchases", description="Display the most recent purchases.")
    @app_commands.default_permissions()
    async def recentpurchases(self, interaction: discord.Interaction):
        """Display the most recent purchases."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(RecentPurchase).order_by(RecentPurchase.timestamp.desc()).limit(10))
                purchases = result.scalars().all()
                if not purchases:
                    await interaction.response.send_message("No recent purchases found.", ephemeral=True)
                    return

                embed = discord.Embed(title="Recent Purchases", color=discord.Color.purple())
                for purchase in purchases:
                    embed.add_field(name=purchase.username, value=f"Purchased {purchase.county_name} for ${purchase.price} KyBucks", inline=False)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in 'recentpurchases' command: {e}")
            await interaction.response.send_message("An error occurred while fetching recent purchases. Please try again later.", ephemeral=True)

class ConfirmationView(discord.ui.View):
    def __init__(self, user: discord.User, county_name: str, price: int, currency_cog, session: AsyncSession, cog: StoreCog):
        super().__init__(timeout=StoreCog.REACTION_TIMEOUT)
        self.user = user
        self.county_name = county_name
        self.price = price
        self.currency_cog = currency_cog
        self.session = session
        self.cog = cog

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("You cannot confirm this purchase.", ephemeral=True)
            return

        await self.currency_cog.update_balance(self.user.id, -self.price)
        await self.cog.save_recent_purchase(self.session, self.user.name, self.county_name, self.price)
        await interaction.response.send_message(
            f"{self.user.mention}, you have successfully purchased {self.county_name} for ${self.price} KyBucks.",
            ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("You cannot cancel this purchase.", ephemeral=True)
            return

        await interaction.response.send_message("Purchase cancelled.", ephemeral=True)
        self.stop()

async def setup(bot: commands.Bot) -> None:
    cog = StoreCog(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
