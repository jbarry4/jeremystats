"""
results.py -- The Results catalog and the Storyboard store.

RESULTS
    Everything BARRY saves is cataloged here automatically: figures exported
    from the builder, single-window trace exports, and any image or table a
    pipeline stage drops into a session folder. A result is a row of metadata --
    what it is, which session it came from, who made it, which run produced it --
    plus a pointer to the file. The file itself stays where it was written.

    The catalog is rebuilt by scanning, not maintained by hand, so a figure
    someone produced on another machine and committed shows up here after a
    pull without any bookkeeping.

STORYBOARD
    Slide decks that assemble results into a sequence: images, text, drawings
    and per-slide notes. Stored as JSON, one file per deck, so decks merge
    through git the same way everything else does.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"}
DOC_EXTS = {".pdf"}
TABLE_EXTS = {".csv", ".xlsx", ".xls", ".tsv"}
RESULT_EXTS = IMAGE_EXTS | DOC_EXTS | TABLE_EXTS

# Folders a pipeline stage writes its output into. Scanned for results so a
# MATLAB stage's figures are cataloged without the GUI having produced them.
STAGE_OUTPUT_DIRS = ("pipeline output", "output", "figures", "figs")

MAX_SCAN_FILES = 6000


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Results:
    """Catalog of saved artifacts, plus the storyboard decks."""

    def __init__(self, store, outputs_dir, repo_root):
        self.store = store
        self.outputs_dir = outputs_dir
        self.repo_root = repo_root
        self.root = os.path.join(store.root, "results")
        self.decks_dir = os.path.join(store.root, "storyboards")
        os.makedirs(self.root, exist_ok=True)
        os.makedirs(self.decks_dir, exist_ok=True)
        self._cache = {"at": 0, "items": []}

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------
    def catalog(self, refresh=False, extra_roots=None):
        """Every result BARRY has saved, newest first.

        Deliberately one source: the Results folder in the repo. It used to
        also sweep data roots for whatever a MATLAB stage had left in a
        session directory, which meant the catalog filled up with files nobody
        had asked it to track, whose provenance it could not vouch for, and
        which lived outside the repo so nobody else could see them. Everything
        here is something the GUI produced and committed.

        `extra_roots` is accepted and ignored, so existing callers keep working.
        """
        del extra_roots                     # no longer scanned; see above
        if not refresh and time.time() - self._cache["at"] < 5:
            return self._cache["items"]

        items = {}

        # 1. Anything exported through BARRY, which carries real provenance.
        for rec in self.store.all_runs():
            out = rec.get("output") or {}
            path = out.get("path")
            if not path:
                continue
            full = os.path.abspath(path)
            if not self._inside(full):
                continue        # an older record from before the move
            items[full] = self._from_run(rec, out)

        # 2. Whatever else is in the folder -- including files pulled from a
        #    colleague's commit, which have no local run record.
        self._scan_dir(self.outputs_dir, items, source="results")

        # 3. Curated notes, tags and stars.
        for path, meta in self._sidecars().items():
            if path in items:
                items[path].update(meta)
            elif os.path.isfile(path) and self._inside(path):
                items[path] = dict(self._from_file(path, "sidecar"), **meta)

        out = sorted(items.values(), key=lambda r: r.get("mtime") or 0, reverse=True)
        self._cache = {"at": time.time(), "items": out}
        return out

    def _inside(self, path):
        """Is this path inside the Results folder? Nothing else is cataloged."""
        try:
            return os.path.abspath(path).startswith(self.outputs_dir)
        except (TypeError, ValueError):
            return False

    def _from_run(self, rec, out):
        path = os.path.abspath(out["path"])
        base = self._from_file(path, "figure")
        prov = rec.get("provenance") or {}
        sess = rec.get("session") or {}
        base.update({
            "run_id": rec.get("id"),
            "title": rec.get("label") or base["name"],
            "kind": rec.get("kind") or "figure",
            "format": rec.get("format") or base["ext"].lstrip("."),
            "author": prov.get("user"),
            "machine": prov.get("machine"),
            "created": prov.get("at"),
            "session_label": sess.get("label"),
            "session_key": sess.get("key"),
            "session_path": sess.get("path"),
            "parameters": rec.get("parameters") or {},
            "panels": rec.get("panels") or [],
            "github": out.get("github"),
            "rel": out.get("rel"),
        })
        return base

    def _from_file(self, path, source):
        try:
            st = os.stat(path)
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = 0, 0
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        return {
            "id": _result_id(path),
            "path": path,
            "name": name,
            "title": os.path.splitext(name)[0],
            "ext": ext,
            "type": ("image" if ext in IMAGE_EXTS else
                     "pdf" if ext in DOC_EXTS else
                     "table" if ext in TABLE_EXTS else "file"),
            "bytes": size,
            "mtime": mtime,
            "created": datetime.fromtimestamp(mtime).astimezone().isoformat(
                timespec="seconds") if mtime else None,
            "source": source,
            "kind": "file",
            "tags": [],
            "notes": "",
        }

    def _scan_dir(self, folder, items, source, depth=4):
        if not folder or not os.path.isdir(folder):
            return
        count = 0
        for root, dirs, files in os.walk(folder):
            if root[len(folder):].count(os.sep) >= depth:
                dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if os.path.splitext(name)[1].lower() not in RESULT_EXTS:
                    continue
                path = os.path.abspath(os.path.join(root, name))
                count += 1
                if count > MAX_SCAN_FILES:
                    return
                if path in items:
                    continue
                rec = self._from_file(path, source)
                try:
                    rec["rel"] = os.path.relpath(path, self.outputs_dir).replace("\\", "/")
                except ValueError:
                    rec["rel"] = None
                items[path] = rec

    def _sidecar_path(self):
        return os.path.join(self.root, "curation.json")

    def _sidecars(self):
        try:
            with open(self._sidecar_path(), "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        return {os.path.abspath(k): v for k, v in raw.items()}

    def curate(self, path, patch):
        """Attach tags/notes/title to a result, keyed by its path."""
        path = os.path.abspath(path)
        data = self._sidecars()
        rec = data.get(path, {})
        rec.update({k: v for k, v in patch.items()
                    if k in ("title", "tags", "notes", "starred")})
        rec["updated"] = self.store.provenance()
        data[path] = rec
        target = self._sidecar_path()
        _write_json(target, data)
        self.store._stage(target)
        self._cache["at"] = 0
        return rec

    def get(self, result_id):
        for r in self.catalog():
            if r["id"] == result_id:
                return r
        return None

    # ------------------------------------------------------------------
    # Storyboard decks
    # ------------------------------------------------------------------
    def deck_path(self, deck_id):
        safe = "".join(c for c in str(deck_id) if c.isalnum() or c in "._-")
        return os.path.join(self.decks_dir, safe + ".json")

    def list_decks(self):
        out = []
        for name in sorted(os.listdir(self.decks_dir)) if os.path.isdir(self.decks_dir) else []:
            if not name.endswith(".json"):
                continue
            d = _read_json(os.path.join(self.decks_dir, name))
            if not d:
                continue
            out.append({
                "id": d.get("id"), "title": d.get("title"),
                "slides": len(d.get("slides") or []),
                "updated": (d.get("updated") or {}).get("at"),
                "author": (d.get("created") or {}).get("user"),
                "thumb": _first_image(d),
            })
        out.sort(key=lambda x: x.get("updated") or "", reverse=True)
        return out

    def get_deck(self, deck_id):
        return _read_json(self.deck_path(deck_id))

    def save_deck(self, deck):
        deck = dict(deck)
        deck.setdefault("id", "deck_" + uuid.uuid4().hex[:8])
        deck.setdefault("title", "Untitled deck")
        deck.setdefault("slides", [])
        deck.setdefault("created", self.store.provenance())
        deck["updated"] = self.store.provenance()
        deck["schema"] = 1
        path = self.deck_path(deck["id"])
        _write_json(path, deck)
        self.store._stage(path)
        return deck

    def delete_deck(self, deck_id):
        path = self.deck_path(deck_id)
        try:
            os.remove(path)
            return True
        except OSError:
            return False


def _result_id(path):
    """Stable id from the path, so the same file keeps its id everywhere."""
    import hashlib
    return hashlib.sha1(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:12]


def _first_image(deck):
    for sl in (deck.get("slides") or []):
        for it in (sl.get("items") or []):
            if it.get("type") == "result" and it.get("result_id"):
                return it["result_id"]
    return None


def _read_json(path):
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, data):
    import tempfile
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False,
                                sort_keys=True) + "\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
