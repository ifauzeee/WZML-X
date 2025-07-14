# FINAL YTDLP CODE (V17 - Manual Quality, Auto Destination for Mirror)
#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from pyrogram.types import Message
from asyncio import create_task, wait_for, Event
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

@new_task
async def select_format(_, query, obj):
    data = query.data.split()
    message = query.message
    await query.answer()

    if data[1] == "dict":
        b_name = data[2]
        await obj.qual_subbuttons(b_name)
    elif data[1] == "mp3":
        await obj.mp3_subbuttons()
    elif data[1] == "back":
        await obj.back_to_main()
    elif data[1] == "cancel":
        await editMessage(message, "Task has been cancelled.")
        obj.qual = None
        obj.is_cancelled = True
        obj.event.set()
    else:
        if data[1] == "sub":
            obj.qual = obj.formats[data[2]][data[3]][1]
        elif "|" in data[1]:
            obj.qual = obj.formats[data[1]]
        else:
            obj.qual = data[1]
        obj.event.set()


class YtSelection:
    def __init__(self, client, message):
        self.__message = message
        self.__user_id = message.from_user.id
        self.__client = client
        self.__reply_to = None
        self.__time = time()
        self.__timeout = 120
        self.is_cancelled = False
        self.__main_buttons = None
        self.event = Event()
        self.formats = {}
        self.qual = None

    async def __event_handler(self):
        pfunc = partial(select_format, obj=self)
        handler = self.__client.add_handler(
            CallbackQueryHandler(pfunc, filters=regex("^ytq") & user(self.__user_id)),
            group=-1,
        )
        try:
            await wait_for(self.event.wait(), timeout=self.__timeout)
        except Exception:
            await editMessage(self.__reply_to, "Timed Out. Task has been cancelled!")
            self.qual = None
            self.is_cancelled = True
            self.event.set()
        finally:
            self.__client.remove_handler(*handler)

    async def get_quality(self, result):
        future = create_task(self.__event_handler())
        buttons = ButtonMaker()
        
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

                    self.formats.setdefault(b_name, {})[f"{item['tbr']}"] = [size, v_format]

            for b_name, tbr_dict in self.formats.items():
                if len(tbr_dict) == 1:
                    tbr, v_list = next(iter(tbr_dict.items()))
                    buttonName = f"{b_name} ({get_readable_file_size(v_list[0])})"
                    buttons.ibutton(buttonName, f"ytq sub {b_name} {tbr}")
                else:
                    buttons.ibutton(b_name, f"ytq dict {b_name}")
            
            buttons.ibutton("MP3", "ytq mp3")
            buttons.ibutton("Best Video", "ytq bv*+ba/b")
            buttons.ibutton("Best Audio", "ytq ba/b")
            buttons.ibutton("Cancel", "ytq cancel", "footer")
            self.__main_buttons = buttons.build_menu(2)
            msg = f"Choose Video Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        
        self.__reply_to = await sendMessage(self.__message, msg, self.__main_buttons)
        await future
        if not self.is_cancelled:
            await deleteMessage(self.__reply_to)
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
    
    arg_base = {"link": "", "-n": "", "-name": "", "-s": False, "-select": False}
    args = arg_parser(input_list[1:], arg_base)
    name = args["-n"] or args["-name"]
    select = args["-s"] or args["-select"]
    link = args["link"]

    if not link and (reply_to := message.reply_to_message) and reply_to.text:
        link = reply_to.text.split("\n", 1)[0].strip()

    if not is_url(link):
        return await sendMessage(message, YT_HELP_MESSAGE[0])

    if (sender_chat := message.sender_chat):
        tag = sender_chat.title
    else:
        tag = message.from_user.mention

    # --- Destination Logic ---
    if isLeech:
        up = "leech"
        drive_id = ""
        index_link = ""
    else: # This is /ytdl (mirror)
        up = "gd"
        drive_id = VIDEO_FOLDER_ID
        index_link = config_dict.get("INDEX_URL", "")
    
    listener = MirrorLeechListener(message, isLeech=isLeech, tag=tag, drive_id=drive_id, upPath=up, isYtdlp=True, source_url=link)

    options = {"usenetrc": True, "cookiefile": "cookies.txt", "playlist_items": "0"}
    
    try:
        result = await sync_to_async(extract_info, link, options)
    except Exception as e:
        return await sendMessage(message, f"{tag} {str(e).replace('<', ' ').replace('>', ' ')}")
    
    # --- Quality Selection Logic (ALWAYS ON) ---
    qual = ""
    if not select:
        qual = await YtSelection(client, message).get_quality(result)
        if qual is None:
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
