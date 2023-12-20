from hashlib import md5 as md5hasher
from pathlib import Path
from sys import getsizeof
from types import SimpleNamespace
from typing import Collection
from zipfile import ZipInfo

from game.gameinfo import GameInfo
from game.gamelanguage import GameLanguage
from game.gameutil import Entry_pkg_version
from rich.progress import Progress, TaskID
from setuptools._vendor.packaging import version as semver
from util.bruhcopy import BruhCopy
from util.bruhhpatchz import BruhHPatchZ
from util.bruhzipfile import BruhZipFile
from util.logger import LOGGER


class PatchProcesser:
    STEPN_DELETEFILES_TXT = 1
    STEPN_EXTRACT_STANDALONE = 2
    STEPN_EXTRACT_INPKG = 3
    STEPN_PATCH_HDIFF = 4
    STEPN_VERIFY = 5

    @staticmethod
    def step_move_audioassests_from_persistent_to_streamingassets(
        persistent_dir: Path,
        streamingassets_dir: Path,
        lang: SimpleNamespace,
        progress: Progress,
        taskid: TaskID,
    ):
        LOGGER.notice(
            "Readying: Move AudioAssests from Persistent dir %s to StreamingAssets dir %s",
            persistent_dir,
            streamingassets_dir,
        )
        progress.update(taskid, description="AfP2S moving", lang=lang, kolor="yellow")
        for pd, _, pfs in persistent_dir.walk():
            sd = streamingassets_dir / pd.relative_to(persistent_dir)
            sd.mkdir(parents=True, exist_ok=True)
            for pf in pfs:
                pfile, sfile = pd / pf, sd / pf
                LOGGER.debug(
                    "Replacing file %s with %s",
                    pfile,
                    sfile,
                )
                (pfile).replace(sfile)
                progress.advance(taskid, getsizeof(str(pfile)) + getsizeof(str(sfile)))

    @staticmethod
    def step_delete_deprecated_files(
        delete_in: Path,
        files: Collection[Path],
        lang: SimpleNamespace,
        progress: Progress,
        taskid: TaskID,
    ):
        LOGGER.notice("Readying: Delete deprecated files from %s", delete_in)
        progress.update(
            taskid, description="Deprecated deleting", lang=lang, kolor="yellow"
        )
        PatchProcesser._delete_files(delete_in, files, progress, taskid)

    @staticmethod
    def step_delete_files_in_deletefiles_txt(
        delete_in: Path,
        lang: GameLanguage,
        files: Collection[Path],
        progress: Progress,
        taskid: TaskID,
    ):
        LOGGER.notice(
            "Patching %s step %d: Delete files in deletefiles.txt from %s",
            lang,
            PatchProcesser.STEPN_DELETEFILES_TXT,
            delete_in,
        )
        progress.update(taskid, description="Extra deleting", lang=lang)
        PatchProcesser._delete_files(delete_in, files, progress, taskid)

    @staticmethod
    def _delete_files(
        delete_in: Path, files: Collection[Path], progress: Progress, taskid: TaskID
    ):
        for file in files:
            to_delete = delete_in / file
            LOGGER.debug("Deleting file %s", to_delete)
            to_delete.unlink(True)
            progress.advance(taskid, getsizeof(str(to_delete)))

    @staticmethod
    def step_extract_files(
        extract_to: Path,
        lang: GameLanguage,
        update_file: Path | list[Path],
        standalone_file_list: Collection[ZipInfo],
        inpkg_file_list: Collection[ZipInfo],
        patching_file_list: Collection[ZipInfo],
        temp_dir: Path,
        hpatchz_dir: Path,
        progress: Progress,
        taskid: TaskID,
    ):
        with BruhZipFile(
            update_file, lambda _, step: progress.advance(taskid, step)
        ) as zf:
            progress.update(taskid, description="Std extracting", lang=lang)
            PatchProcesser._step_extract_standalone_files(
                extract_to, lang, zf, standalone_file_list
            )
            progress.update(taskid, description="Pkg extracting", lang=lang)
            PatchProcesser._step_extract_inpkg_files(
                extract_to, lang, zf, inpkg_file_list
            )
            progress.update(taskid, description="Hdiff patching", lang=lang)
            PatchProcesser._step_patch_files_in_hdifffiles_txt(
                extract_to,
                lang,
                zf,
                patching_file_list,
                temp_dir,
                hpatchz_dir,
            )

    @staticmethod
    def _step_extract_standalone_files(
        extract_to: Path,
        lang: GameLanguage,
        update_file: BruhZipFile,
        file_list: Collection[ZipInfo],
    ):
        LOGGER.notice(
            "Patching %s step %d: Extract standalone files from update file %s to %s",
            lang,
            PatchProcesser.STEPN_EXTRACT_STANDALONE,
            update_file.filename,
            extract_to,
        )
        PatchProcesser._extract_files(update_file, file_list, extract_to)

    @staticmethod
    def _step_extract_inpkg_files(
        extract_to: Path,
        lang: GameLanguage,
        update_file: BruhZipFile,
        file_list: Collection[ZipInfo],
    ):
        LOGGER.notice(
            "Patching %s step %d: Extract inpkg files from update file %s to %s",
            lang,
            PatchProcesser.STEPN_EXTRACT_INPKG,
            update_file.filename,
            extract_to,
        )
        PatchProcesser._extract_files(update_file, file_list, extract_to)

    @staticmethod
    def _extract_files(
        zf: BruhZipFile,
        infolist: Collection[ZipInfo],
        extract_to: Path,
    ):
        for info in infolist:
            LOGGER.debug(
                "Extracting file %s to %s",
                info.filename,
                extract_to / info.filename,
            )
            zf.extract(info, extract_to)

    @staticmethod
    def _step_patch_files_in_hdifffiles_txt(
        patch_to: Path,
        lang: GameLanguage,
        update_file: BruhZipFile,
        file_list: Collection[ZipInfo],
        temp_dir: Path,
        hpatchz_dir: Path,
    ):
        hpatchzexe = hpatchz_dir / "hpatchz.exe"
        LOGGER.notice(
            "Patching %s step %d: Patch hdiff files from update file %s to %s. Expecting hpatchzexe at %s",
            lang,
            PatchProcesser.STEPN_PATCH_HDIFF,
            update_file.filename,
            patch_to,
            hpatchzexe,
        )
        for info in file_list:
            LOGGER.debug(
                "Extracting hdiff patch file %s to %s",
                info.filename,
                temp_dir / info.filename,
            )
            # patched = hdiff.parent / Path(info.filename).stem
            hdiff = Path(update_file.extract(info, temp_dir))
            old = (patch_to / info.filename).with_suffix("")
            new = hdiff.with_suffix("")
            LOGGER.debug(
                "Patching to new file %s using old file %s and hdiff file %s",
                new,
                old,
                hdiff,
            )
            ret_new = BruhHPatchZ(
                old,
                hdiff,
                new,
                lambda _, step, info=info: update_file.progress_callback(info, step),
                hpatchzexe,
            ).patch()
            LOGGER.debug(
                "Moving patched file %s to replace old file %s",
                ret_new,
                old,
            )
            BruhCopy(
                lambda _, step, info=info: update_file.progress_callback(info, step)
            ).bruh_move(ret_new, old, hdiff, True)

    @staticmethod
    def step_verify_files(
        verify_in: Path,
        lang: GameLanguage,
        raw_pkg_version_of_update_file: bytes,
        entries: Collection[Entry_pkg_version],
        progress: Progress,
        taskid: TaskID,
    ):
        LOGGER.notice(
            "Patching %s step %d: Verify inpkg files of language %s in %s",
            lang,
            PatchProcesser.STEPN_VERIFY,
            lang.verbose_str,
            verify_in,
        )
        progress.update(taskid, description="Verifying", lang=lang)
        pkg_version_file = verify_in / lang.audio_str
        LOGGER.debug(
            "Verifying pkg_version file %s",
            pkg_version_file,
        )
        if pkg_version_file.read_bytes() != raw_pkg_version_of_update_file:
            raise AssertionError(
                f"The pkg_version {pkg_version_file} isn't the same file from the update file."
            )
        progress.advance(taskid, len(raw_pkg_version_of_update_file))
        for entry in entries:
            PatchProcesser._verify_file(
                verify_in / entry.remoteName,
                entry.md5,
                entry.fileSize,
                progress,
                taskid,
            )

    @staticmethod
    def _verify_file(
        file: Path,
        md5: str,
        expectedsize: int,
        progress: Progress,
        taskid: TaskID,
    ):
        LOGGER.debug(
            "Verifying file %s, expecting size %d, md5 %s",
            file,
            expectedsize,
            md5,
        )
        filesize = file.stat().st_size
        if filesize != expectedsize:
            raise AssertionError(
                f"The {file} size {filesize} isn't expected {expectedsize}."
            )
        bfsize = BruhCopy.COPY_BUFSIZE
        hasher = md5hasher()
        with memoryview(bytearray(bfsize)) as mv, file.open("rb") as f:
            while b := f.readinto(mv):
                if b < bfsize:
                    with mv[:b] as smv:
                        hasher.update(smv)
                        progress.advance(taskid, b)
                    break
                else:
                    hasher.update(mv)
                    progress.advance(taskid, b)
        hashed = hasher.hexdigest()
        if hashed != md5:
            raise AssertionError(f"The file {file} hash {hashed} isn't expected {md5}.")

    @staticmethod
    def step_write_config_ini(
        write_in: Path,
        config_ini_text: str,
        version: semver.Version,
    ):
        LOGGER.notice(
            "Finishing: Writing new game config file %s in %s for version %s",
            GameInfo.CONFIG_FILE,
            write_in,
            version,
        )
        (write_in / "config.ini").write_text(config_ini_text, newline="\n")


class FileIntegrityError(Exception):
    def __init__(
        self,
        file: Path,
        expected_size: int,
        actual_size: int,
        expected_md5: str,
        actual_md5: str,
        *args: object,
    ) -> None:
        self.file = file
        self.expected_size = expected_size
        self.actual_size = actual_size
        self.expected_md5 = expected_md5
        self.actual_md5 = actual_md5
        super().__init__(*args)
