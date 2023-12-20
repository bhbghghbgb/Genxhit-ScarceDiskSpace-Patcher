# use this to purge all non-critical game files and empty folders
# it will also purge hot-update files and the game will download them again and verify again
from json import loads
from os import system
from pathlib import Path
from config import Config
from game.gamelanguage import GameLanguage


config = Config(Path("config.txt"))
game_path = config.game_path
languages = (GameLanguage.GAME, GameLanguage.EN_US)
expected_files = {
    game_path / loads(line)["remoteName"]
    for lang in languages
    for line in open(game_path / lang.audio_str)
    if line
}
expected_files.add(game_path / "config.ini")
expected_files.update(game_path / lang.audio_str for lang in languages)
available_files = {dir / file for dir, _, files in game_path.walk() for file in files}
print(len(expected_files), len(available_files))
extra_files = available_files - expected_files
missing_files = expected_files - available_files
print(missing_files)
system("pause")
for file in extra_files:
    print("Deleting file", file)
    file.unlink(True)
system("pause")
for root, _, files in game_path.walk(top_down=False):
    if not files:
        try:
            root.rmdir()
            print("Delete empty dir ", root)
        except OSError:
            pass
