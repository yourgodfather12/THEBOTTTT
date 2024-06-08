import discord
from discord.ext import commands
from discord import app_commands
from sqlalchemy.future import select
from db.database import AsyncSessionLocal, UserCurrency, County, RecentPurchase
import logging

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

    @app_commands.command(name="add_item", description="Add an item to the store")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_item(self, interaction: discord.Interaction, item_name: str, item_cost: int, folder_path: str):
        async with AsyncSessionLocal() as session:
            new_item = County(name=item_name, folder_count=item_cost, folder_path=folder_path)
            session.add(new_item)
            await session.commit()
            await interaction.response.send_message(f'Item {item_name} has been added to the store for {item_cost} KyBucks.')

    @app_commands.command(name="buy_item", description="Buy an item from the store")
    async def buy_item(self, interaction: discord.Interaction, item_name: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(County).filter_by(name=item_name))
            item = result.scalars().first()
            if not item:
                await interaction.response.send_message(f'Item {item_name} does not exist.')
                return

            balance = await self.get_balance(interaction.user.id)
            if balance < item.folder_count:
                await interaction.response.send_message(f'You do not have enough KyBucks to buy {item_name}.')
                return

            await self.update_balance(interaction.user.id, interaction.user.name, -item.folder_count)
            new_purchase = RecentPurchase(username=interaction.user.name, county_name=item_name, price=item.folder_count)
            session.add(new_purchase)
            await session.commit()
            await interaction.response.send_message(f'You bought {item_name} for {item.folder_count} KyBucks. Here is the folder link: {item.folder_path}')

    @app_commands.command(name="list_items", description="List all items in the store")
    async def list_items(self, interaction: discord.Interaction):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(County))
            items = result.scalars().all()
            if not items:
                await interaction.response.send_message('No items are available in the store.')
                return
            item_list = '\n'.join([f'{item.name}: {item.folder_count} KyBucks' for item in items])
            await interaction.response.send_message(f'Available items:\n{item_list}')

async def setup(bot):
    cog = Store(bot)
    await bot.add_cog(cog)
