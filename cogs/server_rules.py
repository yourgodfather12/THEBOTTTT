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
                logger.warning("Missing `Embed Links` permission.")
                return

            rules = [
                {
                    "title": "1. No Underage Content",
                    "description": (
                        "Posting, sharing, or discussing any content that involves individuals under the legal age of consent "
                        "is strictly prohibited. This includes, but is not limited to, images, videos, or discussions that depict "
                        "or suggest underage individuals in explicit or inappropriate situations."
                    )
                },
                {
                    "title": "2. Permission for Posting Pics",
                    "description": (
                        "Members must obtain explicit consent before posting any pictures of individuals, whether they are "
                        "themselves or others. This rule ensures that all posted content respects the privacy and consent of the "
                        "individuals involved."
                    )
                },
                {
                    "title": "3. Verification Process",
                    "description": (
                        "To become verified, members must post a nude picture in the verify channel following the format (First_name "
                        "Last_name, county). Failure to comply with this requirement will result in non-verification. This process "
                        "helps maintain accountability and authenticity within the community."
                    )
                },
                {
                    "title": "4. No White Knights",
                    "description": "White knighting is not allowed and will result in disciplinary action."
                },
                {
                    "title": "5. Weekly Image Posting Requirement",
                    "description": (
                        "To remain active in the server, members must post a minimum of five images every week. Failure to meet this "
                        "requirement will result in being kicked from the server. The bot will automatically remove members who have "
                        "not posted the required number of images every Friday at 11 am sharp."
                    )
                },
                {
                    "title": "6. Posting Verification Picture",
                    "description": (
                        "After being verified, new members must post their verification picture in the county they are from. This "
                        "ensures that verified members are transparent about their location and helps maintain accountability within "
                        "the community."
                    )
                }
            ]

            verification_instructions = (
                "To get verified, make sure you follow this format:\n"
                "For example:\n"
                "Jane Doe, Fayette Co\n\n"
                "Please make sure:\n"
                "- The first letter of the first name (FirstName) is capitalized.\n"
                "- The first letter of the last name (LastName) is capitalized.\n"
                "- There is a comma after the last name.\n"
                "- The first letter of the county name (CountyName) is capitalized.\n"
                "- The abbreviation 'Co' is used after the county name, and it is capitalized."
            )

            embed = discord.Embed(
                title="Server Rules",
                description="Please make sure to read and follow the server rules:",
                color=discord.Color.blue()
            )

            for rule in rules:
                embed.add_field(name=rule["title"], value=rule["description"], inline=False)

            embed.add_field(name="Verification Instructions", value=verification_instructions, inline=False)
            embed.set_footer(text="These rules are subject to change, so please check back regularly.")

            await interaction.response.send_message(embed=embed)
            logger.info("Server rules displayed successfully.")
        except discord.Forbidden:
            logger.warning("Bot doesn't have permission to send messages or embeds.")
        except discord.HTTPException as http_exc:
            logger.error(f"HTTP exception occurred: {http_exc}")
            await interaction.response.send_message("An error occurred while displaying the rules. Please try again later.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error displaying server rules: {e}", exc_info=True)
            await interaction.response.send_message("An error occurred while displaying the rules. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot):
    cog = ServerRulesCog(bot)
    await bot.add_cog(cog)
