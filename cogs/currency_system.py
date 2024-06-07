import logging
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from db.database import UserCurrency, Transaction, AsyncSessionLocal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
                result = await db.execute(
                    select(UserCurrency).filter_by(user_id=user_id)
                )
                user_currency = result.scalar()
                return user_currency.balance if user_currency else 0
        except Exception as e:
            logger.error(f"Error fetching balance for user {user_id}: {e}")
            return 0

    async def update_balance(self, user_id: int, amount: int, description: str = None) -> None:
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(UserCurrency).filter_by(user_id=user_id)
                )
                user_currency = result.scalar()
                if user_currency:
                    user_currency.balance += amount
                else:
                    user_currency = UserCurrency(user_id=user_id, balance=amount)
                    db.add(user_currency)
                db.add(Transaction(user_id=user_id, amount=amount, description=description))
                await db.commit()
        except Exception as e:
            logger.error(f"Error updating balance for user {user_id}: {e}")

    async def get_transaction_history(self, user_id: int, limit: int = 10):
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(Transaction).filter_by(user_id=user_id).order_by(Transaction.timestamp.desc()).limit(limit)
                )
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
    @app_commands.default_permissions(administrator=True)
    async def balance(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        balance = await self.get_balance(user_id)
        await self.send_embed_message(interaction, "KyBucks Balance", f"Your current balance is {balance} KyBucks.")

    @app_commands.command(name="give", description="Give KyBucks to another user")
    @app_commands.describe(user="The user to give KyBucks to", amount="The amount of KyBucks to give")
    @app_commands.default_permissions(administrator=True)
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

        await self.update_balance(giver_id, -amount, f"Gave {amount} KyBucks to {user.display_name}")
        await self.update_balance(receiver_id, amount, f"Received {amount} KyBucks from {interaction.user.display_name}")

        await self.send_embed_message(interaction, "Success", f"You have successfully given {amount} KyBucks to {user.display_name}.")
        try:
            await user.send(f"You have received {amount} KyBucks from {interaction.user.display_name}.")
        except discord.Forbidden:
            logger.warning(f"Failed to send DM to {user.display_name}")

    @app_commands.command(name="history", description="View your transaction history")
    @app_commands.default_permissions(administrator=True)
    async def history(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        transactions = await self.get_transaction_history(user_id)
        if not transactions:
            await self.send_embed_message(interaction, "Transaction History", "You have no transaction history.")
            return

        history_message = "Your last transactions:\n"
        for transaction in transactions:
            history_message += f"{transaction.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {transaction.amount} KyBucks - {transaction.description}\n"
        await self.send_embed_message(interaction, "Transaction History", history_message)

    @app_commands.command(name="leaderboard", description="View the top users with the most KyBucks")
    @app_commands.default_permissions(administrator=True)
    async def leaderboard(self, interaction: discord.Interaction):
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(UserCurrency).order_by(UserCurrency.balance.desc()).limit(10)
                )
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
    @app_commands.default_permissions(administrator=True)
    async def daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            async with SessionLocal() as db:
                last_claim = await db.execute(
                    select(Transaction).filter_by(user_id=user_id, description='Daily Reward').order_by(Transaction.timestamp.desc()).limit(1)
                )
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

async def setup(bot: commands.Bot):
    cog = CurrencySystem(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registrations
