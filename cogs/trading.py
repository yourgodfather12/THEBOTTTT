import asyncio
import hashlib
import io
import os
from typing import Optional, Dict

import discord
import moviepy.editor as mp  # Library for handling video files
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput

# Constants for attachment validation
VALID_ATTACHMENT_TYPES = ['image/jpeg', 'image/png', 'video/mp4', 'video/quicktime']
MAX_ATTACHMENT_SIZE = 8 * 1024 * 1024  # 8 MB
TRADE_TIMEOUT = 300  # 5 minutes

class TradeModal(Modal):
    def __init__(self, user: discord.User, view: View):
        super().__init__(title="Trade Details")
        self.user = user
        self.view = view

        self.username_input = TextInput(
            label="Username",
            placeholder="Enter the username of the person you want to trade with",
            min_length=1,
            max_length=32
        )
        self.name_input = TextInput(
            label="Name of the Item",
            placeholder="Enter the name of the item you are trading",
            min_length=1,
            max_length=32
        )
        self.time_limit_select = Select(
            placeholder="Select time limit",
            options=[
                discord.SelectOption(label="30 minutes", value="30"),
                discord.SelectOption(label="1 hour", value="60"),
                discord.SelectOption(label="4 hours", value="240"),
                discord.SelectOption(label="8 hours", value="480")
            ]
        )

        self.add_item(self.username_input)
        self.add_item(self.name_input)
        self.add_item(self.time_limit_select)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username_input.value.strip()
        name = self.name_input.value.strip()
        time_limit = int(self.time_limit_select.values[0])

        if username == self.user.name:
            await interaction.response.send_message("You can't trade with yourself.", ephemeral=True)
            return

        target_user = discord.utils.get(self.view.bot.users, name=username)
        if not target_user:
            await interaction.response.send_message("The specified user does not exist.", ephemeral=True)
            return

        self.view.trade_data = {
            "username": username,
            "name": name,
            "time_limit": time_limit,
            "target_user": target_user,
            "expires_at": discord.utils.utcnow() + discord.utils.timedelta(minutes=time_limit)
        }

        await interaction.response.send_message(
            f"Trade details submitted:\n- **Username:** {username}\n- **Item Name:** {name}\n- **Time Limit:** {time_limit} minutes.",
            ephemeral=True
        )

        await interaction.followup.send(
            f"Please upload the attachment you want to trade, {self.user.mention}.",
            ephemeral=True
        )

class TradeView(View):
    def __init__(self, user: discord.User, bot: commands.Bot):
        super().__init__()
        self.user = user
        self.bot = bot
        self.trade_data: Optional[Dict] = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id == self.user.id:
            return True
        await interaction.response.send_message("You can only interact with this menu.", ephemeral=True)
        return False

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="next_stage")
    async def next_stage(self, button: Button, interaction: discord.Interaction):
        modal = TradeModal(interaction.user, self)
        await interaction.response.send_modal(modal)

class TradingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_trades: Dict[int, TradeView] = {}
        self.log_dir = os.path.join(os.path.dirname(__file__), "../logs")
        self.trades_dir = os.path.join(self.log_dir, "trades")
        os.makedirs(self.trades_dir, exist_ok=True)

    @app_commands.command(name="trade", description="Initiate a trade")
    @app_commands.describe()
    @app_commands.default_permissions(manage_messages=True)
    async def trade(self, interaction: discord.Interaction):
        user = interaction.user
        if isinstance(interaction.channel, discord.DMChannel):
            await self.start_trade(user, interaction)
        else:
            await interaction.response.send_message("I will DM you to continue the trade process.", ephemeral=True)
            await self.start_trade(user, interaction)

    async def start_trade(self, user: discord.User, interaction: discord.Interaction):
        if user.id not in self.active_trades:
            self.active_trades[user.id] = TradeView(user, self.bot)
            dm_status = await self.send_dm(user, "Welcome to the trade menu! Click 'Next' to proceed to the trade details form.", view=self.active_trades[user.id])
            if not dm_status:
                await interaction.followup.send(f"{user.mention}, I cannot send you direct messages. Please adjust your privacy settings to allow direct messages from server members and try again.", ephemeral=True)
            await self.log_trade(user, "Trade menu opened")
        else:
            await interaction.followup.send("You already have an active trade session.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get('custom_id')
            if custom_id == "next_stage":
                await self.handle_next_stage(interaction)

    async def handle_next_stage(self, interaction: discord.Interaction):
        user = interaction.user
        if user.id in self.active_trades:
            trade_view = self.active_trades[user.id]
            trade_data = trade_view.trade_data

            if not trade_data:
                await interaction.response.send_message("Please complete the trade details form first.", ephemeral=True)
                return

            target_user = trade_data["target_user"]
            await interaction.response.send_message("Please upload the attachment you want to trade.", ephemeral=True)
            await self.send_dm(user, f"Waiting for {target_user.mention} to confirm the trade.")

            try:
                attachment_message = await self.bot.wait_for('message', timeout=TRADE_TIMEOUT, check=lambda m: m.author == user and m.attachments)
                await self.confirm_trade(interaction, user, target_user, attachment_message, trade_data["name"])
            except asyncio.TimeoutError:
                await self.send_dm(user, "Trade timed out.")
                del self.active_trades[user.id]
                await self.log_trade(user, "Trade timed out.")
        else:
            await interaction.response.send_message("You are not currently in a trade session.", ephemeral=True)

    async def confirm_trade(self, interaction: discord.Interaction, user: discord.User, target_user: discord.User, attachment_message: discord.Message, name: str):
        attachment = attachment_message.attachments[0]

        # Validate attachment
        if not await self.validate_attachment(interaction, attachment):
            return

        await self.send_dm(target_user, f"{user.mention} wants to trade with you. Please reply with 'yes' or 'no' to confirm or decline the trade.")
        await interaction.response.send_message(f"Waiting for {target_user.mention} to confirm the trade.", ephemeral=True)

        try:
            confirmation = await self.bot.wait_for('message', timeout=TRADE_TIMEOUT, check=lambda m: m.author == target_user and m.content.lower() in ['yes', 'no'])
            if confirmation.content.lower() == 'yes':
                await self.send_dm(target_user, "Trade confirmed. Please upload your attachment(s). You have 5 minutes to upload.")
                await self.send_dm(user, "Trade confirmed. Please upload your attachment(s). You have 5 minutes to upload.")

                await asyncio.gather(
                    self.wait_for_attachments(user, target_user, attachment, name),
                    self.wait_for_attachments(target_user, user)
                )
            else:
                await self.send_dm(target_user, "Trade declined.")
                await self.send_dm(user, "Trade declined.")
                del self.active_trades[user.id]
                await self.log_trade(user, "Trade declined by target user.")
        except asyncio.TimeoutError:
            await self.send_dm(user, "Trade confirmation timed out.")
            await self.send_dm(target_user, "Trade confirmation timed out.")
            del self.active_trades[user.id]
            await self.log_trade(user, "Trade confirmation timed out.")

    async def wait_for_attachments(self, user: discord.User, target_user: discord.User, initial_attachment: Optional[discord.Attachment] = None, name: Optional[str] = None):
        try:
            if initial_attachment:
                attachment_message = initial_attachment
            else:
                await self.send_dm(user, "Please upload your attachment now. You have 5 minutes.")
                attachment_message = await self.bot.wait_for('message', timeout=TRADE_TIMEOUT, check=lambda m: m.author == user and m.attachments)
        except asyncio.TimeoutError:
            await self.send_dm(user, "Trade process timed out.")
            await self.send_dm(target_user, "Trade process timed out.")
            del self.active_trades[user.id]
            await self.log_trade(user, "Trade process timed out.")
            return

        for attachment in attachment_message.attachments:
            if not await self.validate_attachment(None, attachment, user, target_user, name):
                return

            filename_hash = hashlib.sha256((name or attachment.filename).encode()).hexdigest()
            filename = f"{filename_hash}.dat"
            trade_path = os.path.join(self.trades_dir, filename)
            try:
                await attachment.save(trade_path)
            except Exception as e:
                await self.send_dm(user, f"Failed to save attachment: {str(e)}")
                await self.send_dm(target_user, "Trade process failed due to attachment issue.")
                del self.active_trades[user.id]
                await self.log_trade(user, f"Failed to save attachment: {str(e)}")
                return

            await self.send_dm(target_user, f"{user.name} has uploaded an attachment:", file=discord.File(trade_path))
            await self.send_dm(user, "Attachment sent to the other user.")

    async def validate_attachment(self, interaction: Optional[discord.Interaction], attachment: discord.Attachment, user: Optional[discord.User] = None, target_user: Optional[discord.User] = None, name: Optional[str] = None):
        if attachment.size > MAX_ATTACHMENT_SIZE:
            if attachment.content_type.startswith('video/'):
                # Compress video
                try:
                    compressed_path = await self.compress_video(attachment)
                    await self.send_dm(user, "Video was too large and has been compressed.")
                    return True
                except Exception as e:
                    await self.send_dm(user, f"Failed to compress video: {str(e)}")
                    return False
            else:
                if interaction:
                    await interaction.response.send_message("Attachment is too large. Please upload a file smaller than 8 MB.", ephemeral=True)
                else:
                    await self.send_dm(user, "One of the attachments is too large. Please upload files smaller than 8 MB.")
                return False
        if attachment.content_type not in VALID_ATTACHMENT_TYPES:
            if interaction:
                await interaction.response.send_message(f"Invalid attachment type. Please upload one of the following types: {', '.join(VALID_ATTACHMENT_TYPES)}", ephemeral=True)
            else:
                await self.send_dm(user, f"Invalid attachment type. Please upload one of the following types: {', '.join(VALID_ATTACHMENT_TYPES)}")
            return False
        return True

    async def compress_video(self, attachment: discord.Attachment):
        video_bytes = await attachment.read()
        input_video = mp.VideoFileClip(io.BytesIO(video_bytes))
        compressed_path = os.path.join(self.trades_dir, f"compressed_{attachment.filename}")

        input_video.write_videofile(compressed_path, codec="libx264", bitrate="500k")
        return compressed_path

    async def log_trade(self, user: discord.User, message: str):
        log_file = os.path.join(self.log_dir, f"{user.id}_trades.log")
        os.makedirs(self.log_dir, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(f"{discord.utils.utcnow()}: {message}\n")

    async def send_dm(self, user: discord.User, content: str, **kwargs):
        try:
            await user.send(content, **kwargs)
            return True
        except discord.Forbidden:
            await self.log_trade(user, f"Failed to send DM: {content}")
            print(f"Failed to send DM to {user.name}")
            return False

async def setup(bot: commands.Bot):
    cog = TradingCog(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
