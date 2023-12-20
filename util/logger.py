import logging
from collections.abc import Mapping
from logging import Logger, addLevelName, getLogger, setLoggerClass
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Queue
from types import TracebackType
from typing import TypeAlias, cast

from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

from util.markup import markup_obj, EXTRA_ENABLE_MARKUP

_SysExcInfoType: TypeAlias = (
    tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None]
)
_ExcInfoType: TypeAlias = None | bool | _SysExcInfoType | BaseException

TRACE = 5
VERBOSE = 15
NOTICE = 25
SUCCESS = 35


class MyLogger(Logger):
    def trace(
        self,
        msg: object,
        *args: object,
        exc_info: _ExcInfoType = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None:
        if super().isEnabledFor(TRACE):
            self._log(
                TRACE,
                msg,
                args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

    def verbose(
        self,
        msg: object,
        *args: object,
        exc_info: _ExcInfoType = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None:
        if super().isEnabledFor(VERBOSE):
            self._log(
                VERBOSE,
                msg,
                args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

    def notice(
        self,
        msg: object,
        *args: object,
        exc_info: _ExcInfoType = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None:
        if super().isEnabledFor(NOTICE):
            self._log(
                NOTICE,
                msg,
                args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

    def success(
        self,
        msg: object,
        *args: object,
        exc_info: _ExcInfoType = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None
    ) -> None:
        if super().isEnabledFor(SUCCESS):
            self._log(
                SUCCESS,
                msg,
                args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

    def _log(
        self,
        level: int,
        msg: object,
        args: object,
        exc_info: _ExcInfoType = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        return super()._log(
            level,
            msg,
            tuple(markup_obj(arg) for arg in args),  # type: ignore
            exc_info=exc_info,
            stack_info=stack_info,
            stacklevel=stacklevel,
            extra=extra or EXTRA_ENABLE_MARKUP,
        )


logging.logMultiprocessing = False
logging.logProcesses = False
logging.logThreads = False
addLevelName(TRACE, "TRACE")
addLevelName(VERBOSE, "VERBOSE")
addLevelName(NOTICE, "NOTICE")
addLevelName(SUCCESS, "SUCCESS")
setLoggerClass(MyLogger)
CONSOLE = Console(
    theme=Theme(
        {
            "logging.level.trace": "grey50",
            "logging.level.verbose": "cyan",
            "logging.level.notice": "magenta",
            "logging.level.success": "white on bright_green",
        }
    )
)
handler = RichHandler(
    level=TRACE,
    console=CONSOLE,
    omit_repeated_times=False,
    show_path=False,
    enable_link_path=False,
    # markup=True,
    rich_tracebacks=True,
    log_time_format="%H:%M:%S.%f",
)
# MULTIPROCESSING_QUEUE = Queue()
MULTIPROCESSING_QUEUE = None
LOGGER = cast(MyLogger, getLogger(__name__))
# LOGGER.addHandler(QueueHandler(MULTIPROCESSING_QUEUE))
# LOGGING_QUEUE_LISTENER = QueueListener(
#     MULTIPROCESSING_QUEUE, handler, respect_handler_level=True
# )
LOGGER.addHandler(handler)
LOGGER.setLevel(TRACE)
# LOGGING_QUEUE_LISTENER.start()
