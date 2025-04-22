# bot.py

import os
import requests
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the bot token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Upload Function ---
def upload_to_external_service(file_path):
    """Uploads the file to transfer.sh and returns the download link."""
    try:
        with open(file_path, 'rb') as f:
            # Using transfer.sh as an example
            response = requests.put(
                f"https://transfer.sh/{os.path.basename(file_path)}",
                data=f,
                timeout=60 # Add a timeout
            )
        response.raise_for_status() # Raise an exception for bad status codes
        link = response.text.strip()
        logger.info(f"Uploaded {os.path.basename(file_path)} to {link}")
        return link
    except requests.exceptions.RequestException as e:
        logger.error(f"Upload failed: {e}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during upload: {e}")
        return None

# --- File Handler ---
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming documents, photos, or videos."""
    msg = update.message
    file_id = None
    file_name = "file" # Default name
    temp_dir = "/tmp" # Make sure this directory exists and is writable

    # Create temp directory if it doesn't exist
    if not os.path.exists(temp_dir):
        try:
            os.makedirs(temp_dir)
        except OSError as e:
            logger.error(f"Failed to create temp directory {temp_dir}: {e}")
            await msg.reply_text("Server error: Could not create temporary storage.")
            return

    # Identify file type and get file_id/name
    if msg.document:
        file_id = msg.document.file_id
        file_name = msg.document.file_name or "document"
    elif msg.photo:
        # Get the largest photo
        file_id = msg.photo[-1].file_id
        file_name = f"photo_{file_id}.jpg"
    elif msg.video:
        file_id = msg.video.file_id
        file_name = msg.video.file_name or f"video_{file_id}.mp4"
    else:
        # Ignore messages that aren't documents, photos, or videos
        logger.info("Received non-file message, ignoring.")
        return # Or reply with "Please send a file"

    if not file_id:
        await msg.reply_text("Could not get file information.")
        return

    await msg.reply_text("Processing your file, please wait...")

    try:
        bot_file = await context.bot.get_file(file_id)
        temp_file_path = os.path.join(temp_dir, file_name)

        # Download the file
        logger.info(f"Downloading {file_name} to {temp_file_path}")
        await bot_file.download_to_drive(temp_file_path)
        logger.info(f"Downloaded {file_name} successfully.")

        # Upload the file
        logger.info(f"Uploading {file_name} to external service...")
        external_link = upload_to_external_service(temp_file_path)

        # Reply with the link or an error message
        if external_link:
            await msg.reply_text(f"Download link: {external_link}")
        else:
            await msg.reply_text("Sorry, the upload failed.")

    except Exception as e:
        logger.error(f"Error handling file {file_name}: {e}", exc_info=True)
        await msg.reply_text("An error occurred while processing your file.")
    finally:
        # Clean up the temporary file
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Removed temporary file: {temp_file_path}")
            except OSError as e:
                logger.error(f"Failed to remove temporary file {temp_file_path}: {e}")


# --- Main Function ---
def main():
    """Starts the bot."""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return

    logger.info("Starting bot...")
    app = ApplicationBuilder().token(TOKEN).build()

    # Add handler for documents, photos, and videos
    app.add_handler(MessageHandler(
        (filters.Document.ALL | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_file
    ))

    # Start polling
    logger.info("Bot started polling.")
    app.run_polling()
    logger.info("Bot stopped.")


if __name__ == "__main__":
    main() 