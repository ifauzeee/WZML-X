# FIXED MIRROR_LEECH.PY (V2)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex, create
from pyrogram.enums import ChatType

from bot import (
    bot,
    DOWNLOAD_DIR,
    config_dict,
    categories_dict,
    user_data,
)
from bot.helper.telegram_helper.message_utils import (
    sendMessage,
    deleteMessage,
    auto_delete_message,
    open_category_btns,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.mirror_utils.download_utils.aria2_download import add_aria2c_download
from bot.helper.mirror_utils.download_utils.qbit_downloader import add_qb_torrent
from bot.helper.mirror_utils.download_utils.telegram_downloader import (
    TelegramDownloadHelper,
)
from bot.helper.ext_utils.bot_utils import (
    get_content_type,
    is_gdrive_link,
    is_magnet,
    is_mega_link,
    is_rclone_path,
    is_telegram_link,
    is_url,
    sync_to_async,
    new_task,
    arg_parser,
    fetch_user_tds,
)
from bot.helper.mirror_utils.rclone_utils.list import RcloneList
from bot.helper.mirror_utils.upload_utils.gdriveTools import GoogleDriveHelper
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.ext_utils.task_manager import task_utils


async def get_category(message, custom_upload_path=""):
    user_tds = await fetch_user_tds(message.from_user.id)
    if not custom_upload_path:
        if len(user_tds) == 1:
            return next(iter(user_tds.values()))
        if len(user_tds) > 1:
            return await open_category_btns(message)
    for drive_name, drive_dict in {**categories_dict, **user_tds}.items():
        if custom_upload_path.casefold() == drive_name.casefold():
            return drive_dict
    return "not_found", "not_found", False


@new_task
async def _mirror_leech(
    client,
    message,
    isQbit=False,
    isLeech=False,
    sameDir=None,
    isZip=False,
    isRclone=False,
    custom_upload_path="",
):
    text = message.text.split("\n")
    input_list = text[0].split(" ")

    args = arg_parser(
        input_list[1:],
        {
            "link": "",
            "-m": "",
            "-sd": "",
            "-samedir": "",
            "-d": False,
            "-dont_auto_extract": False,
            "-n": "",
            "-name": "",
            "-up": "",
            "-upload": "",
            "-id": "",
            "-index": "",
            "-rcf": "",
        },
    )

    link = args["link"]
    folder_name = args["-m"] or args["-sd"] or args["-samedir"]
    name = args["-n"] or args["-name"]
    up = args["-up"] or args["-upload"] or custom_upload_path
    drive_id = args["-id"]
    index_link = args["-index"]
    rcf = args["-rcf"]

    if not isinstance(isZip, bool):
        isZip = isZip or "z" in input_list[0] or "zip" in input_list[0]

    if folder_name:
        isZip = False

    if not link and (reply_to := message.reply_to_message):
        link = reply_to.text.split("\n", 1)[0].strip() if reply_to.text else reply_to.link

    if not is_url(link) and not is_magnet(link) and not await aiopath.exists(link):
        await sendMessage(message, "Provide a valid link/magnet/path.")
        return

    if (sender_chat := message.sender_chat) and sender_chat.type == ChatType.CHANNEL:
        tag = sender_chat.title
    else:
        tag = message.from_user.mention

    listener = MirrorLeechListener(
        message,
        isZip=isZip,
        isLeech=isLeech,
        tag=tag,
        sameDir=sameDir,
        rcFlags=rcf,
        upPath=up,
        drive_id=drive_id,
        index_link=index_link,
    )

    if is_gdrive_link(link):
        if not isZip and not isLeech:
            gdrive = GoogleDriveHelper(listener)
            res, size, name, files = await sync_to_async(gdrive.helper, link)
            if res != "":
                return await sendMessage(message, res)
            if config_dict["STOP_DUPLICATE"]:
                LOGGER.info("Checking File/Folder if already in Drive")
                s_msg = await sendMessage(
                    message, f"Checking File/Folder if already in Drive..."
                )
                if files <= 1:
                    file_name = str(name).rsplit("/", 1)[-1]
                    telegraph_content, contents_no = await gdrive.search(
                        file_name, isRecursive=True
                    )
                else:
                    telegraph_content, contents_no = await gdrive.search(
                        name, isRecursive=True
                    )
                if telegraph_content:
                    await deleteMessage(s_msg)
                    return await sendMessage(
                        message,
                        f"File/Folder is already available in Drive.\nHere are the search results:\n{telegraph_content}",
                    )
                await deleteMessage(s_msg)
        await add_aria2c_download(link, DOWNLOAD_DIR, listener, name)
    elif is_mega_link(link):
        await add_aria2c_download(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener)
    elif isQbit:
        await add_qb_torrent(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener)
    elif is_telegram_link(link):
        await TelegramDownloadHelper(listener).add_download(link, f"{DOWNLOAD_DIR}{listener.uid}/")
    else:
        # This is for replied files and direct links
        if (reply_to := message.reply_to_message) and reply_to.media:
            # FIX: Correctly call the download helper for replied files
            await TelegramDownloadHelper(listener).add_download(reply_to, f"{DOWNLOAD_DIR}{listener.uid}/", name)
        else:
            # For direct links
            await add_aria2c_download(link, f"{DOWNLOAD_DIR}{listener.uid}/", listener, name)

@new_task
async def mirror_leech_callback(client, query):
    message = query.message
    user_id = query.from_user.id
    data = query.data.split()

    if user_id != int(data[1]):
        return await query.answer("This is not for you!", show_alert=True)

    await query.answer()
    up_path = "gd"
    if len(data) > 2:
        if data[2] == "confirm":
            if len(data) > 3:
                up_path = data[3]
            isLeech = query.data.startswith("leech")
            isQbit = query.data.startswith("qbmirror")
            
            # FIX: Use HTML for bolding
            await editMessage(
                message, f"✅ Oke! File akan di-mirror ke folder <b>{up_path.upper()}</b>."
            )
            
            original_message = message.reply_to_message
            await _mirror_leech(client, original_message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=up_path)
        else:
            await deleteMessage(message)
    else:
        await deleteMessage(message)

@new_task
async def mirror_leech_handler(client, message):
    if (
        message.text.startswith(f"/{BotCommands.MirrorCommand}")
        or message.text.startswith(f"/{BotCommands.LeechCommand}")
        or message.text.startswith(f"/{BotCommands.QbMirrorCommand}")
        or message.text.startswith(f"/{BotCommands.QbLeechCommand}")
    ):
        isLeech = (
            message.text.startswith(f"/{BotCommands.LeechCommand}")
            or message.text.startswith(f"/{BotCommands.QbLeechCommand}")
        )
        isQbit = (
            message.text.startswith(f"/{BotCommands.QbMirrorCommand}")
            or message.text.startswith(f"/{BotCommands.QbLeechCommand}")
        )
        
        # Check if the user is replying to a message with a file/link
        reply_to = message.reply_to_message
        if reply_to is not None:
            # If replying, we can start the process directly
            drive_dict = await get_category(message)
            if isinstance(drive_dict, tuple):
                drive_id, index_link, is_cancelled = drive_dict
                if is_cancelled:
                    return
            else:
                drive_id = drive_dict["drive_id"]
                index_link = drive_dict["index_link"]

            await _mirror_leech(client, message, isQbit=isQbit, isLeech=isLeech, custom_upload_path=drive_id)
        else:
            # If not replying, show category buttons
            drive_dict = await get_category(message)
            if isinstance(drive_dict, tuple):
                drive_id, index_link, is_cancelled = drive_dict
                if is_cancelled:
                    return
            else:
                drive_id = drive_dict["drive_id"]
                index_link = drive_dict["index_link"]
            
            cmd = message.text.split()[0].replace("/", "")
            buttons = ButtonMaker()
            buttons.ibutton("Confirm", f"{cmd} {message.from_user.id} confirm {drive_id}")
            buttons.ibutton("Cancel", f"{cmd} {message.from_user.id} cancel")
            await sendMessage(
                message,
                "Pilih kategori untuk melanjutkan:",
                buttons.build_menu(2),
                reply_to_message_id=message.id,
            )

# Register Handlers
bot.add_handler(
    MessageHandler(
        mirror_leech_handler,
        filters=command(
            [
                BotCommands.MirrorCommand,
                BotCommands.LeechCommand,
                BotCommands.QbMirrorCommand,
                BotCommands.QbLeechCommand,
            ]
        )
        & CustomFilters.authorized,
    )
)
bot.add_handler(
    CallbackQueryHandler(
        mirror_leech_callback,
        filters=regex(r"^(mirror|leech|qbmirror|qbleech)") & CustomFilters.authorized,
    )
)
