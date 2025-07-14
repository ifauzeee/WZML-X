# FINAL MIRROR_LEECH.PY (V21 - Separated Handlers)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from pyrogram.types import Message

from bot import (
    bot,
    DOWNLOAD_DIR,
    LOGGER,
    config_dict,
)
from bot.helper.ext_utils.bot_utils import (
    is_url,
    is_magnet,
    new_task,
    arg_parser,
)
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
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
)
from bot.helper.listeners.tasks_listener import MirrorLeechListener

# --- CUSTOM CATEGORY IDs ---
CUSTOM_CATEGORIES = {
    'image':       '1Ma-Zw9aTY62csTGJlLHojWO-RSG2cCPY',
    'document':    '1xS5BoYrHEHE145zhBgEzZmH3Pbqk5Fyg',
    'audio':       '1nrJhp_iPhqq8yJqjgT4TgM5r-yvSRj6o',
    'video':       '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'archive':     '10ME4IfXdluY_23NKUcybu4Zbi__h40fR',
    'application': '1I45We4iE9z2R6-VW1LW2eo6asPNhTk13',
    'others':      '1WsTfhh0DEZmF5ehNfftX4jFQmSbB_KOb'
}

def get_category_by_mime(mime_type, file_name):
    mime_type = mime_type or ""
    file_name = file_name or ""
    
    if mime_type.startswith('image'): return 'image'
    if mime_type.startswith('video'): return 'video'
    if mime_type.startswith('audio'): return 'audio'
    if 'zip' in mime_type or 'rar' in mime_type or '7z' in mime_type or file_name.lower().endswith(('.zip', '.rar', '.7z')): return 'archive'
    if 'pdf' in mime_type or 'word' in mime_type or 'excel' in mime_type or 'powerpoint' in mime_type: return 'document'
    if 'x-msdownload' in mime_type or 'vnd.android.package-archive' in mime_type or file_name.lower().endswith(('.exe', '.apk')): return 'application'
    return 'others'

async def category_selection_logic(client, message: Message, isQbit=False, isLeech=False, isZip=False):
    reply_to = message.reply_to_message
    if not reply_to or not reply_to.media:
        await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, isZip=isZip)
        return

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
    
    # Other categories
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

async def _mirror_leech(client, message, isQbit=False, isLeech=False, isZip=False, custom_drive_id=""):
    args = arg_parser(message.text.split(" ", 1)[1] if ' ' in message.text else "", {'-n': ''})
    name = args.get('-n', '')

    link = ""
    reply_to = message.reply_to_message
    if reply_to:
        link = reply_to.text.split("\n", 1)[0].strip() if reply_to.text else reply_to.link
    elif args.get("link"):
        link = args.get("link")

    if not link and not (reply_to and reply_to.media):
        await sendMessage(message, "Provide a valid link/magnet or reply to a file.")
        return

    tag = message.from_user.mention
    
    up = custom_drive_id or config_dict.get("GDRIVE_ID")
    if isLeech:
        up = "leech"

    listener = MirrorLeechListener(message, isZip=isZip, isLeech=isLeech, tag=tag, upPath=up)

    if reply_to and reply_to.media:
        await TelegramDownloadHelper(listener).add_download(reply_to, f"{DOWNLOAD_DIR}{listener.uid}/", name)
    elif isQbit:
        await add_qb_torrent(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener)
    else:
        await add_aria2c_download(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener, name)

async def mirror(client, message): await category_selection_logic(client, message)
async def leech(client, message): await category_selection_logic(client, message, isLeech=True)
async def zip_mirror(client, message): await category_selection_logic(client, message, isZip=True)
async def zip_leech(client, message): await category_selection_logic(client, message, isLeech=True, isZip=True)
async def qb_mirror(client, message): await category_selection_logic(client, message, isQbit=True)
async def qb_leech(client, message): await category_selection_logic(client, message, isQbit=True, isLeech=True)
async def qb_zip_mirror(client, message): await category_selection_logic(client, message, isQbit=True, isZip=True)
async def qb_zip_leech(client, message): await category_selection_logic(client, message, isQbit=True, isLeech=True, isZip=True)


# Register Handlers
bot.add_handler(MessageHandler(mirror, filters=command(BotCommands.MirrorCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(leech, filters=command(BotCommands.LeechCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(zip_mirror, filters=command(f"{BotCommands.MirrorCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(zip_leech, filters=command(f"{BotCommands.LeechCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_mirror, filters=command(BotCommands.QbMirrorCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_leech, filters=command(BotCommands.QbLeechCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_zip_mirror, filters=command(f"{BotCommands.QbMirrorCommand}zip") & CustomFilters.authorized))
bot.add_handler(MessageHandler(qb_zip_leech, filters=command(f"{BotCommands.QbLeechCommand}zip") & CustomFilters.authorized))

bot.add_handler(CallbackQueryHandler(mirror_leech_callback, filters=regex(r"^cat_sel")))
