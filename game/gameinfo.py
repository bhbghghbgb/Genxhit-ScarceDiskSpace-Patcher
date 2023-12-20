from configparser import ConfigParser
from pathlib import Path
from sys import getsizeof

from config import Config
from game.gamelanguage import GameLanguage
from game.gameutil import AudioAsset
from setuptools._vendor.packaging import version as semver
from util.logger import LOGGER


class GameInfo:
    CONFIG_FILE = Path("config.ini")
    DEFAULT_CONFIG = ConfigParser(
        default_section="General",
        defaults={
            "channel": "1",
            "cps": "mihoyo",
            "game_version": "",  # this must be set to a version
            "sub_channel": "0",
        },
    )

    def __init__(self, config: Config):
        self.path = config.game_path
        self.raw_config_ini, self._parser, self.version = self.read_game_config(
            self.path
        )
        self.game = GameLanguage.GAME
        self.langs = self.get_installed_languages(self.path)
        # game must have at least one language
        assert len(self.langs) > 0
        self.audioassests = {
            AudioAsset.PERSISTENT: self.path / AudioAsset.PERSISTENT.value,
            AudioAsset.STREAMING: self.path / AudioAsset.STREAMING.value,
        }

    @staticmethod
    def read_game_config(game_path: Path):
        config_path = game_path / "config.ini"
        LOGGER.verbose(
            "Reading game config file %s",
            config_path,
        )
        parser = ConfigParser()
        raw_config_ini = config_path.read_bytes()
        parser.read_string(raw_config_ini.decode())
        GameInfo.validate_game_config(parser)
        gamev = semver.Version(parser["General"]["game_version"])
        LOGGER.info("Game version %s", gamev)
        return raw_config_ini, parser, gamev

    @staticmethod
    def validate_game_config(parser: ConfigParser):
        LOGGER.debug(
            "Validating game config file %s",
            GameInfo.CONFIG_FILE,
        )
        general = parser["General"]
        allgemein = GameInfo.DEFAULT_CONFIG["General"]
        for key in "channel", "cps", "sub_channel":
            current = general.get(key)
            expected = allgemein.get(key)
            if current != expected:
                raise ValueError(f"{general}[{key} should be {expected}, not {current}")

    @classmethod
    def create_new_config(cls, new_version: semver.Version):
        new_config = ConfigParser(
            default_section="General", defaults=cls.DEFAULT_CONFIG.defaults()
        )
        new_config["General"]["game_version"] = str(new_version)
        return new_config

    @staticmethod
    def get_installed_languages(game_path: Path):
        langs = {
            GameLanguage.get(line.strip())
            for line in (
                game_path / "GenshinImpact_Data" / "Persistent" / "audio_lang_14"
            )
            .read_text()
            .splitlines()
            if line
        }
        LOGGER.info(
            "Game installed languages %s",
            langs,
        )
        return langs

    def get_copying_persistent_audioassests_bytes(self):
        return self.audioassests[AudioAsset.PERSISTENT].stat().st_size

    def get_moving_persistent_audioassests_to_streaming_bytes(self):
        return sum(
            # audioassets_bytes += sum(getsizeof(file) for file in files)
            # # "Persistent" 10c -> "StreamingAssets" 15c
            # streamingassets_bytes += sum(getsizeof(file) + 6 for file in files)
            getsizeof(str(root / file)) * 2 + 5
            for root, _, files in self.audioassests[AudioAsset.PERSISTENT].walk()
            for file in files
        )
