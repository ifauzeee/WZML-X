# FINAL YTDLP CODE (V18 - Rewritten with client.listen for Stability)
#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from pyrogram.errors import Timeout
from asyncio import sleep
from aiofiles.os import path as aiopath
from yt_dlp import YoutubeDL
from functools import partial
from time import time

from bot import DOWNLOAD_DIR, bot, categories_dict, config_dict, user_data, LOGGER
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    deleteMessage,
    delete_links,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import (
    get_readable_file_size,
    is_url,
    new_task,
    sync_to_async,
    get_readable_time,
    arg_parser,
)
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YoutubeDLHelper
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import YT_HELP_MESSAGE

# --- CUSTOM FOLDER ID ---
VIDEO_FOLDER_ID = '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R'

class YtSelection:
    def __init__(self, client, message):
        self.__message = message
        self.__user_id = message.from_user.id
        self.__client = client
        self.qual = None
        self.is_cancelled = False

    async def get_quality(self, result):
        buttons = ButtonMaker()
        formats = {}
        
        format_dict = result.get("formats")
        if format_dict is not None:
            for item in format_dict:
                if item.get("tbr"):
                    format_id = item["format_id"]
                    size = item.get("filesize") or item.get("filesize_approx") or 0

                    if item.get("video_ext") == "none" and item.get("acodec") != "none":
                        b_name = f"{item['acodec']}-{item['ext']}"
                        v_format = format_id
                    elif item.get("height"):
                        height = item["height"]
                        ext = item["ext"]
                        fps = item.get("fps", "")
                        b_name = f"{height}p{fps}-{ext}"
                        v_format = f"{format_id}+ba/b[height=?{height}]"
                    else:
                        continue
                    
                    # Use a simple key for callback data
                    key = f"ytq {v_format}" 
                    formats[key] = v_format
                    buttons.ibutton(f"{b_name} ({get_readable_file_size(size)})", key)

        buttons.ibutton("Best Video", "ytq bv*+ba/b")
        buttons.ibutton("Best Audio", "ytq ba/b")
        buttons.ibutton("Cancel", "ytq cancel", "footer")
        
        main_buttons = buttons.build_menu(2)
        msg = f"Choose Video Quality:\nTimeout: 2 minutes"
        reply_message = await sendMessage(self.__message, msg, main_buttons)
        
        try:
            # Use client.listen for robust callback handling
            cb = await self.__client.listen(
                user_id=self.__user_id, 
                chat_id=self.__message.chat.id, 
                message_id=reply_message.id,
                timeout=120
            )
            data = cb.data.split(maxsplit=1)
            if data[0] == "ytq":
                if data[1] == "cancel":
                    self.is_cancelled = True
                    await editMessage(reply_message, "Task has been cancelled.")
                else:
                    self.qual = data[1]
            await cb.answer() # Acknowledge the button press
        except Timeout:
            self.is_cancelled = True
            await editMessage(reply_message, "Timed Out. Task has been cancelled!")
        
        await deleteMessage(reply_message)
        return self.qual

def extract_info(link, options):
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(link, download=False)
        if result is None:
            raise ValueError("Info result is None")
        return result

@new_task
async def _ytdl(client, message, isLeech=False):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    
    arg_base = {"link": "", "-n": "", "-name": ""}
    args = arg_parser(input_list[1:], arg_base)
    name = args["-n"] or args["-name"]
    link = args["link"]

    if not link and (reply_to := message.reply_to_message) and reply_to.text:
        link = reply_to.text.split("\n", 1)[0].strip()

    if not is_url(link):
        return await sendMessage(message, YT_HELP_MESSAGE[0])

    tag = message.from_user.mention

    # --- Destination Logic ---
    if isLeech:
        up = "leech"
        drive_id = ""
    else: # This is /ytdl (mirror)
        up = "gd"
        drive_id = VIDEO_FOLDER_ID
    
    listener = MirrorLeechListener(message, isLeech=isLeech, tag=tag, drive_id=drive_id, upPath=up, isYtdlp=True, source_url=link)

    options = {"usenetrc": True, "cookiefile": "cookies.txt", "playlist_items": "0"}
    
    try:
        result = await sync_to_async(extract_info, link, options)
    except Exception as e:
        return await sendMessage(message, f"{tag} {str(e).replace('<', ' ').replace('>', ' ')}")
    
    # --- Quality Selection Logic ---
    yt_selector = YtSelection(client, message)
    qual = await yt_selector.get_quality(result)
    
    if yt_selector.is_cancelled or not qual:
        return

    await delete_links(message)
    LOGGER.info(f"Downloading with YT-DLP: {link} | Quality: {qual}")
    path = f"{DOWNLOAD_DIR}{listener.uid}"
    playlist = "entries" in result
    ydl = YoutubeDLHelper(listener)
    await ydl.add_download(link, path, name, qual, playlist, options)

async def ytdl(client, message):
    await _ytdl(client, message)

async def ytdlleech(client, message):
    await _ytdl(client, message, isLeech=True)

bot.add_handler(
    MessageHandler(
        ytdl,
        filters=command(BotCommands.YtdlCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        ytdlleech,
        filters=command(BotCommands.YtdlLeechCommand) & CustomFilters.authorized & ~CustomFilters.blacklisted,
    )
)
