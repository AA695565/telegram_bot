# bot.py

import os
import requests
import logging
import asyncio # Import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes # Import Application instead of ApplicationBuilder
from dotenv import load_dotenv
from aiohttp import web # Import aiohttp web

# Load environment variables from .env file
load_dotenv()

# Get the bot token from environment variable
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Get the port for the web server from environment variable (provided by Koyeb)
PORT = int(os.getenv("PORT", "8080")) # Default to 8080 if not set

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
            await msg.reply_text(f"Download link:\n{external_link}")
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

# --- Web Server Handler ---
async def health_check(request):
    """A simple handler that returns 200 OK for health checks."""
    logger.info("Health check request received.")
    return web.Response(text="OK")

# --- Main Async Function ---
async def main():
    """Runs the Telegram bot and the simple web server concurrently."""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return

    # --- Initialize Telegram Bot Application ---
    logger.info("Initializing Telegram application...")
    # Use Application directly for more control
    application = Application.builder().token(TOKEN).build()

    # Add handler for documents, photos, and videos
    application.add_handler(MessageHandler(
        (filters.Document.ALL | filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
        handle_file
    ))

    # --- Initialize Web Server ---
    logger.info("Initializing web server...")
    webapp = web.Application()
    webapp.add_routes([web.get('/', health_check)]) # Route for health check
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT) # Listen on 0.0.0.0 and $PORT

    # --- Run both concurrently ---
    # Application.initialize() prepares the bot but doesn't block
    await application.initialize()
    logger.info(f"Starting web server on port {PORT}...")
    await site.start() # Start the web server
    logger.info("Starting Telegram bot polling...")
    # Application.start() starts background tasks (like polling) but doesn't block
    await application.start()
    # Keep the application running
    # await application.updater.start_polling() # This might be redundant after application.start()
    logger.info("Bot and web server started successfully.")

    # Keep the main function running until interrupted
    while True:
        await asyncio.sleep(3600) # Keep alive, sleep for an hour

    # --- Proper Shutdown (won't typically be reached in this setup) ---
    # logger.info("Shutting down...")
    # await application.updater.stop()
    # await application.stop()
    # await application.shutdown()
    # await runner.cleanup()
    # logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.") 
