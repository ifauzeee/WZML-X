#!/usr/bin/env python3
from random import choice
from time import time
from copy import deepcopy
from pytz import timezone
from datetime import datetime
from urllib.parse import unquote, quote
from requests import utils as rutils
from aiofiles.os import path as aiopath, remove as aioremove, listdir, makedirs
from os import walk, path as ospath
from html import escape
from aioshutil import move
from asyncio import create_subprocess_exec, sleep, Event
from pyrogram.enums import ChatType

from bot import (
    OWNER_ID,
    Interval,
    aria2,
    DOWNLOAD_DIR,
    download_dict,
    download_dict_lock,
    LOGGER,
    bot_name,
    DATABASE_URL,
    MAX_SPLIT_SIZE,
    config_dict,
    status_reply_dict_lock,
    user_data,
    non_queued_up,
    non_queued_dl,
    queued_up,
    queued_dl,
    queue_dict_lock,
    bot,
    GLOBAL_EXTENSION_FILTER,
)
from bot.helper.ext_utils.bot_utils import (
    extra_btns,
    sync_to_async,
    get_readable_file_size,
    get_readable_time,
    is_mega_link,
    is_gdrive_link,
)
from bot.helper.ext_utils.fs_utils import (
    get_base_name,
    get_path_size,
    clean_download,
    clean_target,
    is_first_archive_split,
    is_archive,
    is_archive_split,
    join_files,
    edit_metadata,
)
from bot.helper.ext_utils.leech_utils import (
    split_file,
    format_filename,
    get_document_type,
)
from bot.helper.ext_utils.exceptions import NotSupportedExtractionArchive
from bot.helper.ext_utils.task_manager import start_from_queued
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.zip_status import ZipStatus
from bot.helper.mirror_utils.status_utils.split_status import SplitStatus
from bot.helper.mirror_utils.status_utils.gdrive_status import GdriveStatus
from bot.helper.mirror_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.mirror_utils.status_utils.ddl_status import DDLStatus
from bot.helper.mirror_utils.status_utils.rclone_status import RcloneStatus
from bot.helper.mirror_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.mirror_utils.upload_utils.pyrogramEngine import TgUploader
from bot.helper.mirror_utils.upload_utils.ddlEngine import DDLUploader
from bot.helper.mirror_utils.rclone_utils.transfer import RcloneTransferHelper
from bot.helper.mirror_utils.status_utils.metadata_status import MetadataStatus
from bot.helper.telegram_helper.message_utils import (
    sendCustomMsg,
    sendMessage,
    editMessage,
    deleteMessage,
    delete_all_messages,
    delete_links,
    sendMultiMessage,
    update_all_messages,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.themes import BotTheme


class MirrorLeechListener:
    def __init__(
        self,
        message,
        compress=False,
        extract=False,
        isQbit=False,
        isLeech=False,
        tag=None,
        select=False,
        seed=False,
        sameDir=None,
        rcFlags=None,
        upPath=None,
        isClone=False,
        join=False,
        drive_id=None,
        index_link=None,
        isYtdlp=False,
        source_url=None,
        logMessage=None,
        leech_utils={},
        category_name=None,
    ):
        if sameDir is None:
            sameDir = {}
        self.message = message
        self.uid = message.id
        self.excep_chat = bool(
            str(message.chat.id) in config_dict["EXCEP_CHATS"].split()
        )
        self.extract = extract
        self.compress = compress
        self.isQbit = isQbit
        self.isLeech = isLeech
        self.isClone = isClone
        self.isMega = is_mega_link(source_url) if source_url else False
        self.isGdrive = is_gdrive_link(source_url) if source_url else False
        self.isYtdlp = isYtdlp
        self.tag = tag
        self.seed = seed
        self.newDir = ""
        self.dir = f"{DOWNLOAD_DIR}{self.uid}"
        self.select = select
        self.isSuperGroup = message.chat.type in [ChatType.SUPERGROUP, ChatType.CHANNEL]
        self.isPrivate = message.chat.type == ChatType.BOT
        self.user_id = self.message.from_user.id
        self.user_dict = user_data.get(self.user_id, {})
        self.isPM = config_dict["BOT_PM"] or self.user_dict.get("bot_pm")
        self.suproc = None
        self.sameDir = sameDir
        self.rcFlags = rcFlags
        self.upPath = upPath
        self.random_pic = "IMAGES" if config_dict["IMAGES"] else None
        self.join = join
        self.drive_id = drive_id
        self.index_link = index_link
        self.logMessage = logMessage
        self.linkslogmsg = None
        self.botpmmsg = None
        self.upload_details = {}
        self.leech_utils = leech_utils
        self.category_name = category_name
        self.source_url = (
            source_url
            if source_url and source_url.startswith("http")
            else (
                f"https://t.me/share/url?url={source_url}"
                if source_url
                else message.link
            )
        )
        self.source_msg = ""
        self.__setModeEng()
        self.__parseSource()

    def _getStatusMessage(self, name, size, gid):
        status = download_dict[self.uid]
        
        msg = f"<code>{escape(name)}</code>\n"
        msg += "\n┠\n"
        msg += f"<code>Size      : </code>{size}\n"
        msg += "\n┠\n"

        mode_line = "<code>Mode      : </code>"
        if self.isLeech:
            mode_line += "#Leech"
        elif self.isClone:
            mode_line += "#Clone"
        elif self.upPath not in ['gd', 'ddl']:
            mode_line += "#Rclone"
        elif self.upPath == 'ddl':
            mode_line += "#DDL"
        else:
            mode_line += "#GDrive"

        if self.isQbit:
            mode_line += ' | #qBit'
        elif self.isYtdlp:
            mode_line += ' | #YTDLP'
        elif self.isGdrive or self.isClone:
            mode_line += ' | #GDrive'
        elif self.isMega:
            mode_line += ' | #Mega'
        elif self.source_url and self.source_url != self.message.link:
             mode_line += ' | #Aria2'
        else:
            mode_line += ' | #Telegram'

        msg += f"{mode_line}\n"
        msg += "\n┠\n"

        if self.category_name:
            msg += f"<code>Path      : </code>{self.category_name}\n\n┠\n"
        
        msg += f"<code>Elapsed   : </code>{get_readable_time(time() - self.message.date.timestamp())}\n"
        
        # Tambahkan baris By di akhir dengan karakter yang sesuai
        last_line_char = "┖"
        msg += f"{last_line_char}<code>By        : </code>{self.tag}"
        
        # Tambah progress bar setelah semua detail
        progress = status.progress() if hasattr(status, 'progress') else '0%'
        progress_bar = status.progress_bar() if hasattr(status, 'progress_bar') else '[--------------------]'
        
        msg += f"\n\n{progress_bar}\n"
        msg += f"<code>Progress  : </code>{progress}"
        
        return msg


    async def onDownloadComplete(self):
        # ... (sisa file ini sama persis dengan yang Anda berikan sebelumnya, 
        # namun dengan perubahan penting di bawah ini saat membuat status object) ...
        
        # Contoh perubahan (lakukan ini untuk semua status object):

        # ... Di dalam onDownloadComplete ...
        if self.isLeech:
            # ...
            tg = TgUploader(up_name, up_dir, self)
            # PERHATIKAN: 'self' dikirimkan sebagai listener
            tg_upload_status = TelegramStatus(tg, size, self, gid, "up")
            async with download_dict_lock:
                download_dict[self.uid] = tg_upload_status
            # ...
        elif self.upPath == "gd":
            # ...
            drive = GoogleDriveHelper(up_name, up_dir, self)
            # PERHATIKAN: 'self' dikirimkan sebagai listener
            upload_status = GdriveStatus(drive, size, self, gid, "up")
            async with download_dict_lock:
                download_dict[self.uid] = upload_status
            # ...
        elif self.upPath == "ddl":
            # ...
            ddl = DDLUploader(self, up_name, up_dir)
            # PERHATIKAN: 'self' dikirimkan sebagai listener
            ddl_upload_status = DDLStatus(ddl, size, self, gid)
            async with download_dict_lock:
                download_dict[self.uid] = ddl_upload_status
            # ...
        else: # Rclone
            # ...
            RCTransfer = RcloneTransferHelper(self, up_name)
            async with download_dict_lock:
                # PERHATIKAN: 'self' dikirimkan sebagai listener
                download_dict[self.uid] = RcloneStatus(RCTransfer, self, gid, "up")
            # ...

        # KODE LENGKAP onDownloadComplete dan sisa file:
        # (Untuk menghindari membuat file ini terlalu panjang, saya akan menyalin fungsi onDownloadComplete
        # secara utuh dengan perubahan yang sudah diterapkan. Salin dari sini sampai akhir file.)
    
    # ... PASTE SELURUH SISA KODE DARI FILE tasks_listener.py ANDA DI SINI ...
    # (Saya akan menulis ulang onDownloadComplete dan sisanya agar Anda bisa langsung copy-paste)
    async def onDownloadComplete(self):
        multi_links = False
        while True:
            if self.sameDir:
                if (
                    self.sameDir["total"] in [1, 0]
                    or self.sameDir["total"] > 1
                    and len(self.sameDir["tasks"]) > 1
                ):
                    break
            else:
                break
            await sleep(0.2)
        async with download_dict_lock:
            if self.sameDir and self.sameDir["total"] > 1:
                self.sameDir["tasks"].remove(self.uid)
                self.sameDir["total"] -= 1
                folder_name = self.sameDir["name"]
                spath = f"{self.dir}/{folder_name}"
                des_path = (
                    f"{DOWNLOAD_DIR}{list(self.sameDir['tasks'])[0]}/{folder_name}"
                )
                await makedirs(des_path, exist_ok=True)
                for item in await listdir(spath):
                    if item.endswith((".aria2", ".!qB")):
                        continue
                    item_path = f"{self.dir}/{folder_name}/{item}"
                    if item in await listdir(des_path):
                        await move(item_path, f"{des_path}/{self.uid}-{item}")
                    else:
                        await move(item_path, f"{des_path}/{item}")
                multi_links = True
            download = download_dict[self.uid]
            name = str(download.name()).replace("/", "")
            gid = download.gid()
        LOGGER.info(f"Download Completed: {name}")
        if multi_links:
            await self.onUploadError("Downloaded! Starting other part of the Task...")
            return
        if (
            name == "None"
            or self.isQbit
            or not await aiopath.exists(f"{self.dir}/{name}")
        ):
            try:
                files = await listdir(self.dir)
            except Exception as e:
                await self.onUploadError(str(e))
                return
            name = files[-1]
            if name == "yt-dlp-thumb":
                name = files[0]

        dl_path = f"{self.dir}/{name}"
        up_path = ""
        size = await get_path_size(dl_path)
        async with queue_dict_lock:
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
        await start_from_queued()
        user_dict = user_data.get(self.message.from_user.id, {})

        if self.join and await aiopath.isdir(dl_path):
            await join_files(dl_path)

        if self.extract:
            pswd = self.extract if isinstance(self.extract, str) else ""
            try:
                if await aiopath.isfile(dl_path):
                    up_path = get_base_name(dl_path)
                LOGGER.info(f"Extracting: {name}")
                async with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, size, gid, self)
                if await aiopath.isdir(dl_path):
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        up_path = f"{self.newDir}/{name}"
                    else:
                        up_path = dl_path
                    for dirpath, _, files in await sync_to_async(
                        walk, dl_path, topdown=False
                    ):
                        for file_ in files:
                            if (
                                is_first_archive_split(file_)
                                or is_archive(file_)
                                and not file_.endswith(".rar")
                            ):
                                f_path = ospath.join(dirpath, file_)
                                t_path = (
                                    dirpath.replace(self.dir, self.newDir)
                                    if self.seed
                                    else dirpath
                                )
                                cmd = [
                                    "7z", "x", f"-p{pswd}", f_path, f"-o{t_path}",
                                    "-aot", "-xr!@PaxHeader",
                                ]
                                if not pswd:
                                    del cmd[2]
                                if (self.suproc == "cancelled" or self.suproc is not None and self.suproc.returncode == -9):
                                    return
                                self.suproc = await create_subprocess_exec(*cmd)
                                code = await self.suproc.wait()
                                if code == -9:
                                    return
                                elif code != 0:
                                    LOGGER.error("Unable to extract archive splits!")
                    if (not self.seed and self.suproc is not None and self.suproc.returncode == 0):
                        for file_ in files:
                            if is_archive_split(file_) or is_archive(file_):
                                del_path = ospath.join(dirpath, file_)
                                try:
                                    await aioremove(del_path)
                                except:
                                    return
                else:
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        up_path = up_path.replace(self.dir, self.newDir)
                    cmd = [
                        "7z", "x", f"-p{pswd}", dl_path, f"-o{up_path}",
                        "-aot", "-xr!@PaxHeader",
                    ]
                    if not pswd:
                        del cmd[2]
                    if self.suproc == "cancelled":
                        return
                    self.suproc = await create_subprocess_exec(*cmd)
                    code = await self.suproc.wait()
                    if code == -9:
                        return
                    elif code == 0:
                        LOGGER.info(f"Extracted Path: {up_path}")
                        if not self.seed:
                            try:
                                await aioremove(dl_path)
                            except:
                                return
                    else:
                        LOGGER.error("Unable to extract archive! Uploading anyway")
                        self.newDir = ""
                        up_path = dl_path
            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                self.newDir = ""
                up_path = dl_path

        if self.compress:
            pswd = self.compress if isinstance(self.compress, str) else ""
            if up_path:
                dl_path = up_path
                up_path = f"{up_path}.zip"
            elif self.seed and self.isLeech:
                self.newDir = f"{self.dir}10000"
                up_path = f"{self.newDir}/{name}.zip"
            else:
                up_path = f"{dl_path}.zip"
            async with download_dict_lock:
                download_dict[self.uid] = ZipStatus(name, size, gid, self)
            LEECH_SPLIT_SIZE = (user_dict.get("split_size", False) or config_dict["LEECH_SPLIT_SIZE"])
            cmd = ["7z", f"-v{LEECH_SPLIT_SIZE}b", "a", "-mx=0", f"-p{pswd}", up_path, dl_path]
            for ext in GLOBAL_EXTENSION_FILTER:
                cmd.append(f"-xr!*.{ext}")
            if self.isLeech and int(size) > LEECH_SPLIT_SIZE:
                if not pswd:
                    del cmd[4]
                LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}.0*")
            else:
                del cmd[1]
                if not pswd:
                    del cmd[3]
                LOGGER.info(f"Zip: orig_path: {dl_path}, zip_path: {up_path}")
            if self.suproc == "cancelled":
                return
            self.suproc = await create_subprocess_exec(*cmd)
            code = await self.suproc.wait()
            if code == -9:
                return
            elif not self.seed:
                await clean_target(dl_path)

        if not self.compress and not self.extract:
            up_path = dl_path

        up_dir, up_name = up_path.rsplit("/", 1)
        size = await get_path_size(up_dir)
        if self.isLeech:
            m_size = []
            o_files = []
            if not self.compress:
                checked = False
                LEECH_SPLIT_SIZE = (user_dict.get("split_size", False) or config_dict["LEECH_SPLIT_SIZE"])
                for dirpath, _, files in await sync_to_async(walk, up_dir, topdown=False):
                    for file_ in files:
                        f_path = ospath.join(dirpath, file_)
                        f_size = await aiopath.getsize(f_path)
                        if f_size > LEECH_SPLIT_SIZE:
                            if not checked:
                                checked = True
                                async with download_dict_lock:
                                    download_dict[self.uid] = SplitStatus(
                                        up_name, size, gid, self
                                    )
                                LOGGER.info(f"Splitting: {up_name}")
                            res = await split_file(f_path, f_size, file_, dirpath, LEECH_SPLIT_SIZE, self)
                            if not res: return
                            if res == "errored":
                                if f_size <= MAX_SPLIT_SIZE:
                                    continue
                                try:
                                    await aioremove(f_path)
                                except:
                                    return
                            elif not self.seed or self.newDir:
                                try:
                                    await aioremove(f_path)
                                except:
                                    return
                            else:
                                m_size.append(f_size)
                                o_files.append(file_)

        added_to_queue = False
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            up = len(non_queued_up)
            if (config_dict["QUEUE_ALL"] and dl + up >= config_dict["QUEUE_ALL"] and (not config_dict["QUEUE_UPLOAD"] or up >= config_dict["QUEUE_UPLOAD"])) or (config_dict["QUEUE_UPLOAD"] and up >= config_dict["QUEUE_UPLOAD"]):
                added_to_queue = True
                LOGGER.info(f"Added to Queue/Upload: {name}")
                event = Event()
                queued_up[self.uid] = event
        if added_to_queue:
            async with download_dict_lock:
                download_dict[self.uid] = QueueStatus(name, size, gid, self, "Up")
            await event.wait()
            async with download_dict_lock:
                if self.uid not in download_dict:
                    return
            LOGGER.info(f"Start from Queued/Upload: {name}")
        async with queue_dict_lock:
            non_queued_up.add(self.uid)
        if self.isLeech:
            size = await get_path_size(up_dir)
            for s in m_size:
                size = size - s
            LOGGER.info(f"Leech Name: {up_name}")
            tg = TgUploader(up_name, up_dir, self)
            tg_upload_status = TelegramStatus(tg, size, self, gid, "up")
            async with download_dict_lock:
                download_dict[self.uid] = tg_upload_status
            await update_all_messages()
            await tg.upload(o_files, m_size, size)
        elif self.upPath == "gd":
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name}")
            drive = GoogleDriveHelper(up_name, up_dir, self)
            upload_status = GdriveStatus(drive, size, self, gid, "up")
            async with download_dict_lock:
                download_dict[self.uid] = upload_status
            await update_all_messages()
            await sync_to_async(drive.upload, up_name, size, self.drive_id)
        elif self.upPath == "ddl":
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name} via DDL")
            ddl = DDLUploader(self, up_name, up_dir)
            ddl_upload_status = DDLStatus(ddl, size, self, gid)
            async with download_dict_lock:
                download_dict[self.uid] = ddl_upload_status
            await update_all_messages()
            await ddl.upload(up_name, size)
        else:
            size = await get_path_size(up_path)
            LOGGER.info(f"Upload Name: {up_name} via RClone")
            RCTransfer = RcloneTransferHelper(self, up_name)
            async with download_dict_lock:
                download_dict[self.uid] = RcloneStatus(RCTransfer, self, gid, "up")
            await update_all_messages()
            await RCTransfer.upload(up_path, size)

    async def onUploadComplete(self, link, size, files, folders, mime_type, name, rclonePath=""):
        if (self.isSuperGroup and config_dict["INCOMPLETE_TASK_NOTIFIER"] and DATABASE_URL):
            await DbManger().rm_complete_task(self.message.link)
        user_id = self.message.from_user.id
        name, _ = await format_filename(name, user_id, isMirror=not self.isLeech)
        user_dict = user_data.get(user_id, {})
        msg = BotTheme("NAME", Name=("Task has been Completed!" if config_dict["SAFE_MODE"] and self.isSuperGroup else escape(name)))
        msg += BotTheme("SIZE", Size=get_readable_file_size(size))
        msg += BotTheme("ELAPSE", Time=get_readable_time(time() - self.message.date.timestamp()))
        msg += BotTheme("MODE", Mode=self.upload_details["mode"])
        LOGGER.info(f"Task Done: {name}")
        buttons = ButtonMaker()
        if self.isLeech:
            msg += BotTheme("L_TOTAL_FILES", Files=folders)
            if mime_type != 0:
                msg += BotTheme("L_CORRUPTED_FILES", Corrupt=mime_type)
            msg += BotTheme("L_CC", Tag=self.tag)
            if not files:
                await sendMessage(self.message, msg, photo=self.random_pic)
            else:
                fmsg, total_files = "\n", 0
                for index, (link, name) in enumerate(files.items(), start=1):
                    fmsg += f"{index}. <a href='{link}'>{name}</a>\n"
                    total_files += 1
                    if len(fmsg.encode()) > 3900:
                        if self.isPM:
                            await sendMultiMessage(user_id, msg + fmsg)
                        elif self.isSuperGroup:
                            if config_dict["SAVE_MSG"]:
                                buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                            await sendMessage(self.message, msg + fmsg, buttons.build_menu(2))
                        fmsg = ""
                if fmsg != "":
                    if self.isPM:
                        await sendMultiMessage(user_id, msg + fmsg)
                    elif self.isSuperGroup:
                        if config_dict["SAVE_MSG"]:
                            buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
                        await sendMessage(self.message, msg + fmsg, buttons.build_menu(2))
            if self.seed:
                if self.newDir:
                    await clean_target(self.newDir)
                async with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                await start_from_queued()
                return
        else:
            msg += BotTheme("M_TYPE", Mimetype=mime_type)
            if mime_type == "Folder":
                msg += BotTheme("M_SUBFOLD", Folder=folders)
                msg += BotTheme("TOTAL_FILES", Files=files)
            if link and (user_id == OWNER_ID or not config_dict["DISABLE_DRIVE_LINK"]):
                buttons.ubutton(BotTheme("CLOUD_LINK"), link)
            INDEX_URL = self.index_link or config_dict["INDEX_URL"]
            if INDEX_URL:
                url_path = rutils.quote(f"{name}")
                share_url = f"{INDEX_URL}/{url_path}"
                if mime_type == "Folder":
                    share_url += "/"
                    buttons.ubutton(BotTheme("INDEX_LINK_F"), share_url)
                else:
                    buttons.ubutton(BotTheme("INDEX_LINK_D"), share_url)
                    if mime_type.startswith(("image", "video", "audio")):
                        share_urls = f"{INDEX_URL}/{url_path}?a=view"
                        buttons.ubutton(BotTheme("VIEW_LINK"), share_urls)
            if rclonePath:
                msg += BotTheme("RCPATH", RCpath=rclonePath)
            msg += BotTheme("M_CC", Tag=self.tag)
            if config_dict["MIRROR_LOG_ID"] and not self.excep_chat:
                await sendCustomMsg(config_dict["MIRROR_LOG_ID"], msg, buttons.build_menu(2), self.random_pic)
            if config_dict["SAVE_MSG"] and self.isSuperGroup:
                buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
            await sendMessage(self.message, msg, buttons.build_menu(2), photo=self.random_pic)
            if self.seed:
                if self.newDir:
                    await clean_target(self.newDir)
                elif self.compress:
                    await clean_target(f"{self.dir}/{name}")
                async with queue_dict_lock:
                    if self.uid in non_queued_up:
                        non_queued_up.remove(self.uid)
                await start_from_queued()
                return
        await clean_download(self.dir)
        async with download_dict_lock:
            if self.uid in download_dict:
                del download_dict[self.uid]
            count = len(download_dict)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()
        async with queue_dict_lock:
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)
        await start_from_queued()
        await delete_links(self.message)

    async def onDownloadError(self, error, button=None):
        async with download_dict_lock:
            if self.uid in download_dict:
                del download_dict[self.uid]
            count = len(download_dict)
            if self.sameDir and self.uid in self.sameDir["tasks"]:
                self.sameDir["tasks"].remove(self.uid)
                self.sameDir["total"] -= 1
        msg = f"Hey, {self.tag}!\n\nYour download has been stopped!\n\n<b>Reason:</b> {escape(error)}\n\nThank you for using me."
        await sendMessage(self.message, msg, button)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()
        if self.isSuperGroup and config_dict["INCOMPLETE_TASK_NOTIFIER"] and DATABASE_URL:
            await DbManger().rm_complete_task(self.message.link)
        async with queue_dict_lock:
            if self.uid in queued_dl:
                queued_dl[self.uid].set()
                del queued_dl[self.uid]
            if self.uid in queued_up:
                queued_up[self.uid].set()
                del queued_up[self.uid]
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)
        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.newDir:
            await clean_download(self.newDir)

    async def onUploadError(self, error):
        async with download_dict_lock:
            if self.uid in download_dict:
                del download_dict[self.uid]
            count = len(download_dict)
        await sendMessage(self.message, f"Hey, {self.tag}!\n\n{escape(error)}")
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()
        if self.isSuperGroup and config_dict["INCOMPLETE_TASK_NOTIFIER"] and DATABASE_URL:
            await DbManger().rm_complete_task(self.message.link)
        async with queue_dict_lock:
            if self.uid in queued_dl:
                queued_dl[self.uid].set()
                del queued_dl[self.uid]
            if self.uid in queued_up:
                queued_up[self.uid].set()
                del queued_up[self.uid]
            if self.uid in non_queued_dl:
                non_queued_dl.remove(self.uid)
            if self.uid in non_queued_up:
                non_queued_up.remove(self.uid)
        await start_from_queued()
        await sleep(3)
        await clean_download(self.dir)
        if self.newDir:
            await clean_download(self.newDir)
