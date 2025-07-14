# FINAL AUTOMATED YTDL CODE
from secrets import token_hex
from aiofiles.os import path as aiopath, remove as aioremove
from asyncio import sleep

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    config_dict,
)
from bot.helper.ext_utils.bot_utils import (
    is_url,
    new_task,
)
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YtDlpDownloadHelper
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    deleteMessage,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener

# --- CUSTOM FOLDER IDs (Imported from mirror_leech) ---
CUSTOM_DESTINATIONS = {
    'video': '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    # Other IDs are not needed here but kept for context
    'app': '1tUCYi4x3l1_omXwspD2eiPlblBCJSgOV',
    'audio': '1M0eYHR0qg9OtzQUJT030b-x5fxt8DKAx',
    'files': '1gxPwlYhbKmzhYSk-ququFUzfBG5cj-lc',
    'folder': '1E9Ng9uMqJ2yAK8hqirp7EOImSGgKecW6',
}

@new_task
async def ytdl(client, message):
    await _ytdl_task(client, message)

@new_task
async def ytdlleech(client, message):
    await _ytdl_task(client, message, isLeech=True)

async def _ytdl_task(client, message, isLeech=False):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    
    if len(input_list) < 2:
        return await sendMessage(
            message, f"<b>Usage:</b> /{BotCommands.YtdlCommand} [link] [options]"
        )

    link = input_list[1].strip()
    
    if not is_url(link):
        return await sendMessage(message, "Please provide a valid URL.")

    # Automatically select the best quality
    format_selector = "bestvideo+bestaudio/best"
    
    # Check if the task should be a leech or a mirror
    if isLeech:
        up = "leech"
        drive_id = ""
        index_link = ""
    else:
        # Automatically set the upload destination to the 'video' folder ID
        up = "gd"
        drive_id = CUSTOM_DESTINATIONS.get('video')
        if not drive_id:
            return await sendMessage(message, "Video folder ID not found in CUSTOM_DESTINATIONS.")
        index_link = config_dict.get("INDEX_URL", "")

    # Create the listener
    listener = MirrorLeechListener(
        message,
        isLeech=isLeech,
        up=up,
        drive_id=drive_id,
        index_link=index_link,
        source_url=link
    )

    # Start the download
    try:
        ytdl_down = YtDlpDownloadHelper(listener)
        path = f"{DOWNLOAD_DIR}{listener.uid}"
        await ytdl_down.add_download(link, path, format_selector)
    except Exception as e:
        LOGGER.error(f"Error in YTDL download: {e}")
        await sendMessage(message, f"An error occurred: {e}")
