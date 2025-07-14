# FINAL CATEGORY-BASED MIRROR_LEECH.PY
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message
from pyrogram.filters import command, regex
from html import escape
from base64 import b64encode
from re import match as re_match
from asyncio import sleep

from bot import (
    bot,
    DOWNLOAD_DIR,
    LOGGER,
    config_dict,
)
from bot.helper.ext_utils.bot_utils import (
    is_url,
    is_magnet,
    is_mega_link,
    is_gdrive_link,
    new_task,
    sync_to_async,
    is_rclone_path,
    arg_parser,
)
from bot.helper.ext_utils.task_manager import task_utils
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.gd_download import add_gd_download
from bot.helper.mirror_utils.download_utils.qbit_download import add_qb_torrent
from bot.helper.mirror_utils.download_utils.telegram_download import (
    TelegramDownloadHelper,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    editMessage,
    deleteMessage,
    delete_links,
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener

# --- NEW CUSTOM CATEGORY IDs ---
CUSTOM_CATEGORIES = {
    'image':       '1Ma-Zw9aTY62csTGJlLHojWO-RSG2cCPY',
    'document':    '1xS5BoYrHEHE145zhBgEzZmH3Pbqk5Fyg',
    'audio':       '1nrJhp_iPhqq8yJqjgT4TgM5r-yvSRj6o',
    'video':       '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R', # Your existing video folder
    'archive':     '10ME4IfXdluY_23NKUcybu4Zbi__h40fR',
    'application': '1I45We4iE9z2R6-VW1LW2eo6asPNhTk13',
    'others':      '1WsTfhh0DEZmF5ehNfftX4jFQmSbB_KOb'
}

@new_task
async def _mirror_leech(client, message, isQbit=False, isLeech=False, isZip=False, custom_drive_id=""):
    
    args = arg_parser(message.text.split(" ", 1)[1] if ' ' in message.text else "", {'-n': ''})
    name = args.get('-n', '')

    reply_to = message.reply_to_message
    if not (link := args.get("link")) and reply_to:
        link = reply_to.text.split("\n", 1)[0].strip() if reply_to.text else reply_to.link

    if not is_url(link) and not is_magnet(link) and not (reply_to and reply_to.media):
        await sendMessage(message, "Provide a valid link/magnet or reply to a file.")
        return

    tag = message.from_user.mention
    
    # Set upload path logic
    up = custom_drive_id
    if not isLeech and not up:
        up = config_dict.get("GDRIVE_ID")
    elif isLeech:
        up = "leech"

    listener = MirrorLeechListener(message, isZip=isZip, isLeech=isLeech, tag=tag, drive_id=up)

    if reply_to and reply_to.media:
        await TelegramDownloadHelper(listener).add_download(reply_to, f"{DOWNLOAD_DIR}{listener.uid}/", name)
    elif isQbit:
        await add_qb_torrent(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener)
    else:
        await add_aria2c_download(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener, name)

def get_category_by_mime(mime_type, file_name):
    if not mime_type:
        return 'others'
    if mime_type.startswith('image'): return 'image'
    if mime_type.startswith('video'): return 'video'
    if mime_type.startswith('audio'): return 'audio'
    if 'zip' in mime_type or 'rar' in mime_type or '7z' in mime_type or file_name.lower().endswith(('.zip', '.rar', '.7z')):
        return 'archive'
    if 'pdf' in mime_type or 'word' in mime_type or 'excel' in mime_type or 'powerpoint' in mime_type:
        return 'document'
    if 'x-msdownload' in mime_type or 'vnd.android.package-archive' in mime_type or file_name.lower().endswith(('.exe', '.apk')):
        return 'application'
    return 'others'

@new_task
async def category_selection_logic(client, message, isQbit=False, isLeech=False, isZip=False):
    reply_to = message.reply_to_message
    category = 'others' # Default category

    if reply_to and reply_to.media:
        media = getattr(reply_to, reply_to.media.value)
        mime_type = getattr(media, 'mime_type', '')
        file_name = getattr(media, 'file_name', '')
        category = get_category_by_mime(mime_type, file_name)
    else:
        await sendMessage(message, "Silakan reply ke sebuah file atau berikan link.")
        return

    user_id = message.from_user.id
    buttons = ButtonMaker()
    
    msg = f"<b>Tipe file terdeteksi:</b> <code>{category.upper()}</code>\n"
    msg += "Pilih folder tujuan:"

    cmd_prefix = "qbmirror" if isQbit else "mirror"
    if isLeech: cmd_prefix = "qbleech" if isQbit else "leech"
    if isZip: cmd_prefix += "zip"

    for cat, folder_id in CUSTOM_CATEGORIES.items():
        buttons.ibutton(f"📂 {cat.capitalize()}", f"cat_sel|{cmd_prefix}|{user_id}|{message.id}|{folder_id}")
    
    # Add a default button
    buttons.ibutton("Default GDrive", f"cat_sel|{cmd_prefix}|{user_id}|{message.id}|{config_dict.get('GDRIVE_ID')}")

    buttons.ibutton("❌ Batal", f"cat_sel|cancel|{user_id}|{message.id}", "footer")

    await sendMessage(message, msg, buttons.build_menu(2))

@bot.on_callback_query(regex(r"^cat_sel"))
async def category_select_callback(client, query):
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


# Register Handlers
@new_task
async def mirror_leech_entry(client, message):
    isQbit = message.text.startswith(f"/{BotCommands.QbMirrorCommand}")
    isLeech = message.text.startswith(f"/{BotCommands.LeechCommand}")
    isZip = "zip" in message.text

    if " " in message.text or (message.reply_to_message and message.reply_to_message.text):
        await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, isZip=isZip)
    else:
        await category_selection_logic(client, message, isQbit=isQbit, isLeech=isLeech, isZip=isZip)

bot.add_handler(MessageHandler(mirror_leech_entry, filters=command([BotCommands.MirrorCommand, BotCommands.LeechCommand, BotCommands.QbMirrorCommand, BotCommands.QbLeechCommand, f"{BotCommands.MirrorCommand}zip", f"{BotCommands.LeechCommand}zip"]) & CustomFilters.authorized))
