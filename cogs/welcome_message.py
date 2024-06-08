import discord
from discord.ext import commands

class WelcomeMessage(commands.Cog):
    def __init__(self, bot, welcome_channel_id):
        self.bot = bot
        self.welcome_channel_id = welcome_channel_id

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            channel = self.bot.get_channel(self.welcome_channel_id)
            if channel is None:
                channel = member.guild.system_channel
                if channel is None:
                    self.bot.logger.warning(f"No welcome channel found for guild: {member.guild.name}")
                    return

            welcome_message = (
                f'Welcome to the server, {member.mention}! We hope you enjoy your stay.\n\n'
                'Please make sure to read and follow the server rules:\n'
                '1. **No Underage Content**\n'
                'Posting, sharing, or discussing any content that involves individuals under the legal age of consent is strictly prohibited. This includes, but is not limited to, images, videos, or discussions that depict or suggest underage individuals in explicit or inappropriate situations.\n\n'
                '2. **Permission for Posting Pics**\n'
                'Members must obtain explicit consent before posting any pictures of individuals, whether they are themselves or others. This rule ensures that all posted content respects the privacy and consent of the individuals involved.\n\n'
                '3. **Verification Process**\n'
                'To become verified, members must post a nude picture in the verify channel following the format (First_name Last_name, county). Failure to comply with this requirement will result in non-verification. This process helps maintain accountability and authenticity within the community.\n\n'
                '4. **No White Knights**\n'
                'White knighting is not allowed and will result in disciplinary action.\n\n'
                '5. **Weekly Image Posting Requirement**\n'
                'To remain active in the server, members must post a minimum of five images every week. Failure to meet this requirement will result in being kicked from the server. The bot will automatically remove members who have not posted the required number of images every Friday at 11 am sharp.\n\n'
                '6. **Posting Verification Picture**\n'
                'After being verified, new members must post their verification picture in the county they are from. This ensures that verified members are transparent about their location and helps maintain accountability within the community.\n\n'
                'Verification Instructions:\n'
                'To get verified, make sure you follow this format:\n'
                'For example:\n'
                '`Jane Doe, Fayette Co`\n\n'
                'Please make sure:\n'
                '- The first letter of the first name (FirstName) is capitalized.\n'
                '- The first letter of the last name (LastName) is capitalized.\n'
                '- There is a comma after the last name.\n'
                '- The first letter of the county name (CountyName) is capitalized.\n'
                '- The abbreviation \'Co\' is used after the county name, and it is capitalized.\n\n'
                'These rules are subject to change, so please check back regularly.'
            )

            await channel.send(welcome_message)
        except Exception as e:
            self.bot.logger.error(f"Failed to send welcome message: {e}")

async def setup(bot):
    await bot.add_cog(WelcomeMessage(bot, YOUR_WELCOME_CHANNEL_ID))
