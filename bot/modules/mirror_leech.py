# FINAL AND COMPLETE mirror_leech.py (V22)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from pyrogram.types import Message
from html import escape
from base64 import b64encode
from re import match as re_match
from asyncio import sleep

from bot import (
    bot,
    DOWNLOAD_DIR,
    LOGGER,
    config_dict,
    user_data,
    categories_dict
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
    fetch_user_tds
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
from bot.helper.ext_utils.bulk_links import extract_bulk_links
from bot.modules.gen_pyro_sess import get_decrypt_key

# --- CUSTOM CATEGORIES ---
CUSTOM_CATEGORIES = {
    'image':       '1Ma-Zw9aTY62csTGJlLHojWO-RSG2cCPY',
    'document':    '1xS5BoYrHEHE145zhBgEzZmH3Pbqk5Fyg',
    'audio':       '1nrJhp_iPhqq8yJqjgT4TgM5r-yvSRj6o',
    'video':       '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'archive':     '10ME4IfXdluY_23NKUcybu4Zbi__h40fR',
    'application': '1I45We4iE9z2R6-VW1LW2eo6asPNhTk13',
    'others':      '1WsTfhh0DEZmF5ehNfftX4jFQmSbB_KOb'
}

@new_task
async def _mirror_leech(client, message, isQbit=False, isLeech=False, sameDir=None, bulk=[], isZip=False, custom_drive_id=""):
    text = message.text.split("\n")
    input_list = text[0].split(" ")
    
    args = arg_parser(input_list[1:], {'-n': '', '-up': '', '-id': ''})
    name = args.get('-n', '')
    up = custom_drive_id or args.get('-up')
    drive_id = args.get('-id')

    link = ""
    reply_to = message.reply_to_message
    if reply_to:
        if reply_to.text:
            link = reply_to.text.split("\n", 1)[0].strip()
    elif len(input_list) > 1:
        link = input_list[1]
    
    if not link and reply_to and reply_to.media:
        pass  # Handle replied files later
    elif not is_url(link) and not is_magnet(link):
        await sendMessage(message, "Provide a valid link/magnet or reply to a file.")
        return

    tag = message.from_user.mention
    
    if not isLeech and not up:
        up = config_dict.get("GDRIVE_ID")
    elif isLeech:
        up = "leech"

    listener = MirrorLeechListener(message, isZip=isZip, isLeech=isLeech, tag=tag, drive_id=up)

    if reply_to and reply_to.media:
        # Pass the 'session' and 'decrypter' which are None for public files
        await TelegramDownloadHelper(listener).add_download(reply_to, f"{DOWNLOAD_DIR}{listener.uid}/", name, "", None)
    elif isQbit:
        await add_qb_torrent(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener)
    else:
        await add_aria2c_download(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener, name)

def get_category_by_mime(mime_type, file_name):
    mime_type = mime_type or ""
    file_name = file_name or ""
    
    if mime_type.startswith('image'): return 'image'
    if mime_type.startswith('video'): return 'video'
    if mime_type.startswith('audio'): return 'audio'
    if any(ext in file_name.lower() for ext in ['.zip', '.rar', '.7z']): return 'archive'
    if any(mime in mime_type for mime in ['pdf', 'word', 'excel', 'powerpoint']): return 'document'
    if any(ext in file_name.lower() for ext in ['.exe', '.apk']): return 'application'
    return 'others'

async def mirror_leech_router(client, message, isQbit=False, isLeech=False, isZip=False):
    if message.reply_to_message and message.reply_to_message.media:
        await category_selection_logic(client, message, isQbit, isLeech, isZip)
    else:
        await _mirror_leech(client, message, isQbit, isLeech, isZip)

async def category_selection_logic(client, message, isQbit=False, isLeech=False, isZip=False):
    reply_to = message.reply_to_message
    media = getattr(reply_to, reply_to.media.value)
    category = get_category_by_mime(getattr(media, 'mime_type', ''), getattr(media, 'file_name', ''))
    
    user_id = message.from_user.id
    buttons = ButtonMaker()
    
    msg = f"<b>Tipe file terdeteksi:</b> <code>{category.upper()}</code>\n"
    msg += "Pilih folder tujuan:"

    cmd_prefix = "qbmirror" if isQbit else "mirror"
    if isLeech: cmd_prefix = "qbleech" if isQbit else "leech"
    if isZip: cmd_prefix += "zip"

    # Auto-suggested category button
    buttons.ibutton(f"📂 {category.capitalize()} (Auto)", f"cat_sel|{cmd_prefix}|{user_id}|{message.id}|{CUSTOM_CATEGORIES.get(category)}")
    for cat, folder_id in CUSTOM_CATEGORIES.items():
        if cat != category:
            buttons.ibutton(f"📂 {cat.capitalize()}", f"cat_sel|{cmd_prefix}|{user_id}|{message.id}|{folder_id}")
    
    buttons.ibutton("Default GDrive", f"cat_sel|{cmd_prefix}|{user_id}|{message.id}|{config_dict.get('GDRIVE_ID')}", 'footer')
    buttons.ibutton("❌ Batal", f"cat_sel|cancel|{user_id}|{message.id}", "footer")

    await sendMessage(message, msg, buttons.build_menu(2))

@new_task
async def mirror_leech_callback(client, query):
    data = query.data.split("|")
    user_id = query.from_user.id
    
    if int(data[2]) != user_id:
        return await query.answer("Ini bukan tombol untukmu!", show_alert=True)
    
    if data[1] == "cancel":
        await query.answer()
        return await deleteMessage(query.message)

    await query.answer()
    
    cmd_prefix = data[1]
    original_msg_id = int(data[3])
    drive_id = data[4]
    
    try:
        original_message = await client.get_messages(chat_id=query.message.chat.id, message_ids=original_msg_id)
    except Exception as e:
        LOGGER.error(f"Could not get original message: {e}")
        return await editMessage(query.message, "Error: Tidak dapat menemukan pesan asli.")

    await deleteMessage(query.message)
    
    isQbit = 'qb' in cmd_prefix
    isLeech = 'leech' in cmd_prefix
    isZip = 'zip' in cmd_prefix
    
    await _mirror_leech(client, original_message, isQbit=isQbit, isLeech=isLeech, isZip=isZip, custom_drive_id=drive_id)

async def mirror(client, message): await mirror_leech_router(client, message)
async def qb_mirror(client, message): await mirror_leech_router(client, message, isQbit=True)
async def zip_mirror(client, message): await mirror_leech_router(client, message, isZip=True)
async def qb_zip_mirror(client, message): await mirror_leech_router(client, message, isQbit=True, isZip=True)
async def leech(client, message): await mirror_leech_router(client, message, isLeech=True)
async def qb_leech(client, message): await mirror_leech_router(client, message, isQbit=True, isLeech=True)
async def zip_leech(client, message): await mirror_leech_router(client, message, isLeech=True, isZip=True)
async def qb_zip_leech(client, message): await mirror_leech_router(client, message, isQbit=True, isLeech=True, isZip=True)

bot.add_handler(MessageHandler(mirror, filters=command(BotCommands.MirrorCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_mirror, filters=command(BotCommands.QbMirrorCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(zip_mirror, filters=command(f"{BotCommands.MirrorCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_zip_mirror, filters=command(f"{BotCommands.QbMirrorCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(leech, filters=command(BotCommands.LeechCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_leech, filters=command(BotCommands.QbLeechCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(zip_leech, filters=command(f"{BotCommands.LeechCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_zip_leech, filters=command(f"{BotCommands.QbLeechCommand}zip") & CustomFilters.authorized))
bot.add_handler(CallbackQueryHandler(mirror_leech_callback, filters=regex(r"^cat_sel")))
