from argparse import ArgumentParser, FileType
from json import loads
from os import path
from pathlib import Path
from sys import copyright
from typing import Optional, cast

from game.gamelanguage import GameLanguage


def dir_path(string):
    if path.isdir(string):
        return string
    raise NotADirectoryError(string)


class Config:
    def __init__(self, config_file: Path):
        self._parser = ArgumentParser(
            prog="gsp",
            description="Manual patch utility for low-disk-spacers.",
            epilog=copyright,
        )
        self._parser.add_argument(
            "-g",
            "--gamepath",
            type=dir_path,
            required=True,
            help="Path of Genshin Impact game directory.",
        )
        self._parser.add_argument(
            "-t",
            "--temppath",
            type=dir_path,
            required=True,
            help="Path to the directory where the compressed patch files are extracted in and is patched in.",
        )
        self._parser.add_argument(
            "-p",
            "--patchpath",
            type=dir_path,
            required=True,
            help="Path to the directory where the compressed patch files are resident.",
        )
        self._parser.add_argument(
            "-l",
            "--logpath",
            type=dir_path,
            default=".",
            help="Stores current state of patching for resuming purposes. (Not implemented, currently won't do anything)",
        )
        self._parser.add_argument(
            "-z",
            "--hpatchzpath",
            type=dir_path,
            default="./playground/GS launcher",
            help="Path to the directory where hpatchz.exe resides.",
        )
        self._parser.add_argument(
            "-a",
            "--apifile",
            type=FileType(),
            required=False,
            help="Get the mhy api result from the file instead of online.",
        )
        self._parser.add_argument(
            "-do",
            "--downloadonly",
            action="store_true",
            required=False,
            help="Do download update archives without extracting or patching the game with them (Preinstallation).",
        )
        self._parser.add_argument(
            "-po",
            "--predownloadonly",
            action="store_true",
            required=False,
            help="Force update to only predownload's version.",
        )
        self._parser.add_argument(
            "-la",
            "--language",
            nargs="+",
            choices=[
                str(lang)
                for _, lang in GameLanguage.__members__.items()
                if lang is not GameLanguage.GAME
            ],
            required=False,
            help="Languages to download if game is not installed. Use language code. Don't specify if you don't want to download game.",
        )
        with open(config_file, "r") as f:
            # simple ignorance
            self._args = self._parser.parse_args(
                tuple(
                    line
                    for line in cast(list[str], f.read().splitlines())
                    if not line.startswith("#")
                )
            )
        self.game_path = Path(self._args.gamepath)
        self.temp_path = Path(self._args.temppath)
        self.patch_path = Path(self._args.patchpath)
        self.log_path = Path(self._args.logpath)
        self.hpatchz_path = Path(self._args.hpatchzpath)
        self.api_str: Optional[dict] = None
        if self._args.apifile:
            self.api_str = loads(self._args.apifile.read())
            self._args.apifile.close()
        self.download_only: bool = self._args.downloadonly
        self.predownload_only: bool = self._args.predownloadonly
        self.languages: Optional[set[GameLanguage]] = (
            {GameLanguage.get(arg) for arg in self._args.language}
            if self._args
            else None
        )
        # these are used to force certain updates from being downloaded or being used to patch (if will cause a success without doing anything)
        # self.download_exclude = {GameLanguage.GAME}
        self.download_exclude = {}
        # self.patch_exclude = {GameLanguage.GAME, GameLanguage.EN_US}
        self.patch_exclude = {}


if __name__ == "__main__":
    conf = Config(Path("config.txt"))
