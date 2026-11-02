"""
figures.py -- a figure, its draft and its versions.

A figure is one recording's, and it is frozen: once a version is exported it
is never redrawn on newer data and never changed in place. Editing and
exporting again makes the next version beside it. That is what the version
tree in the builder shows, and what the walk-through compares against.

    GUI_logs/figures/<id>@<machine>.json        the record (sharded, merged)
    Results/Figures/<recording>/<title> <id> v<n>.png|svg|pdf
    Results/Figures/<recording>/.figdata/<id>.v<n>.npz
                                                what each panel plotted

The record travels by git like every other GUI_logs shard. The files are in
Results/, which git carries too; the cloud gets the catalogue row and never
the picture (cloudsync.upload_results skips Results/Figures).

Record:
    id, gid, recording, title, status (draft|exported), created, by,
    draft, draft_at, versions[], archived, legacy
Version:
    id, v, at, by, machine, app_version, commit, layout, digest, files,
    data, lineage, note, from_v, source
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import uuid

from . import shards

SCHEMA = "fig/2"
SPEC = {"versions": shards.BYID, "created": shards.FIRST}
FIG_DIR = "Figures"
DATA_DIR = ".figdata"

_LOCK = threading.RLock()


class FigureError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe(text, n=60):
    keep = re.sub(r"[^\w \-.()]+", "_", str(text or "")).strip(" ._")
    return (keep or "figure")[:n].rstrip(" ._") or "figure"


def layout_digest(layout):
    """What a version IS: its panels and page, not when it was made."""
    keep = {k: layout.get(k) for k in ("profile", "width", "height_mm",
                                        "rows", "cols", "title", "subtitle",
                                        "gap_mm", "panels", "recording",
                                        "footer")}
    raw = json.dumps(keep, sort_keys=True, default=str,
                     separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class Figures:
    def __init__(self, logs_dir, store, outputs_dir):
        self.store = store
        self.outputs_dir = outputs_dir
        self.book = shards.Book(os.path.join(logs_dir, "figures"), SPEC,
                                store)

    # -- reading ----------------------------------------------------------
    def get(self, fid):
        rec = self.book.read(fid)
        if not rec:
            raise FigureError("There is no figure %s." % fid, 404)
        return rec

    def list(self, gid=None, archived=False):
        out = []
        for rec in self.book.all():
            if gid and rec.get("gid") != gid:
                continue
            if rec.get("archived") and not archived:
                continue
            out.append(self.summary(rec))
        out.sort(key=lambda r: r.get("updated") or "", reverse=True)
        return out

    @staticmethod
    def summary(rec):
        vs = sorted(rec.get("versions") or [], key=lambda v: v.get("v") or 0)
        last = vs[-1] if vs else None
        return {
            "id": rec.get("id"), "gid": rec.get("gid"),
            "title": rec.get("title"), "status": rec.get("status"),
            "recording": rec.get("recording"),
            "archived": bool(rec.get("archived")),
            "created": rec.get("created"), "by": rec.get("by"),
            "n_versions": len(vs),
            "latest": ({k: last.get(k) for k in ("v", "at", "by", "files",
                                                  "machine", "note")}
                       if last else None),
            "draft_at": rec.get("draft_at"),
            "updated": max([rec.get("draft_at") or ""]
                           + [v.get("at") or "" for v in vs]),
            "legacy": rec.get("legacy"),
        }

    def version(self, fid, v):
        rec = self.get(fid)
        for row in rec.get("versions") or []:
            if int(row.get("v") or 0) == int(v):
                return rec, row
        raise FigureError("Figure %s has no version %s." % (fid, v), 404)

    # -- writing ----------------------------------------------------------
    def create(self, layout, prov, legacy=None, created=None,
               archived=False):
        """A new figure, as a draft holding this layout."""
        with _LOCK:
            fid = "f" + uuid.uuid4().hex[:10]
            rec = {
                "id": fid, "schema": SCHEMA,
                "gid": (layout.get("recording") or {}).get("gid"),
                "recording": _recording_of(layout),
                "title": layout.get("title") or "Figure",
                "status": "draft", "created": created or _now(),
                "by": (prov or {}).get("user"),
                "draft": _strip(layout, fid), "draft_at": _now(),
                "versions": [], "archived": bool(archived),
            }
            if legacy:
                rec["legacy"] = legacy
            return self.book.write(fid, rec)

    def save_draft(self, fid, layout):
        with _LOCK:
            rec = self.get(fid)
            _same_recording(rec, layout)
            rec["draft"] = _strip(layout, fid)
            rec["draft_at"] = _now()
            rec["title"] = layout.get("title") or rec.get("title")
            return self.book.write(fid, rec)

    def archive(self, fid, on=True):
        with _LOCK:
            rec = self.get(fid)
            rec["archived"] = bool(on)
            return self.book.write(fid, rec)

    def next_v(self, rec):
        return 1 + max([int(v.get("v") or 0)
                        for v in rec.get("versions") or []] or [0])

    def paths_for(self, rec, v, title):
        """Where version v's files go, relative to Results/."""
        label = _safe((rec.get("recording") or {}).get("label")
                      or rec.get("gid") or "Unfiled", 80)
        stem = "%s %s v%d" % (_safe(title, 60), rec["id"], v)
        base = "%s/%s" % (FIG_DIR, label)
        return {"dir": base, "stem": stem,
                "data": "%s/%s/%s.v%d.npz" % (base, DATA_DIR, rec["id"], v)}

    def add_version(self, fid, layout, blobs, numbers, lineage, prov,
                    note=None, from_v=None, source="builder", files=None,
                    at=None):
        """File the rendered bytes and the plotted numbers, then the row.

        `blobs` is {fmt: bytes}. `files` is for a version whose files are
        already on disk (the migration): {fmt: rel}.
        """
        import numpy as np
        with _LOCK:
            rec = self.get(fid)
            _same_recording(rec, layout)
            v = self.next_v(rec)
            where = self.paths_for(rec, v, layout.get("title") or "figure")
            out_files = dict(files or {})
            for fmt, blob in (blobs or {}).items():
                rel = "%s/%s.%s" % (where["dir"], where["stem"], fmt)
                self._write(rel, blob)
                out_files[fmt] = rel
            data_rel = None
            if numbers:
                buf = io.BytesIO()
                np.savez_compressed(buf, **numbers)
                data_rel = where["data"]
                self._write(data_rel, buf.getvalue())
            lay = _strip(layout, fid)
            lay["v"] = v
            row = {
                "id": "%s.%s" % (fid, uuid.uuid4().hex[:8]), "v": v,
                "at": at or _now(), "by": (prov or {}).get("user"),
                "machine": (prov or {}).get("machine"),
                "app_version": (prov or {}).get("app_version"),
                "commit": (prov or {}).get("commit"),
                "layout": lay, "digest": layout_digest(lay),
                "files": out_files, "data": data_rel,
                "lineage": lineage or {}, "note": note,
                "from_v": from_v, "source": source,
            }
            rec.setdefault("versions", []).append(row)
            rec["status"] = "exported"
            rec["title"] = layout.get("title") or rec.get("title")
            # The draft carries on from what was just exported, so the next
            # edit starts here rather than at an older draft.
            rec["draft"] = dict(lay)
            rec["draft"].pop("v", None)
            rec["draft_at"] = _now()
            self.book.write(fid, rec)
            return row

    def _write(self, rel, blob):
        full = os.path.join(self.outputs_dir, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, full)
        if self.store is not None:
            try:
                self.store._stage(full)
            except Exception:                             # noqa: BLE001
                pass

    def full_path(self, rel):
        full = os.path.abspath(os.path.join(self.outputs_dir,
                                            rel.replace("/", os.sep)))
        if not full.startswith(os.path.abspath(self.outputs_dir)):
            raise FigureError("That file is not in Results.", 403)
        return full


def _recording_of(layout):
    rec = dict(layout.get("recording") or {})
    return {k: rec.get(k) for k in ("gid", "label", "path", "invert",
                                    "identity", "probe", "fs_text",
                                    "duration_text") if rec.get(k) is not None}


def _same_recording(rec, layout):
    want = rec.get("gid")
    got = (layout.get("recording") or {}).get("gid")
    if want and got and want != got:
        raise FigureError("This figure is of %s; a layout of another "
                          "recording cannot be saved into it."
                          % ((rec.get("recording") or {}).get("label") or want))


def _strip(layout, fid):
    """A layout as it is kept: no request-only keys, and its figure id."""
    out = {k: v for k, v in (layout or {}).items()
           if not str(k).startswith("_")}
    out["id"] = fid
    out["schema"] = SCHEMA
    panels = []
    for p in out.get("panels") or []:
        panels.append({k: v for k, v in p.items()
                       if not str(k).startswith("_")})
    out["panels"] = panels
    return out
