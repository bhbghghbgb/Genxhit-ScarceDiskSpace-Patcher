# Genxhit-ScarceDiskSpace-Patcher
Or Genshin updates downloader and patcher for **power**users without much disk space to spare for game updating.

Genxhit-ScarceDiskSpace-Patcher is a not-very-user-friendly python project that allows players (with Python knowledge) to download update files, patch game files to a custom path, purge non-critical game files,... all for the very one reason: **lessen the disk space requirement** on the volume hoarding the game files.

It also tries to write timestamps of the files from the update archive to the game files to allow for a better experience of robocopy (rsync) in case you want to sync the game files to different computers without redownloading/repatching.

[Tips](#tips) I learned

## Dependencies (for Windows)
- Python 3.12.
- pipenv
- hpatchz.exe (https://github.com/sisong/HDiffPatch).
    - Or, the Offical Launcher's directory.

## Installation
Clone the project, then `pipenv install`.

## Configuration
Edit the `config.txt` with your paths.

## Usage
Run `pipenv run python gsp.py`.

## Testing
It runs on my machine.
- I have tested patch `4.2.0` -> `4.3.0`.
- I have tested download full game `4.3.0`.
- I have tested patch `4.5.0` -> `4.6.0`. (In action video https://youtu.be/hos_2SXQ-aw)
Sorry, I didn't write the project with testability in mind.

## Caution
As stated, you **MUST** have Python knowledge to use this project since I did not make it so friendly like the only thing you need to do is entering some game paths.
- I did not handle any errors or exceptions that are not normal program flow.
- You may need to manually inspect and debug the code to determine the problem if you are willing to fix it, because what you get is only a stack trace.
- As it is, with the usage of pywin32 to write timestamps and preallocate disk space for downloading update files, the project is only for **Windows** users, although you can remove it from the code so it becomes platform-independent again.
- This project requires hpatchz, in case you don't have the launcher installed (it is included there), visit https://github.com/sisong/HDiffPatch for more information.
- Because of no error handling, you may have to redownload the whole game if something snapped in the middle of *patch* step. *Download* step can now handle split files (for full game download) and partial downloaded files.
- As it is, it runs a md5 file integrity check as a verification step, however **YOU SHOULD COMMENT IT OUT**, because it will throw when a file is unexpected, while the game itself can already do this.
- The project contains copied python source code (`ZipFile` -> `BruhZipFile`, `shutil.copy`\* -> `BruhCopy`) because I wanted to provide progress updates on top of them.

### Why this project (Rant)
My sincere apologies for all the headaches, I made the project while learning python, so I didn't know good practices from bad, and how to manage a python project for user friendly.

In the past, the offical launcher was able to resolve symlinks, so all I had to do was to download to another drive then create a symlink on the game directory. Somewhere around 3.8.0 it stopped working (why tho), so I tried https://github.com/Scighost/Starward (it's the best launcher, although it still extract patch files to the game directory), unfortunately it also doesn't recognize symlinks.

I really don't know what is the problem with symlinks, all my programs on my linux mint never have problems with symlinks. I was frustrated, and so this project was born.

I know there's not a lot of people in my shoes, so let me explain my problems:
- I don't have a big SSD, but I still want to play the game on it.
- The game (4.2.0, en-us) takes 80GiB, and the offical launcher requested 30GiB to update.
- I could manage with symlinking the update archives from another drive (big HDD), and can manage it extracting the patch files to the game directory, but it no longer recognize symlinks.

## Features
- **It should recognize all symlinks.**
- Being friend with your scarce space remaining SSD partition, this utility allows you to download patch archives, extract and patch, to any paths you wish, before replacing them back into your game directory.
- Use *threading* to allow simultaneous downloading and patching at the same time\*:
    - The update archive have to be downloaded in full before patching with it.
    - While the patch job started on the downloaded file, it will run the download job for the next archive.
    - Only one download and one patch job is run at a time.
- Use Textutal's `rich` to show patch progress.
- Currently Windows-only, but if you remove the pywin32 requirement (file preallocate and timestamp writing), it will be cross-platform.

## Workflows:
1. Clears all deprecated files before patching.
    - ~~It does not clears non-critical game files such as webCaches and logs (in case you need them for whatever), ~~if you want to restore a little more space here, run the `delete_standalone.py` script~~. **DOES NOT WORK**, read [here](#current-expected-problems)
1. Runs the download job for each of the update archive to download.
1. Once the download job of an update archive has finished, runs a patch job with it, and runs the download job for the next archive.
    1. Clears deprecated files in `deletefiles.txt`.
    1. Extract all standard files (files that are not `.hdiff`, or files that aren't in `hdifffiles.txt`).
    1. Extract the `.hdiff` files, patch to a new file, copy it back to the game directory, then delete it.
    1. (Optionally, should **not** use) Run a md5 file integrity using entries in `*_pkg_version`.
1. Write a new `config.ini` for the current version.

## Project's future
- I don't plan on improving anything, since I might just rewrite it from scratch cause this thing is too much a mess.

## Getting involved
- If you have any problems, suggestions, or want to try improve the project, feel free. I appreciate all contributions.

## License
- MIT, because `MIT may protect you from being sued if bug in your code is the cause of their rocket explosion on launch`. (https://www.reddit.com/r/github/comments/hvp4k6/comment/fyuxhis/)

## Credits
- Heavily inspired by these projects:
    - https://github.com/GamerYuan/GenshinPatcher (patching workflows)
    - https://github.com/Scighost/Starward (API parsing, progress reporting)
    - https://github.com/DevonTM/genshin-updater (downloading workflows, progress reporting)

## Current expected problems
- `delete_standalone.py` does **NOT** work correctly. Only use it to check whether you have non-tracked files (files that are not in `pkg_version`).
- Instead, delete `GenshinImpact_Data\Persistent` with administrator privileges, game will redownload hot-patch again on its own.
- `delete_standalone.py` can not delete some files in `GenshinImpact_Data\Persistent` because they are marked read-only.
- **Delete** `GenshinImpact_Data\Persistent`, optionally `GenshinImpact_Data\webCaches` if it's taking too much space, or game doesn't work correctly.

## Tips
- If you want minimal disk writes, use a ramdisk for temporary files, I use ImDisk Virtual Disk Driver and create a 2GB drive.
- If you need game installation on multiple machines, you can use python pyftpdlib library to create ftp server and use WinSCP to download game files from it.
    - Make sure to use optimized settings such as `Delete files`, and file difference checks such as `Modified date` and `File size`.
    - Better use `Synchronize` function and set target directory to `Local`.
    - Files deleted by WinSCP by default will be sent to Recycle Bin, so remember to clear it afterwards.
    - See demo video https://youtu.be/bp26BKjW56w
