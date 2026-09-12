"""
notes.py -- the version, and what changed in it.

There is one place the version is written: the newest heading in
CHANGELOG.md. Not a constant in the code as well, because two sources of the
same fact drift -- and the one that drifts is always the one nobody thought
to update.

Versions are dated rather than numbered. Jarvis ships continuously out of the
repo: there is no release to number, only the state everybody last pulled.
So "2026.09.08" says something useful on its own, and the commit beside it
says what this machine is actually running -- which is the question when a
colleague reports something you cannot reproduce.

The parser is deliberately small. It reads `## <version> — <title>`,
`### <section>` and `- item`, and anything it does not recognise is passed
through as prose rather than dropped, so the notes cannot be silently
truncated by writing them slightly differently.
"""
from __future__ import annotations

import os
import re
import subprocess

HEAD = re.compile(r"^##\s+(?P<version>[^\s—-]+)\s*[—-]*\s*(?P<title>.*)$")
SECTION = re.compile(r"^###\s+(?P<name>.+?)\s*$")
ITEM = re.compile(r"^[-*]\s+(?P<text>.+)$")


def _strip_md(text):
    """Bold and code marks out. The viewer renders text, not markdown."""
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    out = re.sub(r"`(.+?)`", r"\1", out)
    return out.strip()


def parse(text):
    """CHANGELOG.md as a list of releases, newest first.

    Markdown wraps, so a bullet is however many lines it takes. `in_item`
    tracks whether the last thing seen was a bullet: a non-blank line after
    one continues it, and a blank line ends it. Without that, the second
    line of every wrapped bullet became a paragraph of its own and the notes
    read as fragments.
    """
    entries = []
    preamble = []
    cur = None
    section = None
    in_item = False
    in_prose = False

    def open_section(name):
        got = {"name": name, "items": [], "prose": []}
        cur["sections"].append(got)
        return got

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.startswith("# ") or line.strip() == "---":
            continue
        if not line.strip():
            # A blank line ends both a bullet and a paragraph. It is the
            # only thing in markdown that does.
            in_item = False
            in_prose = False
            continue

        m = HEAD.match(line)
        if m:
            cur = {"version": m.group("version").strip(),
                   "title": _strip_md(m.group("title")),
                   "sections": []}
            entries.append(cur)
            section = None
            in_item = False
            in_prose = False
            continue

        if cur is None:
            preamble.append(line.strip())
            continue

        m = SECTION.match(line)
        if m:
            section = open_section(_strip_md(m.group("name")))
            in_item = False
            in_prose = False
            continue

        if section is None:
            section = open_section(None)

        m = ITEM.match(line.strip())
        if m:
            section["items"].append(_strip_md(m.group("text")))
            in_item = True
            in_prose = False
            continue

        if in_item and section["items"]:
            section["items"][-1] += " " + _strip_md(line.strip())
        elif in_prose and section["prose"]:
            # A paragraph is however many lines it is wrapped over. One <p>
            # per source line turned every paragraph into a stack of
            # fragments a few words wide.
            section["prose"][-1] += " " + _strip_md(line.strip())
        else:
            section["prose"].append(_strip_md(line.strip()))
            in_prose = True

    # A section that ended up with nothing in it is an artefact of the
    # markdown, not a section.
    for e in entries:
        e["sections"] = [x for x in e["sections"]
                         if x["items"] or x["prose"]]
    return {"preamble": " ".join(preamble), "entries": entries}


def commit(root):
    """The commit this machine is running, if the repo can say.

    Short hash plus whether the tree is dirty, because "running 8966435 with
    local changes" and "running 8966435" are different answers to "why does
    it behave differently for me".
    """
    def git(*args):
        try:
            res = subprocess.run(["git"] + list(args), cwd=root,
                                 capture_output=True, text=True, timeout=10)
        except Exception:                            # noqa: BLE001
            return None
        if res.returncode != 0:
            return None
        return (res.stdout or "").strip()

    short = git("rev-parse", "--short", "HEAD")
    if not short:
        return None
    when = git("log", "-1", "--format=%cI")
    dirty = git("status", "--porcelain")
    return {"commit": short, "at": when or None,
            "dirty": bool(dirty), "branch": git("rev-parse",
                                                "--abbrev-ref", "HEAD")}


class Notes:
    def __init__(self, app_dir, repo_root=None):
        self.path = os.path.join(app_dir, "CHANGELOG.md")
        self.repo_root = repo_root or app_dir
        self._cache = None
        self._stamp = None

    def read(self):
        """The notes, re-read when the file changes and not otherwise."""
        try:
            stamp = os.stat(self.path).st_mtime_ns
        except OSError:
            return {"ok": False, "version": None, "entries": [],
                    "error": "No CHANGELOG.md beside the app, so there are "
                             "no patch notes to show."}
        if self._cache is not None and stamp == self._stamp:
            return self._cache

        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                got = parse(fh.read())
        except OSError as exc:
            return {"ok": False, "version": None, "entries": [],
                    "error": "Could not read CHANGELOG.md: %s" % exc}

        entries = got["entries"]
        out = {
            "ok": True,
            # The newest heading IS the version. One source, so it cannot
            # disagree with itself.
            "version": entries[0]["version"] if entries else None,
            "preamble": got["preamble"],
            "entries": entries,
            "running": commit(self.repo_root),
        }
        self._cache = out
        self._stamp = stamp
        return out
