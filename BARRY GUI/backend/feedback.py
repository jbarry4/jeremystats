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
        """Every report, with everybody's triage merged in.

        A report is filed once, by one machine, into that machine's file --
        and then anybody may set its state or add a note. Those arrive as
        overlays in the shard of whoever made them, so the reading is: take
        the report as filed, then apply every overlay anybody has written
        for it. Newest state wins; notes are the union, oldest first.
        """
        import json
        base, overlays = {}, {}
        for path in self._all_files():
            try:
                with io.open(path, encoding="utf-8") as fh:
                    rec = json.load(fh)
            except Exception:                        # noqa: BLE001
                # A half-written or hand-edited file should not take the
                # whole list down with it.
                continue
            rid = rec.get("id")
            if not rid:
                continue
            if rec.get("_overlay"):
                overlays.setdefault(rid, []).append(rec)
                continue
            rec["_file"] = os.path.basename(path)
            # Two machines can only hold the same report as filed if
            # somebody copied a file by hand. The earlier one is the
            # original.
            if rid not in base or (rec.get("at") or "") < (
                    base[rid].get("at") or ""):
                base[rid] = rec

        out = []
        for rid, rec in base.items():
            rows = overlays.get(rid) or []
            if rows:
                rec = dict(rec)
                notes = list(rec.get("notes") or [])
                seen = {(n.get("at"), n.get("by"), n.get("text"))
                        for n in notes}
                newest = None
                for ov in rows:
                    for n in (ov.get("notes") or []):
                        key = (n.get("at"), n.get("by"), n.get("text"))
                        if key not in seen:
                            seen.add(key)
                            notes.append(n)
                    if ov.get("state") and (
                            newest is None
                            or (ov.get("state_at") or "") > (newest.get("state_at") or "")):
                        newest = ov
                notes.sort(key=lambda n: n.get("at") or "")
                rec["notes"] = notes
                if newest and (newest.get("state_at") or "") > (
                        rec.get("state_at") or ""):
                    rec["state"] = newest["state"]
                    rec["state_at"] = newest.get("state_at")
                    rec["state_by"] = newest.get("state_by")
                rec["_machines"] = sorted(
                    {rec.get("shard") or ""}
                    | {ov.get("shard") or "" for ov in rows})
            out.append(rec)
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
            # The ten minutes before the report was filed: what was clicked,
            # what failed, and what the server served. Attached by the route
            # rather than by the form, because the person filing cannot know
            # which lines matter.
            "recent": body.get("recent") or None,
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

    def _overlay_file(self, rec_id):
        return os.path.join(self.dir, "%s~%s.json" % (rec_id, self.machine))

    def update(self, rec_id, patch, user=None):
        """Set a state or add a note, in THIS machine's file only.

        It used to write `<id>@<the filer's shard>.json` -- so triaging a
        report somebody else filed edited their file, on a store whose one
        rule is that no two machines ever write the same file. That is a
        guaranteed git conflict, and the side that loses the merge has its
        triage quietly undone. The change goes in an overlay of our own
        instead, and `all()` merges them on the way out.
        """
        import json
        rec = self.get(rec_id)
        if not rec:
            raise ValueError("No such report.")

        mine = rec.get("shard") == self.machine and not rec.get("_overlay")
        path = self._file(rec_id) if mine else self._overlay_file(rec_id)

        if mine:
            out = dict(rec)
            out.pop("_file", None)
            out.pop("_machines", None)
        else:
            # Only what this machine is asserting, so the overlay cannot
            # drift into being a stale second copy of the whole report.
            out = {"id": rec_id, "_overlay": True, "shard": self.machine,
                   "of": rec.get("shard")}
            try:
                with io.open(path, encoding="utf-8") as fh:
                    out.update(json.load(fh))
            except Exception:                        # noqa: BLE001
                pass
            out["_overlay"] = True
            out["shard"] = self.machine

        if "state" in patch:
            state = str(patch["state"])
            if state not in STATES:
                raise ValueError("Unknown state %r." % state)
            out["state"] = state
            out["state_at"] = _now()
            out["state_by"] = user or ""
        if patch.get("note"):
            out.setdefault("notes", []).append({
                "at": _now(), "by": user or "",
                "text": str(patch["note"])[:2000],
            })
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)
        return self.get(rec_id)

    def absorb(self, row, notes=None):
        """Take a report, or somebody's triage of one, from the cloud.

        Two cases, and they are different on purpose:

        A report this machine has never seen is written as a report of its
        own, under the machine that filed it -- so nothing claims it was
        filed here, and the shard rule still holds.

        One it already has is left exactly as it is, except for the state and
        the notes. Those go through `update`, which writes an overlay of our
        own -- the same path as triaging it here, so absorbing somebody's
        decision cannot corrupt the file the report lives in.

        Returns True when something changed, so a pull can report a number
        that means something.
        """
        import json
        rid = (row or {}).get("id")
        if not rid:
            return False

        mine = self.get(rid)
        if not mine:
            rec = {
                "id": rid,
                "kind": row.get("kind") or "bug",
                "title": (row.get("title") or "")[:300],
                "detail": row.get("body") or "",
                "wants": row.get("wants") or "",
                "context": row.get("context") or {},
                "state": row.get("state") or "open",
                "at": row.get("created_at") or _now(),
                "by": row.get("created_by") or "",
                "machine": row.get("machine") or "",
                # Under the machine that filed it, not ours.
                "shard": row.get("machine") or "cloud",
                "screenshots": row.get("shots") or [],
                "recent": None,
                "notes": [],
                "from_cloud": True,
            }
            if row.get("state_at"):
                rec["state_at"] = row["state_at"]
                rec["state_by"] = row.get("state_by")
            path = os.path.join(self.dir, "%s@%s.json"
                                % (rid, rec["shard"]))
            os.makedirs(self.dir, exist_ok=True)
            with io.open(path, "w", encoding="utf-8", newline=chr(10)) as fh:
                json.dump(rec, fh, indent=1, ensure_ascii=False)
            return True

        # Already here. Only a newer state, and notes we do not hold, and
        # both through the overlay path.
        changed = False
        theirs = row.get("state_at") or ""
        if (row.get("state") and row["state"] != mine.get("state")
                and theirs > (mine.get("state_at") or "")):
            self.update(rid, {"state": row["state"]},
                        user=row.get("state_by") or "")
            changed = True
        have = {(n.get("at"), n.get("text")) for n in (mine.get("notes") or [])}
        for n in (notes or []):
            key = (n.get("at"), n.get("body"))
            if key in have or not n.get("body"):
                continue
            self.update(rid, {"note": n["body"]}, user=n.get("note_by") or "")
            changed = True
        return changed

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
