"""
conflicts.py -- Can a file in GUI_logs produce a git merge conflict?

A conflict needs a file git tracks and two machines that both change it.
Take either away and it cannot happen, so every file under GUI_logs has to
be one of:

    per-machine   the name carries a machine tag, so only that machine
                  writes it: `<base>@<machine>.json` (shards) or a feedback
                  overlay, `<id>~<machine>.json`
    write-once    created once and never edited (shards.WRITE_ONCE)
    untracked     derived, and git ignores it
    inert         documentation no code writes

Anything else is SHARED: a latent conflict, named so somebody fixes it
before the first bad pull finds it.

One classification for both places that ask -- the Sync panel
(app.conflict_audit) and tools/conflict_check.py. They were two copies, and
the panel's had never learned about feedback overlays, so it reported seven
of them as conflicts while the command line said, correctly, that nothing
here could conflict.
"""
from __future__ import annotations

import os
import subprocess

from . import feedback, shards

INERT = ("README.md", ".gitignore")


def classify(rel, name):
    """(kind, why) for one file, by `rel` (its path under GUI_logs, with /)
    and `name`. Does not ask git: SHARED means "would conflict if tracked"."""
    if rel.startswith(shards.WRITE_ONCE):
        return "write-once", "written once and never edited"
    if name in INERT:
        return "inert", "documentation"
    stem = name.rsplit(".", 1)[0]
    if shards.SIGIL in stem:
        machine = stem.rsplit(shards.SIGIL, 1)[1]
        return "per-machine", "only " + machine + " writes this"
    # A feedback overlay is per-machine too. It carries a different sigil so
    # the shard layer cannot mistake it for another machine's copy of the
    # report, but the machine is in the name and only that machine writes it.
    if feedback.OVERLAY_SIGIL in stem:
        machine = stem.rsplit(feedback.OVERLAY_SIGIL, 1)[1]
        return "per-machine", "only " + machine + " writes this overlay"
    return "SHARED", "no machine tag: two people can both edit it"


def machine_of(name):
    """The machine a per-machine file belongs to, or None."""
    stem = name.rsplit(".", 1)[0]
    for sigil in (shards.SIGIL, feedback.OVERLAY_SIGIL):
        if sigil in stem:
            return stem.rsplit(sigil, 1)[1]
    return None


def tracked(repo, path, git="git"):
    """Is git watching this file? Untracked files cannot conflict. When git
    cannot be asked, assume it is: the cautious answer for a conflict check."""
    try:
        res = subprocess.run([git, "check-ignore", "-q", path],
                             cwd=repo, capture_output=True, timeout=10)
        return res.returncode != 0
    except Exception:                                    # noqa: BLE001
        return True


def walk(root):
    """(full path, rel, name) for every record under `root`. Skips the
    cache, dot-folders and dotfiles (configuration such as .cloud.json,
    which is gitignored and holds this machine's key)."""
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in (".cache", "__pycache__")
                   and not d.startswith(".")]
        for name in sorted(files):
            if name.startswith("."):
                continue
            full = os.path.join(folder, name)
            yield full, os.path.relpath(full, root).replace("\\", "/"), name


def audit(root, git="git", limit=12):
    """The whole of GUI_logs, classified. `shared` lists at most `limit`
    files that could conflict; git is asked only about those, so a clean
    store costs no subprocess at all."""
    root = os.path.abspath(root)
    repo = os.path.dirname(root)
    kinds, shared, machines, n = {}, [], set(), 0
    for full, rel, name in walk(root):
        n += 1
        kind, _why = classify(rel, name)
        if kind == "SHARED":
            if not tracked(repo, full, git):
                kind = "untracked"
            elif len(shared) < limit:
                shared.append(rel)
        else:
            m = machine_of(name)
            if m:
                machines.add(m)
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "ok": not kinds.get("SHARED"),
        "files": n,
        "kinds": kinds,
        "shared": shared,
        "n_shared": kinds.get("SHARED", 0),
        "machines": sorted(machines),
        "mine": shards.machine_id(),
    }
