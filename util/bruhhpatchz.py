from asyncio import create_subprocess_exec, run, wait_for
from asyncio.subprocess import PIPE
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from util.logger import LOGGER


class HPatchZError(Exception):
    def __init__(
        self,
        hpatchz: Path,
        old: Path,
        diff: Path,
        new: Path,
        errcode: int,
        output: str,
        *args: object,
    ) -> None:
        self.hpatchz = hpatchz
        self.old = old
        self.diff = diff
        self.new = new
        self.errcode = errcode
        self.output = output
        super().__init__(
            f"HPatchZError({errcode}): {output} --- {hpatchz} {old} {diff} {new}",
            *args,
        )


class BruhHPatchZ:
    STAT_INTERVAL = 1

    def __init__(
        self,
        old: Path,
        diff: Path,
        new: Path,
        progress_callback: Callable[[Optional[int], int], None],
        hpatchz=Path("hpatchz.exe"),
        expected_size: Optional[int] = None,
    ):
        self.old = old
        self.diff = diff
        self.new = new
        self.expected_size = expected_size
        self.progress_callback = progress_callback
        self.hpatchz = hpatchz
        self.captured_output = BytesIO()

    def patch(self):
        return run(self.subprocess())

    async def subprocess(self):
        self._hpatchz = await create_subprocess_exec(
            str(self.hpatchz.absolute().as_posix()),
            str(self.old.absolute()),
            str(self.diff.absolute()),
            str(self.new.absolute().as_posix()),
            stdout=PIPE,
            stderr=PIPE,
        )
        # the subprocess buffers and won't output anything :(
        # while not (line := await self.subprocess_readline()).startswith(
        #     "newDataSize : "
        # ):
        #     pass
        # self._expected_size = int(line.split()[-1])
        # LOGGER.trace(
        #     "Patching in Subprocess hpatchz reported newDataSize %d",
        #     self._expected_size,
        # )
        return await self.statsize()

    async def statsize(self):
        self._current_size = 0
        while True:
            try:
                new_size = self.new.stat().st_size
            except FileNotFoundError:
                LOGGER.trace(
                    "Patching in Subprocess hpatchz new file %s isn't found yet",
                    self.new,
                )
                new_size = 0
            self.progress_callback(self.expected_size, new_size - self._current_size)
            self._current_size = new_size
            if (
                self.expected_size is not None
                and self._current_size >= self.expected_size
            ):
                LOGGER.trace(
                    "Patching in Subprocess hpatchz waiting for exit indefinitely as size expected %d",
                    self.expected_size,
                )
                return_code = await self._hpatchz.wait()
                break
            try:
                LOGGER.trace(
                    "Patching in Subprocess hpatchz waiting for exit %fs",
                    self.STAT_INTERVAL,
                )
                return_code = await wait_for(self._hpatchz.wait(), self.STAT_INTERVAL)
                LOGGER.trace(
                    "Patching in Subprocess hpatchz exited while waiting, return code %d",
                    return_code,
                )
                break
            except TimeoutError:
                LOGGER.trace(
                    "Patching in Subprocess hpatchz waited %fs without exit",
                    self.STAT_INTERVAL,
                )
                await self.subprocess_errored_check()
        LOGGER.trace("Patching in Subprocess hpatchz exited with code %d", return_code)
        self.progress_callback(
            self.expected_size, self.new.stat().st_size - self._current_size
        )
        if return_code:
            await self.subprocess_errored_check()
        return self.new

    async def subprocess_errored_check(self):
        stderr_test_data = b""
        try:
            # try to consume stderr at this point in time
            stderr_test_data = await wait_for(self._hpatchz.stderr.read(1), 0.1)  # type: ignore
        except TimeoutError:
            # no data present in stderr yet
            pass
        if stderr_test_data or self._hpatchz.stdout.at_eof() or self._hpatchz.returncode is not None and self._hpatchz.returncode != 0:  # type: ignore
            # wait for process to end first, then gets all output possible for error reporting
            await self._hpatchz.wait()
            self.captured_output.write(b"stdout: " + await self._hpatchz.stdout.read())  # type: ignore
            self.captured_output.write(b"stderr: " + stderr_test_data + await self._hpatchz.stderr.read())  # type: ignore
            raise HPatchZError(
                self.hpatchz,
                self.old,
                self.diff,
                self.new,
                self._hpatchz.returncode,  # type: ignore
                self.captured_output.getvalue().decode(errors="replace"),
            )

    async def subprocess_readline(self) -> str:
        await self.subprocess_errored_check()
        line = await self._hpatchz.stdout.readline()  # type: ignore
        self.captured_output.write(b"stdout: " + line)
        return line.decode(errors="replace").strip()
