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
        self.user_id = self.message.from_user.id
        self.name = ""
        self.suproc = None
        self.sameDir = sameDir
        self.rcFlags = rcFlags
        self.upPath = upPath
        self.join = join
        self.drive_id = drive_id
        self.index_link = index_link
        self.leech_utils = leech_utils
        self.category_name = category_name
        self.source_url = source_url

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
        
        self.name = name
        LOGGER.info(f"Download Completed: {name}")

        if multi_links:
            await self.onUploadError("Downloaded! Starting other part of the Task...")
            return
        
        dl_path = f"{self.dir}/{name}"
        up_path = ""
        size = await get_path_size(dl_path)
        
        # ... (kode lain di onDownloadComplete tetap sama)

        # Perubahan utama ada di sini
        if self.isLeech:
            tg = TgUploader(up_name, up_dir, self)
            async with download_dict_lock:
                download_dict[self.uid] = TelegramStatus(tg, size, self, gid, "up")
            await update_all_messages()
            await tg.upload(o_files, m_size, size)
        elif self.upPath == "gd":
            drive = GoogleDriveHelper(up_name, up_dir, self)
            async with download_dict_lock:
                download_dict[self.uid] = GdriveStatus(drive, size, self, gid, "up")
            await update_all_messages()
            await sync_to_async(drive.upload, up_name, size, self.drive_id)
        # ... dan seterusnya untuk DDL, Rclone, dll.
        # Pastikan semua pembuatan status object menggunakan 'self' sebagai listener

    # ... (Sisa file listener Anda, seperti onUploadComplete, onError, dll., tetap sama)
