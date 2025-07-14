# Ganti seluruh isi file dengan ini
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message
from pyrogram.filters import command, regex
from html import escape
from traceback import format_exc
from base64 import b64encode
from re import match as re_match
from asyncio import sleep, wrap_future
from aiofiles import open as aiopen
from aiofiles.os import path as aiopath
from cloudscraper import create_scraper

from bot import (
    bot,
    DOWNLOAD_DIR,
    LOGGER,
    config_dict,
    bot_name,
    categories_dict,
    user_data,
)
from bot.helper.mirror_utils.download_utils.direct_downloader import add_direct_download
from bot.helper.ext_utils.bot_utils import (
    is_url,
    is_magnet,
    is_mega_link,
    is_gdrive_link,
    get_content_type,
    new_task,
    sync_to_async,
    is_rclone_path,
    is_telegram_link,
    arg_parser,
    fetch_user_tds,
    fetch_user_dumps,
    get_stats,
)
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_utils.download_utils.mega_download import add_mega_download
from bot.helper.mirror_utils.download_utils.rclone_download import add_rclone_download
from bot.helper.mirror_utils.rclone_utils.list import RcloneList
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.download_utils.direct_link_generator import (
    direct_link_generator,
)
from bot.helper.mirror_utils.download_utils.telegram_download import (
    TelegramDownloadHelper,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    editReplyMarkup,
    deleteMessage,
    get_tg_link_content,
    delete_links,
    auto_delete_message,
    open_category_btns,
    open_dump_btns,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.help_messages import (
    MIRROR_HELP_MESSAGE,
    CLONE_HELP_MESSAGE,
    YT_HELP_MESSAGE,
    help_string,
)
from bot.modules.gen_pyro_sess import get_decrypt_key

CUSTOM_DESTINATIONS = {
    'image':       '1Ma-Zw9aTY62csTGJlLHojWO-RSG2cCPY',
    'document':    '1xS5BoYrHEHE145zhBgEzZmH3Pbqk5Fyg',
    'audio':       '1nrJhp_iPhqq8yJqjgT4TgM5r-yvSRj6o',
    'video':       '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'archive':     '10ME4IfXdluY_23NKUcybu4Zbi__h40fR',
    'application': '1I45We4iE9z2R6-VW1LW2eo6asPNhTk13',
    'others':      '1WsTfhh0DEZmF5ehNfftX4jFQmSbB_KOb',
}

CATEGORY_DISPLAY_NAMES = {
    'image': '🖼️ Gambar',
    'document': '📄 Dokumen',
    'audio': '🎵 Audio',
    'video': '📹 Video',
    'archive': '🗜️ Arsip',
    'application': '💿 Aplikasi',
    'others': '📂 Lainnya',
}

@new_task
async def _mirror_leech(
    client, message, isQbit=False, isLeech=False, sameDir=None, bulk=[], custom_upload_path=None, category_name=None
):
    # ... (kode fungsi ini tidak berubah dari versi asli Anda)
    # Untuk singkatnya, saya hanya akan menunjukkan bagian yang relevan
    # Pastikan file Anda lengkap. Jika ragu, gunakan kode dari prompt sebelumnya.
    listener = MirrorLeechListener(message, compress, extract, isQbit, isLeech, tag, select, seed, sameDir, rcf, up, join, drive_id=drive_id, index_link=index_link, source_url=org_link, leech_utils={"screenshots": sshots, "thumb": thumb}, category_name=category_name)
    
    # ... sisa fungsi ...

def get_file_category(link, reply_to_message):
    # ... (kode fungsi ini tidak berubah) ...
    return 'others'

async def run_mirror_leech_entry(client, message: Message, isQbit=False, isLeech=False):
    text_args = message.text.split()
    if any(arg in ['-s', '-select', '-up', '-samedir', '-sd', '-m', '-id'] for arg in text_args):
        await _mirror_leech(client, message, isQbit, isLeech)
    else:
        link = ""
        reply_to = message.reply_to_message
        
        command_parts = message.text.split(' ', 1)
        if len(command_parts) > 1:
            link = command_parts[1].strip()
        elif reply_to and reply_to.text:
            link = reply_to.text.strip().split('\n', 1)[0]
        elif reply_to and reply_to.media:
            pass

        if not link and not (reply_to and reply_to.media):
            await sendMessage(message, "Tidak ada link atau file yang valid untuk di-mirror.")
            return

        category = get_file_category(link, reply_to)
        up_path = CUSTOM_DESTINATIONS.get(category)
        
        if not up_path:
            await sendMessage(message, "Kategori tidak dapat ditentukan atau tidak valid!")
            return
        
        category_name = CATEGORY_DISPLAY_NAMES.get(category)
        
        # PERBAIKAN PESAN =
        await sendMessage(message, f"✅ Oke! File akan di-mirror ke folder = {category_name}.")
        await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=up_path, category_name=category_name)
        
# ... Sisa file (wzmlxcb, mirror, qb_mirror, etc.) tidak berubah
# Pastikan Anda menggunakan versi lengkap dari file yang sudah ada
