# FINAL YTDLP CODE (V19 - Standard CallbackQueryHandler for Ultimate Stability)
#!/usr/bin/env python3
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, user
from asyncio import Event, wait_for
from yt_dlp import YoutubeDL
from time import time

from bot import DOWNLOAD_DIR, bot, user_data, config_dict, LOGGER
from bot.helper.telegram_helper.message_utils import sendMessage, editMessage, deleteMessage, delete_links
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.bot_utils import get_readable_file_size, is_url, new_task, sync_to_async, get_readable_time, arg_parser
from bot.helper.mirror_utils.download_utils.yt_dlp_download import YoutubeDLHelper
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import YT_HELP_MESSAGE

# --- CUSTOM FOLDER ID ---
VIDEO_FOLDER_ID = '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R'

# Dictionary to store user's quality selection event
yt_events = {}

class YtSelection:
    def __init__(self, message, client):
        self.__message = message
        self.__user_id = message.from_user.id
        self.__client = client

    async def get_quality(self, result):
        """Creates the quality selection buttons and waits for user's choice."""
        if self.__user_id in yt_events:
            # Cancel previous event if user sends new command
            yt_events[self.__user_id]['event'].set()
            
        yt_events[self.__user_id] = {'event': Event(), 'qual': None, 'is_cancelled': False}

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
                    
                    formats[v_format] = f"{b_name} ({get_readable_file_size(size)})"
                    buttons.ibutton(formats[v_format], f"ytq {self.__user_id} {v_format}")

        buttons.ibutton("Best Video", f"ytq {self.__user_id} bv*+ba/b")
        buttons.ibutton("Best Audio", f"ytq {self.__user_id} ba/b")
        buttons.ibutton("Cancel", f"ytq {self.__user_id} cancel", "footer")
        
        main_buttons = buttons.build_menu(2)
        msg = f"Choose Video Quality:\nTimeout: 2 minutes"
        reply_message = await sendMessage(self.__message, msg, main_buttons)

        try:
            await wait_for(yt_events[self.__user_id]['event'].wait(), timeout=120)
        except Exception:
            yt_events[self.__user_id]['is_cancelled'] = True
            await editMessage(reply_message, "Timed Out. Task has been cancelled!")
        
        await deleteMessage(reply_message)
        
        is_cancelled = yt_events[self.__user_id]['is_cancelled']
        qual = yt_events[self.__user_id]['qual']
        
        # Clean up the event from the dictionary
        del yt_events[self.__user_id]
        
        return qual, is_cancelled

@bot.on_callback_query(regex("^ytq"))
async def yt_qual_callback(_, query):
    """Handles the button presses for quality selection."""
    user_id = query.from_user.id
    data = query.data.split()
    
    # Data format: "ytq USER_ID QUALITY_STRING"
    cb_user_id = int(data[1])
    
    if user_id != cb_user_id:
        return await query.answer("This is not for you!", show_alert=True)
        
    if cb_user_id not in yt_events:
        return await query.answer("This task has already been processed or cancelled.", show_alert=True)

    event_data = yt_events[cb_user_id]
    quality = " ".join(data[2:])

    if quality == "cancel":
        event_data['is_cancelled'] = True
    else:
        event_data['qual'] = quality

    event_data['event'].set()
    await query.answer()

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

    if isLeech:
        up = "leech"
        drive_id = ""
    else:
        up = "gd"
        drive_id = VIDEO_FOLDER_ID
    
    listener = MirrorLeechListener(message, isLeech=isLeech, tag=tag, drive_id=drive_id, upPath=up, isYtdlp=True, source_url=link)

    options = {"usenetrc": True, "cookiefile": "cookies.txt", "playlist_items": "0"}
    
    try:
        result = await sync_to_async(extract_info, link, options)
    except Exception as e:
        return await sendMessage(message, f"{tag} {str(e).replace('<', ' ').replace('>', ' ')}")
    
    yt_selector = YtSelection(message, client)
    qual, is_cancelled = await yt_selector.get_quality(result)
    
    if is_cancelled or not qual:
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
