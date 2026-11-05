"""The launchers' folder, kept working: run bits, the Windows shortcut, and
what the move from "BARRY GUI" left behind.

Standard library only, and no import of anything else in backend/, because
start.py calls this before it has checked the dependencies -- the first
thing a machine does after pulling the move is double-click Activate, and
that must work even if nothing else does yet.

Three jobs, each safe to repeat on every start:

`make_runnable()` -- macOS will not run a .command file without its execute
bit, and the bit has been lost before: "Activate Jarvis.command" went into
git without it on 2026-10-12 and stayed that way until 10-30, so every Mac
that cloned in between needed a `chmod +x` by hand. git carries the bit now,
but a copy unzipped from GitHub, or a checkout with `core.fileMode` off, can
still drop it. Put back on every start and every setup, so a launcher that
has run once keeps working.

`make_shortcut()` -- "Activate Jarvis.lnk", the launcher with the icon. It
used to be tracked, which cannot work: a shortcut holds absolute paths, so
the committed one pointed at whichever machine saved it last (it read
C:\\Users\\Z390\\OneDrive\\...\\Activate Jarvis.bat on a machine that has no
such folder). Each Windows machine now makes its own, ignored by git.

`leftovers()` -- git moves what it tracks. When a machine pulls the move to
_Jarvis/app, everything git does NOT carry stays behind in the old
"BARRY GUI" folder: the Supabase key (GUI_logs/.cloud.json), the VACC
sign-in (.vacc.json), VACC runs in flight, caches, results not yet
committed. Those are moved across here, never over a file that already
exists, and the old folder is removed only once nothing is left in it. A
file on both sides is removed from the old folder only when the two are
byte-identical; otherwise both are kept and listed, newer-than-in-use
ones loudly (see `_carry`).
"""
from __future__ import annotations

import filecmp
import os
import shutil
import stat
import subprocess

from .paths import APP_DIR, HOME_DIR, REPO_ROOT, OLD_APP_DIRS

LAUNCHERS = ("Activate Jarvis.command", "Setup Mac.command")

# Never worth carrying: rebuilt on import, and a stale one from another
# Python is exactly what should not follow the code.
_SKIP = {"__pycache__"}

# Left in an old folder that could not be emptied, saying why. Not carried.
NOTE = "MOVED TO _Jarvis.txt"


def make_runnable():
    """Give the Mac launchers their execute bit back. Returns the names
    that needed it."""
    if os.name == "nt":
        return []
    fixed = []
    for name in LAUNCHERS:
        path = os.path.join(HOME_DIR, name)
        try:
            mode = os.stat(path).st_mode
        except OSError:
            continue
        want = mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        if want != mode:
            try:
                os.chmod(path, want)
                fixed.append(name)
            except OSError:
                pass
    return fixed


def make_shortcut():
    """Make (or repair) this machine's "Activate Jarvis.lnk" beside the
    .bat, with the app's icon. Windows only; quiet on any failure, since
    the .bat beside it does the same job without the icon."""
    if os.name != "nt":
        return False
    lnk = os.path.join(HOME_DIR, "Activate Jarvis.lnk")
    bat = os.path.join(HOME_DIR, "Activate Jarvis.bat")
    ico = os.path.join(APP_DIR, "web", "img", "jarvis.ico")
    if not os.path.isfile(bat):
        return False
    q = lambda s: "'" + s.replace("'", "''") + "'"  # noqa: E731
    script = (
        "$w = New-Object -ComObject WScript.Shell; "
        "$s = $w.CreateShortcut(%s); "
        "if ($s.TargetPath -ieq %s -and $s.IconLocation -like (%s + '*')) { exit 3 }; "
        "$s.TargetPath = %s; $s.WorkingDirectory = %s; "
        "if (Test-Path %s) { $s.IconLocation = %s + ',0' }; "
        "$s.Description = 'Start the workbench'; $s.Save()"
        % (q(lnk), q(bat), q(ico), q(bat), q(HOME_DIR), q(ico), q(ico)))
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0


def _same_file(a, b):
    """Byte-for-byte the same? filecmp checks the sizes first, so two files
    that differ in length cost nothing to tell apart. Any trouble reading
    is "not the same", which keeps both."""
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _carry(src, dst, moved, kept, newer=None, same=None):
    """Move src to dst unless something is already there; into folders that
    exist on both sides, one entry at a time.

    A file on both sides is never decided by which side it is on. The old
    folder can hold the NEWER copy: a server still running from "BARRY GUI"
    when the move was pulled (the app is often left open while GitHub
    Desktop pulls) keeps writing its shards -- curation, sessions, the bank
    -- to absolute paths in the old folder, while git has already put the
    older tracked copy in the new one. So: identical copies are one copy,
    and the old one is removed; different copies are BOTH kept, the old one
    left where it is and listed, and flagged in `newer` when it was written
    after the one in use, so start-up can say so loudly instead of anyone
    deleting the folder on the strength of a note."""
    if os.path.basename(src) in _SKIP:
        return
    if not os.path.lexists(dst):
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved.append(dst)
        except OSError:
            kept.append(src)
        return
    if os.path.isdir(src) and os.path.isdir(dst) and not os.path.islink(src):
        for name in os.listdir(src):
            _carry(os.path.join(src, name), os.path.join(dst, name),
                   moved, kept, newer, same)
        return
    plain = (os.path.isfile(src) and os.path.isfile(dst)
             and not os.path.islink(src) and not os.path.islink(dst))
    if plain and _same_file(src, dst):
        try:
            os.remove(src)
            if same is not None:
                same.append(src)
            return
        except OSError:
            pass                # held open: listed below like any other
    kept.append(src)
    if plain and newer is not None:
        try:
            if os.path.getmtime(src) > os.path.getmtime(dst):
                newer.append(src)
        except OSError:
            pass


def _prune(folder):
    """Remove folders left empty (and caches) from the bottom up. True when
    `folder` itself is gone."""
    if not os.path.isdir(folder):
        return True
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        if name in _SKIP:
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.isdir(p) and not os.path.islink(p):
            _prune(p)
    try:
        os.rmdir(folder)
        return True
    except OSError:
        return False


def leftovers():
    """Carry what the old app folder still holds into this one.

    Returns {"from": path, "moved": n, "same": n, "kept": [paths],
    "newer": [paths], "gone": bool} or None when there is no old folder.
    `kept` is what stays where it was: a file that differs from the one of
    the same name already here, or one another program held open. Neither
    side wins a difference by being newer or older -- both are kept, and the
    app goes on using the copy in the new folder. `newer` is the part of
    `kept` that was written AFTER the copy in use, which is the case that
    can lose work (see `_carry`), and start-up says so out loud. `same` is
    how many old copies were byte-identical to the new ones and removed.
    """
    for old in OLD_APP_DIRS:
        src = os.path.join(REPO_ROOT, old)
        if not os.path.isdir(src) or os.path.normcase(src) == os.path.normcase(APP_DIR):
            continue
        moved, kept, newer, same = [], [], [], []
        for name in os.listdir(src):
            if name == NOTE:
                continue
            _carry(os.path.join(src, name), os.path.join(APP_DIR, name),
                   moved, kept, newer, same)
        gone = _prune(src)
        if not gone:
            _write_note(src, kept, newer)
        return {"from": src, "moved": len(moved), "same": len(same),
                "kept": kept, "newer": newer, "gone": gone}
    return None


def _write_note(src, kept, newer):
    """The note left in an old folder that could not be emptied.

    It must never read as "safe to delete": a kept file may be the only
    copy of someone's latest curation. So it names, file by file, which old
    copies are newer than the ones in use, says where the one in use is,
    and asks for each to be checked first. Rewritten on every start, so it
    always matches what is actually still here."""
    rel = lambda p: os.path.relpath(p, src)          # noqa: E731
    is_newer = set(newer)
    older = [k for k in kept if k not in is_newer]
    new_home = os.path.relpath(APP_DIR, REPO_ROOT)
    parts = [
        "This folder moved to _Jarvis (the launchers) and %s (everything "
        "else). Everything that could be carried across has been.\n\n"
        "What is still here was NOT moved, because a different file of the "
        "same name was already in the new folder, or another program had it "
        "open. Nothing was overwritten: both copies are kept, and the app "
        "now uses the one in the new folder, at the same place inside it.\n\n"
        "Do not delete this folder until every file below has been checked. "
        "If the old app was still running from here when the move was "
        "pulled, these can hold work done after the move: close it, compare "
        "each file with its partner in the new folder, and keep the right "
        "one there before removing anything here.\n" % new_home]
    if newer:
        parts.append(
            "\nNEWER than the copy now in use (check these first -- they "
            "were written after the copy the app is using):\n"
            + "\n".join("  " + rel(k) for k in newer) + "\n")
    if older:
        parts.append(
            "\nDifferent from the copy now in use, or held open by another "
            "program:\n" + "\n".join("  " + rel(k) for k in older) + "\n")
    try:
        with open(os.path.join(src, NOTE), "w", encoding="utf-8") as fh:
            fh.write("".join(parts))
    except OSError:
        pass
