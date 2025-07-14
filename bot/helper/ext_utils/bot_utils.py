#!/usr/bin/env python3
import platform
from base64 import b64encode
from datetime import datetime
from os import path as ospath
from pkg_resources import get_distribution, DistributionNotFound
from aiofiles import open as aiopen
from aiofiles.os import remove as aioremove, path as aiopath, mkdir
from re import match as re_match
from time import time
from html import escape
from uuid import uuid4
from subprocess import run as srun
from psutil import (
    disk_usage,
    disk_io_counters,
    Process,
    cpu_percent,
    swap_memory,
    cpu_count,
    cpu_freq,
    getloadavg,
    virtual_memory,
    net_io_counters,
    boot_time,
)
from asyncio import (
    create_subprocess_exec,
    create_subprocess_shell,
    run_coroutine_threadsafe,
    sleep,
)
from asyncio.subprocess import PIPE
from functools import partial, wraps
from concurrent.futures import ThreadPoolExecutor

from aiohttp import ClientSession as aioClientSession
from psutil import virtual_memory, cpu_percent, disk_usage
from requests import get as rget
from mega import MegaApi
from pyrogram.enums import ChatType
from pyrogram.types import BotCommand
from pyrogram.errors import PeerIdInvalid

from bot.helper.ext_utils.db_handler import DbManger
from bot.helper.themes import BotTheme
from bot.version import get_version
from bot import (
    OWNER_ID,
    bot_name,
    bot_cache,
    DATABASE_URL,
    LOGGER,
    get_client,
    aria2,
    download_dict,
    download_dict_lock,
    botStartTime,
    user_data,
    config_dict,
    bot_loop,
    extra_buttons,
    user,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.ext_utils.shortners import short_url

THREADPOOL = ThreadPoolExecutor(max_workers=1000)
MAGNET_REGEX = r"magnet:\?xt=urn:(btih|btmh):[a-zA-Z0-9]*\s*"
URL_REGEX = r"^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$"
SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
STATUS_START = 0
PAGES = 1
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "Upload"
    STATUS_DOWNLOADING = "Download"
    STATUS_CLONING = "Clone"
    STATUS_QUEUEDL = "QueueDL"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVING = "Archive"
    STATUS_EXTRACTING = "Extract"
    STATUS_SPLITTING = "Split"
    STATUS_CHECKING = "CheckUp"
    STATUS_SEEDING = "Seed"
    STATUS_METADATA = "Metadata"


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.task = bot_loop.create_task(self.__set_interval())

    async def __set_interval(self):
        while True:
            await sleep(self.interval)
            await self.action()

    def cancel(self):
        self.task.cancel()


def get_readable_file_size(size_in_bytes):
    if size_in_bytes is None:
        return "0B"
    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1
    return (
        f"{size_in_bytes:.2f}{SIZE_UNITS[index]}" if index > 0 else f"{size_in_bytes}B"
    )


async def getDownloadByGid(gid):
    async with download_dict_lock:
        return next((dl for dl in download_dict.values() if dl.gid() == gid), None)


async def getAllDownload(req_status, user_id=None):
    dls = []
    async with download_dict_lock:
        for dl in list(download_dict.values()):
            if user_id and hasattr(dl, 'listener') and user_id != dl.listener.user_id:
                continue
            status = dl.status()
            if req_status in ["all", status]:
                dls.append(dl)
    return dls


def get_readable_message():
    msg = ""
    button = None
    STATUS_LIMIT = config_dict["STATUS_LIMIT"]
    tasks = len(download_dict)
    globals()["PAGES"] = (tasks + STATUS_LIMIT - 1) // STATUS_LIMIT
    if PAGE_NO > PAGES and PAGES != 0:
        globals()["STATUS_START"] = STATUS_LIMIT * (PAGES - 1)
        globals()["PAGE_NO"] = PAGES
    
    # ===========================================================
    # INI ADALAH FUNGSI YANG DIUBAH SECARA TOTAL
    # ===========================================================
    for download in list(download_dict.values())[STATUS_START : STATUS_LIMIT + STATUS_START]:
        if not hasattr(download, 'listener'):
            continue # Lewati jika task tidak memiliki listener (task lama/rusak)
            
        listener = download.listener
        
        # Mulai membangun pesan dengan format baru
        msg += f"<code>{escape(download.name())}</code>\n"
        
        if download.status() not in [MirrorStatus.STATUS_SPLITTING, MirrorStatus.STATUS_SEEDING, MirrorStatus.STATUS_METADATA]:
            # Format baru untuk status normal (downloading, uploading, dll)
            msg += "\n┠\n"
            msg += f"<code>Size      : </code>{download.size()}\n"
            msg += "\n┠\n"

            mode_line = "<code>Mode      : </code>"
            if listener.isLeech: mode_line += "#Leech"
            elif listener.isClone: mode_line += "#Clone"
            elif listener.upPath and listener.upPath not in ['gd', 'ddl']: mode_line += "#Rclone"
            elif listener.upPath == 'ddl': mode_line += "#DDL"
            else: mode_line += "#GDrive"
            
            if listener.isQbit: mode_line += ' | #qBit'
            elif listener.isYtdlp: mode_line += ' | #YTDLP'
            elif listener.isGdrive or listener.isClone: mode_line += ' | #GDrive'
            elif listener.isMega: mode_line += ' | #Mega'
            elif listener.source_url and listener.source_url != listener.message.link: mode_line += ' | #Aria2'
            else: mode_line += ' | #Telegram'
                
            msg += f"{mode_line}\n"
            msg += "\n┠\n"

            if listener.category_name:
                msg += f"<code>Path      : </code>{listener.category_name}\n\n┠\n"
            
            elapsed = time() - download.message.date.timestamp()
            msg += f"<code>Elapsed   : </code>{get_readable_time(elapsed)}\n"
            msg += f"┖<code>By        : </code>{listener.tag}"
            
            msg += f"\n\n{download.progress_bar()}\n"
            msg += f"<code>Progress  : </code>{download.progress()}"
        
        elif download.status() == MirrorStatus.STATUS_SEEDING:
            # Format untuk Seeding (menggunakan BotTheme agar tidak rusak)
            msg += BotTheme("STATUS", Status=download.status(), Url=listener.message.link)
            msg += BotTheme("SEED_SIZE", Size=download.size())
            msg += BotTheme("SEED_SPEED", Speed=download.upload_speed())
            msg += BotTheme("UPLOADED", Upload=download.uploaded_bytes())
            msg += BotTheme("RATIO", Ratio=download.ratio())
            msg += BotTheme("TIME", Time=download.seeding_time())
            msg += BotTheme("SEED_ENGINE", Engine=download.eng())
            msg += BotTheme("USER", User=listener.tag, Id=listener.user_id)
        else:
            # Fallback untuk status lain (split, metadata)
            msg += BotTheme("STATUS", Status=download.status(), Url=listener.message.link)
            msg += BotTheme("STATUS_SIZE", Size=download.size())
            msg += BotTheme("NON_ENGINE", Engine=download.eng())
            msg += BotTheme("USER", User=listener.tag, Id=listener.user_id)
            
        msg += f"\n\n/cancel_{download.gid()}"
        msg += "\n\n"
    # ===========================================================
    # AKHIR DARI BLOK YANG DIUBAH
    # ===========================================================

    if len(msg) == 0:
        return None, None

    dl_speed, up_speed = 0, 0
    for download in download_dict.values():
        tstatus = download.status()
        spd = ""
        try:
            if tstatus == MirrorStatus.STATUS_SEEDING:
                spd = download.upload_speed()
            else:
                spd = download.speed()
        except: pass
        
        speed_in_bytes_per_second = 0
        if "K" in spd:
            speed_in_bytes_per_second = float(spd.split("K")[0]) * 1024
        elif "M" in spd:
            speed_in_bytes_per_second = float(spd.split("M")[0]) * 1048576
        
        if tstatus == MirrorStatus.STATUS_DOWNLOADING:
            dl_speed += speed_in_bytes_per_second
        elif tstatus in [MirrorStatus.STATUS_UPLOADING, MirrorStatus.STATUS_SEEDING]:
            up_speed += speed_in_bytes_per_second

    msg += BotTheme("FOOTER")
    buttons = ButtonMaker()
    buttons.ibutton(BotTheme("REFRESH", Page=f"{PAGE_NO}/{PAGES}"), "status ref")
    if tasks > STATUS_LIMIT:
        if config_dict["BOT_MAX_TASKS"]:
            msg += BotTheme("BOT_TASKS", Tasks=tasks, Ttask=config_dict["BOT_MAX_TASKS"], Free=config_dict["BOT_MAX_TASKS"] - tasks)
        else:
            msg += BotTheme("TASKS", Tasks=tasks)
        buttons = ButtonMaker()
        buttons.ibutton(BotTheme("PREVIOUS"), "status pre")
        buttons.ibutton(BotTheme("REFRESH", Page=f"{PAGE_NO}/{PAGES}"), "status ref")
        buttons.ibutton(BotTheme("NEXT"), "status nex")
    button = buttons.build_menu(3)
    
    msg += BotTheme("Cpu", cpu=cpu_percent())
    msg += BotTheme("FREE", free=get_readable_file_size(disk_usage(config_dict["DOWNLOAD_DIR"]).free), free_p=round(100 - disk_usage(config_dict["DOWNLOAD_DIR"]).percent, 1))
    msg += BotTheme("Ram", ram=virtual_memory().percent)
    msg += BotTheme("uptime", uptime=get_readable_time(time() - botStartTime))
    msg += BotTheme("DL", DL=get_readable_file_size(dl_speed))
    msg += BotTheme("UL", UL=get_readable_file_size(up_speed))
    return msg, button


async def turn_page(data):
    STATUS_LIMIT = config_dict["STATUS_LIMIT"]
    global STATUS_START, PAGE_NO
    async with download_dict_lock:
        if data[1] == "nex":
            if PAGE_NO == PAGES:
                STATUS_START = 0; PAGE_NO = 1
            else:
                STATUS_START += STATUS_LIMIT; PAGE_NO += 1
        elif data[1] == "pre":
            if PAGE_NO == 1:
                STATUS_START = STATUS_LIMIT * (PAGES - 1); PAGE_NO = PAGES
            else:
                STATUS_START -= STATUS_LIMIT; PAGE_NO -= 1


def get_readable_time(seconds):
    seconds = int(seconds)
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result


def is_magnet(url):
    return bool(re_match(MAGNET_REGEX, url))


def is_url(url):
    return bool(re_match(URL_REGEX, url))


def is_gdrive_link(url):
    return "drive.google.com" in url


def is_telegram_link(url):
    return url.startswith(("https://t.me/", "https://telegram.me/", "https://telegram.dog/", "https://telegram.space/", "tg://openmessage?user_id="))


def is_share_link(url):
    return bool(re_match(r"https?:\/\/.+\.gdtot\.\S+|https?:\/\/(.+\.filepress|filebee|appdrive|gdflix|www.jiodrive)\.\S+", url))


def is_index_link(url):
    return bool(re_match(r"https?:\/\/.+\/\d+\:\/", url))


def is_mega_link(url):
    return "mega.nz" in url or "mega.co.nz" in url


def is_rclone_path(path):
    return bool(re_match(r"^(mrcc:)?(?!magnet:)(?![- ])[a-zA-Z0-9_\. -]+(?<! ):(?!.*\/\/).*$|^rcl$", path))


def get_mega_link_type(url):
    return "folder" if "folder" in url or "/#F!" in url else "file"


def arg_parser(items, arg_base):
    if not items:
        return arg_base
    bool_arg_set = {"-b", "-e", "-z", "-s", "-j", "-d"}
    t = len(items)
    i = 0
    arg_start = -1
    while i + 1 <= t:
        part = items[i].strip()
        if part in arg_base:
            if arg_start == -1:
                arg_start = i
            if i + 1 == t and part in bool_arg_set or part in ["-s", "-j"]:
                arg_base[part] = True
            else:
                sub_list = []
                for j in range(i + 1, t):
                    item = items[j].strip()
                    if item in arg_base:
                        if part in bool_arg_set and not sub_list:
                            arg_base[part] = True
                        break
                    sub_list.append(item.strip())
                    i += 1
                if sub_list:
                    arg_base[part] = " ".join(sub_list)
        i += 1
    link = []
    if items[0].strip() not in arg_base:
        if arg_start == -1:
            link.extend(item.strip() for item in items)
        else:
            link.extend(items[r].strip() for r in range(arg_start))
        if link:
            arg_base["link"] = " ".join(link)
    return arg_base


async def get_content_type(url):
    try:
        async with aioClientSession(trust_env=True) as session:
            async with session.get(url, verify_ssl=False) as response:
                return response.headers.get("Content-Type")
    except Exception:
        return None


def update_user_ldata(id_, key=None, value=None):
    exception_keys = ["is_sudo", "is_auth", "dly_tasks", "is_blacklist", "token", "time"]
    if key is None and value is None:
        if id_ in user_data:
            updated_data = {k: v for k, v in user_data[id_].items() if k in exception_keys}
            user_data[id_] = updated_data
        return
    user_data.setdefault(id_, {})
    user_data[id_][key] = value


async def download_image_url(url):
    path = "Images/"
    if not await aiopath.isdir(path):
        await mkdir(path)
    image_name = url.split("/")[-1]
    des_dir = ospath.join(path, image_name)
    async with aioClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiopen(des_dir, "wb") as file:
                    async for chunk in response.content.iter_chunked(1024):
                        await file.write(chunk)
                LOGGER.info(f"Image Downloaded Successfully as {image_name}")
            else:
                LOGGER.error(f"Failed to Download Image from {url}")
    return des_dir


async def cmd_exec(cmd, shell=False):
    if shell:
        proc = await create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)
    else:
        proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await proc.communicate()
    stdout = stdout.decode().strip()
    stderr = stderr.decode().strip()
    return stdout, stderr, proc.returncode


def new_task(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return bot_loop.create_task(func(*args, **kwargs))
    return wrapper


async def sync_to_async(func, *args, wait=True, **kwargs):
    pfunc = partial(func, *args, **kwargs)
    future = bot_loop.run_in_executor(THREADPOOL, pfunc)
    return await future if wait else future


def async_to_sync(func, *args, wait=True, **kwargs):
    future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
    return future.result() if wait else future


def new_thread(func):
    @wraps(func)
    def wrapper(*args, wait=False, **kwargs):
        future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
        return future.result() if wait else future
    return wrapper

# FUNGSI YANG SEBELUMNYA HILANG, DIKEMBALIKAN
async def get_user_tasks(user_id, maxtask):
    if tasks := await getAllDownload("all", user_id):
        return len(tasks) >= maxtask

async def fetch_user_tds(user_id, force=False):
    user_dict = user_data.get(user_id, {})
    if config_dict["USER_TD_MODE"] and user_dict.get("td_mode", False) or force:
        return user_dict.get("user_tds", {})
    return {}

async def fetch_user_dumps(user_id):
    user_dict = user_data.get(user_id, {})
    if dumps := user_dict.get("ldump", False):
        if not isinstance(dumps, dict):
            update_user_ldata(user_id, "ldump", {})
            return {}
        return dumps
    return {}

async def checking_access(user_id, button=None):
    if not config_dict["TOKEN_TIMEOUT"] or bool(
        user_id == OWNER_ID or user_id in user_data and user_data[user_id].get("is_sudo")
    ):
        return None, button
    user_data.setdefault(user_id, {})
    data = user_data[user_id]
    expire = data.get("time")
    if config_dict["LOGIN_PASS"] is not None and data.get("token", "") == config_dict["LOGIN_PASS"]:
        return None, button
    isExpired = (expire is None or expire is not None and (time() - expire) > config_dict["TOKEN_TIMEOUT"])
    if isExpired:
        token = data["token"] if expire is None and "token" in data else str(uuid4())
        if expire is not None:
            del data["time"]
        data["token"] = token
        user_data[user_id].update(data)
        if button is None:
            button = ButtonMaker()
        encrypt_url = b64encode(f"{token}&&{user_id}".encode()).decode()
        button.ubutton("Generate New Token", short_url(f"https://t.me/{bot_name}?start={encrypt_url}"))
        return (
            f'<i>Temporary Token has been expired,</i> Kindly generate a New Temp Token to start using bot Again.\n<b>Validity :</b> <code>{get_readable_time(config_dict["TOKEN_TIMEOUT"])}</code>',
            button,
        )
    return None, button

def extra_btns(buttons, already=False):
    if extra_buttons and not already:
        for btn_name, btn_url in extra_buttons.items():
            buttons.ubutton(btn_name, btn_url, "l_body")
    return buttons, True

async def set_commands(client):
    if not config_dict["SET_COMMANDS"]: return
    # ... (Sisa fungsi tidak perlu diubah) ...
