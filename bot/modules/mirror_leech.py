# FINAL MERGED AND CORRECTED CODE (V7) zee
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
from bot.helper.ext_utils.bulk_links import extract_bulk_links
from bot.modules.gen_pyro_sess import get_decrypt_key


# --- CUSTOM FOLDER IDs ---
CUSTOM_DESTINATIONS = {
    'app':       '1tUCYi4x3l1_omXwspD2eiPlblBCJSgOV',
    'video':     '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'audio':     '1M0eYHR0qg9OtzQUJT030b-x5fxt8DKAx',
    'files':     '1gxPwlYhbKmzhYSk-ququFUzfBG5cj-lc',
    'folder':    '1E9Ng9uMqJ2yAK8hqirp7EOImSGgKecW6',
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
        nextmsg = await client.get_messages(chat_id=message.chat.id, message_ids=nextmsg.id)
        if folder_name:
            sameDir["tasks"].add(nextmsg.id)
        nextmsg.from_user = message.from_user
        await sleep(5)
        _mirror_leech(client, nextmsg, isQbit, isLeech, sameDir, bulk)

    __run_multi()

    path = f"{DOWNLOAD_DIR}{message.id}{folder_name}"
    
    sender_chat = message.sender_chat
    if sender_chat:
        tag = sender_chat.title
    else:
        tag = message.from_user.mention
    
    decrypter = None
    reply_to = message.reply_to_message
    if not link and reply_to:
        if reply_to.text:
            link = reply_to.text.split("\n", 1)[0].strip()
            
    if link and is_telegram_link(link):
        try:
            reply_to, session = await get_tg_link_content(link, message.from_user.id)
        except Exception as e:
            await sendMessage(message, f"ERROR: {e}")
            return

    if reply_to:
        file_ = getattr(reply_to, reply_to.media.value) if reply_to.media else None
        if file_ is None and reply_to.text:
            reply_text = reply_to.text.split("\n", 1)[0].strip()
            if is_url(reply_text) or is_magnet(reply_text):
                link = reply_text
        elif reply_to.document and (file_.mime_type == "application/x-bittorrent" or file_.file_name.endswith(".torrent")):
            link = await reply_to.download()
            file_ = None

    if (not is_url(link) and not is_magnet(link) and not await aiopath.exists(link) and not is_rclone_path(link) and file_ is None):
        await sendMessage(message, MIRROR_HELP_MESSAGE[0])
        return

    error_msg = []
    error_button = None
    task_utilis_msg, error_button = await task_utils(message)
    if task_utilis_msg:
        error_msg.extend(task_utilis_msg)

    if error_msg:
        final_msg = f"Hey {tag},\n"
        for __i, __msg in enumerate(error_msg, 1):
            final_msg += f"\n<b>{__i}</b>: {__msg}\n"
        if error_button is not None:
            error_button = error_button.build_menu(2)
        await sendMessage(message, final_msg, error_button)
        return

    org_link = link
    if link:
        LOGGER.info(link)

    if not isLeech:
        if custom_upload_path:
            drive_id = custom_upload_path
            up = 'gd'
        if not up:
            if config_dict["DEFAULT_UPLOAD"] == "rc":
                up = config_dict.get("RCLONE_PATH", "")
            else:
                up = "gd"
        if up == "gd" and not drive_id and not config_dict.get("GDRIVE_ID"):
             await sendMessage(message, "GDRIVE_ID not Provided!")
             return
        if up == "gd" and drive_id and not await sync_to_async(GoogleDriveHelper().getFolderData, drive_id):
            return await sendMessage(message, "Google Drive ID validation failed!!")
        if not up:
            await sendMessage(message, "No Upload Destination specified!")
            return
        if up != 'gd' and not is_rclone_path(up):
            await sendMessage(message, f"Wrong Rclone Upload Destination: {up}")
            return
    else:
        up = 'leech'

    listener = MirrorLeechListener(message, compress, extract, isQbit, isLeech, tag, select, seed, sameDir, rcf, up, join, drive_id=drive_id, index_link=index_link, source_url=org_link, leech_utils={"screenshots": sshots, "thumb": thumb})

    if file_ is not None:
        await TelegramDownloadHelper(listener).add_download(reply_to, f"{path}/", name)
    elif is_rclone_path(link):
        await add_rclone_download(link, config_dict.get("RCLONE_CONFIG"), f"{path}/", name, listener)
    elif is_gdrive_link(link):
        await add_gd_download(link, path, listener, name)
    elif is_mega_link(link):
        await add_mega_download(link, f"{path}/", listener, name)
    elif isQbit:
        await add_qb_torrent(link, path, listener, ratio, seed_time)
    else:
        headers = ""
        if ussr or pssw:
            auth = f"{ussr}:{pssw}"
            headers = f"authorization: Basic {b64encode(auth.encode()).decode('ascii')}"
        await add_aria2c_download(link, path, listener, name, headers, ratio, seed_time)

# --- START OF CUSTOM CATEGORY LOGIC ---

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

async def category_selection_logic(client, message: Message, isQbit=False, isLeech=False):
    isBulk = 'bulk' in message.text.split(' ')[0].lower()
    
    link = ""
    reply_to = message.reply_to_message
    if reply_to:
        if reply_to.text:
            link = reply_to.text.strip()
        elif reply_to.media:
            link = await get_tg_link_content(reply_to, message.from_user.id)
    
    if not link:
        command_parts = message.text.split(' ', 1)
        if len(command_parts) > 1:
            link = command_parts[1].strip()

    if not link:
        return await sendMessage(message, "Tidak ada link/file yang valid untuk di-mirror.")

    category = get_file_category(link, reply_to)
    user_id = message.from_user.id
    buttons = ButtonMaker()
    
    msg = f"<b>Tipe file terdeteksi:</b> <code>{category.upper()}</code>\n"
    msg += "Pilih folder tujuan untuk melanjutkan mirror:"

    flags = f"{isQbit}|{isLeech}|{isBulk}|{message.id}"

    buttons.ibutton("🎬 Video", f"cat_up|video|{user_id}|{flags}")
    buttons.ibutton("🎵 Audio", f"cat_up|audio|{user_id}|{flags}")
    buttons.ibutton("📦 Aplikasi", f"cat_up|app|{user_id}|{flags}")
    buttons.ibutton("📄 Dokumen", f"cat_up|files|{user_id}|{flags}")
    buttons.ibutton("🗂️ Arsip (ZIP/RAR)", f"cat_up|folder|{user_id}|{flags}")
    buttons.ibutton("❌ Batal", f"cat_up|cancel|{user_id}|{flags}")

    await sendMessage(message, msg, buttons.build_menu(2))

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
        return await deleteMessage(message)

    await query.answer()
    category_key = data[1]
    up_path = CUSTOM_DESTINATIONS.get(category_key)
    
    if not up_path:
        return await editMessage(message, "Kategori tidak valid!")

    try:
        flags_data = data[3:]
        isQbit = flags_data[0] == 'True'
        isLeech = flags_data[1] == 'True'
        isBulk = flags_data[2] == 'True'
        original_msg_id = int(flags_data[3])
    except (ValueError, IndexError):
        return await editMessage(message, "Error: Callback data tidak lengkap. Harap mulai lagi.")
    
    try:
        original_message = await client.get_messages(chat_id=message.chat.id, message_ids=original_msg_id)
    except Exception as e:
        LOGGER.error(f"Could not get original message: {e}")
        return await editMessage(message, "Error: Tidak dapat menemukan pesan asli. Harap mulai lagi.")

    await editMessage(message, f"✅ Oke! File akan di-mirror ke folder **{category_key.upper()}**.")
    await _mirror_leech(client, original_message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=up_path)


async def run_mirror_leech_entry(client, message: Message, isQbit=False, isLeech=False):
    text_args = message.text.split()
    if any(arg in ['-s', '-select', '-up', '-samedir', '-sd', '-m'] for arg in text_args):
        await _mirror_leech(client, message, isQbit, isLeech)
    else:
        await category_selection_logic(client, message, isQbit, isLeech)

@new_task
async def wzmlxcb(_, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()
    if user_id != int(data[1]):
        return await query.answer(text="Not Yours!", show_alert=True)
    elif data[2] == "logdisplay":
        await query.answer()
        async with aiopen("log.txt", "r") as f:
            logFileLines = (await f.read()).splitlines()
        def parseline(line):
            try:
                return "[" + line.split("] [", 1)[1]
            except IndexError:
                return line
        ind, Loglines = 1, ""
        try:
            while len(Loglines) <= 3500:
                Loglines = parseline(logFileLines[-ind]) + "\n" + Loglines
                if ind == len(logFileLines):
                    break
                ind += 1
            startLine = f"<b>Showing Last {ind} Lines from log.txt:</b> \n\n----------<b>START LOG</b>----------\n\n"
            endLine = "\n----------<b>END LOG</b>----------"
            btn = ButtonMaker()
            btn.ibutton("Cʟᴏsᴇ", f"wzmlx {user_id} close")
            await sendMessage(
                message, startLine + escape(Loglines) + endLine, btn.build_menu(1)
            )
            await editReplyMarkup(message, None)
        except Exception as err:
            LOGGER.error(f"TG Log Display : {str(err)}")
    elif data[2] == "webpaste":
        await query.answer()
        async with aiopen("log.txt", "r") as f:
            logFile = await f.read()
        cget = create_scraper().request
        resp = cget(
            "POST",
            "https://spaceb.in/api/v1/documents",
            data={"content": logFile, "extension": "None"},
        ).json()
        if resp["status"] == 201:
            btn = ButtonMaker()
            btn.ubutton(
                "📨 Web Paste (SB)", f"https://spaceb.in/{resp['payload']['id']}"
            )
            await editReplyMarkup(message, btn.build_menu(1))
        else:
            LOGGER.error(f"Web Paste Failed : {str(err)}")
    elif data[2] == "botpm":
        await query.answer(url=f"https://t.me/{bot_name}?start=wzmlx")
    elif data[2] == "help":
        await query.answer()
        btn = ButtonMaker()
        btn.ibutton("Cʟᴏsᴇ", f"wzmlx {user_id} close")
        if data[3] == "CLONE":
            await editMessage(message, CLONE_HELP_MESSAGE[1], btn.build_menu(1))
        elif data[3] == "MIRROR":
            if len(data) == 4:
                msg = MIRROR_HELP_MESSAGE[1][:4000]
                btn.ibutton("Nᴇxᴛ Pᴀɢᴇ", f"wzmlx {user_id} help MIRROR readmore")
            else:
                msg = MIRROR_HELP_MESSAGE[1][4000:]
                btn.ibutton("Pʀᴇ Pᴀɢᴇ", f"wzmlx {user_id} help MIRROR")
            await editMessage(message, msg, btn.build_menu(2))
        if data[3] == "YT":
            await editMessage(message, YT_HELP_MESSAGE[1], btn.build_menu(1))
    elif data[2] == "guide":
        btn = ButtonMaker()
        btn.ibutton("Bᴀᴄᴋ", f"wzmlx {user_id} guide home")
        btn.ibutton("Cʟᴏsᴇ", f"wzmlx {user_id} close")
        if data[3] == "basic":
            await editMessage(message, help_string[0], btn.build_menu(2))
        elif data[3] == "users":
            await editMessage(message, help_string[1], btn.build_menu(2))
        elif data[3] == "miscs":
            await editMessage(message, help_string[3], btn.build_menu(2))
        elif data[3] == "admin":
            if not await CustomFilters.sudo("", query):
                return await query.answer("Not Sudo or Owner!", show_alert=True)
            await editMessage(message, help_string[2], btn.build_menu(2))
        else:
            buttons = ButtonMaker()
            buttons.ibutton("Basic", f"wzmlx {user_id} guide basic")
            buttons.ibutton("Users", f"wzmlx {user_id} guide users")
            buttons.ibutton("Mics", f"wzmlx {user_id} guide miscs")
            buttons.ibutton("Owner & Sudos", f"wzmlx {user_id} guide admin")
            buttons.ibutton("Close", f"wzmlx {user_id} close")
            await editMessage(
                message,
                "㊂ <b><i>Help Guide Menu!</i></b>\n\n<b>NOTE: <i>Click on any CMD to see more minor detalis.</i></b>",
                buttons.build_menu(2),
            )
        await query.answer()
    elif data[2] == "stats":
        msg, btn = await get_stats(query, data[3])
        await editMessage(message, msg, btn, "IMAGES")
    else:
        await query.answer()
        await deleteMessage(message)
        if message.reply_to_message:
            await deleteMessage(message.reply_to_message)
            if message.reply_to_message.reply_to_message:
                await deleteMessage(message.reply_to_message.reply_to_message)


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
