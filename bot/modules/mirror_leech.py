from bot import LOGGER, config_dict
from bot.helper.ext_utils.bot_utils import (
    sync_to_async,
    get_readable_file_size,
    is_gdrive_link,
    is_mega_link,
    is_url,
)
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.telegram_helper.message_utils import sendMessage
from bot.helper.ext_utils.fs_utils import get_mime_type
from bot.helper.mirror_utils.status_utils.gdrive_status import GdriveStatus
from bot.helper.mirror_utils.status_utils.telegram_status import TelegramStatus
from bot.helper.mirror_utils.status_utils.aria2_status import Aria2Status
from bot.helper.mirror_utils.download_utils.aria2_download import Aria2DownloadHelper
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloader
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.mega_download import MegaDownloader
from bot.helper.mirror_utils.download_utils.direct_downloader import DirectDownloader
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException
from bot.helper.telegram_helper.button_build import ButtonMaker
import aiohttp
import re
import os
from urllib.parse import urlparse

CUSTOM_DESTINATIONS = {
    'video': ('1oGKB2mZ3lFt4sR0eG0iN0vM2gY3kW9xP', '🎬 Video'),
    'audio': ('1t5Y8nZ2mX3kW9xP0eG0iN0vM2gY3kW9xP', '🎵 Audio'),
    'image': ('1iM2gY3kW9xP0eG0iN0vM2gY3kW9xP0eG', '🖼️ Gambar'),
    'app': ('1aP0eG0iN0vM2gY3kW9xP0eG0iN0vM2gY', '📱 Aplikasi'),
    'folder': ('1fJ2gY3kW9xP0eG0iN0vM2gY3kW9xP0eG', '🗂️ Arsip (ZIP/RAR)'),
    'document': ('1dM2gY3kW9xP0eG0iN0vM2gY3kW9xP0eG', '📄 Dokumen'),
}

async def wzmlxcb(message, client):
    user_id = message.from_user.id
    msg = message.text.split(maxsplit=1)
    reply_to = message.reply_to_message
    url = msg[1] if len(msg) > 1 else None
    file_name = None
    tag = f"@{message.from_user.username}" if message.from_user.username else str(user_id)

    if reply_to and reply_to.media:
        file_name = getattr(reply_to, reply_to.media.value).file_name
        mime_type = getattr(reply_to, reply_to.media.value).mime_type or get_mime_type(file_name)
    elif url and is_url(url):
        parsed_url = urlparse(url)
        file_name = os.path.basename(parsed_url.path)
        mime_type = get_mime_type(file_name)
    else:
        await sendMessage(message, "Silakan reply ke file atau berikan URL yang valid.")
        return

    for key, (drive_id, category_name) in CUSTOM_DESTINATIONS.items():
        if mime_type and mime_type.startswith(key) or (file_name and any(file_name.lower().endswith(ext) for ext in ['.zip', '.rar'] if key == 'folder')):
            destination = drive_id
            await sendMessage(message, f"✅ Oke! File akan di-mirror ke folder {category_name}.")
            break
    else:
        destination = config_dict['GDRIVE_ID']
        await sendMessage(message, f"✅ Oke! File akan di-mirror ke folder default.")

    if reply_to and reply_to.media:
        downloader = TelegramDownloader(reply_to, user_id, message, destination)
        tg_status = TelegramStatus(downloader, None, message, None, "dl", {})
        await downloader.download()
    elif url:
        if is_gdrive_link(url):
            drive = GoogleDriveHelper(None, None, message)
            await sync_to_async(drive.upload, url, destination)
        elif is_mega_link(url):
            mega_dl = MegaDownloader(url, message)
            await mega_dl.add_download(destination, None)
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, allow_redirects=True) as resp:
                        content_type = resp.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            async with session.get(url) as resp:
                                data = await resp.json()
                                file_name = data.get('name', file_name)
                        else:
                            file_name = file_name or 'downloaded_file'
                            mime_type = content_type or mime_type
            except Exception as e:
                LOGGER.error(f"Failed to fetch URL metadata: {e}")
                file_name = file_name or 'downloaded_file'
                mime_type = mime_type or 'application/octet-stream'

            try:
                link = await direct_link_generator(url)
                downloader = DirectDownloader(link, file_name, message, destination)
                aria2_status = Aria2Status(downloader, None, message, None, {})
                await downloader.start_download()
            except DirectDownloadLinkException as e:
                await sendMessage(message, str(e))
                return

    LOGGER.info(f"Task started for {file_name} by {tag}")
