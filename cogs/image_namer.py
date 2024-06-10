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
        self.image_folder = r'C:\Users\joshu\PycharmProjects\THEBOTTTT\database\need_names'  # Update with your actual folder path
        self.image_formats = ('.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif')
        self.current_images = {}  # Dictionary to track posted images and their message IDs
        self.load_images()

    def load_images(self):
        """Load images from the specified folder."""
        if not os.path.exists(self.image_folder):
            logger.error(f"Image folder '{self.image_folder}' does not exist.")
            self.image_files = []
        else:
            self.image_files = [f for f in os.listdir(self.image_folder)
                                if os.path.isfile(os.path.join(self.image_folder, f)) and f.lower().endswith(self.image_formats)]

    def validate_filename(self, name):
        """Sanitize the filename by removing invalid characters."""
        return ''.join(c for c in name if c.isalnum() or c in (' ', '_')).rstrip()

    async def send_ephemeral_message(self, interaction: discord.Interaction, message: str):
        """Send an ephemeral message to the user."""
        await interaction.response.send_message(message, ephemeral=True)

    async def post_image(self, interaction: discord.Interaction, image_path: str):
        """Post an image to the channel."""
        try:
            with open(image_path, 'rb') as f:
                picture = discord.File(f)
                msg = await interaction.channel.send("Please provide a name for this image:", file=picture)
                self.current_images[msg.id] = os.path.basename(image_path)  # Associate the message ID with the image file
        except Exception as e:
            logger.error(f"Failed to post image '{os.path.basename(image_path)}': {e}")
            await self.send_ephemeral_message(interaction, f"Failed to post image '{os.path.basename(image_path)}'.")

    @app_commands.command(name='post_all_images', description='Post all images that need names.')
    async def post_all_images(self, interaction: discord.Interaction):
        """Post all images that need names."""
        if not self.image_files:
            await self.send_ephemeral_message(interaction, "No more images to post!")
            return

        for image in self.image_files:
            image_path = os.path.join(self.image_folder, image)
            await self.post_image(interaction, image_path)

        await self.send_ephemeral_message(interaction, "All images have been posted.")

    @app_commands.command(name='name_image', description='Name an image by message ID.')
    @app_commands.describe(message_id='The message ID of the image to be named', name='The new name for the image')
    async def name_image(self, interaction: discord.Interaction, message_id: int, name: str):
        """Name an image based on the message ID."""
        name = self.validate_filename(name)
        if message_id in self.current_images:
            old_name = self.current_images.pop(message_id)
            extension = os.path.splitext(old_name)[1]
            new_name = f"{name}{extension}"

            if new_name in self.image_files:
                await self.send_ephemeral_message(interaction, "This name is already taken. Please choose a different name.")
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
                await self.send_ephemeral_message(interaction, "An error occurred while renaming the image.")
        else:
            await self.send_ephemeral_message(interaction, "Invalid message ID or the image has already been named.")

    @app_commands.command(name='list_images', description='List all available images.')
    async def list_images(self, interaction: discord.Interaction):
        """List all available images."""
        if not self.image_files:
            await self.send_ephemeral_message(interaction, "No images available.")
        else:
            await self.send_ephemeral_message(interaction, "Available images:\n" + "\n".join(self.image_files))

    @app_commands.command(name='remaining_images', description='List all remaining images to be named.')
    async def remaining_images(self, interaction: discord.Interaction):
        """List all remaining images that need names."""
        remaining = [img for img in self.image_files if img not in self.current_images.values()]
        if not remaining:
            await self.send_ephemeral_message(interaction, "No more images to name.")
        else:
            await self.send_ephemeral_message(interaction, "Remaining images:\n" + "\n".join(remaining))

    @app_commands.command(name='delete_image', description='Delete an image by its name.')
    @app_commands.describe(name='The name of the image to delete')
    async def delete_image(self, interaction: discord.Interaction, name: str):
        """Delete an image by its name."""
        name = self.validate_filename(name)
        image_path = os.path.join(self.image_folder, name)

        if os.path.exists(image_path):
            try:
                os.remove(image_path)
                self.image_files.remove(name)
                await self.send_ephemeral_message(interaction, f"Image {name} deleted.")
            except Exception as e:
                logger.error(f"Failed to delete image '{name}': {e}")
                await self.send_ephemeral_message(interaction, "An error occurred while deleting the image.")
        else:
            await self.send_ephemeral_message(interaction, "Image not found.")

    @app_commands.command(name='describe_image', description='Add a description to an image.')
    @app_commands.describe(name='The name of the image', description='The description to add')
    async def describe_image(self, interaction: discord.Interaction, name: str, description: str):
        """Add a description to an image."""
        name = self.validate_filename(name)
        image_path = os.path.join(self.image_folder, name)

        if os.path.exists(image_path):
            try:
                description_file = image_path + ".txt"
                with open(description_file, 'w') as f:
                    f.write(description)
                await self.send_ephemeral_message(interaction, f"Description added to {name}.")
            except Exception as e:
                logger.error(f"Failed to add description to image '{name}': {e}")
                await self.send_ephemeral_message(interaction, "An error occurred while adding the description.")
        else:
            await self.send_ephemeral_message(interaction, "Image not found.")

async def setup(bot):
    await bot.add_cog(ImageNamer(bot))
