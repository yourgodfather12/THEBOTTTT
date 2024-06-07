import logging
import discord
from discord.ext import commands
from discord import app_commands

# Initialize the logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServerRulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rules", description="Show a list of rules for the server")
    @app_commands.default_permissions()
    async def show_rules(self, interaction: discord.Interaction) -> None:
        """Show a list of rules for the server"""
        try:
            if not interaction.channel.permissions_for(interaction.guild.me).embed_links:
                await interaction.response.send_message("I need the `Embed Links` permission to send rules.", ephemeral=True)
                return

            rules = [
                {"title": "1. Be Respectful", "description": "Treat everyone with respect. Absolutely no harassment, witch hunting, sexism, racism, or hate speech will be tolerated."},
                {"title": "2. No Spam", "description": "Don't spam messages, images, or reactions."},
                {"title": "3. No NSFW Content", "description": "This server is SFW. Do not post or discuss any NSFW content."},
                {"title": "4. Follow Discord's Terms of Service", "description": "Make sure to follow [Discord's Terms of Service](https://discord.com/terms) and [Community Guidelines](https://discord.com/guidelines)."},
                {"title": "5. No Self-Promotion", "description": "Do not promote your own content without permission from the server staff."},
                {"title": "6. Use Appropriate Channels", "description": "Post content in the appropriate channels. Read the channel descriptions for guidance."},
                {"title": "7. No Impersonation", "description": "Do not impersonate other users, including staff members."},
                {"title": "8. Respect Privacy", "description": "Do not share personal information of yourself or others."},
            ]

            embed = discord.Embed(
                title="Server Rules",
                description="Please make sure to read and follow the server rules:",
                color=discord.Color.blue()
            )

            for rule in rules:
                embed.add_field(name=rule["title"], value=rule["description"], inline=False)

            embed.set_footer(text="These rules are subject to change, so please check back regularly.")

            await interaction.response.send_message(embed=embed)
            logger.info("Server rules displayed successfully.")
        except Exception as e:
            logger.error(f"Error displaying server rules: {e}")
            await interaction.response.send_message("An error occurred while displaying the rules. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = ServerRulesCog(bot)
    await bot.add_cog(cog)
    # Removed duplicate command registration
