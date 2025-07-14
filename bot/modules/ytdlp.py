# FINAL AUTOMATED YTDL CODE (V10 - Correct Class Name)
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command
from secrets import token_hex
from aiofiles.os import path as aiopath, remove as aioremove
from asyncio import sleep
from yt_dlp import YoutubeDL
from functools import partial

from bot import (
    DOWNLOAD_DIR,
    bot,
    config_dict,
    LOGGER,
)
from bot.helper.ext_utils.bot_utils import (
    is_url,
    new_task,
    sync_to_async,
    arg_parser
)
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YoutubeDLHelper
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    deleteMessage,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener

# --- CUSTOM FOLDER IDs ---
CUSTOM_DESTINATIONS = {
    'video': '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
}

@new_task
async def ytdl(client, message):
    await _ytdl_task(client, message, isLeech=False)

@new_task
async def ytdlleech(client, message):
    await _ytdl_task(client, message, isLeech=True)

async def _ytdl_task(client, message, isLeech=False):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    
    arg_base = {
        "link": "",
        "-n": "",
        "-name": "",
        "-opt": "",
        "-options": "",
    }

    args = arg_parser(input_list[1:], arg_base)
    link = args["link"]
    name = args["-n"] or args["-name"]
    opt = args["-opt"] or args["-options"]

    if not is_url(link):
        return await sendMessage(message, "Tolong berikan URL YouTube yang valid.")

    # Automatically select the best quality
    qual = "bestvideo+bestaudio/best"
    
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
            return await sendMessage(message, "ID Folder Video tidak ditemukan!")
        index_link = config_dict.get("INDEX_URL", "")

    tag = f"@{message.from_user.username}" if message.from_user.username else message.from_user.mention
    
    listener = MirrorLeechListener(
        message,
        isLeech=isLeech,
        tag=tag,
        upPath=up,
        drive_id=drive_id,
        index_link=index_link,
        isYtdlp=True,
        source_url=link
    )

    path = f"{DOWNLOAD_DIR}{listener.uid}"
    
    ydl = YoutubeDLHelper(listener)
    await ydl.add_download(link, path, name, qual, playlist=False, opt=opt)
    
    await deleteMessage(message)

# Add Handlers
bot.add_handler(
    MessageHandler(
        ytdl,
        filters=command(BotCommands.YtdlCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        ytdlleech,
        filters=command(BotCommands.YtdlLeechCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
