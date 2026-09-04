"""
feedback.py -- bug reports, feature requests and suggestions, with pictures.

Why here rather than an issue tracker
-------------------------------------
The thing you want to report is almost always something you just saw on
screen, and the useful half of it is the screen. By the time you have
switched to a browser, found the repo, opened a new issue and described the
pane layout in words, either the detail is gone or you have decided it was
not worth reporting. Most of what a lab actually notices is lost that way.

So it is a form in the app, next to the errors, and it takes screenshots.

Storage follows the same rule as everything else here: one file per report,
named by id, sharded by machine, so two people filing on two computers never
touch the same file and a pull never conflicts. Attachments sit beside them
in a folder of their own.
"""
from __future__ import annotations

import base64
import io
import os
import re
import time

from . import shards

KINDS = {
    "bug": "Something is broken",
    "feature": "Something is missing",
    "improvement": "Something could be better",
}

STATES = ("open", "planned", "done", "declined")

# Attachments are screenshots. A PNG of a 4K screen is about 4 MB; ten of
# those in one report is more than anybody needs and enough to notice in a
# repository, so both ends are capped.
MAX_SHOT_BYTES = 8 * 1024 * 1024
MAX_SHOTS = 8

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) \
        + time.strftime("%z")


class Feedback:
    """Reports on disk, one file each, sharded by machine."""

    def __init__(self, root):
        self.root = root
        self.dir = os.path.join(root, "feedback")
        self.shots = os.path.join(self.dir, "screenshots")
        os.makedirs(self.shots, exist_ok=True)
        self.machine = shards.machine_id()

    # -- paths ----------------------------------------------------------
    def _file(self, rec_id):
        return os.path.join(self.dir, "%s@%s.json" % (rec_id, self.machine))

    def _all_files(self):
        out = []
        for name in sorted(os.listdir(self.dir)):
            if name.endswith(".json"):
                out.append(os.path.join(self.dir, name))
        return out

    # -- reading --------------------------------------------------------
    def all(self):
        import json
        out = []
        for path in self._all_files():
            try:
                with io.open(path, encoding="utf-8") as fh:
                    rec = json.load(fh)
                rec["_file"] = os.path.basename(path)
                out.append(rec)
            except Exception:                        # noqa: BLE001
                # A half-written or hand-edited file should not take the
                # whole list down with it.
                continue
        out.sort(key=lambda r: r.get("at") or "", reverse=True)
        return out

    def get(self, rec_id):
        for rec in self.all():
            if rec.get("id") == rec_id:
                return rec
        return None

    # -- writing --------------------------------------------------------
    def add(self, body, user=None):
        import json
        import uuid

        kind = str(body.get("kind") or "bug")
        if kind not in KINDS:
            raise ValueError("Unknown kind %r." % kind)
        title = (body.get("title") or "").strip()
        if not title:
            raise ValueError("A report needs a one-line summary.")

        rec_id = "f" + uuid.uuid4().hex[:11]
        shots = self._save_shots(rec_id, body.get("screenshots") or [])

        rec = {
            "id": rec_id,
            "kind": kind,
            "title": title[:300],
            "detail": (body.get("detail") or "").strip(),
            # Where they were and what was on screen. Volunteered by the
            # client because the server has no idea which view is up.
            "context": body.get("context") or {},
            "wants": (body.get("wants") or "").strip(),
            "state": "open",
            "at": _now(),
            "by": user or body.get("by") or "",
            "machine": os.environ.get("COMPUTERNAME") or "",
            "shard": self.machine,
            "screenshots": shots,
            "notes": [],
        }
        os.makedirs(self.dir, exist_ok=True)
        with io.open(self._file(rec_id), "w", encoding="utf-8",
                     newline="\n") as fh:
            json.dump(rec, fh, indent=1, ensure_ascii=False)
        return rec

    def _save_shots(self, rec_id, items):
        """Write data-URI screenshots out as files, return their names."""
        out = []
        for i, item in enumerate(items[:MAX_SHOTS]):
            uri = item if isinstance(item, str) else (item or {}).get("data")
            if not uri or "," not in uri:
                continue
            head, b64 = uri.split(",", 1)
            ext = "png"
            if "jpeg" in head or "jpg" in head:
                ext = "jpg"
            try:
                raw = base64.b64decode(b64)
            except Exception:                        # noqa: BLE001
                continue
            if not raw or len(raw) > MAX_SHOT_BYTES:
                continue
            name = "%s-%d.%s" % (rec_id, i + 1, ext)
            with io.open(os.path.join(self.shots, name), "wb") as fh:
                fh.write(raw)
            out.append({"file": name, "bytes": len(raw),
                        "caption": (isinstance(item, dict)
                                    and (item.get("caption") or "") or "")})
        return out

    def update(self, rec_id, patch, user=None):
        import json
        rec = self.get(rec_id)
        if not rec:
            raise ValueError("No such report.")
        # Only the machine that filed it owns the file; anyone else's change
        # would land in a different shard and the two would both be right.
        # So edits are notes, which merge, plus a state that is last-write.
        if "state" in patch:
            state = str(patch["state"])
            if state not in STATES:
                raise ValueError("Unknown state %r." % state)
            rec["state"] = state
        if patch.get("note"):
            rec.setdefault("notes", []).append({
                "at": _now(), "by": user or "", "text": str(patch["note"])[:2000],
            })
        rec.pop("_file", None)
        path = os.path.join(self.dir, "%s@%s.json" % (rec_id, rec.get("shard")
                                                      or self.machine))
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=1, ensure_ascii=False)
        return rec

    def shot_path(self, name):
        """Resolve an attachment name, refusing anything that escapes."""
        safe = _SAFE.sub("", os.path.basename(name or ""))
        if not safe:
            return None
        path = os.path.join(self.shots, safe)
        if not os.path.isfile(path):
            return None
        return path

    def counts(self):
        out = {"open": 0, "total": 0}
        for rec in self.all():
            out["total"] += 1
            st = rec.get("state") or "open"
            out[st] = out.get(st, 0) + 1
        return out
