"""
mice.py -- What is true about an animal, as opposed to a recording.

A session record answers "what happened in this recording". It is the wrong
place for genotype, cohort or sex, because those belong to the mouse and
repeating them on every one of its recordings means eleven chances to disagree
with yourself.

So: one record per mouse, holding free-form attributes.

Free-form on purpose. A fixed set of columns is a guess about what the lab
will want to record, and it is always wrong within a month -- someone needs
"implant date", someone else needs "virus batch". Attributes are whatever you
name them, and the housekeeping view can group the tree by any of them, so
"show me the tree by genotype" costs nothing to add.

Some names are known, only so they are offered first and spelled the same way
by everyone. Nothing stops a new one.

One file per mouse, so two people editing two animals never touch the same
file.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import shards

SCHEMA = 1

# Offered in the UI, and given a consistent spelling. Not a limit: any
# attribute name is allowed, and unknown ones behave identically.
SUGGESTED = [
    {"id": "group", "name": "Group", "note": "PTEN, CTL, ...",
     "common": ["PTEN", "CTL", "KCNT1", "WT"]},
    {"id": "subgroup", "name": "Subgroup", "note": "IED+, IED-, ...",
     "common": ["IED+", "IED-", "CTL"]},
    {"id": "genotype", "name": "Genotype", "note": "", "common": []},
    {"id": "sex", "name": "Sex", "note": "", "common": ["M", "F"]},
    {"id": "dob", "name": "Date of birth", "note": "", "common": []},
    {"id": "implant", "name": "Implant", "note": "probe and date",
     "common": []},
    {"id": "virus", "name": "Virus", "note": "", "common": []},
    {"id": "status", "name": "Status", "note": "",
     "common": ["active", "done", "excluded"]},
]

SUGGESTED_IDS = {a["id"] for a in SUGGESTED}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(text)).strip("-") or "x"


def attr_key(name):
    """A stable key for an attribute name, so "Group" and "group" are one."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


class MouseBook:
    def __init__(self, logs_dir, store):
        self.dir = os.path.join(logs_dir, "mice")
        self.store = store
        os.makedirs(self.dir, exist_ok=True)
        # Attributes merge one at a time, so whoever fills in the genotype
        # and whoever fills in the implant date do not have to take turns.
        self.book = shards.Book(self.dir, {
            "attrs": shards.MAPLWW,
            "created": shards.FIRST,
        }, store)
        self.book.absorb_legacy()

    def base(self, project, mouse):
        return shards.safe_base(_slug(project or "unfiled"),
                                "m" + _slug(mouse))

    def path(self, project, mouse):
        return self.book.mine(self.base(project, mouse))

    def get(self, project, mouse):
        return self.book.read(self.base(project, mouse))

    def all(self):
        return self.book.all()

    def _write(self, rec):
        rec["updated"] = self.store.provenance() if self.store else {"at": _now()}
        return self.book.write(self.base(rec.get("project"),
                                         rec.get("mouse")), rec)

    @shards.atomic
    def set(self, project, mouse, attrs, note=None, replace=False):
        """Attach attributes to a mouse. Merges unless `replace`.

        A value of None or "" removes the attribute, so a mistake can be taken
        back rather than only overwritten.
        """
        rec = self.get(project, mouse) or {
            "schema": SCHEMA,
            "project": project,
            "mouse": mouse,
            "attrs": {},
            "created": self.store.provenance() if self.store else {"at": _now()},
        }
        if replace:
            rec["attrs"] = {}
        for k, v in (attrs or {}).items():
            key = attr_key(k)
            if not key:
                continue
            if v is None or (isinstance(v, str) and not v.strip()):
                rec["attrs"].pop(key, None)
            else:
                rec["attrs"][key] = v.strip() if isinstance(v, str) else v
        if note is not None:
            rec["note"] = note
        return self._write(rec)

    def delete(self, project, mouse):
        return bool(self.book.erase(self.base(project, mouse)))

    # ------------------------------------------------------------------
    def index(self):
        """project -> mouse -> attrs, for decorating the session tree."""
        out = {}
        for rec in self.all():
            out.setdefault(str(rec.get("project")), {})[
                str(rec.get("mouse"))] = rec
        return out

    def attributes(self):
        """Every attribute name in use, with the values seen for each.

        This is what makes "group the tree by genotype" possible without
        anyone declaring a schema: the names come from what has been filled
        in, and the values come with them so the view can offer a picker.
        """
        seen = {}
        for rec in self.all():
            for k, v in (rec.get("attrs") or {}).items():
                slot = seen.setdefault(k, {"id": k, "values": {}, "n": 0})
                slot["n"] += 1
                key = str(v)
                slot["values"][key] = slot["values"].get(key, 0) + 1
        out = []
        for a in SUGGESTED:
            hit = seen.pop(a["id"], None)
            out.append({
                "id": a["id"], "name": a["name"], "note": a["note"],
                "suggested": True,
                "n": (hit or {}).get("n", 0),
                "values": sorted((hit or {}).get("values", {}).items(),
                                 key=lambda kv: -kv[1]),
                "common": a["common"],
            })
        for k in sorted(seen):
            out.append({
                "id": k, "name": k.replace("_", " ").title(), "note": "",
                "suggested": False, "n": seen[k]["n"],
                "values": sorted(seen[k]["values"].items(),
                                 key=lambda kv: -kv[1]),
                "common": [],
            })
        return out
