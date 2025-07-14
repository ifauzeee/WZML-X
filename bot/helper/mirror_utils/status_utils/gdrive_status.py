#!/usr/bin/env python3
from time import time
from bot.helper.ext_utils.bot_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
    get_progress_bar_string,
)

class GdriveStatus:
    def __init__(self, obj, size, listener, gid, status):
        self.__obj = obj
        self.__size = size
        self.__gid = gid
        self.__status = status
        self.listener = listener

    def progress_bar(self):
        return get_progress_bar_string(self)
        
    def progress_message(self):
        return self.listener._getStatusMessage(self.name(), self.size(), self.gid())

    def processed_bytes(self):
        return self.__obj.processed_bytes

    def size(self):
        return get_readable_file_size(self.__size)

    def status(self):
        if self.__status == "up":
            return MirrorStatus.STATUS_UPLOADING
        elif self.__status == "dl":
            return MirrorStatus.STATUS_DOWNLOADING
        else:
            return MirrorStatus.STATUS_CLONING

    def name(self):
        return self.__obj.name

    def gid(self) -> str:
        return self.__gid

    def progress(self):
        try:
            return f"{round(self.__obj.processed_bytes / self.__size * 100, 2)}%"
        except:
            return "0.0%"

    def speed(self):
        return f"{get_readable_file_size(self.__obj.speed)}/s"

    def eta(self):
        try:
            seconds = (self.__size - self.__obj.processed_bytes) / self.__obj.speed
            return get_readable_time(seconds)
        except:
            return "-"

    def download(self):
        return self.__obj
