import discord
from discord.ext import commands
import logging
import os
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
load_dotenv()

class WelcomeMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_config()

    def load_config(self):
        # Load welcome message from environment variable or use default
        self.welcome_message = os.getenv(
            'WELCOME_MESSAGE',
            "Welcome to the server, {member.name}! We're glad to have you here."
        )
        self.rules_channel_id = int(os.getenv('RULES_CHANNEL_ID', 0))
        self.help_channel_id = int(os.getenv('HELP_CHANNEL_ID', 0))

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            embed = discord.Embed(
                title="🎉 Welcome to Our Server! 🎉",
                description=self.welcome_message.format(member=member),
                color=discord.Color.blue()
            )

            if self.rules_channel_id:
                rules_channel = self.bot.get_channel(self.rules_channel_id)
                if rules_channel:
                    embed.add_field(
                        name="📜 **Rules** 📜",
                        value=f"Please make sure to read the [rules]({rules_channel.jump_url}) to avoid any issues.",
                        inline=False
                    )

            if self.help_channel_id:
                help_channel = self.bot.get_channel(self.help_channel_id)
                if help_channel:
                    embed.add_field(
                        name="🆘 **Need Help?** 🆘",
                        value=f"If you have any questions, feel free to ask in the [help channel]({help_channel.jump_url}).",
                        inline=False
                    )

            await member.send(embed=embed)
            logging.info(f"Sent welcome message to {member.name}")

        except discord.Forbidden:
            logging.warning(f"Could not send welcome message to {member.name} - Forbidden")
        except Exception as e:
            logging.error(f"An error occurred when sending welcome message to {member.name}: {e}")

async def setup(bot):
    await bot.add_cog(WelcomeMessage(bot))