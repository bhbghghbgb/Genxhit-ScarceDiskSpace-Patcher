from queue import Queue
from threading import Thread
from types import SimpleNamespace
from typing import Mapping, Optional

from config import Config
from game.gamedownloader import GameDownloader
from game.gameinfo import GameInfo
from game.gamelanguage import GameLanguage
from game.gameutil import AudioAsset, UpdateFile
from rich.progress import Progress, TaskID
from util.logger import LOGGER
from util.patchprocesser import PatchProcesser


class GamePatcher:
    def __init__(
        self,
        config: Config,
        gameinfo: Optional[GameInfo],
        progress: Progress,
        game_task: TaskID,
        langs_task: Mapping[GameLanguage, TaskID],
        patch_queue: Queue[tuple[UpdateFile | SimpleNamespace | None, TaskID | None]],
    ):
        # make sure the users allows game patching (they may only require preinstallation)
        assert not config.download_only
        self.config = config
        self.path = config.temp_path
        self.hpatchzpath = config.hpatchz_path
        self.gameinfo = gameinfo
        self.progress = progress
        self.taskids = {
            lang: taskid
            for lang, taskid in ((GameLanguage.GAME, game_task), *(langs_task.items()))
        }
        self.patch_queue = patch_queue
        self.downloader = GameDownloader(
            config, gameinfo, progress, game_task, langs_task, self.patch_queue
        )
        self.downloader_thread = None

    def patch(self, download_full_game: bool):
        if download_full_game:
            self._extract()
        else:
            self._patch()

    def _extract(self):
        self.downloader_thread = Thread(
            target=self.downloader.download_full_game,
            name="Downloader",
            args=(),
            daemon=True,
        )
        self.downloader_thread.start()
        self._consume_downloaded_file()
        while self.downloader_thread.is_alive():
            self.downloader_thread.join(0.1)
        finishing_task = self.progress.add_task(
            description="Concluding",
            total=None,
            kolor="wheat4",
            lang=SimpleNamespace(name="OTHER"),
        )
        PatchProcesser.step_write_config_ini(
            self.gameinfo.path if self.gameinfo is not None else self.config.game_path,
            self.downloader.new_config_ini_text,
            self.downloader.version[1],
        )
        self.progress.remove_task(finishing_task)

    def _patch(self):
        assert self.gameinfo is not None
        other = SimpleNamespace(name="OTHER")
        readying_task = self.progress.add_task(
            description="Prelimary",
            total=self.gameinfo.get_moving_persistent_audioassests_to_streaming_bytes()
            + self.downloader.get_deprecated_bytes(self.gameinfo.path),
            kolor="wheat4",
            lang=other,
        )
        PatchProcesser.step_move_audioassests_from_persistent_to_streamingassets(
            self.gameinfo.audioassests[AudioAsset.PERSISTENT],
            self.gameinfo.audioassests[AudioAsset.STREAMING],
            other,
            self.progress,
            readying_task,
        )
        PatchProcesser.step_delete_deprecated_files(
            self.gameinfo.path,
            self.downloader.deprecated_files,
            other,
            self.progress,
            readying_task,
        )
        self.progress.remove_task(readying_task)
        self.downloader_thread = Thread(
            target=self.downloader.download_game_update,
            name="Downloader",
            args=(),
            daemon=True,
        )
        self.downloader_thread.start()
        self._consume_downloaded_file()
        while self.downloader_thread.is_alive():
            self.downloader_thread.join(0.1)
        finishing_task = self.progress.add_task(
            description="Concluding",
            total=None,
            kolor="wheat4",
            lang=other,
        )
        PatchProcesser.step_write_config_ini(
            self.gameinfo.path,
            self.downloader.new_config_ini_text,
            self.downloader.version[1],
        )
        self.progress.remove_task(finishing_task)

    def _consume_downloaded_file(self):
        LOGGER.debug("Entering update file consumer")
        game_path = (
            self.gameinfo.path if self.gameinfo is not None else self.config.game_path
        )
        while item := self.patch_queue.get():
            if item == (None, None):
                LOGGER.notice(
                    "Consumer Patcher received signal to end, queue %s, sentinel %s",
                    self.patch_queue,
                    item,
                )
                break
            LOGGER.debug(
                "Consumer Patcher received job from patch queue %s, item update file %s",
                self.patch_queue,
                item,
            )
            update_file = item[0]
            task_id = item[1]
            if isinstance(item[0], SimpleNamespace):
                LOGGER.notice("Consumer Patcher received a dummy %s", item)
                self._signal_item_done(task_id, update_file)
                continue
            assert isinstance(update_file, UpdateFile)
            assert task_id is not None
            self.progress.reset(
                task_id,
                total=update_file.get_patch_bytes(game_path),
                description="Patching",
                kolor="yellow",
                lang=update_file.lang,
            )
            PatchProcesser.step_delete_files_in_deletefiles_txt(
                game_path,
                update_file.lang,
                update_file.deletefiles,
                self.progress,
                task_id,
            )
            PatchProcesser.step_extract_files(
                game_path,
                update_file.lang,
                update_file.path,
                update_file.standalonefiles_info,
                update_file.inpkgfiles_info,
                update_file.hdifffiles_info,
                self.path,
                self.hpatchzpath,
                self.progress,
                task_id,
            )
            PatchProcesser.step_verify_files(
                game_path,
                update_file.lang,
                update_file.raw_pkg_version,
                update_file.pkg_version,
                self.progress,
                task_id,
            )
            self._signal_item_done(task_id, update_file)

    def _signal_item_done(
        self, task_id: TaskID | None, update_file: UpdateFile | SimpleNamespace | None
    ):
        if task_id is not None and update_file is not None:
            self.progress.update(
                task_id,
                description="Patched",
                kolor="purple",
                lang=update_file.lang,
            )
        self.patch_queue.task_done()
