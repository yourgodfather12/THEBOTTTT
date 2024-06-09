import logging
from datetime import datetime, timedelta
import os

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import pytz

from db.database import UserCurrency, Transaction, County, RecentPurchase

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./kywins.db')
engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# Timezone setup
eastern = pytz.timezone('US/Eastern')

def has_any_role(member: discord.Member, *role_names: str) -> bool:
    return any(role.name in role_names for role in member.roles)

class CurrencySystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_reward_amount = 10  # Default daily reward amount
        self.kybucks_per_attachment = 3  # Default KyBucks per attachment

    async def get_balance(self, user_id: int) -> int:
        try:
            async with SessionLocal() as db:
                result = await db.execute(select(UserCurrency).filter_by(user_id=user_id))
                user_currency = result.scalar()
                return user_currency.balance if user_currency else 0
        except Exception as e:
            logger.error(f"Error fetching balance for user {user_id}: {e}")
            return 0

    async def update_balance(self, user_id: int, amount: int, description: str = None) -> None:
        async with SessionLocal() as db:
            async with db.begin():
                try:
                    result = await db.execute(select(UserCurrency).filter_by(user_id=user_id).with_for_update())
                    user_currency = result.scalar()
                    if user_currency:
                        user_currency.balance += amount
                    else:
                        user_currency = UserCurrency(user_id=user_id, balance=amount)
                        db.add(user_currency)
                    db.add(Transaction(user_id=user_id, amount=amount, description=description))
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Error updating balance for user {user_id}: {e}")
                    raise
                else:
                    await db.commit()

    async def get_transaction_history(self, user_id: int, limit: int = 10):
        try:
            async with SessionLocal() as db:
                result = await db.execute(select(Transaction).filter_by(user_id=user_id).order_by(Transaction.timestamp.desc()).limit(limit))
                return result.scalars().all()
        except Exception as e:
            logger.error(f"Error fetching transaction history for user {user_id}: {e}")
            return []

    async def send_embed_message(self, interaction: discord.Interaction, title: str, description: str) -> None:
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        try:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            logger.warning(f"Context not found when sending message: {title} - {description}")

    @app_commands.command(name="balance", description="Check your KyBucks balance")
    async def balance(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        balance = await self.get_balance(user_id)
        await self.send_embed_message(interaction, "KyBucks Balance", f"Your current balance is {balance} KyBucks.")

    @app_commands.command(name="give", description="Give KyBucks to another user")
    @app_commands.describe(user="The user to give KyBucks to", amount="The amount of KyBucks to give")
    async def give(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if amount <= 0:
            await self.send_embed_message(interaction, "Error", "The amount must be positive.")
            return

        giver_id = interaction.user.id
        receiver_id = user.id

        if giver_id == receiver_id:
            await self.send_embed_message(interaction, "Error", "You cannot give KyBucks to yourself.")
            return

        giver_balance = await self.get_balance(giver_id)
        if giver_balance < amount:
            await self.send_embed_message(interaction, "Error", "You do not have enough KyBucks.")
            return

        async with SessionLocal() as db:
            async with db.begin():
                try:
                    await self.update_balance(giver_id, -amount, f"Gave {amount} KyBucks to {user.display_name}")
                    await self.update_balance(receiver_id, amount, f"Received {amount} KyBucks from {interaction.user.display_name}")
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Error giving KyBucks from {giver_id} to {receiver_id}: {e}")
                    await self.send_embed_message(interaction, "Error", "An error occurred while processing the transaction.")
                    return

        await self.send_embed_message(interaction, "Success", f"You have successfully given {amount} KyBucks to {user.display_name}.")
        try:
            await user.send(f"You have received {amount} KyBucks from {interaction.user.display_name}.")
        except discord.Forbidden:
            logger.warning(f"Failed to send DM to {user.display_name}")

    @app_commands.command(name="history", description="View your transaction history")
    async def history(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        transactions = await self.get_transaction_history(user_id)
        if not transactions:
            await self.send_embed_message(interaction, "Transaction History", "You have no transaction history.")
            return

        history_message = "Your last transactions:\n"
        for transaction in transactions:
            timestamp_est = transaction.timestamp.astimezone(eastern)
            history_message += f"{timestamp_est.strftime('%Y-%m-%d %H:%M:%S')} - {transaction.amount} KyBucks - {transaction.description}\n"
        await self.send_embed_message(interaction, "Transaction History", history_message)

    @app_commands.command(name="leaderboard", description="View the top users with the most KyBucks")
    async def leaderboard(self, interaction: discord.Interaction):
        try:
            async with SessionLocal() as db:
                result = await db.execute(select(UserCurrency).order_by(UserCurrency.balance.desc()).limit(10))
                top_users = result.scalars().all()
                leaderboard_message = "Top users with the most KyBucks:\n"
                for user_currency in top_users:
                    user = self.bot.get_user(user_currency.user_id)
                    leaderboard_message += f"{user.display_name if user else 'Unknown User'}: {user_currency.balance} KyBucks\n"
                await self.send_embed_message(interaction, "KyBucks Leaderboard", leaderboard_message)
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            await self.send_embed_message(interaction, "Error", "An error occurred while retrieving the leaderboard.")

    @app_commands.command(name="daily", description="Claim your daily KyBucks reward")
    async def daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            async with SessionLocal() as db:
                last_claim = await db.execute(select(Transaction).filter_by(user_id=user_id, description='Daily Reward').order_by(Transaction.timestamp.desc()).limit(1))
                last_claim = last_claim.scalar()
                if last_claim and last_claim.timestamp > datetime.utcnow() - timedelta(days=1):
                    time_left = (last_claim.timestamp + timedelta(days=1)) - datetime.utcnow()
                    hours, remainder = divmod(time_left.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    await self.send_embed_message(interaction, "Daily Reward", f"You have already claimed your daily reward. Try again in {time_left.days}d {hours}h {minutes}m.")
                    return

                await self.update_balance(user_id, self.daily_reward_amount, 'Daily Reward')
                await self.send_embed_message(interaction, "Daily Reward", f"You have claimed your daily reward of {self.daily_reward_amount} KyBucks!")
        except Exception as e:
            logger.error(f"Error claiming daily reward for user {user_id}: {e}")
            await self.send_embed_message(interaction, "Error", "An error occurred while claiming your daily reward.")

    @app_commands.command(name="setdailyreward", description="Set the daily KyBucks reward amount (Admin only)")
    @app_commands.describe(amount="The amount of KyBucks for the daily reward")
    @app_commands.default_permissions(administrator=True)
    async def set_daily_reward(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await self.send_embed_message(interaction, "Error", "The amount must be positive.")
            return

        self.daily_reward_amount = amount
        await self.send_embed_message(interaction, "Daily Reward Set", f"The daily reward amount has been set to {amount} KyBucks.")

    @app_commands.command(name="setattachmentreward", description="Set the KyBucks per attachment reward amount (Admin only)")
    @app_commands.describe(amount="The amount of KyBucks per attachment")
    @app_commands.default_permissions(administrator=True)
    async def set_attachment_reward(self, interaction: discord.Interaction, amount: int):
        if amount <= 0:
            await self.send_embed_message(interaction, "Error", "The amount must be positive.")
            return

        self.kybucks_per_attachment = amount
        await self.send_embed_message(interaction, "Attachment Reward Set", f"The KyBucks per attachment reward amount has been set to {amount} KyBucks.")

    @app_commands.command(name="adminadd", description="Admin: Add KyBucks to a user's balance")
    @app_commands.describe(user="The user to add KyBucks to", amount="The amount of KyBucks to add")
    @app_commands.default_permissions(administrator=True)
    async def admin_add(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if amount <= 0:
            await self.send_embed_message(interaction, "Error", "The amount must be positive.")
            return

        await self.update_balance(user.id, amount, f"Admin added {amount} KyBucks")
        await self.send_embed_message(interaction, "Admin Add", f"Added {amount} KyBucks to {user.display_name}'s balance.")

    @app_commands.command(name="adminremove", description="Admin: Remove KyBucks from a user's balance")
    @app_commands.describe(user="The user to remove KyBucks from", amount="The amount of KyBucks to remove")
    @app_commands.default_permissions(administrator=True)
    async def admin_remove(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if amount <= 0:
            await self.send_embed_message(interaction, "Error", "The amount must be positive.")
            return

        balance = await self.get_balance(user.id)
        if balance < amount:
            await self.send_embed_message(interaction, "Error", f"{user.display_name} does not have enough KyBucks.")
            return

        await self.update_balance(user.id, -amount, f"Admin removed {amount} KyBucks")
        await self.send_embed_message(interaction, "Admin Remove", f"Removed {amount} KyBucks from {user.display_name}'s balance.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.attachments:
            user_id = message.author.id
            kybucks_earned = self.kybucks_per_attachment * len(message.attachments)
            await self.update_balance(user_id, kybucks_earned, 'Earned from attachments')
            try:
                await message.author.send(f"You have earned {kybucks_earned} KyBucks for posting attachments!")
            except discord.Forbidden:
                logger.warning(f"Failed to send DM to {message.author.display_name}")

    # Store cog functionalities
    async def add_new_item(self, item_name, item_cost, folder_path, item_description, item_image_url):
        try:
            async with SessionLocal() as session:
                existing_item = await session.execute(select(County).filter_by(name=item_name))
                if existing_item.scalars().first():
                    return False, "Item already exists."
                new_item = County(name=item_name, folder_count=item_cost, folder_path=folder_path, description=item_description, image_url=item_image_url)
                session.add(new_item)
                await session.commit()
                return True, f"Item {item_name} has been added to the store for {item_cost} KyBucks."
        except Exception as e:
            logger.error(f"Error adding new item {item_name}: {e}")
            return False, "An error occurred while adding the item. Please try again later."

    async def buy_store_item(self, user_id, username, item_name):
        try:
            async with SessionLocal() as session:
                result = await session.execute(select(County).filter_by(name=item_name))
                item = result.scalars().first()
                if not item:
                    return False, "Item does not exist."
                balance = await self.get_balance(user_id)
                if balance < item.folder_count:
                    return False, "Insufficient KyBucks."
                async with session.begin():
                    await self.update_balance(user_id, username, -item.folder_count)
                    new_purchase = RecentPurchase(user_id=user_id, username=username, county_name=item_name, price=item.folder_count)
                    session.add(new_purchase)
                    await session.commit()
                return True, f"You bought {item_name} for {item.folder_count} KyBucks. Here is the folder link: {item.folder_path}"
        except Exception as e:
            logger.error(f"Error buying item {item_name} for user {user_id}: {e}")
            return False, "An error occurred while processing the purchase. Please try again later."

    @app_commands.command(name="add_item", description="Add an item to the store")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_item(self, interaction: discord.Interaction, item_name: str, item_cost: int, folder_path: str, item_description: str = "", item_image_url: str = ""):
        """Adds a new item to the store."""
        if item_cost <= 0:
            await interaction.response.send_message("Item cost must be greater than zero.", ephemeral=True)
            return
        success, message = await self.add_new_item(item_name, item_cost, folder_path, item_description, item_image_url)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="buy_item", description="Buy an item from the store")
    async def buy_item(self, interaction: discord.Interaction, item_name: str):
        """Allows a user to buy an item from the store."""
        success, message = await self.buy_store_item(interaction.user.id, interaction.user.name, item_name)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="list_items", description="List all items in the store")
    async def list_items(self, interaction: discord.Interaction):
        """Lists all available items in the store."""
        try:
            async with SessionLocal() as session:
                result = await session.execute(select(County))
                items = result.scalars().all()
                if not items:
                    await interaction.response.send_message('No items are available in the store.', ephemeral=True)
                    return
                embed = discord.Embed(title="Store Items", description="Here are the items available for purchase:")
                for item in items:
                    embed.add_field(name=f"{item.name} - {item.folder_count} KyBucks", value=item.description, inline=False)
                    if item.image_url:
                        embed.set_image(url=item.image_url)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error listing items: {e}")
            await interaction.response.send_message("An error occurred while listing items. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = CurrencySystem(bot)
    await bot.add_cog(cog)
