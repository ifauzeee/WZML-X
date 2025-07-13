# MODIFIED FOR CATEGORY SELECTION
import asyncio
import re
import shlex
import time
from asyncio import gather
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message
from bot import (LOGGER, STOP_DUPLICATE, TORRENT_DIRECT_LIMIT,
                ZIP_UNZIP_LIMIT, LEECH_LIMIT, MEGA_LIMIT,
                GDRIVE_LIMIT, YTDLP_LIMIT, PLAYLIST_LIMIT,
                BUTTON_FOUR_NAME, BUTTON_FOUR_URL, BUTTON_FIVE_NAME,
                BUTTON_FIVE_URL, BUTTON_SIX_NAME, BUTTON_SIX_URL,
                VIEW_LINK, bot)
from bot.helper.ext_utils.bot_utils import (get_readable_time, is_magnet,
                                            is_mega_link, is_gdrive_link,
                                            is_gdtot_link, is_filepress_link,
                                            is_udrive_link, is_sharer_link, is_sharedrive_link,
                                            is_ytdl_link, get_content_type,
                                            is_direct_link, is_rclone_path,
                                            is_telegram_link, get_multi_links,
                                            get_readable_file_size, is_share_link,
                                            is_dood_link, is_streamwish_link, is_streamtape_link,
                                            is_filehost_link)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.task_manager import task_manager
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_utils.download_utils.mega_download import add_mega_download
from bot.helper.mirror_utils.download_utils.rclone_download import add_rclone_download
from bot.helper.mirror_utils.download_utils.telegram_download import TelegramDownloadHelper
from bot.helper.mirror_utils.download_utils.yt_dlp_download import add_yt_dlp_download
from bot.helper.mirror_utils.gdrive_utlis.list import gdriveList
from bot.helper.mirror_utils.rclone_utils.list import rcloneList
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (anno_checker, delete_links,
                                                    edit_message, auto_delete_message,
                                                    get_tg_link_content, send_message,
                                                    delete_message, send_to_pm)
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

async def run_mirror_leech(client, message: Message, is_leech=False, is_qbit=False, is_ytdlp=False, is_gdrive=False, is_rclone=False):
    if not hasattr(message, 'from_user') or not message.from_user:
        return

    text = message.text.split('\n')
    input_list = text[0].split(' ')

    tag = f"@{message.from_user.username}"
    user_id = message.from_user.id

    try:
        args = shlex.split(input_list[0])
    except:
        args = input_list[0].split()

    cmd = args[0].lower()
    if user_id != bot.owner_id and len(await get_user_tasks(user_id)) >= WZML_MID.MAX_TASKS_PER_USER:
        return await send_message(message, WZML_MID.MAX_TASKS_MSG.format(WZML_MID.MAX_TASKS_PER_USER))

    is_bulk = 'bulk' in cmd
    if not is_bulk:
        await get_some_info(message, is_leech=is_leech, is_qbit=is_qbit, is_ytdlp=is_ytdlp, is_gdrive=is_gdrive, is_rclone=is_rclone)

    if len(input_list) == 1 and reply_to := message.reply_to_message:
        if reply_to.text:
            text = reply_to.text.split('\n')

    if is_bulk:
        try:
            link, _ = extract_bulk_links(message, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone)
        except:
            await send_message(message, 'Please provide links in valid format!')
            return
    else:
        link = ""
        if len(input_list) > 1:
            link = input_list[1].strip()
            if link.startswith(("|", "pswd:", "enc:")):
                link = ""

    if reply_to := message.reply_to_message:
        if not link and reply_to.text:
            link = reply_to.text.strip()
        if not link and (reply_to.document or reply_to.video or reply_to.audio or reply_to.photo or reply_to.voice or reply_to.video_note or reply_to.sticker or reply_to.animation):
            if not reply_to.from_user:
                reply_to.from_user = await anno_checker(reply_to)
            if reply_to.from_user.is_bot:
                await send_message(message, "Bot files are not supported!")
                return
            link = await get_tg_link_content(reply_to)

    if not link:
        await send_message(message, WZML_MID.MIRROR_NO_LINK)
        return

    LOGGER.info(f"Link: {link}")

    # --- CATEGORY SELECTION LOGIC ---
    try:
        await select_category_and_start(message, link, tag, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, is_bulk)
    except Exception as e:
        LOGGER.error(f"Error in category selection: {e}")
        await send_message(message, f"Terjadi kesalahan: {e}")

def get_file_category(link, reply_to_message):
    if reply_to_message:
        if reply_to_message.video: return 'video'
        if reply_to_message.audio or reply_to_message.voice: return 'audio'
        if reply_to_message.document:
            mime = reply_to_message.document.mime_type
            if mime == 'application/vnd.android.package-archive': return 'app'
            if 'application/zip' in mime or 'application/x-rar' in mime: return 'folder'
            if 'pdf' in mime or 'word' in mime or 'powerpoint' in mime or 'excel' in mime: return 'files'

    if is_magnet(link): return 'folder'

    # Check by extension for links
    if '.apk' in link.lower(): return 'app'
    if any(ext in link.lower() for ext in ['.mp4', '.mkv', '.webm', '.flv']): return 'video'
    if any(ext in link.lower() for ext in ['.mp3', '.flac', '.wav', '.m4a']): return 'audio'
    if any(ext in link.lower() for ext in ['.zip', '.rar', '.7z']): return 'folder'
    if any(ext in link.lower() for ext in ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']): return 'files'

    return 'files' # Default category

async def select_category_and_start(message, link, tag, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, is_bulk):
    reply_to = message.reply_to_message
    category = get_file_category(link, reply_to)

    buttons = ButtonMaker()
    msg = f"<b>Tipe file terdeteksi:</b> <code>{category.upper()}</code>\n"
    msg += "Pilih folder tujuan untuk melanjutkan mirror:"

    # Create buttons
    buttons.cb_buildbutton("🎬 Video", f"cat_up|video|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")
    buttons.cb_buildbutton("🎵 Audio", f"cat_up|audio|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")
    buttons.cb_buildbutton("📦 Aplikasi", f"cat_up|app|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")
    buttons.cb_buildbutton("📄 Dokumen", f"cat_up|files|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")
    buttons.cb_buildbutton("🗂️ Arsip (ZIP/RAR)", f"cat_up|folder|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")
    buttons.cb_buildbutton("❌ Batal", f"cat_up|cancel|{is_leech}|{is_qbit}|{is_ytdlp}|{is_gdrive}|{is_rclone}")

    await send_message(message, msg, buttons.finalize(2))

async def start_mirror_leech_final(client, cb_message, link, up_path, tag, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, is_bulk):
    text = cb_message.message.reply_to_message.text
    args = text.split(maxsplit=1)

    name = ""
    if len(args) > 1:
        arg_val = args[1]
        if not (arg_val.startswith(("|", "pswd:", "enc:")) or is_magnet(arg_val) or is_url(arg_val) or is_rclone_path(arg_val)):
            name = arg_val

    if up_path.startswith('mrcc:'):
        is_rclone = True

    listener = MirrorLeechListener(cb_message, is_leech=is_leech, is_qbit=is_qbit, is_ytdlp=is_ytdlp, is_gdrive=is_gdrive, is_rclone=is_rclone, tag=tag, is_bulk=is_bulk)

    if is_gdrive_link(link) or is_filepress_link(link) or is_udrive_link(link) or is_sharer_link(link) or is_sharedrive_link(link):
        if not is_leech and not is_qbit and not is_ytdlp:
            gdrive_limit = GDRIVE_LIMIT
            if gdrive_limit:
                listener.size = get_readable_file_size(link)
            if gdrive_limit and listener.size > gdrive_limit * 1024**3:
                return await listener.onDownloadError(WZML_MID.GDRIVE_LIMIT_EXCEEDED.format(gdrive_limit, listener.size))
        if is_gdrive:
            await gdriveList(link, listener)
        else:
            await add_gd_download(link, up_path, listener, name)
    elif is_mega_link(link):
        mega_limit = MEGA_LIMIT
        if mega_limit:
            listener.size = get_readable_file_size(link)
        if mega_limit and listener.size > mega_limit * 1024**3:
            return await listener.onDownloadError(WZML_MID.MEGA_LIMIT_EXCEEDED.format(mega_limit, listener.size))
        await add_mega_download(link, f'{listener.dir}{name}', listener)
    elif is_qbit:
        await add_qb_torrent(link, up_path, listener, tag)
    elif is_rclone_path(link):
        if not is_rclone_config(listener.user_id):
            return await send_message(cb_message.message, 'Rclone config not exists!')
        if not is_rclone:
            return await send_message(cb_message.message, 'Please provide rclone argument after command!')
        await rcloneList(link, get_rclone_data(listener.user_id, 'RCLONE_CONFIG'), listener)
    elif is_ytdlp:
        ytdlp_limit = YTDLP_LIMIT
        if ytdlp_limit:
            listener.size = get_readable_file_size(link)
        if ytdlp_limit and listener.size > ytdlp_limit * 1024**3:
            return await listener.onDownloadError(WZML_MID.YTDLP_LIMIT_EXCEEDED.format(ytdlp_limit, listener.size))
        playlist_limit = PLAYLIST_LIMIT
        if playlist_limit and ('playlist' in link or '/c/' in link or '/user/' in link):
            playlist_count = await add_yt_dlp_download(link, f'{up_path}/{name}', listener, True)
            if playlist_count > playlist_limit:
                return await listener.onDownloadError(WZML_MID.PLAYLIST_LIMIT_EXCEEDED.format(playlist_limit))
        await add_yt_dlp_download(link, f'{up_path}/{name}', listener)
    else:
        if is_magnet(link):
            torrent_limit = TORRENT_DIRECT_LIMIT
            if torrent_limit:
                listener.size = get_readable_file_size(link)
            if torrent_limit and listener.size > torrent_limit * 1024**3:
                return await listener.onDownloadError(WZML_MID.TORRENT_LIMIT_EXCEEDED.format(torrent_limit, listener.size))
        else:
            direct_limit = TORRENT_DIRECT_LIMIT
            if direct_limit:
                listener.size = get_readable_file_size(link)
            if direct_limit and listener.size > direct_limit * 1024**3:
                return await listener.onDownloadError(WZML_MID.DIRECT_LIMIT_EXCEEDED.format(direct_limit, listener.size))
        await add_aria2c_download(link, up_path, listener, name, tag)
    await delete_links(cb_message.message)

async def mirror_leech_callback(client, callback_query):
    query = callback_query
    user_id = query.from_user.id
    message = query.message
    data = query.data.split("|")

    if int(data[2]) != user_id and not await CustomFilters.sudo(client, query):
        return await query.answer("This is not for you!", show_alert=True)

    if data[1] == "cancel":
        await query.answer()
        await delete_message(message)
        return

    await query.answer()
    category_key = data[1]
    up_path = CUSTOM_DESTINATIONS.get(category_key)

    if not up_path:
        await edit_message(message, "Kategori tidak valid!")
        return

    is_leech = data[2] == 'True'
    is_qbit = data[3] == 'True'
    is_ytdlp = data[4] == 'True'
    is_gdrive = data[5] == 'True'
    is_rclone = data[6] == 'True'

    tag = f"@{query.from_user.username}"
    reply_to = message.reply_to_message.reply_to_message

    if reply_to:
        link = await get_tg_link_content(reply_to) if not reply_to.text else reply_to.text.strip()
        is_bulk = 'bulk' in message.reply_to_message.text.lower()
    else:
        link = "" # This part needs careful handling if original link is not from reply

    if not link:
        await edit_message(message, "Tidak dapat menemukan link/file asli. Harap mulai lagi.")
        return

    await edit_message(message, f"✅ Oke! File akan di-mirror ke folder **{category_key.upper()}**.")
    await start_mirror_leech_final(client, query, link, up_path, tag, is_leech, is_qbit, is_ytdlp, is_gdrive, is_rclone, is_bulk)

async def mirror(client, message: Message):
    await run_mirror_leech(client, message)

async def qb_mirror(client, message: Message):
    await run_mirror_leech(client, message, is_qbit=True)

async def leech(client, message: Message):
    await run_mirror_leech(client, message, is_leech=True)

async def qb_leech(client, message: Message):
    await run_mirror_leech(client, message, is_leech=True, is_qbit=True)

async def ytdl(client, message: Message):
    await run_mirror_leech(client, message, is_ytdlp=True)

async def ytdl_leech(client, message: Message):
    await run_mirror_leech(client, message, is_leech=True, is_ytdlp=True)

async def gdrive(client, message: Message):
    await run_mirror_leech(client, message, is_gdrive=True)

async def rclone(client, message: Message):
    await run_mirror_leech(client, message, is_rclone=True)
