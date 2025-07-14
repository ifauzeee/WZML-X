#!/usr/bin/env python3
from time import time
from bot.helper.ext_utils.bot_utils import (
    MirrorStatus,
    EngineStatus,
    get_readable_file_size,
    get_readable_time,
    get_progress_bar_string,
)

class DDLStatus:
    def __init__(self, obj, size, listener, gid):
        self.__obj = obj
        self.__size = size
        self.__gid = gid
        self.listener = listener
        self.message = listener.message

    def progress_bar(self):
        return get_progress_bar_string(self.progress())

    def processed_bytes(self):
        return self.__obj.processed_bytes

    def size(self):
        return get_readable_file_size(self.__size)

    def status(self):
        return MirrorStatus.STATUS_DOWNLOADING

    def name(self):
        return self.listener.name
        
    def eng(self):
        return EngineStatus().STATUS_ARIA

    def progress(self):
        try:
            progress_raw = self.__obj.processed_bytes / self.__size * 100
        except:
            progress_raw = 0
        return f"{round(progress_raw, 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self.__obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self.__size - self.processed_bytes()) / self.__obj.speed
            return get_readable_time(seconds)
        except:
            return "-"

    def gid(self) -> str:
        return self.__gid

    def download(self):
        return self.__obj
