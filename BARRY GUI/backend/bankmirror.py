"""
bankmirror.py -- The Event Bank, as folders you can open.

The bank lives in GUI_logs as one JSON file per entry, named for git's
benefit rather than a person's. That is the right shape for a record and the
wrong shape for finding the dentate spikes for m34 s8 when you are not in
BARRY -- which is most of the time, for most people.

So this writes the same content out again, laid out the way the Event Bank
view groups it:

    Data Bank/
      PTEN/
        m34/
          s8 2024-06-10/
            ds - DS candidates (ETS).csv       one time per line
            ds - DS candidates (ETS).json      everything else about it
        _mouse.json                            what is true about the animal
      _index.csv                               every entry, one row each

Derived, and deterministic: every machine generating it from the same records
produces byte-identical files, so it is safe to commit and cannot conflict.
Delete the whole tree and the next sync rebuilds it.

The CSV is the point. It opens in Excel, it goes into MATLAB in one line, and
it does not need anything of BARRY's to read.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re

FOLDER = "Data Bank"
README = """# Data Bank

Written by BARRY, from the Event Bank. Open anything here in Excel or MATLAB;
nothing needs BARRY to read it.

    <Project>/m<mouse>/s<session> <date>/<type> - <name>.csv     the times
    <Project>/m<mouse>/s<session> <date>/<type> - <name>.json    everything else
    <Project>/m<mouse>/_mouse.json                               the animal
    _index.csv                                                   all of it

`specified` is the column that matters. False means a detector proposed these
times and nobody has been through them yet; true means somebody has, and the
label says what they called it. They are different claims and the bank does
not blur them.

This folder is generated. Edit it and the next sync writes over you -- change
things in BARRY, or in the database, and they land here.
"""


def _safe(text, fallback="x"):
    """A path segment that Windows, macOS and git all accept."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", str(text or "")).strip(" .")
    s = re.sub(r"\s+", " ", s)
    return (s or fallback)[:80]


def _entry_dir(root, entry):
    project = _safe(entry.get("project") or "Unfiled", "Unfiled")
    mouse = entry.get("mouse")
    mdir = "m%s" % mouse if mouse is not None else "m unknown"
    sess = entry.get("session")
    date = (entry.get("recording_start") or "")[:10]
    sdir = "s%s" % sess if sess is not None else "s unknown"
    if date:
        sdir += " " + date
    return os.path.join(root, project, _safe(mdir), _safe(sdir))


def _entry_stem(entry):
    return _safe("%s - %s" % (entry.get("type") or "event",
                              entry.get("name") or entry.get("id")))


def _write_if_changed(path, text):
    """Only touch a file whose content actually differs.

    Rewriting an identical file every two minutes would make `git status`
    permanently dirty and every sync look like a change.
    """
    data = text.encode("utf-8")
    try:
        with open(path, "rb") as fh:
            if fh.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    return True


def _csv(rows, header):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


class BankMirror:
    def __init__(self, repo_dir, bank, mice=None, store=None):
        # Sits beside Results, not inside GUI_logs: this is for people, and
        # GUI_logs is for the machine.
        self.root = os.path.join(repo_dir, FOLDER)
        self.bank = bank
        self.mice = mice
        self.store = store

    # ------------------------------------------------------------------
    def rebuild(self, prune=True):
        """Write the tree. Returns what changed."""
        os.makedirs(self.root, exist_ok=True)
        written, wanted = 0, set()

        if _write_if_changed(os.path.join(self.root, "README.md"), README):
            written += 1
        wanted.add(os.path.join(self.root, "README.md"))

        index = []
        for entry in sorted(self.bank.all(),
                            key=lambda e: (str(e.get("project") or ""),
                                           e.get("mouse") or 0,
                                           e.get("session") or 0,
                                           str(e.get("id")))):
            folder = _entry_dir(self.root, entry)
            stem = _entry_stem(entry)
            events = entry.get("events") or []

            # ---- the times ------------------------------------------
            rows = []
            for ev in events:
                rows.append([
                    _fmt(ev.get("start")), _fmt(ev.get("end")),
                    ev.get("channel") if ev.get("channel") is not None else "",
                    _fmt(ev.get("amplitude")),
                    ev.get("label") or "",
                ])
            csv_path = os.path.join(folder, stem + ".csv")
            if _write_if_changed(csv_path, _csv(
                    rows, ["start_s", "end_s", "channel", "amplitude",
                           "label"])):
                written += 1
            wanted.add(csv_path)

            # ---- everything else ------------------------------------
            meta = {k: v for k, v in entry.items()
                    if k not in ("events", "_sync", "path")}
            meta["n_events"] = len(events)
            meta["times_file"] = os.path.basename(csv_path)
            json_path = os.path.join(folder, stem + ".json")
            if _write_if_changed(json_path, json.dumps(
                    meta, indent=2, sort_keys=True, default=str) + "\n"):
                written += 1
            wanted.add(json_path)

            index.append([
                entry.get("project"), entry.get("mouse"), entry.get("session"),
                (entry.get("recording_start") or "")[:10],
                entry.get("type"), entry.get("name"), len(events),
                "yes" if entry.get("specified") else "no",
                entry.get("curation_label") or "",
                (entry.get("source") or {}).get("pipeline") or "",
                (entry.get("added") or {}).get("by") or "",
                (entry.get("added") or {}).get("at") or "",
                entry.get("gid") or "", entry.get("id"),
                os.path.relpath(csv_path, self.root).replace("\\", "/"),
            ])

        # ---- the mice -------------------------------------------------
        for rec in (self.mice.all() if self.mice else []):
            if rec.get("mouse") is None:
                continue
            path = os.path.join(self.root, _safe(rec.get("project")
                                                 or "Unfiled", "Unfiled"),
                                _safe("m%s" % rec["mouse"]), "_mouse.json")
            body = {k: v for k, v in rec.items() if not k.startswith("_")}
            if _write_if_changed(path, json.dumps(
                    body, indent=2, sort_keys=True, default=str) + "\n"):
                written += 1
            wanted.add(path)

        # ---- the index ------------------------------------------------
        idx = os.path.join(self.root, "_index.csv")
        if _write_if_changed(idx, _csv(index, [
                "project", "mouse", "session", "date", "type", "name",
                "n_events", "specified", "curation_label", "pipeline",
                "added_by", "added_at", "gid", "entry_id", "times_file"])):
            written += 1
        wanted.add(idx)

        removed = self._prune(wanted) if prune else 0
        return {"written": written, "removed": removed,
                "entries": len(index), "root": self.root}

    def _prune(self, wanted):
        """Take away what the bank no longer has.

        Without this, deleting an entry in BARRY leaves its CSV sitting in a
        folder looking exactly as authoritative as the real ones.
        """
        removed = 0
        for folder, dirs, files in os.walk(self.root, topdown=False):
            for name in files:
                full = os.path.join(folder, name)
                if full in wanted or name.endswith(".tmp"):
                    continue
                try:
                    os.remove(full)
                    removed += 1
                except OSError:
                    pass
            try:
                if folder != self.root and not os.listdir(folder):
                    os.rmdir(folder)
            except OSError:
                pass
        return removed


def _fmt(v):
    """Times as plain decimals: 315.275, not 3.15275e+02."""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:
        return ""
    return ("%.6f" % f).rstrip("0").rstrip(".") or "0"
