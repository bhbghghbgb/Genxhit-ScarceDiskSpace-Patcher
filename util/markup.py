from pathlib import Path
from typing import Callable, TypeVar, cast

from game.gamelanguage import GameLanguage
from rich.markup import escape
from setuptools._vendor.packaging import version as semver

_MARKUP_COLORS: dict[type, Callable[[object], str]] = {
    semver.Version: lambda s: f"[cyan]{escape(str(s))}[/]",
    Path: lambda s: f"[green]{escape(str(s))}[/]",
    str: lambda s: f"[bright_green]{escape(str(s))}[/]",
    # int: lambda s: f"[{"bright_red" if cast(int, s) < 0 else "cyan"}]{escape(str(s))}[/]",
    GameLanguage: lambda s: f"[dark_orange]{escape(str(s))}[/]",
}
T = TypeVar("T")

EXTRA_ENABLE_MARKUP = {"markup": True}


def markup_obj(obj: T) -> T | str:
    colorer = _MARKUP_COLORS.get(type(obj), None)
    if colorer is None:
        for obj_type, obj_colorer in _MARKUP_COLORS.items():
            if isinstance(obj, obj_type):
                colorer = obj_colorer
                _MARKUP_COLORS[type(obj)] = obj_colorer
                break
    return obj if colorer is None else colorer(obj)
