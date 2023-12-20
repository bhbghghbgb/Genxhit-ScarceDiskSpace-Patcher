import os
from pathlib import Path
from struct import unpack
from time import mktime
from typing import Callable, override
from zipfile import ZipFile, ZipInfo

from ntsecuritycon import FILE_WRITE_ATTRIBUTES
from pywintypes import TimeStamp
from split_file_reader import SplitFileReader
from util.logger import LOGGER
from win32file import (
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_DELETE,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    OPEN_EXISTING,
    CreateFile,
    SetFileTime,
)

# Copied from zipfile.py
_WINDOWS = os.name == "nt"
COPY_BUFSIZE = 1024 * 1024 if _WINDOWS else 64 * 1024


class BruhZipFile(ZipFile):
    # Callable[CurrentFile, bytes_written_this_iteration]
    def __init__(
        self,
        file: Path | list[Path],
        progress_callback: Callable[[ZipInfo, int], None],
    ):
        if isinstance(file, list):
            self.split_file_reader = SplitFileReader(file)
            super().__init__(self.split_file_reader)  # type: ignore
        else:
            self.split_file_reader = None
            super().__init__(file)
        self.progress_callback = progress_callback

    @override
    def close(self):
        super().close()
        if self.split_file_reader is not None:
            self.split_file_reader.close()

    # copied from zipfile.py
    @override
    def _extract_member(self, member, targetpath, pwd):  # type: ignore
        """Extract the ZipInfo object 'member' to a physical
        file on the path targetpath.
        """
        if not isinstance(member, ZipInfo):
            member = self.getinfo(member)

        # build the destination pathname, replacing
        # forward slashes to platform specific separators.
        arcname = member.filename.replace("/", os.path.sep)

        if os.path.altsep:
            arcname = arcname.replace(os.path.altsep, os.path.sep)
        # interpret absolute pathname as relative, remove drive letter or
        # UNC path, redundant separators, "." and ".." components.
        arcname = os.path.splitdrive(arcname)[1]
        invalid_path_parts = ("", os.path.curdir, os.path.pardir)
        arcname = os.path.sep.join(
            x for x in arcname.split(os.path.sep) if x not in invalid_path_parts
        )
        if os.path.sep == "\\":
            # filter illegal characters on Windows
            arcname = self._sanitize_windows_name(arcname, os.path.sep)  # type: ignore

        targetpath = os.path.join(targetpath, arcname)
        targetpath = os.path.normpath(targetpath)

        # Create all upper directories if necessary.
        upperdirs = os.path.dirname(targetpath)
        if upperdirs and not os.path.exists(upperdirs):
            os.makedirs(upperdirs)

        if member.is_dir():
            if not os.path.isdir(targetpath):
                os.mkdir(targetpath)
            return targetpath

        with self.open(member, pwd=pwd) as source, open(targetpath, "wb") as target:
            # shutil.copyfileobj(source, target)
            # CHANGE
            self._copyfileobj(source, target, member)
            # EXTRA
            self._write_timestamps(targetpath, self._get_timestamps(member), member)

        return targetpath

    # copied from shutil.py
    # CHANGE
    # def copyfileobj(fsrc, fdst, length=0):
    def _copyfileobj(self, fsrc, fdst, fzip, length=0):
        """copy data from file-like object fsrc to file-like object fdst"""
        # Localize variable access to minimize overhead.
        if not length:
            length = COPY_BUFSIZE
        fsrc_read = fsrc.read
        fdst_write = fdst.write
        while True:
            buf = fsrc_read(length)
            if not buf:
                break
            # fdst_write(buf)
            # CHANGE
            self.progress_callback(fzip, fdst_write(buf))

    # Bing Chat answer
    # https://fossies.org/linux/unzip/proginfo/extrafld.txt
    @staticmethod
    def _get_timestamps(zi: ZipInfo):
        mactime = {}
        # Get the extra field data as bytes
        extra = zi.extra
        # Loop through the extra field blocks
        while len(extra) >= 4:
            # Each block has a header with two unsigned short values
            # The first value is the block ID
            # The second value is the block size
            header = unpack("<HH", extra[:4])
            block_id = header[0]
            block_size = header[1]
            # Check if the block ID is 0x000a, which means NTFS
            if block_id == 0x000A:
                # The NTFS block has the following format:
                # Size   Content
                # 4      Reserved
                # 2      Tag1 ID
                # 2      Tag1 size
                # 8      Mtime
                # 8      Atime
                # 8      Ctime
                # Skip the reserved bytes
                ntfs_data = extra[8 : 8 + block_size]
                # Get the tag ID and size
                tag_id, tag_size = unpack("<HH", ntfs_data[:4])
                # Check if the tag ID is 0x0001, which means standard info
                if tag_id == 0x0001 and tag_size == 24:
                    # Get the timestamps as 64-bit values
                    mactime["mtime"], mactime["atime"], mactime["ctime"] = unpack(
                        "<QQQ", ntfs_data[4:28]
                    )
                    # Convert from Windows file time to Unix time
                    # mtime = (mtime - 116444736000000000) / 10000000
                    # atime = (atime - 116444736000000000) / 10000000
                    # ctime = (ctime - 116444736000000000) / 10000000
                    # print(f"Mtime: {mtime}")
                    # print(f"Atime: {atime}")
                    # print(f"Ctime: {ctime}")
            # Move to the next block
            extra = extra[4 + block_size :]
        return mactime

    # https://stackoverflow.com/questions/9813243/extract-files-from-zip-file-and-retain-mod-date
    # https://stackoverflow.com/questions/4996405/how-do-i-change-the-file-creation-date-of-a-windows-file
    @staticmethod
    def _write_timestamps(targetpath: str, mactime, zi: ZipInfo):
        if not mactime:
            # fallback
            dt = mktime(zi.date_time + (0, 0, -1))
            dt = (dt, dt)
            LOGGER.trace(
                "Writing timestamp fallback utime method for file %s time %s",
                targetpath,
                dt,
            )
            os.utime(targetpath, dt)
            return
        mactime = {mac: TimeStamp(stamp) for mac, stamp in mactime.items()}
        LOGGER.trace(
            "Writing timestamp winapi method for file %s time %s",
            targetpath,
            mactime,
        )
        handle = CreateFile(
            targetpath,
            FILE_WRITE_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        SetFileTime(
            handle, mactime["ctime"], mactime["atime"], mactime["mtime"]  # type:ignore
        )
        handle.close()


# if __name__ == '__main__':
#     b = BruhZipFile('E:\\Download\\apache-maven-3.8.6-bin.zip',
#                     lambda zipinfo, bw: print(zipinfo, bw))
#     print(b)
