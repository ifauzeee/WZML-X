#!/usr/bin/env python3
from time import time
from bot.helper.ext_utils.bot_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
    get_progress_bar_string,
    EngineStatus,
)

class TelegramStatus:
    def __init__(self, obj, size, listener, gid, status="up"):
        self.__obj = obj
        self.__size = size
        self.__gid = gid
        self.__status = status
        self.listener = listener
        self.message = listener.message

    def progress_bar(self):
        return get_progress_bar_string(self)

    def processed_bytes(self):
        return self.__obj.processed_bytes if hasattr(self.__obj, 'processed_bytes') else 0

    def size(self):
        return get_readable_file_size(self.__size)

    def status(self):
        if self.__status == "up":
            return MirrorStatus.STATUS_UPLOADING
        return MirrorStatus.STATUS_DOWNLOADING

    def name(self):
        return self.listener.name

    def gid(self) -> str:
        return self.__gid

    def progress(self):
        try:
            return f"{round(self.processed_bytes() / self.__size * 100, 2)}%"
        except:
            return "0.0%"

    def speed(self):
        return f"{get_readable_file_size(self.__obj.speed)}/s" if hasattr(self.__obj, 'speed') else '0 B/s'

    def eta(self):
        try:
            return get_readable_time((self.__size - self.processed_bytes()) / self.__obj.speed)
        except:
            return "-"

    def download(self):
        return self.__obj

    def eng(self):
        return EngineStatus().STATUS_TG
