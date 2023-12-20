from dataclasses import dataclass, field
from enum import Enum
from os import name
from typing import Collection


@dataclass
class GameUpdateItem:
    code: str
    name = "Game"

    def __post_init__(self):
        self._audio_str = "pkg_version"
        self._verbose_str = f"<{self.code}: {self.name}>"

    def __str__(self):
        return self.code

    @property
    def audio_str(self):
        return self._audio_str

    @property
    def verbose_str(self):
        return self._verbose_str


@dataclass
class GameLanguageItem(GameUpdateItem):
    name: str = field(hash=True)

    def __post_init__(self):
        super().__post_init__()
        self._audio_str = f"Audio_{self.name}_{super().audio_str}"


class GameLanguage(Enum):
    GAME = GameUpdateItem("game")
    ZH_CN = GameLanguageItem("zh-cn", "Chinese")
    EN_US = GameLanguageItem("en-us", "English(US)")
    JA_JP = GameLanguageItem("ja-jp", "Japanese")
    KO_KR = GameLanguageItem("ko-kr", "Korean")

    def __str__(self):
        return self.value.__str__()

    def __repr__(self):
        return f"<{self.value.code}: {self.value.name}>"

    @property
    def audio_str(self):
        return self.value._audio_str

    @property
    def verbose_str(self):
        return self.value._verbose_str

    @classmethod
    def get_bycode(cls, code: str):
        for item in cls.__members__.values():
            if code == item.value.code:
                return item
        raise KeyError(f"No game language has code {code}")

    @classmethod
    def get_byname(cls, name: str):
        for item in cls.__members__.values():
            if name == item.value.name:
                return item
        raise KeyError(f"No game language named {name}")

    @classmethod
    def get(cls, code_or_name: str):
        for item in cls.__members__.values():
            if code_or_name == item.value.name or code_or_name == item.value.code:
                return item
        raise KeyError(f"No game language known as {code_or_name}")

    @classmethod
    def list_verbose_str(cls, langs: Collection["GameLanguage"]):
        return [lang.verbose_str for lang in langs]

    @classmethod
    def list_str(cls, langs: Collection["GameLanguage"]):
        return [str(lang) for lang in langs]

    @classmethod
    def list_name_str(cls, langs: Collection["GameLanguage"]):
        return [lang.name for lang in langs]


if __name__ == "__main__":
    print(repr(GameLanguage.get("en-us")))
    print(GameLanguage.get("Chinese").audio_str)
    print(GameLanguage.get("ko-kr").verbose_str)
    print(GameLanguage.GAME.audio_str)
