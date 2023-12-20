from datetime import datetime

print(datetime.now())
from rich.traceback import install
from util.logger import CONSOLE, LOGGER, MULTIPROCESSING_QUEUE

install(
    console=CONSOLE,
    show_locals=True,
    locals_max_length=None,  # type: ignore
    locals_max_string=None,  # type: ignore
    locals_hide_dunder=False,
)
from pathlib import Path
from queue import Queue
from random import randint
from time import sleep
from types import SimpleNamespace
from typing import Optional

from config import Config
from game.gamedownloader import GameDownloader
from game.gameinfo import GameInfo
from game.gamelanguage import GameLanguage
from game.gamepatcher import GamePatcher
from game.gameutil import UpdateFile
from rich.console import Group
from rich.highlighter import Highlighter
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Confirm
from util.logger import CONSOLE, LOGGER


class App:
    class RainbowHighlighter(Highlighter):
        def highlight(self, text):
            for index in range(len(text)):
                text.stylize(f"color({randint(0, 255)})", index, index + 1)

    def __init__(self):
        self.config = Config(Path("config.txt"))
        self.progress_elapsed_timer = Progress(
            TextColumn(
                "[gold3]GSP Project - [progress.description]{task.description} -",
                # highlighter=self.RainbowHighlighter(),
            ),
            TimeElapsedColumn(),
            refresh_per_second=1,
            speed_estimate_period=1,
            console=CONSOLE,
        )
        self.progress_elapsed_timer_task = self.progress_elapsed_timer.add_task(
            "Working your magic", start=False, total=None
        )
        self.progress = Progress(
            TextColumn(
                "[{task.fields[kolor]}][progress.description]{task.description}",
                justify="right",
            ),
            TextColumn("[dark_orange][progress.description]{task.fields[lang].name}"),
            BarColumn(bar_width=None),
            TaskProgressColumn(
                "[progress.percentage]{task.percentage:>3.2f}%", justify="right"
            ),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(compact=True, elapsed_when_finished=True),
            console=CONSOLE,
            speed_estimate_period=30,
            expand=True,
        )
        self.live = Live(
            Group(self.progress_elapsed_timer, self.progress),
            refresh_per_second=10,
            console=CONSOLE,
        )
        self.patch_queue: Optional[
            Queue[tuple[UpdateFile | SimpleNamespace | None, TaskID | None]]
        ] = (None if self.config.download_only else Queue())
        self.game_task = self.progress.add_task(
            description="Unknown",
            total=None,
            kolor="magenta",
            lang=GameLanguage.GAME,
        )
        try:
            self.gameinfo = GameInfo(self.config)
        except FileNotFoundError:
            self.gameinfo = None

    def perform_miracles(self):
        if self.gameinfo:
            self._game_installed()
        else:
            self._game_not_installed()

    def _game_not_installed(self):
        assert self.gameinfo is None
        assert self.config.languages is not None
        self.langs_task = {
            lang: self.progress.add_task(
                description="Unknown", total=None, kolor="magenta", lang=lang
            )
            for lang in self.config.languages
        }
        assert len(self.langs_task) > 0
        LOGGER.notice(
            "Game is not installed. You have allowed the full game installation. Download-only %s. Predownload-only %s. Registered languages %s",
            self.config.download_only,
            self.config.predownload_only,
            self.config.languages,
        )
        if self.config.download_only:
            # don't bother starting GamePatcher because we're not going to extract anything
            downloader = GameDownloader(
                self.config,
                self.gameinfo,
                self.progress,
                self.game_task,
                self.langs_task,
                self.patch_queue,
            )
            self._ask_user(
                "Continue with [yellow]DOWNLOADING [bold]WITHOUT[/bold] EXTRACTING[/yellow] full Game?"
            )
            self._start_live()
            LOGGER.notice("Full game download only no extract confirmed")
            downloader.download_full_game()
        else:
            # GamePatcher can also be used to just extract game files (if archives already downloaded GameDownloader will handle it)
            assert self.patch_queue is not None
            patcher = GamePatcher(
                self.config,
                self.gameinfo,
                self.progress,
                self.game_task,
                self.langs_task,
                self.patch_queue,
            )
            self._ask_user(
                "Continue with [yellow]DOWNLOADING [bold]AND[/bold] EXTRACTING[/yellow] full Game?"
            )
            self._start_live()
            LOGGER.notice("Full game download and extract confirmed")
            patcher.patch(download_full_game=True)
        self._app_finished()

    def _game_installed(self):
        assert self.gameinfo is not None
        self.langs_task = {
            lang: self.progress.add_task(
                description="Unknown", total=None, kolor="magenta", lang=lang
            )
            for lang in self.gameinfo.langs
        }
        assert len(self.langs_task) > 0
        LOGGER.notice(
            "Game is already installed, update will run once continue. Download-only %s. Predownload-only %s. Registered (game) languages %s",
            self.config.download_only,
            self.config.predownload_only,
            self.gameinfo.langs,
        )
        if self.config.download_only:
            # don't bother starting GamePatcher because we're not going to patch anything
            downloader = GameDownloader(
                self.config,
                self.gameinfo,
                self.progress,
                self.game_task,
                self.langs_task,
                self.patch_queue,
            )
            self._ask_user(
                "Continue with [yellow]DOWNLOADING UPDATE [bold]WITHOUT[/bold] PATCHING[/yellow] the Game?"
            )
            LOGGER.notice("Game update download no patch confirmed")
            self._start_live()
            downloader.download_game_update()
        else:
            assert self.patch_queue is not None
            # GamePatcher can also be used to just patch game files (if archives already downloaded GameDownloader will handle it)
            patcher = GamePatcher(
                self.config,
                self.gameinfo,
                self.progress,
                self.game_task,
                self.langs_task,
                self.patch_queue,
            )
            self._ask_user(
                "Continue with [yellow]DOWNLOADING UPDATE [bold]AND THEN[/bold] PATCH[/yellow] the Game?"
            )
            LOGGER.notice("Game update download and patch confirmed")
            self._start_live()
            patcher.patch(download_full_game=False)
        self._app_finished()

    def _ask_user(self, prompt):
        # it can take a while until the logs are received
        if MULTIPROCESSING_QUEUE is not None:
            while not MULTIPROCESSING_QUEUE.empty():
                sleep(0.1)
        assert Confirm.ask(prompt=prompt, console=CONSOLE)

    def _wait_user(self, seconds=5):
        wait_task = self.progress.add_task(
            description="Waiting",
            total=seconds * 10,
            kolor="yellow",
            lang=SimpleNamespace(name="USER"),
        )
        for s in range(0, seconds * 10 + 1):
            sleep(0.1)
            self.progress.update(wait_task, completed=s)
        self.progress.remove_task(wait_task)

    def _start_live(self):
        self.live.start()
        self.progress_elapsed_timer.reset(self.progress_elapsed_timer_task)
        # self.progress.start()
        self._wait_user()

    def _app_finished(self):
        self.progress_elapsed_timer.update(
            self.progress_elapsed_timer_task, description="The age of miracles is past"
        )
        self.progress_elapsed_timer.stop()
        LOGGER.success("Hopefully the App succeeded?")


class TestMarkup1:
    def __str__(self):
        return "sieu beo"

    def __rich__(self):
        return f"[red]{self.__str__()}[/red]"


class TestMarkup2:
    def __str__(self):
        return "[red]sieu beo[/red]"


if __name__ == "__main__":
    LOGGER.info(
        "GSP App Starting, %s, %s",
        TestMarkup1(),
        TestMarkup2(),
    )
    app = App()
    app.perform_miracles()
