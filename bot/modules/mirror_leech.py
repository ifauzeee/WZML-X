# MODIFIED FOR CATEGORY SELECTION V4 (FINAL FIX)
import asyncio
import re
import shlex
import time
from asyncio import gather
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message
from bot import (LOGGER, STOP_DUPLICATE, TORRENT_LIMIT, DIRECT_LIMIT,
                 LEECH_LIMIT, MEGA_LIMIT, GDRIVE_LIMIT, YTDLP_LIMIT,
                 PLAYLIST_LIMIT, bot, user_data, config_dict)
from bot.helper.ext_utils.bot_utils import (is_magnet, is_mega_link, is_gdrive_link, is_url,
                                            is_rclone_path, is_telegram_link, get_tg_link_content)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_utils.download_utils.mega_download import add_mega_download
from bot.helper.mirror_utils.download_utils.rclone_download import add_rclone_download
from bot.helper.mirror_utils.download_utils.yt_dlp_download import add_yt_dlp_download
from bot.helper.mirror_utils.gdrive_utlis.list import gdriveList
from bot.helper.mirror_utils.rclone_utils.list import rcloneList
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (anno_checker, delete_links, edit_message, send_message, delete_message)
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.bulk_links import extract_bulk_links
from bot.helper.ext_utils.misc import get_some_info, get_user_tasks
from bot.helper.ext_utils.rclone_data_holder import get_rclone_data, is_rclone_config
from bot.helper.themes.wzml_minimal import WZML_MID

# --- CUSTOM FOLDER IDs ---
CUSTOM_DESTINATIONS = {
    'app':       '1tUCYi4x3l1_omXwspD2eiPlblBCJSgOV',
    'video':     '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'audio':     '1M0eYHR0qg9OtzQUJT030b-x5fxt8DKAx',
    'files':     '1gxPwlYhbKmzhYSk-ququFUzfBG5cj-lc',
    'folder':    '1E9Ng9uMqJ2yAK8hqirp7EOImSGgKecW6',
}

# New entry point for all mirror commands
async def run_mirror_leech_entry(client, message: Message, is_leech=False, is_qbit=False, is_ytdlp=False, is_gdrive=False, is_rclone=False):
    if not hasattr(message, 'from_user') or not message.from_user:
        return

    text_args = message.text.split()
    if any(arg in ['-s', '-select', '-up'] for arg in text_args):
        await original_mirror_leech_logic(client, message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone)
    else:
        await category_selection_logic(client, message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone)

# Shows the category buttons
async def category_selection_logic(client, message: Message, is_leech=False, is_qbit=False, is_ytdlp=False, is_gdrive=False, is_rclone=False):
    is_bulk = 'bulk' in message.text.split(' ')[0].lower()
    
    link = ""
    reply_to = message.reply_to_message
    if reply_to:
        if reply_to.text:
            link = reply_to.text.strip()
        elif reply_to.media:
            link = await get_tg_link_content(reply_to)
    
    if not link:
        command_parts = message.text.split(' ', 1)
        if len(command_parts) > 1:
            link = command_parts[1].strip()

    if not link:
        return await send_message(message, WZML_MID.MIRROR_NO_LINK)

    category = get_file_category(link, reply_to)
    user_id = message.from_user.id
    buttons = ButtonMaker()
    
    msg = f"<b>Tipe file terdeteksi:</b> <code>{category.upper()}</code>\n"
    msg += "Pilih folder tujuan untuk melanjutkan mirror:"

    flags = f"{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}|{is_bulk}"

    buttons.cb_buildbutton("🎬 Video", f"cat_up|video|{user_id}|{flags}")
    buttons.cb_buildbutton("🎵 Audio", f"cat_up|audio|{user_id}|{flags}")
    buttons.cb_buildbutton("📦 Aplikasi", f"cat_up|app|{user_id}|{flags}")
    buttons.cb_buildbutton("📄 Dokumen", f"cat_up|files|{user_id}|{flags}")
    buttons.cb_buildbutton("🗂️ Arsip (ZIP/RAR)", f"cat_up|folder|{user_id}|{flags}")
    buttons.cb_buildbutton("❌ Batal", f"cat_up|cancel|{user_id}|{flags}")

    await send_message(message, msg, buttons.finalize(2))

# Handles the button presses
async def mirror_leech_callback(client, callback_query):
    query = callback_query
    user_id = query.from_user.id
    message = query.message
    data = query.data.split("|")

    try:
        if int(data[2]) != user_id and not await CustomFilters.sudo(client, query):
            return await query.answer("Ini bukan pilihan untukmu!", show_alert=True)
    except IndexError:
        return await query.answer("Callback error!", show_alert=True)
    
    if data[1] == "cancel":
        await query.answer()
        return await delete_message(message)

    await query.answer()
    category_key = data[1]
    up_path = CUSTOM_DESTINATIONS.get(category_key)
    
    if not up_path:
        return await edit_message(message, "Kategori tidak valid!")

    is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, is_bulk = [x == 'True' for x in data[3:]]
    original_message = message.reply_to_message
    
    await edit_message(message, f"✅ Oke! File akan di-mirror ke folder **{category_key.upper()}**.")
    await original_mirror_leech_logic(client, original_message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, custom_upload_path=up_path)

# Helper function to categorize files
def get_file_category(link, reply_to_message):
    media = reply_to_message
    if media:
        if media.video: return 'video'
        if media.audio or media.voice: return 'audio'
        if media.document:
            mime_type = media.document.mime_type or ""
            file_name = media.document.file_name or ""
            if mime_type == 'application/vnd.android.package-archive' or file_name.lower().endswith('.apk'):
                return 'app'
            if 'zip' in mime_type or 'rar' in mime_type or file_name.lower().endswith('.7z'):
                return 'folder'
            if any(x in mime_type for x in ['pdf', 'word', 'powerpoint', 'excel']):
                return 'files'
    
    link_lower = link.lower()
    if is_magnet(link_lower): return 'folder'
    if '.apk' in link_lower: return 'app'
    if any(ext in link_lower for ext in ['.mp4', '.mkv', '.webm', '.flv', '.mov']): return 'video'
    if any(ext in link_lower for ext in ['.mp3', '.flac', '.wav', '.m4a']): return 'audio'
    if any(ext in link_lower for ext in ['.zip', '.rar', '.7z']): return 'folder'
    if any(ext in link_lower for ext in ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']): return 'files'
    
    return 'files'

# This is the original logic of the bot, now callable as a function
async def original_mirror_leech_logic(client, message, is_leech=False, is_qbit=False, is_ytdlp=False, is_gdrive=False, is_rclone=False, custom_upload_path=None):
    text = message.text.split('\n')
    input_list = text[0].split(' ')
    
    tag = f"@{message.from_user.username}" if message.from_user.username else f"tg://user?id={message.from_user.id}"
    user_id = message.from_user.id
    
    is_bulk = 'bulk' in input_list[0].lower()
    if not is_bulk:
        await get_some_info(message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone)

    reply_to = message.reply_to_message
    if len(input_list) == 1 and reply_to and reply_to.text:
        text = reply_to.text.split('\n')
        
    if is_bulk:
        try:
            link, _ = extract_bulk_links(message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone)
        except:
            return await send_message(message, 'Tolong berikan link dalam format yang valid!')
    else:
        link = ""
        if len(input_list) > 1:
            link = input_list[1].strip()
            if link.startswith(("|", "pswd:", "enc:")):
                link = ""
    
    reply_to = message.reply_to_message
    if reply_to:
        if not link and reply_to.text:
            link = reply_to.text.strip()
        if not link and reply_to.media:
            if not hasattr(reply_to, 'from_user') or not reply_to.from_user:
                reply_to.from_user = await anno_checker(reply_to)
            if reply_to.from_user and reply_to.from_user.is_bot:
                return await send_message(message, "File dari bot tidak didukung!")
            link = await get_tg_link_content(reply_to)

    if not link:
        return await send_message(message, WZML_MID.MIRROR_NO_LINK)
    
    LOGGER.info(f"Link: {link}")
    
    up_path = ""
    name = ""
    
    args_list = message.text.split(maxsplit=1)
    if len(args_list) > 1:
        args = shlex.split(args_list[1])
        for x in list(args):
            x = x.strip()
            if x.startswith('-up='):
                up_path = x.split('=', 1)[1]
                args.remove(x)
        if args:
            name = ' '.join(args)

    if custom_upload_path:
        up_path = custom_upload_path
    
    if up_path and up_path.startswith('mrcc:'):
        is_rclone = True
    
    listener = MirrorLeechListener(message, is_leech=is_leech, is_qbit=is_qbit, is_ytdlp=is_ytdlp, is_gdrive=is_gdrive, is_rclone=is_rclone, tag=tag, is_bulk=is_bulk)

    if is_gdrive_link(link):
        await add_gd_download(link, up_path, listener, name)
    elif is_mega_link(link):
        await add_mega_download(link, f'{listener.dir}{name}', listener)
    elif is_qbit:
        await add_qb_torrent(link, up_path, listener, tag)
    elif is_rclone_path(link):
        await rcloneList(link, get_rclone_data(listener.user_id, 'RCLONE_CONFIG'), listener)
    elif is_ytdlp:
        await add_yt_dlp_download(link, f'{up_path}/{name}', listener)
    else:
        await add_aria2c_download(link, up_path, listener, name, tag)
    
    if config_dict.get('DELETE_LINKS'):
        await delete_links(message)

# Entry point functions that will be called by __main__.py
async def mirror(client, message: Message):
    await run_mirror_leech_entry(client, message)

async def qb_mirror(client, message: Message):
    await run_mirror_leech_entry(client, message, is_qbit=True)

async def leech(client, message: Message):
    await run_mirror_leech_entry(client, message, is_leech=True)

async def qb_leech(client, message: Message):
    await run_mirror_leech_entry(client, message, is_leech=True, is_qbit=True)

async def ytdl(client, message: Message):
    await run_mirror_leech_entry(client, message, is_ytdlp=True)

async def ytdl_leech(client, message: Message):
    await run_mirror_leech_entry(client, message, is_leech=True, is_ytdlp=True)

async def gdrive(client, message: Message):
    await run_mirror_leech_entry(client, message, is_gdrive=True)

async def rclone(client, message: Message):
    await run_mirror_leech_entry(client, message, is_rclone=True)

async def clone(client, message: Message):
    await original_mirror_leech_logic(client, message, is_gdrive=True)
