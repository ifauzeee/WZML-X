# -*- coding: utf-8 -*-

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
from urllib.parse import unquote

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
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_download import TelegramDownloadHelper
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
    'image':       '1Ma-Zw9aTY62csTGJlLHojWO-RSG2cCPY',
    'document':    '1xS5BoYrHEHE145zhBgEzZmH3Pbqk5Fyg',
    'audio':       '1nrJhp_iPhqq8yJqjgT4TgM5r-yvSRj6o',
    'video':       '1tKXmbfClZlpFi3NhXvM0aY2fJLk4Aw5R',
    'archive':     '10ME4IfXdluY_23NKUcybu4Zbi__h40fR',
    'application': '1I45We4iE9z2R6-VW1LW2eo6asPNhTk13',
    'others':      '1WsTfhh0DEZmF5ehNfftX4jFQmSbB_KOb',
}

# --- CATEGORY DISPLAY NAMES ---
CATEGORY_DISPLAY_NAMES = {
    'image': '🖼️ Gambar',
    'document': '📄 Dokumen',
    'audio': '🎵 Audio',
    'video': '📹 Video',
    'archive': '🗜️ Arsip',
    'application': '💿 Aplikasi',
    'others': '📂 Lainnya',
}

def get_file_category(link, reply_to_message):
    """
    Menentukan kategori file atau folder berdasarkan MIME type, ekstensi, atau jenis tautan.
    Folder hanya masuk ke kategori 'others'.
    """
    IMG_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
    DOC_EXTS = ['.pdf', '.docx', '.doc', '.txt', '.ppt', '.pptx', '.xls', '.xlsx', '.rtf', '.csv', '.py']
    AUD_EXTS = ['.mp3', '.wav', '.ogg', '.flac', '.m4a']
    VID_EXTS = ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm']
    ARC_EXTS = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']
    APP_EXTS = ['.apk', '.exe', '.iso', '.dmg']

    # Prioritas 1: Cek apakah tautan adalah folder Google Drive
    if link and is_gdrive_link(link):
        try:
            folder_id = GoogleDriveHelper.getIdFromUrl(link)
            folder_data = GoogleDriveHelper().getFolderData(folder_id)
            if folder_data and folder_data['mimeType'] == 'application/vnd.google-apps.folder':
                return 'others'
        except Exception as e:
            LOGGER.error(f"Error checking Google Drive folder: {e}")
            return None

    # Prioritas 2: Analisis media dari pesan yang dibalas
    media = reply_to_message
    if media:
        if media.photo:
            return 'image'
        if media.video:
            return 'video'
        if media.audio or media.voice:
            return 'audio'
        if media.document:
            mime_type = media.document.mime_type or ""
            file_name = (media.document.file_name or "").lower()

            if mime_type.startswith('video/'): return 'video'
            if mime_type.startswith('audio/'): return 'audio'
            if mime_type.startswith('image/'): return 'image'
            if any(x in mime_type for x in ['zip', 'x-rar', 'x-7z-compressed']): return 'archive'
            if any(x in mime_type for x in ['pdf', 'msword', 'powerpoint', 'excel', 'text/plain', 'text/x-python']): return 'document'
            if 'vnd.android.package-archive' in mime_type or 'x-msdownload' in mime_type: return 'application'

            if any(file_name.endswith(ext) for ext in VID_EXTS): return 'video'
            if any(file_name.endswith(ext) for ext in AUD_EXTS): return 'audio'
            if any(file_name.endswith(ext) for ext in IMG_EXTS): return 'image'
            if any(file_name.endswith(ext) for ext in DOC_EXTS): return 'document'
            if any(file_name.endswith(ext) for ext in ARC_EXTS): return 'archive'
            if any(file_name.endswith(ext) for ext in APP_EXTS): return 'application'

    # Prioritas 3: Analisis ekstensi dari link
    link_lower = (link or "").lower()
    if is_magnet(link_lower): return 'archive'
    if any(ext in link_lower for ext in VID_EXTS): return 'video'
    if any(ext in link_lower for ext in AUD_EXTS): return 'audio'
    if any(ext in link_lower for ext in IMG_EXTS): return 'image'
    if any(ext in link_lower for ext in ARC_EXTS): return 'archive'
    if any(ext in link_lower for ext in APP_EXTS): return 'application'
    if any(ext in link_lower for ext in DOC_EXTS): return 'document'

    # Prioritas 4: Ambil metadata dari tautan jika tidak ada ekstensi
    if link and is_url(link):
        try:
            scraper = create_scraper()
            response = scraper.head(link, allow_redirects=True)
            content_type = response.headers.get('Content-Type', '')
            content_disposition = response.headers.get('Content-Disposition', '')
            file_name = ""
            if content_disposition and 'filename=' in content_disposition.lower():
                file_name = unquote(content_disposition.split('filename=')[1].strip('"\'')).lower()
            elif link_lower.split('/')[-1]:
                file_name = unquote(link_lower.split('/')[-1])

            if any(file_name.endswith(ext) for ext in VID_EXTS): return 'video'
            if any(file_name.endswith(ext) for ext in AUD_EXTS): return 'audio'
            if any(file_name.endswith(ext) for ext in IMG_EXTS): return 'image'
            if any(file_name.endswith(ext) for ext in ARC_EXTS): return 'archive'
            if any(file_name.endswith(ext) for ext in APP_EXTS): return 'application'
            if any(file_name.endswith(ext) for ext in DOC_EXTS): return 'document'

            if content_type.startswith('video/'): return 'video'
            if content_type.startswith('audio/'): return 'audio'
            if content_type.startswith('image/'): return 'image'
            if any(x in content_type for x in ['zip', 'x-rar', 'x-7z-compressed']): return 'archive'
            if any(x in content_type for x in ['pdf', 'msword', 'powerpoint', 'excel', 'text/plain', 'text/x-python']): return 'document'
            if 'vnd.android.package-archive' in content_type or 'x-msdownload' in content_type: return 'application'
        except Exception as e:
            LOGGER.error(f"Error fetching metadata for link {link}: {e}")
            return None

    # Jika bukan folder dan tidak ada kategori yang cocok, kembalikan None
    return None

@new_task
async def run_mirror_leech_entry(client, message: Message, isQbit=False, isLeech=False):
    """
    Fungsi entri utama yang menentukan kategori sebelum memanggil logika mirror/leech.
    Folder hanya masuk ke 'others', file tanpa kategori ditolak.
    """
    text_args = message.text.split()
    cmd = text_args[0].split("@")[0].lower()
    is_clone = 'clone' in cmd

    # Jika ada argumen manual, gunakan logika lama
    if any(arg in ['-s', '-select', '-up', '-samedir', '-sd', '-m', '-id'] for arg in text_args):
        await _mirror_leech(client, message, isQbit, isLeech)
        return

    # Ekstrak link dan nama file
    link = ""
    reply_to = message.reply_to_message
    file_display_name = ""

    command_parts = message.text.split(' ', 1)
    if len(command_parts) > 1:
        link = command_parts[1].strip()
    elif reply_to and reply_to.text:
        link = reply_to.text.strip().split('\n', 1)[0]

    if reply_to and reply_to.media:
        media = getattr(reply_to, reply_to.media.value)
        if hasattr(media, 'file_name') and media.file_name:
            file_display_name = media.file_name
    elif reply_to and reply_to.text:
        # Coba ekstrak nama file dari pesan balasan jika ada
        text_lines = reply_to.text.strip().split('\n')
        if len(text_lines) > 1 and not is_url(text_lines[-1]):
            file_display_name = text_lines[-1].strip()

    if not file_display_name and link:
        cleaned_link = link.split('?')[0]
        if '/' in cleaned_link:
            file_display_name = unquote(cleaned_link.split('/')[-1])
        # Coba ambil nama file dari metadata jika masih kosong
        if not file_display_name and is_url(link):
            try:
                scraper = create_scraper()
                response = scraper.head(link, allow_redirects=True)
                content_disposition = response.headers.get('Content-Disposition', '')
                if content_disposition and 'filename=' in content_disposition.lower():
                    file_display_name = unquote(content_disposition.split('filename=')[1].strip('"\''))
            except Exception as e:
                LOGGER.error(f"Error fetching file name from link {link}: {e}")

    if not link and not (reply_to and reply_to.media):
        await sendMessage(message, "Tidak ada link atau file yang valid untuk di-mirror.")
        return

    # Dapatkan kategori
    category = get_file_category(link, reply_to)

    # Khusus untuk /clone, hanya izinkan folder (kategori 'others')
    if is_clone and category != 'others':
        await sendMessage(message, "Perintah /clone hanya dapat digunakan untuk folder Google Drive!")
        return

    if not category:
        await sendMessage(message, "File tidak dapat dikategorikan. Silakan gunakan argumen manual (-up, -id) atau pastikan input adalah folder untuk kategori 'Lainnya'.")
        return

    up_path = CUSTOM_DESTINATIONS.get(category)
    if not up_path:
        await sendMessage(message, "Kategori tidak valid!")
        return

    # Buat pesan konfirmasi
    if is_clone:
        confirmation_message = f"✅ Oke! Folder akan di-clone ke folder <b>{CATEGORY_DISPLAY_NAMES[category]}</b>."
    elif file_display_name:
        confirmation_message = f"✅ Oke! File <b>{escape(file_display_name)}</b> akan di-mirror ke folder <b>{CATEGORY_DISPLAY_NAMES[category]}</b>."
    else:
        confirmation_message = f"✅ Oke! File akan di-mirror ke folder <b>{CATEGORY_DISPLAY_NAMES[category]}</b>."

    await sendMessage(message, confirmation_message)
    await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=up_path)

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

    reply_to = message.reply_to_message
    if not link and reply_to:
        if reply_to.text:
            link = reply_to.text.split("\n", 1)[0].strip()

    if link and is_telegram_link(link):
        try:
            reply_to, session = await get_tg_link_content(link, message.from_user.id)
            decrypter = get_decrypt_key() if session else None
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
        try:
            await TelegramDownloadHelper(listener).add_download(reply_to, f"{path}/", name, session, decrypter)
        except Exception as e:
            LOGGER.error(f"Failed to start Telegram download: {e}")
            await sendMessage(message, "Gagal memulai unduhan file Telegram. Silakan periksa log untuk detail.")
            return
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

async def mirror(client, message):
    await run_mirror_leech_entry(client, message)

async def qb_mirror(client, message):
    await run_mirror_leech_entry(client, message, isQbit=True)

async def leech(client, message):
    await run_mirror_leech_entry(client, message, isLeech=True)

async def qb_leech(client, message):
    await run_mirror_leech_entry(client, message, isQbit=True, isLeech=True)

async def clone(client, message):
    await run_mirror_leech_entry(client, message)

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
            LOGGER.error(f"Web Paste Failed : {str(resp)}")
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

# Handler dengan perintah eksplisit untuk menghindari AttributeError
bot.add_handler(
    MessageHandler(
        mirror,
        filters=command(["mirror", "m"])  # Perintah eksplisit
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        qb_mirror,
        filters=command(["qbmirror"])
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        leech,
        filters=command(["leech"])
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        qb_leech,
        filters=command(["qbleech"])
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(
    MessageHandler(
        clone,
        filters=command(["clone"])
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
bot.add_handler(CallbackQueryHandler(wzmlxcb, filters=regex(r"^wzmlx")))
