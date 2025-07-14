# FINAL AUTOMATED YTDL CODE (V12 - Corrected Arguments)
#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from pyrogram.types import Message
from asyncio import sleep, wait_for, Event, wrap_future
from aiohttp import ClientSession
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
    auto_delete_message,
    delete_links,
    open_category_btns,
    open_dump_btns,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import (
    get_readable_file_size,
    fetch_user_tds,
    fetch_user_dumps,
    is_url,
    is_gdrive_link,
    new_task,
    sync_to_async,
    is_rclone_path,
    new_thread,
    get_readable_time,
    arg_parser,
)
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YoutubeDLHelper
from bot.helper.mirror_utils.rclone_utils.list import RcloneList
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import YT_HELP_MESSAGE
from bot.helper.ext_utils.bulk_links import extract_bulk_links

# --- CUSTOM FOLDER IDs ---
CUSTOM_DESTINATIONS = {
    'video': '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
}

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
    elif data[1] == "audio":
        await obj.audio_format()
    elif data[1] == "aq":
        if data[2] == "back":
            await obj.audio_format()
        else:
            await obj.audio_quality(data[2])
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
        self.__is_m4a = False
        self.__reply_to = None
        self.__time = time()
        self.__timeout = 120
        self.__is_playlist = False
        self.is_cancelled = False
        self.__main_buttons = None
        self.event = Event()
        self.formats = {}
        self.qual = None

    @new_thread
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
        future = self.__event_handler()
        buttons = ButtonMaker()
        if "entries" in result:
            self.__is_playlist = True
            for i in ["144", "240", "360", "480", "720", "1080", "1440", "2160"]:
                video_format = f"bv*[height<=?{i}][ext=mp4]+ba[ext=m4a]/b[height<=?{i}]"
                b_data = f"{i}|mp4"
                self.formats[b_data] = video_format
                buttons.ibutton(f"{i}-mp4", f"ytq {b_data}")
                video_format = f"bv*[height<=?{i}][ext=webm]+ba/b[height<=?{i}]"
                b_data = f"{i}|webm"
                self.formats[b_data] = video_format
                buttons.ibutton(f"{i}-webm", f"ytq {b_data}")
            buttons.ibutton("MP3", "ytq mp3")
            buttons.ibutton("Audio Formats", "ytq audio")
            buttons.ibutton("Best Videos", "ytq bv*+ba/b")
            buttons.ibutton("Best Audios", "ytq ba/b")
            buttons.ibutton("Cancel", "ytq cancel", "footer")
            self.__main_buttons = buttons.build_menu(3)
            msg = f"Choose Playlist Videos Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        else:
            format_dict = result.get("formats")
            if format_dict is not None:
                for item in format_dict:
                    if item.get("tbr"):
                        format_id = item["format_id"]

                        if item.get("filesize"):
                            size = item["filesize"]
                        elif item.get("filesize_approx"):
                            size = item["filesize_approx"]
                        else:
                            size = 0

                        if (
                            item.get("video_ext") == "none"
                            and item.get("acodec") != "none"
                        ):
                            if item.get("audio_ext") == "m4a":
                                self.__is_m4a = True
                            b_name = f"{item['acodec']}-{item['ext']}"
                            v_format = format_id
                        elif item.get("height"):
                            height = item["height"]
                            ext = item["ext"]
                            fps = item["fps"] if item.get("fps") else ""
                            b_name = f"{height}p{fps}-{ext}"
                            ba_ext = (
                                "[ext=m4a]" if self.__is_m4a and ext == "mp4" else ""
                            )
                            v_format = f"{format_id}+ba{ba_ext}/b[height=?{height}]"
                        else:
                            continue

                        self.formats.setdefault(b_name, {})[f"{item['tbr']}"] = [
                            size,
                            v_format,
                        ]

                for b_name, tbr_dict in self.formats.items():
                    if len(tbr_dict) == 1:
                        tbr, v_list = next(iter(tbr_dict.items()))
                        buttonName = f"{b_name} ({get_readable_file_size(v_list[0])})"
                        buttons.ibutton(buttonName, f"ytq sub {b_name} {tbr}")
                    else:
                        buttons.ibutton(b_name, f"ytq dict {b_name}")
                buttons.ibutton("MP3", "ytq mp3")
                buttons.ibutton("Audio Formats", "ytq audio")
                buttons.ibutton("Best Video", "ytq bv*+ba/b")
                buttons.ibutton("Best Audio", "ytq ba/b")
                buttons.ibutton("Cancel", "ytq cancel", "footer")
                self.__main_buttons = buttons.build_menu(2)
                msg = f"Choose Video Quality:\nTimeout: {get_readable_time(self.__timeout-(time()-self.__time))}"
        self.__reply_to = await sendMessage(self.__message, msg, self.__main_buttons)
        await wrap_future(future)
        if not self.is_cancelled:
            await deleteMessage(self.__reply_to)
        return self.qual

def extract_info(link, options):
    with YoutubeDL(options) as ydl:
        result = ydl.extract_info(link, download=False)
        if result is None:
            raise ValueError("Info result is None")
        return result

async def _ytdl(client, message, isLeech=False, sameDir=None, bulk=[]):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    qual = ""
    arg_base = {
        "link": "", "-i": 0, "-m": "", "-sd": "", "-samedir": "", "-s": False, "-select": False,
        "-opt": "", "-options": "", "-b": False, "-bulk": False, "-n": "", "-name": "",
        "-z": False, "-zip": False, "-up": "", "-upload": False, "-rcf": "", "-id": "",
        "-index": "", "-c": "", "-category": "", "-ud": "", "-dump": "", "-ss": "0",
        "-screenshots": "", "-t": "", "-thumb": "",
    }

    args = arg_parser(input_list[1:], arg_base)
    cmd = input_list[0].split("@")[0]

    try:
        multi = int(args["-i"])
    except:
        multi = 0

    select = args["-s"] or args["-select"]
    isBulk = args["-b"] or args["-bulk"]
    opt = args["-opt"] or args["-options"]
    folder_name = args["-m"] or args["-sd"] or args["-samedir"]
    name = args["-n"] or args["-name"]
    up = args["-up"] or args["-upload"]
    rcf = args["-rcf"]
    link = args["link"]
    compress = args["-z"] or args["-zip"] or "z" in cmd or "zip" in cmd
    drive_id = args["-id"]
    index_link = args["-index"]
    gd_cat = args["-c"] or args["-category"]
    user_dump = args["-ud"] or args["-dump"]
    thumb = args["-t"] or args["-thumb"]
    sshots_arg = args["-ss"] or args["-screenshots"]
    sshots = int(sshots_arg) if sshots_arg.isdigit() else 0

    if not link and (reply_to := message.reply_to_message) and reply_to.text:
        link = reply_to.text.split("\n", 1)[0].strip()

    if not is_url(link):
        await sendMessage(message, YT_HELP_MESSAGE[0])
        return

    sender_chat = message.sender_chat
    if sender_chat:
        tag = sender_chat.title
    else:
        tag = message.from_user.mention

    if not isLeech:
        # AUTOMATION LOGIC FOR MIRROR (/ytdl)
        qual = 'bestvideo+bestaudio/best'
        up = 'gd'
        drive_id = CUSTOM_DESTINATIONS.get('video')
        if not drive_id:
            return await sendMessage(message, "Video folder ID not found!")
        LOGGER.info(f"YTDL-Mirror: Auto-selecting best quality for {link}")
    else:
        # ORIGINAL LOGIC FOR LEECH (/ytdlleech)
        up = 'leech'
        drive_id = ''
        index_link = ''
    
    listener = MirrorLeechListener(
        message, compress, isLeech=isLeech, tag=tag, sameDir=sameDir, rcFlags=rcf,
        upPath=up, drive_id=drive_id, index_link=index_link, isYtdlp=True, source_url=link,
        leech_utils={"screenshots": sshots, "thumb": thumb},
    )

    user_id = message.from_user.id
    user_dict = user_data.get(user_id, {})
    yt_opt = opt or user_dict.get("yt_opt") or config_dict["YT_DLP_OPTIONS"]
    
    options = {'usenetrc': True, 'cookiefile': 'cookies.txt'}
    if yt_opt:
        yt_opts = yt_opt.split("|")
        for opt_item in yt_opts:
            key, value = map(str.strip, opt_item.split(":", 1))
            if key == 'format' and not isLeech: continue
            if value.startswith("^"):
                if "." in value or value == "^inf": value = float(value.split("^")[1])
                else: value = int(value.split("^")[1])
            elif value.lower() == 'true': value = True
            elif value.lower() == 'false': value = False
            elif value.startswith(('{', '[', '(')) and value.endswith(('}', ']', ')')):
                value = eval(value)
            options[key] = value

    options['playlist_items'] = '0'

    try:
        result = await sync_to_async(extract_info, link, options)
    except Exception as e:
        msg = str(e).replace('<', ' ').replace('>', ' ')
        return await sendMessage(message, f"{tag} {msg}")

    if not isLeech: # Skip quality selection for mirror
        pass
    else: # Show quality selection for leech
        if not select and (not qual and "format" in options):
            qual = options["format"]
        if not qual:
            qual = await YtSelection(client, message).get_quality(result)
            if qual is None:
                return
                
    await delete_links(message)
    LOGGER.info(f"Downloading with YT-DLP: {link}")
    path = f"{DOWNLOAD_DIR}{listener.uid}{folder_name or ''}"
    playlist = "entries" in result
    ydl = YoutubeDLHelper(listener)
    await ydl.add_download(link, path, name, qual, playlist, yt_opt)

async def ytdl(client, message):
    await _ytdl(client, message)

async def ytdlleech(client, message):
    await _ytdl(client, message, isLeech=True)

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
