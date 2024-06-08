import discord
from discord.ext import commands
from discord import app_commands
import json
import os

class CustomCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_path = 'config/custom_commands.json'
        self.custom_commands = self.load_commands()

    def load_commands(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def save_commands(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.custom_commands, f, indent=4)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.tree.sync()
        print(f"Logged in as {self.bot.user} and ready.")

    @app_commands.command(name="create_command", description="Create a custom command")
    @app_commands.checks.has_permissions(administrator=True)
    async def create_command(self, interaction: discord.Interaction, command_name: str, response: str):
        self.custom_commands[command_name.lower()] = response
        self.save_commands()
        await interaction.response.send_message(f'Custom command {command_name} has been created.')

    @app_commands.command(name="delete_command", description="Delete a custom command")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_command(self, interaction: discord.Interaction, command_name: str):
        if command_name.lower() in self.custom_commands:
            del self.custom_commands[command_name.lower()]
            self.save_commands()
            await interaction.response.send_message(f'Custom command {command_name} has been deleted.')
        else:
            await interaction.response.send_message(f'Custom command {command_name} does not exist.')

    @app_commands.command(name="list_custom_commands", description="List all custom commands")
    async def list_custom_commands(self, interaction: discord.Interaction):
        if self.custom_commands:
            commands_list = "\n".join(f"/{cmd}" for cmd in self.custom_commands)
            await interaction.response.send_message(f'Custom commands:\n{commands_list}')
        else:
            await interaction.response.send_message('There are no custom commands.')

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        command_name = message.content.split()[0].lower()
        if command_name in self.custom_commands:
            await message.channel.send(self.custom_commands[command_name])

async def setup(bot):
    await bot.add_cog(CustomCommands(bot))
