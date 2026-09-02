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

        # 3. Curated notes, tags and stars, matched on the portable key --
        #    `items` is keyed by absolute path, and comparing the two directly
        #    meant no tag ever found its file.
        side = self._sidecars()
        if side:
            by_key = {self.rel_key(p): p for p in items}
            for key, meta in side.items():
                clean = {k: v for k, v in meta.items()
                         if k not in ("key", "rel", "updated")}
                if key in by_key:
                    items[by_key[key]].update(clean)
                    continue
                # A tag on a file that is not on this machine is not an error,
                # but there is nothing to attach it to either.
                guess = os.path.join(self.outputs_dir,
                                     (meta.get("rel") or key).replace("/", os.sep))
                if os.path.isfile(guess) and self._inside(guess):
                    items[os.path.abspath(guess)] = dict(
                        self._from_file(os.path.abspath(guess), "sidecar"),
                        **clean)

        out = sorted(items.values(), key=lambda r: r.get("mtime") or 0, reverse=True)
        self._cache = {"at": time.time(), "items": out}
        return out

    def _inside(self, path):
        """Is this path inside the Results folder? Nothing else is cataloged."""
        try:
            return os.path.abspath(path).startswith(self.outputs_dir)
        except (TypeError, ValueError):
            return False

    def rel_key(self, path):
        """The machine-independent name for a result file.

        This is the one thing everything else keys off, and it has to be the
        same on every machine or nothing that references a result survives a
        git pull.

        It used to be a hash of the absolute path, which is a different string
        on every computer:

            C:\\Users\\Z390\\...\\Results\\PTEN m7\\fig.png
            /Users/jeremy/code/...\\Results/PTEN m7/fig.png

        -- so a deck built here referenced an id that existed nowhere else,
        and every slide came up empty on anyone else's machine. Results lives
        inside the repo, so the path relative to it is identical everywhere.
        Forward slashes because Windows and macOS disagree about separators,
        and lowercased because Windows does not distinguish case.
        """
        try:
            rel = os.path.relpath(os.path.abspath(path), self.outputs_dir)
        except (TypeError, ValueError):
            rel = str(path)
        return rel.replace("\\", "/").lower()

    def _result_id(self, path):
        return _hash(self.rel_key(path))

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
        rel = self.rel_key(path)
        return {
            "id": self._result_id(path),
            # The repo-relative path, kept on every record rather than only on
            # the scanned ones: it is what makes a deck or a tag portable, so
            # nothing should be able to acquire a record without it.
            "rel": os.path.relpath(os.path.abspath(path),
                                   self.outputs_dir).replace("\\", "/"),
            "key": rel,
            "folder": os.path.dirname(rel),
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
                # _from_file already carries rel/key/folder.
                items[path] = self._from_file(path, source)

    # Curation used to be one committed curation.json holding every tag and
    # star in the repo. That is exactly the file two people cannot both edit:
    # tag a figure here, tag a different one there, and the next pull is a
    # conflict in a file neither of you touched the same part of.
    #
    # One file per result instead. The name is a hash of the portable key, so
    # the same figure lands on the same filename on every machine, and two
    # people tagging two different figures write two different files.
    def _sidecar_dir(self):
        d = os.path.join(self.root, "curation")
        os.makedirs(d, exist_ok=True)
        return d

    def _legacy_sidecar(self):
        return os.path.join(self.root, "curation.json")

    def _sidecar_file(self, key):
        return os.path.join(self._sidecar_dir(), _hash(key) + ".json")

    def _sidecars(self):
        """Every result's curation, keyed the portable way.

        Reads the per-result files, and folds in anything left in the old
        shared file so nothing written before the split is lost.
        """
        out = {}

        # The old single file, if it is still there. Absolute-path keys are
        # translated to the portable form on the way through.
        try:
            with open(self._legacy_sidecar(), "r", encoding="utf-8") as fh:
                for k, v in (json.load(fh) or {}).items():
                    key = k if not os.path.isabs(k) else self.rel_key(k)
                    prev = out.get(key)
                    if prev and (prev.get("updated") or {}).get("at", "") \
                            > (v.get("updated") or {}).get("at", ""):
                        continue
                    out[key] = v
        except (OSError, json.JSONDecodeError):
            pass

        d = self._sidecar_dir()
        try:
            names = sorted(os.listdir(d))
        except OSError:
            names = []
        for name in names:
            if not name.endswith(".json"):
                continue
            rec = _read_json(os.path.join(d, name))
            if rec and rec.get("key"):
                out[rec["key"]] = rec
        return out

    def curate(self, path, patch):
        """Attach tags/notes/title to a result, in its own file."""
        key = self.rel_key(path)
        target = self._sidecar_file(key)
        rec = _read_json(target) or self._sidecars().get(key, {})
        rec["key"] = key
        rec["rel"] = os.path.relpath(os.path.abspath(path),
                                     self.outputs_dir).replace("\\", "/")
        rec.update({k: v for k, v in patch.items()
                    if k in ("title", "tags", "notes", "starred")})
        rec["updated"] = self.store.provenance()
        _write_json(target, rec)
        self.store._stage(target)
        self._cache["at"] = 0
        return rec

    def get(self, result_id):
        for r in self.catalog():
            if r["id"] == result_id:
                return r
        return None

    def resolve(self, spec):
        """Find a result from whatever a caller still remembers about it.

        A deck or a figure recipe written before ids were portable carries an
        id that matches nothing here. It also carries the file's name, and
        newer ones carry the relative path -- either of which identifies the
        file perfectly well, because the file itself came through git with
        everyone else's. Try the id, then the path, then the name.
        """
        if not isinstance(spec, dict):
            spec = {"result_id": spec}
        items = self.catalog()

        rid = spec.get("result_id") or spec.get("id")
        if rid:
            for r in items:
                if r["id"] == rid:
                    return r

        rel = spec.get("rel")
        if rel:
            want = str(rel).replace("\\", "/").lower()
            for r in items:
                if r.get("key") == want:
                    return r

        name = spec.get("name")
        if name:
            want = str(name).lower()
            hits = [r for r in items if (r.get("name") or "").lower() == want]
            # Only when it is unambiguous. Two files with the same basename in
            # different folders are not the same result, and guessing between
            # them would put the wrong figure on someone's slide.
            if len(hits) == 1:
                return hits[0]
        return None

    def heal_deck(self, deck):
        """Point a deck's items at results as they are known on this machine.

        Done in memory on the way out, not written back: a read should not
        rewrite what it read. The corrected ids go to the browser and to the
        exporter, and the next ordinary save persists them.
        """
        fixed = 0
        for sl in (deck.get("slides") or []):
            for it in (sl.get("items") or []):
                if it.get("type") != "result":
                    continue
                r = self.resolve(it)
                if not r:
                    continue
                if it.get("result_id") != r["id"] or it.get("rel") != r.get("rel"):
                    it["result_id"] = r["id"]
                    it["rel"] = r.get("rel")
                    it["name"] = r.get("name")
                    fixed += 1
        return fixed

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
                # Resolved rather than taken as written: the thumbnail is the
                # first thing you see of a deck, and a broken one on every
                # card is how "the storyboards do not render" looks from the
                # list before you have even opened one.
                "thumb": self._first_image(d),
            })
        out.sort(key=lambda x: x.get("updated") or "", reverse=True)
        return out

    def get_deck(self, deck_id):
        deck = _read_json(self.deck_path(deck_id))
        # A deck that came through git points at result ids from whichever
        # machine built it. Re-point them at the same files here, or every
        # slide comes up blank.
        if deck:
            self.heal_deck(deck)
        return deck

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

    def _first_image(self, deck):
        """The id of the first result on a deck, as known here."""
        for sl in (deck.get("slides") or []):
            for it in (sl.get("items") or []):
                if it.get("type") != "result":
                    continue
                r = self.resolve(it)
                if r:
                    return r["id"]
        return None

    def delete_deck(self, deck_id):
        path = self.deck_path(deck_id)
        try:
            os.remove(path)
            return True
        except OSError:
            return False


def _hash(text):
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


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
