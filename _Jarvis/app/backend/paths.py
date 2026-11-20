"""Where things are: the app folder, the repo it sits in, the logs.

One place, because the answer changed. Until 2026-11-03 the app was
"BARRY GUI" at the top of the lab's repo, and everything that needed the
repo wrote `os.path.join(APP_DIR, "..")`. Then the folder became
`_Jarvis/app` -- the four launchers in `_Jarvis/`, everything else one
level down -- and every one of those joins pointed at `_Jarvis` instead of
the repo. Asking here instead of counting levels is what lets the next move
happen without hunting them down again.

Importing this module has no side effects and needs nothing beyond the
standard library, so start.py and setup.py can use it before the
dependencies have been checked.
"""
import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(APP_DIR, "GUI_logs")
WEB_DIR = os.path.join(APP_DIR, "web")

# The launchers' folder. `_Jarvis/` holds only Setup and Activate; the app
# is the one folder beside them.
HOME_DIR = os.path.dirname(APP_DIR)

# Every name the app folder has had, newest first. The registry must not
# index any of them as somebody's analysis code, and a machine that pulled
# the move still has the old one beside the new, holding the files git does
# not carry (start.py moves them across: `leftovers`).
OLD_APP_DIRS = ("BARRY GUI",)


def _repo_root(start):
    """The nearest folder above `start` that holds a .git, which is the lab's
    repo. Without one (a copy unzipped from GitHub), the folder above the
    launchers', which is where the repo would have been."""
    d = start
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    if os.path.basename(HOME_DIR).lower() == "_jarvis":
        return os.path.dirname(HOME_DIR)
    return HOME_DIR


REPO_ROOT = _repo_root(APP_DIR)

# How the app folder is spelled from the repo root, for the git commands
# and messages that name it ("_Jarvis/app/GUI_logs").
APP_REL = os.path.relpath(APP_DIR, REPO_ROOT).replace("\\", "/")
