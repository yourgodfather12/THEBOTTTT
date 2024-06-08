import discord
from discord import app_commands
from discord.ext import commands
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageNamer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.image_folder = 'path/to/your/image/folder'  # Update with your actual folder path
        self.image_formats = ('.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif')
        self.load_images()
        self.current_images = {}  # Dictionary to track posted images and their message IDs

    def load_images(self):
        if not os.path.exists(self.image_folder):
            logger.error(f"Image folder '{self.image_folder}' does not exist.")
            self.image_files = []
        else:
            self.image_files = [f for f in os.listdir(self.image_folder) if os.path.isfile(os.path.join(self.image_folder, f)) and f.lower().endswith(self.image_formats)]

    async def cog_load(self):
        self.bot.tree.add_command(self.images)

    def validate_filename(self, name):
        return ''.join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()

    images = app_commands.Group(name='images', description='Manage images')

    @images.command(name='post_all', description='Post all images that need names.')
    async def post_all_images(self, interaction: discord.Interaction):
        if not self.image_files:
            await interaction.response.send_message("No more images to post!", ephemeral=True)
            return

        for image in self.image_files:
            image_path = os.path.join(self.image_folder, image)
            try:
                with open(image_path, 'rb') as f:
                    picture = discord.File(f)
                    msg = await interaction.channel.send("Please provide a name for this image:", file=picture)
                    self.current_images[msg.id] = image  # Associate the message ID with the image file
            except Exception as e:
                logger.error(f"Failed to post image '{image}': {e}")

        await interaction.response.send_message("All images have been posted.", ephemeral=True)

    @images.command(name='name', description='Name an image by message ID.')
    @app_commands.describe(message_id='The message ID of the image to be named', name='The new name for the image')
    async def name_image(self, interaction: discord.Interaction, message_id: int, name: str):
        name = self.validate_filename(name)
        if message_id in self.current_images:
            old_name = self.current_images.pop(message_id)
            extension = os.path.splitext(old_name)[1]
            new_name = f"{name}{extension}"

            if new_name in self.image_files:
                await interaction.response.send_message("This name is already taken. Please choose a different name.", ephemeral=True)
                return

            try:
                os.rename(os.path.join(self.image_folder, old_name), os.path.join(self.image_folder, new_name))  # Rename the file
                self.image_files.remove(old_name)
                self.image_files.append(new_name)

                message = await interaction.channel.fetch_message(message_id)
                await message.delete()

                await interaction.response.send_message(f"Image named: {new_name}")
            except Exception as e:
                logger.error(f"Failed to rename image '{old_name}' to '{new_name}': {e}")
                await interaction.response.send_message("An error occurred while renaming the image.", ephemeral=True)
        else:
            await interaction.response.send_message("Invalid message ID or the image has already been named.", ephemeral=True)

    @images.command(name='list', description='List all available images.')
    async def list_images(self, interaction: discord.Interaction):
        if not self.image_files:
            await interaction.response.send_message("No images available.", ephemeral=True)
        else:
            await interaction.response.send_message("Available images:\n" + "\n".join(self.image_files), ephemeral=True)

    @images.command(name='remaining', description='List all remaining images to be named.')
    async def remaining_images(self, interaction: discord.Interaction):
        remaining = [img for img in self.image_files if img not in self.current_images.values()]
        if not remaining:
            await interaction.response.send_message("No more images to name.", ephemeral=True)
        else:
            await interaction.response.send_message("Remaining images:\n" + "\n".join(remaining), ephemeral=True)

    @images.command(name='delete', description='Delete an image by its name.')
    @app_commands.describe(name='The name of the image to delete')
    async def delete_image(self, interaction: discord.Interaction, name: str):
        name = self.validate_filename(name)
        image_path = os.path.join(self.image_folder, name)

        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                self.image_files.remove(name)
                await interaction.response.send_message(f"Image {name} deleted.", ephemeral=True)
            except Exception as e:
                logger.error(f"Failed to delete image '{name}': {e}")
                await interaction.response.send_message("An error occurred while deleting the image.", ephemeral=True)
        else:
            await interaction.response.send_message("Image not found.", ephemeral=True)

    @images.command(name='describe', description='Add a description to an image.')
    @app_commands.describe(name='The name of the image', description='The description to add')
    async def describe_image(self, interaction: discord.Interaction, name: str, description: str):
        name = self.validate_filename(name)
        image_path = os.path.join(self.image_folder, name)

        if os.path.exists(image_path):
            try:
                description_file = image_path + ".txt"
                with open(description_file, 'w') as f:
                    f.write(description)
                await interaction.response.send_message(f"Description added to {name}.", ephemeral=True)
            except Exception as e:
                logger.error(f"Failed to add description to image '{name}': {e}")
                await interaction.response.send_message("An error occurred while adding the description.", ephemeral=True)
        else:
            await interaction.response.send_message("Image not found.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ImageNamer(bot))
