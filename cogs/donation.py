import os
import discord
import logging
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class DonationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.donation_addresses = self.load_donation_addresses()

    def load_donation_addresses(self):
        """
        Load donation addresses from environment variables.
        """
        cryptos = ["BITCOIN", "ETHEREUM", "LITECOIN"]  # Extend this list as needed
        addresses = {crypto: os.getenv(f"{crypto}_ADDRESS") for crypto in cryptos}
        # Filter out any None values if the environment variable is not set
        return {crypto: addr for crypto, addr in addresses.items() if addr}

    @app_commands.command(name="donate", description="Displays the cryptocurrency donation addresses")
    @app_commands.default_permissions()
    async def donate(self, interaction: discord.Interaction):
        """
        Slash command to display the cryptocurrency donation addresses.
        """
        try:
            if not self.donation_addresses:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="No Donation Addresses Available",
                        description="Currently, there are no donation addresses available. Please check back later.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Cryptocurrency Donation Addresses",
                description="Thank you for considering a donation! Here are the addresses you can send to:",
                color=discord.Color.blue()
            )
            for crypto, address in self.donation_addresses.items():
                embed.add_field(name=crypto, value=address, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.user.send("I don't have permission to send messages in that channel.")
        except Exception as e:
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)
            logging.error(f"Error in donate command: {e}")

async def setup(bot: commands.Bot):
    cog = DonationCog(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
