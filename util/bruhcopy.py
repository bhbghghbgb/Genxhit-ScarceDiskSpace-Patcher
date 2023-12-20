import os
import stat
import sys
from pathlib import Path
from shutil import *  # type: ignore
from typing import Callable, Optional

from ntsecuritycon import FILE_READ_ATTRIBUTES, FILE_WRITE_ATTRIBUTES
from util.logger import LOGGER
from win32file import (
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_DELETE,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    OPEN_EXISTING,
    CreateFile,
    GetFileTime,
    SetFileTime,
)


class BruhCopy:
    def __init__(self, progress_callback: Callable[[int, int], None]):
        self.__progress_callback = progress_callback

    def bruh_move(
        self,
        src: os.PathLike,
        dst: os.PathLike,
        metadata: Optional[os.PathLike],
        delete_metafile=False,
    ):
        return self._bruh(src, dst, metadata, delete_metafile, True)

    def bruh_copy(
        self,
        src: os.PathLike,
        dst: os.PathLike,
        metadata: Optional[os.PathLike],
        delete_metafile=False,
    ):
        return self._bruh(src, dst, metadata, delete_metafile, False)

    def _bruh(
        self,
        src: os.PathLike,
        dst: os.PathLike,
        metadata: Optional[os.PathLike],
        delete_metafile=False,
        delete_src=False,
    ):
        ret_dst = self.copy2(
            os.fspath(src),
            os.fspath(dst),
            os.fspath(metadata) if metadata else None,
            follow_symlinks=False,
        )
        if delete_src:
            Path(src).unlink(True)
        if delete_metafile and metadata:
            Path(metadata).unlink(True)
        return Path(ret_dst)

    _WINDOWS = os.name == "nt"
    COPY_BUFSIZE = 1024 * 1024 if _WINDOWS else 64 * 1024

    # def copy2(src, dst, *, follow_symlinks=True):
    def copy2(self, src, dst, metadata=None, *, follow_symlinks=True):
        """Copy data and metadata. Return the file's destination.

        Metadata is copied with copystat(). Please see the copystat function
        for more information.

        The destination may be a directory.

        If follow_symlinks is false, symlinks won't be followed. This
        resembles GNU's "cp -P src dst".
        """
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))

        # if hasattr(_winapi, "CopyFile2"):
        #     src_ = os.fsdecode(src)
        #     dst_ = os.fsdecode(dst)
        #     flags = _winapi.COPY_FILE_ALLOW_DECRYPTED_DESTINATION # for compat
        #     if not follow_symlinks:
        #         flags |= _winapi.COPY_FILE_COPY_SYMLINK
        #     try:
        #         _winapi.CopyFile2(src_, dst_, flags)
        #         return dst
        #     except OSError as exc:
        #         if (exc.winerror == _winapi.ERROR_PRIVILEGE_NOT_HELD
        #             and not follow_symlinks):
        #             # Likely encountered a symlink we aren't allowed to create.
        #             # Fall back on the old code
        #             pass
        #         elif exc.winerror == _winapi.ERROR_ACCESS_DENIED:
        #             # Possibly encountered a hidden or readonly file we can't
        #             # overwrite. Fall back on old code
        #             pass
        #         else:
        #             raise

        # copyfile(src, dst, follow_symlinks=follow_symlinks)
        self.copyfile(src, dst, follow_symlinks=follow_symlinks)
        # copystat(src, dst, follow_symlinks=follow_symlinks)
        if metadata:
            copystat(metadata, dst, follow_symlinks=follow_symlinks)
            self.copy_timestamps(metadata, dst)
        else:
            copystat(src, dst, follow_symlinks=follow_symlinks)
            self.copy_timestamps(src, dst)
        return dst

    # def copyfile(src, dst, *, follow_symlinks=True):
    def copyfile(self, src, dst, *, follow_symlinks=True):
        """Copy data from src to dst in the most efficient way possible.

        If follow_symlinks is not set and src is a symbolic link, a new
        symlink will be created instead of copying the file it points to.

        """
        sys.audit("shutil.copyfile", src, dst)

        # if _samefile(src, dst):
        if self._samefile(src, dst):
            raise SameFileError("{!r} and {!r} are the same file".format(src, dst))

        file_size = 0
        for i, fn in enumerate([src, dst]):
            try:
                # st = _stat(fn)
                st = self._stat(fn)
            except OSError:
                # File most likely does not exist
                pass
            else:
                # XXX What about other special files? (sockets, devices...)
                if stat.S_ISFIFO(st.st_mode):
                    fn = fn.path if isinstance(fn, os.DirEntry) else fn
                    raise SpecialFileError("`%s` is a named pipe" % fn)
                # if _WINDOWS and i == 0:
                if self._WINDOWS and i == 0:
                    file_size = st.st_size

        # if not follow_symlinks and _islink(src):
        if not follow_symlinks and self._islink(src):
            os.symlink(os.readlink(src), dst)
        else:
            with open(src, "rb") as fsrc:
                try:
                    with open(dst, "wb") as fdst:
                        # # macOS
                        # if _HAS_FCOPYFILE:
                        #     try:
                        #         _fastcopy_fcopyfile(fsrc, fdst, posix._COPYFILE_DATA)
                        #         return dst
                        #     except _GiveupOnFastCopy:
                        #         pass
                        # # Linux
                        # elif _USE_CP_SENDFILE:
                        #     try:
                        #         _fastcopy_sendfile(fsrc, fdst)
                        #         return dst
                        #     except _GiveupOnFastCopy:
                        #         pass
                        # # Windows, see:
                        # # https://github.com/python/cpython/pull/7160#discussion_r195405230
                        # elif _WINDOWS and file_size > 0:
                        if self._WINDOWS and file_size > 0:
                            # _copyfileobj_readinto(
                            self._copyfileobj_readinto(
                                # fsrc, fdst, min(file_size, COPY_BUFSIZE)
                                fsrc,
                                fdst,
                                min(file_size, self.COPY_BUFSIZE),
                            )
                            return dst

                        self.copyfileobj(fsrc, fdst)

                # Issue 43219, raise a less confusing exception
                except IsADirectoryError as e:
                    if not os.path.exists(dst):
                        raise FileNotFoundError(
                            f"Directory does not exist: {dst}"
                        ) from e
                    else:
                        raise

        return dst

    @staticmethod
    def _samefile(src, dst):
        # Macintosh, Unix.
        if isinstance(src, os.DirEntry) and hasattr(os.path, "samestat"):
            try:
                return os.path.samestat(src.stat(), os.stat(dst))
            except OSError:
                return False

        if hasattr(os.path, "samefile"):
            try:
                return os.path.samefile(src, dst)
            except OSError:
                return False

        # All other platforms: check for same pathname.
        return os.path.normcase(os.path.abspath(src)) == os.path.normcase(
            os.path.abspath(dst)
        )

    @classmethod
    def _stat(cls, fn):
        return fn.stat() if isinstance(fn, os.DirEntry) else os.stat(fn)

    @classmethod
    def _islink(cls, fn):
        return fn.is_symlink() if isinstance(fn, os.DirEntry) else os.path.islink(fn)

    # def _copyfileobj_readinto(fsrc, fdst, length=COPY_BUFSIZE):
    def _copyfileobj_readinto(self, fsrc, fdst, length=COPY_BUFSIZE):
        """readinto()/memoryview() based variant of copyfileobj().
        *fsrc* must support readinto() method and both files must be
        open in binary mode.
        """
        # Localize variable access to minimize overhead.
        fsrc_readinto = fsrc.readinto
        fdst_write = fdst.write
        with memoryview(bytearray(length)) as mv:
            while True:
                n = fsrc_readinto(mv)
                if not n:
                    break
                elif n < length:
                    with mv[:n] as smv:
                        # fdst_write(smv)
                        self.report_progress(fdst_write(smv))
                    break
                else:
                    # fdst_write(mv)
                    self.report_progress(fdst_write(mv))

    # def copyfileobj(fsrc, fdst, length=0):
    def copyfileobj(self, fsrc, fdst, length=0):
        """copy data from file-like object fsrc to file-like object fdst"""
        if not length:
            # length = COPY_BUFSIZE
            length = self.COPY_BUFSIZE
        # Localize variable access to minimize overhead.
        fsrc_read = fsrc.read
        fdst_write = fdst.write
        while buf := fsrc_read(length):
            # fdst_write(buf)
            self.report_progress(fdst_write(buf))

    def report_progress(self, nbytes):
        self.__progress_callback(self.COPY_BUFSIZE, nbytes)

    @staticmethod
    def copy_timestamps(src, dst):
        src_handle = CreateFile(
            src,
            FILE_READ_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        src_time = GetFileTime(src_handle)  # type: ignore
        src_handle.close()
        LOGGER.trace(
            "Rewriting timestamp %s from file %s to file %s",
            src_time,
            src,
            dst,
        )
        dst_handle = CreateFile(
            dst,
            FILE_WRITE_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        SetFileTime(dst_handle, *src_time)  # type: ignore
        dst_handle.close()
