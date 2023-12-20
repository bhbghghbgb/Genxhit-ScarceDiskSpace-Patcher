from contextlib import ExitStack
from dataclasses import dataclass, field
from enum import Enum
from json import loads
from msvcrt import get_osfhandle
from pathlib import Path
from sys import getsizeof
from typing import Callable, Collection, Optional
from zipfile import ZipFile, ZipInfo

from game.gamelanguage import GameLanguage
from httpx import Client, HTTPError
from retry import retry
from setuptools._vendor.packaging import version as semver
from split_file_reader import SplitFileReader
from util.logger import LOGGER
from win32file import FileAllocationInfo, SetFileInformationByHandle


class AudioAsset(Enum):
    PERSISTENT = Path("GenshinImpact_Data/Persistent/AudioAssets")
    STREAMING = Path("GenshinImpact_Data/StreamingAssets/AudioAssets")


@dataclass(frozen=True)
class Entry_pkg_version:
    remoteName: Path = field(hash=True)
    md5: str = field(hash=False)
    fileSize: int = field(hash=False)

    @classmethod
    def from_json(cls, jsonline: str):
        line = loads(jsonline)
        return Entry_pkg_version(
            Path(line["remoteName"]), line["md5"], int(line["fileSize"])
        )


class UpdateFile:
    def __init__(
        self,
        update_file: Path | list[Path],
        lang: GameLanguage,
        version: tuple[Optional[semver.Version], semver.Version],
    ):
        self.path = update_file
        self.lang = lang
        self.version = version
        with ExitStack() as ws:
            if isinstance(update_file, list):
                sfr = ws.enter_context(SplitFileReader(update_file))
                zf = ws.enter_context(ZipFile(sfr))  # type: ignore
            elif isinstance(update_file, Path):
                zf = ws.enter_context(ZipFile(update_file))
            self.deletefiles = self.get_deletefiles(zf)
            self.hdifffiles = self.get_hdifffiles(zf)
            self.hdifffiles_wext = self.get_hdifffiles_wext(self.hdifffiles)
            self.raw_pkg_version, self.pkg_version = self.get_pkg_version(zf, self.lang)
            self.inpkgfiles = self.get_inpkgfiles(self.pkg_version)
            self.hdifffiles_info = self.get_hdifffiles_info(zf, self.hdifffiles_wext)
            self.inpkgfiles_info = self.get_inpkgfiles_info(zf, self.inpkgfiles)
            self.standalonefiles_info = self.get_standalonefiles_info(
                zf, self.inpkgfiles_info, self.hdifffiles_info
            )

    @staticmethod
    def get_standalonefiles_info(
        zf: ZipFile,
        inpkgfiles_info: Collection[ZipInfo],
        hdifffiles_info: Collection[ZipInfo],
    ):
        return {
            info
            for info in zf.infolist()
            # exclude directories? (from )
            if not info.is_dir()
            # not the aforementioned ritual
            and info.filename != "deletefiles.txt"
            and info.filename != "hdifffiles.txt"
            and info not in inpkgfiles_info
            and info not in hdifffiles_info
        }

    @staticmethod
    def get_inpkgfiles_info(zf: ZipFile, inpkgfiles: Collection[Path]):
        return {
            # these can't include directories and they will be pushed to standlonefiles
            info
            for info in zf.infolist()
            if Path(info.filename) in inpkgfiles
        }

    @staticmethod
    def get_hdifffiles_info(zf: ZipFile, hdifffiles_wext: Collection[Path]):
        return {zf.getinfo(hdf.as_posix()) for hdf in hdifffiles_wext}

    @staticmethod
    def get_inpkgfiles(pkg_version: Collection[Entry_pkg_version]):
        return {entry.remoteName for entry in pkg_version}

    @staticmethod
    def get_hdifffiles_wext(hdifffiles: Collection[Path]):
        return {Path(f"{path}.hdiff") for path in hdifffiles}

    @staticmethod
    def get_pkg_version(ofile: ZipFile, lang: GameLanguage):
        raw = ofile.read(lang.audio_str)
        return raw, {
            Entry_pkg_version.from_json(line.strip())
            for line in raw.decode().splitlines()
            if line
        }

    @staticmethod
    def get_deletefiles(ofile: ZipFile) -> set[Path]:
        try:
            return {
                Path(line.strip())
                for line in ofile.read("deletefiles.txt").decode().splitlines()
                if line
            }
        except KeyError:
            return set()

    @staticmethod
    def get_hdifffiles(ofile: ZipFile) -> set[Path]:
        try:
            return {
                Path(loads(line.strip())["remoteName"])
                for line in ofile.read("hdifffiles.txt").decode().splitlines()
                if line
            }
        except KeyError:
            return set()

    def __repr__(self):
        version = f"v=({self.version[0]} -> {self.version[1]})"
        file_name = "".join(
            (
                "file=",
                (
                    repr(str(self.path))
                    if isinstance(self.path, Path)
                    else repr(str(self.path[0]))
                    if len(self.path) == 1
                    else f"{repr(str(self.path[0]))} ... {repr(str(self.path[-1])[-3:])}"
                ),
                ")",
            )
        )
        info_count = f"count=(delete={len(self.deletefiles)} standalone={len(self.standalonefiles_info)} inpkg={len(self.inpkgfiles_info)} hdiff={len(self.hdifffiles_info)})"
        return f"<UpdateFile {self.lang} {version} {file_name} {info_count}>"

    def get_deletefiles_bytes_relative(self):
        return sum(getsizeof(str(file)) for file in self.deletefiles)

    def get_deletefiles_bytes(self, from_where: Path):
        return sum(getsizeof(str(from_where / file)) for file in self.deletefiles)

    def get_hdifffiles_bytes(self):
        return sum(info.file_size for info in self.hdifffiles_info)

    def get_patchedhdifffiles_bytes(self):
        return sum(
            entry.fileSize
            for entry in self.pkg_version
            if entry.remoteName in self.hdifffiles
        )

    def get_inpkgfiles_bytes(self):
        return sum(info.file_size for info in self.inpkgfiles_info)

    def get_standalonefiles_bytes(self):
        return sum(info.file_size for info in self.standalonefiles_info)

    def get_verify_bytes(self):
        return sum(pv.fileSize for pv in self.pkg_version)

    def get_pkg_version_bytes(self):
        return len(self.raw_pkg_version)

    def get_patch_bytes(self, game_path: Path):
        return (
            # deletefiles
            self.get_deletefiles_bytes(game_path)
            # files that are in the zip file but not in the pkg file
            + self.get_standalonefiles_bytes()
            # files that are in both the zip file and the pkg flle
            + self.get_inpkgfiles_bytes()
            # hdiff files extract
            + self.get_hdifffiles_bytes()
            # patch hdiff files to result file, and copy them back
            + self.get_patchedhdifffiles_bytes() * 2
            # verify
            + self.get_verify_bytes()
            # pkg_version file that is not an entry in the pkg_version file itself
            + self.get_pkg_version_bytes()
        )


class DownloadFile:
    def __init__(
        self,
        link: str,
        file: Path,
        size: int,
        version: tuple[Optional[semver.Version], semver.Version],
        progress_callback: Callable[[int], None],
        lang: Optional[GameLanguage] = None,
    ):
        self.link = link
        self.file = file
        self.fullsize = size
        self.version = version
        try:
            self.currentsize = self.file.stat().st_size
        except FileNotFoundError:
            self.currentsize = -1
        self.progress_callback = progress_callback
        self.lang = lang

    def download(self, client: Optional[Client] = None):
        LOGGER.info(
            "Downloading file %s from %s size %d/%d",
            self.file,
            self.link,
            self.currentsize,
            self.fullsize,
        )
        if self.currentsize >= self.fullsize:
            LOGGER.info(
                "File %s has already been downloaded in full size %d",
                self.file,
                self.currentsize,
            )
            self.progress_callback(self.currentsize)
        else:
            if client is None:
                with Client() as client:
                    self._download(client)
            else:
                self._download(client)
        return (
            UpdateFile(self.file, self.lang, self.version) if self.lang else self.file
        )

    @retry(HTTPError, delay=2, backoff=2, max_delay=60, logger=LOGGER)
    def _download(self, client: Client):
        something_was_downloaded = self.currentsize > 0
        if something_was_downloaded:
            self.progress_callback(self.currentsize)
        else:
            self.currentsize = 0
        with client.stream(
            "GET",
            self.link,
            headers={"Range": f"bytes={self.currentsize}-{self.fullsize}"}
            if something_was_downloaded
            else None,
        ) as dl, self.file.open("ab" if something_was_downloaded else "wb") as fl:
            receiving_bytes = int(dl.headers["Content-Length"])
            assert (
                receiving_bytes + self.currentsize == self.fullsize
            ), f"Content-Length={receiving_bytes} + {self.currentsize=} != {self.fullsize=}"
            # preallocate file
            SetFileInformationByHandle(
                get_osfhandle(fl.fileno()),
                FileAllocationInfo,
                self.fullsize,
            )
            for chunk in dl.iter_bytes():
                if chunk:
                    leng = fl.write(chunk)
                    self.currentsize += leng
                    self.progress_callback(leng)
