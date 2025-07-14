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

# --- CUSTOM FOLDER IDs ---
CUSTOM_DESTINATIONS = {
    'app':       '1tUCYi4x3l1_omXwspD2eiPlblBCJSgOV',
    'video':     '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'audio':     '1M0eYHR0qg9OtzQUJT030b-x5fxt8DKAx',
    'files':     '1gxPwlYhbKmzhYSk-ququFUzfBG5cj-lc',
    'folder':    '1E9Ng9uMqJ2yAK8hqirp7EOImSGgKecW6',
}

# --- CATEGORY DISPLAY NAMES ---
CATEGORY_DISPLAY_NAMES = {
    'video': '🎬 Video',
    'audio': '🎵 Audio',
    'app': '📦 Aplikasi',
    'files': '📄 Dokumen',
    'folder': '🗂️ Arsip (ZIP/RAR)',
}

@new_task
async def _mirror_leech(
    client, message, isQbit=False, isLeech=False, sameDir=None, bulk=[], custom_upload_path=None
):
    text = message.text.split("\n")
    input_list = text[0].split(" ")

    arg_base = {
        "link": "", "-i": "0", "-m": "", "-sd": "", "-samedir": "", "-d": False, "-seed": False,
        "-j": False, "-join": False, "-s": False, "-select": False, "-b": False, "-bulk": False,
        "-n": "", "-name": "", "-e": False, "-extract": False, "-uz": False, "-unzip": False,
        "-z": False, "-zip": False, "-up": "", "-upload": "", "-rcf": "", "-u": "", "-user": "",
        "-p": "", "-pass": "", "-id": "", "-index": "", "-c": "", "-category": "",
        "-ud": "", "-dump": "", "-h": "", "-headers": "", "-ss": "0", "-screenshots": "",
        "-t": "", "-thumb": "",
    }

    args = arg_parser(input_list[1:], arg_base)
    cmd = input_list[0].split("@")[0]
    multi = int(args["-i"]) if args["-i"].isdigit() else 0
    link = args["link"]
    folder_name = args["-m"] or args["-sd"] or args["-samedir"]
    seed = args["-d"] or args["-seed"]
    join = args["-j"] or args["-join"]
    select = args["-s"] or args["-select"]
    isBulk = args["-b"] or args["-bulk"]
    name = args["-n"] or args["-name"]
    extract = (args["-e"] or args["-extract"] or args["-uz"] or args["-unzip"] or "uz" in cmd or "unzip" in cmd)
    compress = (args["-z"] or args["-zip"] or (not extract and ("z" in cmd or "zip" in cmd)))
    up = args["-up"] or args["-upload"]
    rcf = args["-rcf"]
    drive_id = args["-id"]
    index_link = args["-index"]
    gd_cat = args["-c"] or args["-category"]
    user_dump = args["-ud"] or args["-dump"]
    headers = args["-h"] or args["-headers"]
    ussr = args["-u"] or args["-user"]
    pssw = args["-p"] or args["-pass"]
    thumb = args["-t"] or args["-thumb"]
    sshots_arg = args["-ss"] or args["-screenshots"]
    sshots = int(sshots_arg) if sshots_arg.isdigit() else 0
    bulk_start = 0
    bulk_end = 0
    ratio = None
    seed_time = None
    reply_to = None
    file_ = None
    session = ""
    decrypter = None
        
    if not isinstance(seed, bool):
        dargs = seed.split(":")
        ratio = dargs[0] or None
        if len(dargs) == 2:
            seed_time = dargs[1] or None
        seed = True

    if not isinstance(isBulk, bool):
        dargs = isBulk.split(":")
        bulk_start = dargs[0] or None
        if len(dargs) == 2:
            bulk_end = dargs[1] or None
        isBulk = True

    if drive_id and is_gdrive_link(drive_id):
        drive_id = GoogleDriveHelper.getIdFromUrl(drive_id)

    if folder_name and not isBulk:
        seed = False
        ratio = None
        seed_time = None
        folder_name = f"/{folder_name}"
        if sameDir is None:
            sameDir = {"total": multi, "tasks": set(), "name": folder_name}
        sameDir["tasks"].add(message.id)

    if isBulk:
        try:
            bulk = await extract_bulk_links(message, bulk_start, bulk_end)
            if len(bulk) == 0:
                raise ValueError("Bulk Empty!")
        except:
            await sendMessage(message, "Reply to a text file or a tg message that has links separated by a new line!")
            return
        b_msg = input_list[:1]
        b_msg.append(f"{bulk[0]} -i {len(bulk)}")
        nextmsg = await sendMessage(message, " ".join(b_msg))
        nextmsg = await client.get_messages(chat_id=message.chat.id, message_ids=nextmsg.id)
        nextmsg.from_user = message.from_user
        _mirror_leech(client, nextmsg, isQbit, isLeech, sameDir, bulk)
        return

    if len(bulk) != 0:
        del bulk[0]

    @new_task
    async def __run_multi():
        if multi <= 1:
            return
        await sleep(5)
        if len(bulk) != 0:
            msg = input_list[:1]
            msg.append(f"{bulk[0]} -i {multi - 1}")
            nextmsg = await sendMessage(message, " ".join(msg))
        else:
            msg = [s.strip() for s in input_list]
            index = msg.index("-i")
            msg[index + 1] = f"{multi - 1}"
            nextmsg = await client.get_messages(chat_id=message.chat.id, message_ids=message.reply_to_message_id + 1)
            nextmsg = await sendMessage(nextmsg, " ".join(msg))
        nextmsg = await client.get_messageshydes(client, message: Message, isQbit=False, isLeech=False):
    text_args = message.text.split()
    if any(arg in ['-s', '-select', '-up', '-samedir', '-sd', '-m'] for arg in text_args):
        await _mirror_leech(client, message, isQbit, isLeech)
    else:
        link = ""
        reply_to = message.reply_to_message
        if reply_to:
            if reply_to.text:
                link = reply_to.text.strip()
            elif reply_to.media:
                link = reply_to.text or reply_to.caption or ""

        if not link and not (reply_to and reply_to.media):
            command_parts = message.text.split(' ', 1)
            if len(command_parts) > 1:
                link = command_parts[1].strip()

        if not link and not (reply_to and reply_to.media):
            await sendMessage(message, "Tidak ada link/file yang valid untuk di-mirror.")
            return

        category = get_file_category(link, reply_to)
        up_path = CUSTOM_DESTINATIONS.get(category)
        if not up_path:
            await sendMessage(message, "Kategori tidak valid!")
            return

        await sendMessage(message, f"✅ Oke! File akan di-mirror ke folder {CATEGORY_DISPLAY_NAMES[category]}.")
        await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=up_path)

async def mirror(client, message):
    await run_mirror_leech_entry(client, message)

async def qb_mirror(client, message):
    await run_mirror_leech_entry(client, message, isQbit=True)

async def leech(client, message):
    await run_mirror_leech_entry(client, message, isLeech=True)

async def qb_leech(client, message):
    await run_mirror_leech_entry(client, message, isQbit=True, isLeech=True)

bot.add_handler(
    MessageHandler(
        mirror,
        filters=command(BotCommands.MirrorCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        qb_mirror,
        filters=command(BotCommands.QbMirrorCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        leech,
        filters=command(BotCommands.LeechCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        qb_leech,
        filters=command(BotCommands.QbLeechCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(wzmlxcb, filters=regex(r"^wzmlx")))
