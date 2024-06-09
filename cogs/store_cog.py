import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker
from db.database import AsyncSessionLocal, UserCurrency, County, RecentPurchase
import logging
import os

logger = logging.getLogger(__name__)

class Store(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_balance(self, user_id):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserCurrency).filter_by(user_id=user_id))
            user_currency = result.scalars().first()
            return user_currency.balance if user_currency else 0

    async def update_balance(self, user_id, username, amount):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(UserCurrency).filter_by(user_id=user_id))
            user_currency = result.scalars().first()
            if user_currency:
                user_currency.balance += amount
            else:
                user_currency = UserCurrency(user_id=user_id, username=username, balance=amount)
                session.add(user_currency)
            await session.commit()

    async def add_new_item(self, item_name, item_cost, folder_path, item_description, item_image_url):
        async with AsyncSessionLocal() as session:
            existing_item = await session.execute(select(County).filter_by(name=item_name))
            if existing_item.scalars().first():
                return False, "Item already exists."
            new_item = County(name=item_name, folder_count=item_cost, folder_path=folder_path, description=item_description, image_url=item_image_url)
            session.add(new_item)
            await session.commit()
            return True, f"Item {item_name} has been added to the store for {item_cost} KyBucks."

    async def buy_store_item(self, user_id, username, item_name):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(County).filter_by(name=item_name))
            item = result.scalars().first()
            if not item:
                return False, "Item does not exist."
            balance = await self.get_balance(user_id)
            if balance < item.folder_count:
                return False, "Insufficient KyBucks."
            await self.update_balance(user_id, username, -item.folder_count)
            new_purchase = RecentPurchase(username=username, county_name=item_name, price=item.folder_count)
            session.add(new_purchase)
            await session.commit()
            return True, f"You bought {item_name} for {item.folder_count} KyBucks. Here is the folder link: {item.folder_path}"

    async def get_transaction_history(self, user_id):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(RecentPurchase).filter_by(username=user_id))
            transactions = result.scalars().all()
            return transactions

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
        async with AsyncSessionLocal() as session:
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

    async def handle_balance_command(self, interaction: discord.Interaction):
        balance = await self.get_balance(interaction.user.id)
        await interaction.response.send_message(f'Your current balance is {balance} KyBucks.', ephemeral=True)

    async def handle_transaction_history_command(self, interaction: discord.Interaction):
        transactions = await self.get_transaction_history(interaction.user.id)
        if not transactions:
            await interaction.response.send_message("You have no transaction history.", ephemeral=True)
            return
        transaction_list = '\n'.join([f'{t.county_name} - {t.price} KyBucks on {t.timestamp}' for t in transactions])
        await interaction.response.send_message(f'Your transaction history:\n{transaction_list}', ephemeral=True)

    async def cog_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handles errors for commands in this cog."""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You do not have the necessary permissions to use this command.", ephemeral=True)
        else:
            logger.error(f"An error occurred: {error}", exc_info=True)
            await interaction.response.send_message("An error occurred while processing the command. Please try again later.", ephemeral=True)

async def setup(bot):
    """Setup function to add the cog to the bot."""
    cog = Store(bot)
    await bot.add_cog(cog)

    # Registering 'balance' command if not already registered
    if not bot.tree.get_command('balance'):
        balance_command = app_commands.Command(
            name="balance",
            description="Check your current balance",
            callback=cog.handle_balance_command
        )
        bot.tree.add_command(balance_command)

    # Registering 'transaction_history' command if not already registered
    if not bot.tree.get_command('transaction_history'):
        transaction_history_command = app_commands.Command(
            name="transaction_history",
            description="View your transaction history",
            callback=cog.handle_transaction_history_command
        )
        bot.tree.add_command(transaction_history_command)
