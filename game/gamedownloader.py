from io import StringIO
from os.path import basename
from pathlib import Path
from queue import Queue
from sys import getsizeof
from types import SimpleNamespace
from typing import Mapping, Optional, cast

from config import Config
from game.gameinfo import GameInfo
from game.gamelanguage import GameLanguage
from game.gameutil import DownloadFile, UpdateFile
from httpx import get
from rich.progress import Progress, TaskID
from setuptools._vendor.packaging import version as semver
from util.logger import LOGGER


class GameDownloader:
    MHY_API = "https://sdk-os-static.mihoyo.com/hk4e_global/mdk/launcher/api/resource?launcher_id=10&key=gcStgarh"

    def __init__(
        self,
        config: Config,
        gameinfo: Optional[GameInfo],
        progress: Progress,
        game_task: TaskID,
        langs_task: Mapping[GameLanguage, TaskID],
        patch_queue: Optional[
            Queue[tuple[UpdateFile | SimpleNamespace | None, TaskID | None]]
        ],
    ):
        self.path = config.patch_path
        self.config = config
        self.gameinfo = gameinfo
        self.api_result = config.api_str if config.api_str else self.get_api_result()
        (
            latest_version,
            (self.game_downloads, self.lang_downloads),
            (self.game_updates, self.lang_updates),
            self.deprecated_files,
        ) = self.read_api_result(
            config, self.api_result, self.gameinfo.version if self.gameinfo else None
        )
        self.version = (
            self.gameinfo.version if self.gameinfo else None,
            latest_version,
        )
        (
            self.new_config_ini,
            self.new_config_ini_text,
        ) = self.get_this_version_config_ini(self.version[1])
        self.progress = progress
        self.game_task = game_task
        self.langs_task = langs_task
        self.patch_queue = patch_queue
        self.update_bytes = (
            self.get_download_game_update_bytes() if self.gameinfo else None
        )
        self.download_bytes = self.get_download_full_game_bytes()
        LOGGER.verbose("Init GameDownloader: version %s", self.version)

    @staticmethod
    def get_api_result():
        LOGGER.info(
            "GETting latest game information from mhy api %s", GameDownloader.MHY_API
        )
        return get(GameDownloader.MHY_API).json()

    @staticmethod
    def read_api_result(
        config: Config, api_result: dict, game_version: Optional[semver.Version]
    ):
        deprecated_files: set[Path] = {
            Path(file["name"]) for file in api_result["data"]["deprecated_files"]
        }
        predl_game = api_result["data"]["pre_download_game"]
        game = api_result["data"]["game"]
        game_download = game["latest"]
        lang_download = game_download["voice_packs"]
        version = semver.Version(game_download["version"])
        game_downloads: list[tuple[str, int]] = [
            (seg["path"], int(seg["package_size"])) for seg in game_download["segments"]
        ]
        lang_downloads: list[tuple[GameLanguage, str, int]] = [
            (
                GameLanguage.get_bycode(lang["language"]),
                lang["path"],
                int(lang["package_size"]),
            )
            for lang in lang_download
        ]
        if game_version:
            try:
                if config.predownload_only:
                    raise StopIteration
                # if the installed version is lower than the current version, it will use the current version
                game_update = next(
                    (
                        diff
                        for diff in game["diffs"]
                        if diff["version"] == str(game_version)
                    )
                )
            # StopIteration is raised when there are no updates with version higher than current in game_update
            except StopIteration:
                # if the installed version is the current version, it will use the predownload version, or
                # preinstallation
                assert predl_game is not None
                game_update = next(
                    diff
                    for diff in predl_game["diffs"]
                    if diff["version"] == str(game_version)
                )
                # the version will be the pre_download_game's one and not the current anymore
                version = semver.Version(predl_game["latest"]["version"])
            lang_update = game_update["voice_packs"]
            game_updates: list[tuple[str, int]] = [
                (game_update["path"], int(game_update["package_size"]))
            ]
            lang_updates: list[tuple[GameLanguage, str, int]] = [
                (
                    GameLanguage.get_bycode(lang["language"]),
                    lang["path"],
                    int(lang["package_size"]),
                )
                for lang in lang_update
            ]
            return (
                version,
                (game_downloads, lang_downloads),
                (game_updates, lang_updates),
                deprecated_files,
            )
        return version, (game_downloads, lang_downloads), (None, None), deprecated_files

    def download_game_update(self):
        if (
            self.gameinfo is None
            or self.game_updates is None
            or self.lang_updates is None
        ):
            raise FileExistsError(
                f"{self} is in new download mode because a game's valid installation is found."
            )
        assert self.update_bytes is not None
        # self._queue_for_patch(
        #     UpdateFile(
        #         Path()
        #         / "playground"
        #         / "update"
        #         / "en-us_4.0.1_4.1.0_hdiff_abcdefghijklmnop.zip",
        #         GameLanguage.EN_US,
        #         (semver.Version("4.0.1"), semver.Version("4.1.0")),
        #     )
        # )
        # self._queue_for_patch(
        #     UpdateFile(
        #         Path()
        #         / "playground"
        #         / "update"
        #         / "game_4.0.1_4.1.0_hdiff_abcdefghijklmnop.zip",
        #         GameLanguage.GAME,
        #         (semver.Version("4.0.1"), semver.Version("4.1.0")),
        #     )
        # )
        # return
        LOGGER.notice(
            "Downloading game update from version %s to version %s with languages %s",
            self.version[0],
            self.version[1],
            self.gameinfo.langs,
        )
        self._reset_progress(self.update_bytes)
        self._download_game_only_update()
        self._download_lang_update()
        self._finishing_download_tasks()

    def _download_game_only_update(self):
        # game update is only one file while game download can be many
        assert self.game_updates is not None
        assert len(self.game_updates) == 1
        assert self.update_bytes is not None
        game_update = self.game_updates[0]
        LOGGER.verbose(
            "Downloading %s update file from %s api size %d %d",
            GameLanguage.GAME,
            game_update[0],
            game_update[1],
            self.update_bytes[0],
        )
        self.progress.reset(
            self.game_task,
            total=self.update_bytes[0],
            kolor="blue",
            description="Downloading",
            lang=GameLanguage.GAME,
        )
        self._queue_for_patch(
            cast(
                UpdateFile,
                self._download_file((GameLanguage.GAME, *game_update)),
            )
        )

    def _download_lang_update(self):
        # lang update must exist at least one
        assert self.lang_updates is not None
        assert len(self.lang_updates) > 0
        assert self.gameinfo is not None
        assert self.update_bytes is not None
        for lang in self.lang_updates:
            if lang[0] not in self.gameinfo.langs:
                continue
            LOGGER.verbose(
                "Downloading %s update file from %s api size %d %d",
                lang[0],
                lang[1],
                lang[2],
                self.update_bytes[1][lang[0]],
            )
            self.progress.reset(
                self._get_taskid(lang[0]),
                total=self.update_bytes[1][lang[0]],
                kolor="blue",
                description="Downloading",
                lang=lang[0],
            )
            self._queue_for_patch(cast(UpdateFile, self._download_file(lang)))

    def download_full_game(self):
        # make sure game is not installed, and the user require download full game (by specifying languages in the config)
        assert self.version[0] is None
        assert self.config.languages is not None
        LOGGER.notice(
            "Downloading full game from version %s to version %s with languages %s",
            self.version[0],
            self.version[1],
            self.config.languages,
        )
        self._reset_progress(self.download_bytes)
        self._download_game_only()
        self._download_lang()
        self._finishing_download_tasks()

    def _download_game_only(self):
        # currently only do split game downloads because the single download is unstable
        is_split = len(self.game_downloads) > 1
        LOGGER.info(
            "Downloading complete %s file from %s is_split %s count %d total size %d",
            GameLanguage.GAME,
            self.game_downloads,
            is_split,
            len(self.game_downloads),
            self.download_bytes[0],
        )
        self.progress.reset(
            self.game_task,
            total=self.download_bytes[0],
            kolor="blue",
            description="Downloading",
            lang=GameLanguage.GAME,
        )
        downloaded_files = [
            self._download_file(
                (None if is_split else GameLanguage.GAME, link, size), GameLanguage.GAME
            )
            for link, size in self.game_downloads
        ]
        LOGGER.trace("Collected full game archive file(s) %s", downloaded_files)
        # manually creates UpdateFile if the downloads result in more than one file, in which case _download_file returns a Path instead
        # if the download file is forcefully excluded in config, it skips downloading and return a fake NameSpace that contains 'lang' to satisfy the minimum requirement
        self._queue_for_patch(
            downloaded_files[0]
            if isinstance(downloaded_files[0], (UpdateFile | SimpleNamespace))
            else UpdateFile(
                cast(list[Path], downloaded_files), GameLanguage.GAME, self.version
            )
        )

    def _download_lang(self):
        # user must allow at least one lang update
        assert self.config.languages is not None
        assert len(self.config.languages) > 0
        for lang in self.lang_downloads:
            if lang[0] not in self.config.languages:
                continue
            LOGGER.debug(
                "Downloading complete %s file from %s size %d %d",
                lang[0],
                lang[1],
                lang[2],
                self.download_bytes[1][lang[0]],
            )
            self.progress.reset(
                self._get_taskid(lang[0]),
                total=self.download_bytes[1][lang[0]],
                kolor="blue",
                description="Downloading",
                lang=lang[0],
            )
            self._queue_for_patch(cast(UpdateFile, self._download_file(lang)))

    def _download_file(
        self,
        segment: tuple[Optional[GameLanguage], str, int],
        opt_lang: GameLanguage = GameLanguage.GAME,
    ) -> UpdateFile | Path | SimpleNamespace:
        file_path = self.path / basename(segment[1])
        true_lang = segment[0] if segment[0] is not None else opt_lang
        true_task_id = self._get_taskid(true_lang)
        if true_lang in self.config.download_exclude:
            LOGGER.notice(
                "Skipped download %s (%s) file %s from %s size %s",
                segment[0],
                true_lang,
                file_path,
                segment[1],
                segment[2],
            )
            self.progress.advance(true_task_id, segment[2])
            return SimpleNamespace(lang=true_lang)
        LOGGER.debug(
            "Downloading %s (%s) file %s from %s size %s",
            segment[0],
            true_lang,
            file_path,
            segment[1],
            segment[2],
        )
        return DownloadFile(
            segment[1],
            file_path,
            segment[2],
            self.version,
            lambda step: self.progress.advance(true_task_id, step),
            # if don't provide a language it returns a Path
            segment[0],
        ).download()

    def _queue_for_patch(self, update_file: UpdateFile | SimpleNamespace):
        # preinstallation
        task_id = self._get_taskid(update_file.lang)
        if self.patch_queue is None:
            LOGGER.debug(
                "Producer skipping downloaded file patch enqueue because no queue %s, update file %s",
                self.patch_queue,
                update_file,
            )
            self.progress.update(
                task_id,
                kolor="green",
                description="Downloaded",
                lang=update_file.lang,
            )
            self.progress.stop_task(task_id)
            return
        self.progress.reset(
            task_id,
            start=False,
            total=update_file.get_patch_bytes(
                self.gameinfo.path
                if self.gameinfo is not None
                else self.config.game_path
            ),
            kolor="red",
            description="Patch waiting",
            lang=update_file.lang,
        )
        item = (update_file, task_id)
        LOGGER.debug(
            "Producer Downloader enqueuing a downloaded file, queue %s, item update file %s",
            self.patch_queue,
            item,
        )
        self.patch_queue.put(item)

    def _get_taskid(self, lang: GameLanguage):
        return self.game_task if lang == GameLanguage.GAME else self.langs_task[lang]

    def _reset_progress(
        self, download_or_update_bytes: tuple[int, dict[GameLanguage, int]]
    ):
        self.progress.reset(
            self.game_task,
            start=False,
            total=download_or_update_bytes[0],
            description="Download waiting",
            kolor="yellow",
            lang=GameLanguage.GAME,
        )
        for lang, taskid in self.langs_task.items():
            self.progress.reset(
                taskid,
                description="Download waiting",
                start=False,
                total=download_or_update_bytes[1][lang],
                kolor="yellow",
                lang=lang,
            )

    def _finishing_download_tasks(self):
        sentinel = (None, None)
        LOGGER.notice(
            "All download tasks finished, sending sentinel %s to the patch queue %s",
            sentinel,
            self.patch_queue,
        )
        if self.patch_queue is not None:
            # sentinel
            self.patch_queue.put_nowait((None, None))  # type: ignore

    def get_download_game_update_bytes(self):
        # there must be at least a game update and ONE lang update
        assert self.game_updates and self.lang_updates
        return self._get_download_bytes(self.game_updates, self.lang_updates)

    def get_download_full_game_bytes(self):
        return self._get_download_bytes(self.game_downloads, self.lang_downloads)

    @staticmethod
    def _get_download_bytes(
        game: list[tuple[str, int]], langs: list[tuple[GameLanguage, str, int]]
    ) -> tuple[int, dict[GameLanguage, int]]:
        return sum(size for _, size in game), {lang[0]: lang[2] for lang in langs}

    def get_deprecated_bytes(self, from_where: Path):
        return sum(getsizeof(str(from_where / file)) for file in self.deprecated_files)

    @staticmethod
    def get_this_version_config_ini(new_ver: semver.Version):
        parser = GameInfo.create_new_config(new_ver)
        with StringIO() as sio:
            # this writes crlf new line and an extra 2 linefeed at end
            parser.write(sio, False)
            return parser, sio.getvalue().strip().replace("\r\n", "\n")
