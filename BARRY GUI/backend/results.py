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

from . import shards
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
        # Tags and decks are both edited by whoever is looking at them, so
        # both are per machine and compiled on read.
        self.tags = shards.Book(os.path.join(self.root, "curation"),
                                {"tags": shards.UNION,
                                 "created": shards.FIRST}, store)
        self.decks = shards.Book(self.decks_dir,
                                 {"created": shards.FIRST}, store)
        self.tags.absorb_legacy()
        self.decks.absorb_legacy()
        self._absorb_shared_sidecar()
        # What has been moved or deleted here, so a sync does not put it
        # back. See tombs.py -- this is the bug that turned six figures into
        # twelve.
        from . import tombs
        self.tombs = tombs.Tombs(store.root, store)
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
            if not os.path.isfile(full):
                # The run says it made this and the file is not there any
                # more -- moved by hand, deleted, or on another machine. The
                # run record keeps that history; the Results view should not
                # offer a thumbnail for something nobody can open. This is
                # also the difference between "what the GUI shows" and "what
                # is in the folder" being the same sentence or not.
                continue
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
        shown = os.path.relpath(os.path.abspath(path),
                                self.outputs_dir).replace("\\", "/")
        return {
            "id": self._result_id(path),
            # The repo-relative path, kept on every record rather than only on
            # the scanned ones: it is what makes a deck or a tag portable, so
            # nothing should be able to acquire a record without it.
            "rel": shown,
            "key": rel,
            # From the displayed path, not from the matching key -- the key is
            # lowercased so two machines agree about the same file, and taking
            # the folder from it gave every directory twice: once as "Figure 3"
            # and once as "figure 3".
            "folder": os.path.dirname(shown),
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

    def _absorb_shared_sidecar(self):
        """Fold the one-file-for-everything sidecar into per-result shards.

        `results/curation.json` predates both the per-result split and the
        per-machine split, and being a single shared file it is the most
        conflict-prone thing that was ever in here. Read once, redistributed,
        removed.
        """
        old = self._legacy_sidecar()
        if not os.path.isfile(old):
            return
        try:
            with open(old, "r", encoding="utf-8") as fh:
                data = json.load(fh) or {}
        except (OSError, json.JSONDecodeError):
            data = {}
        for k, v in data.items():
            key = k if not os.path.isabs(k) else self.rel_key(k)
            base = self._sidecar_base(key)
            if self.tags.read(base):
                continue
            rec = dict(v)
            rec["key"] = key
            self.tags.write(base, rec)
        try:
            os.remove(old)
        except OSError:
            pass
        self.store._stage(old)

    def _sidecar_base(self, key):
        return shards.safe_base(_hash(key))

    def _sidecar_file(self, key):
        return self.tags.mine(self._sidecar_base(key))

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

        for rec in self.tags.all():
            if rec and rec.get("key"):
                out[rec["key"]] = rec
        return out

    def curate(self, path, patch):
        """Attach tags/notes/title to a result, in its own file."""
        key = self.rel_key(path)
        base = self._sidecar_base(key)
        rec = self.tags.read(base) or dict(self._sidecars().get(key, {}))
        rec["key"] = key
        rec["rel"] = os.path.relpath(os.path.abspath(path),
                                     self.outputs_dir).replace("\\", "/")
        rec.update({k: v for k, v in patch.items()
                    if k in ("title", "tags", "notes", "starred")})
        rec["updated"] = self.store.provenance()
        rec = self.tags.write(base, rec)
        self._cache["at"] = 0
        return rec


    # ------------------------------------------------------------------
    # Folders
    #
    # A folder here is a real directory under Results/, not a label beside
    # one. That is the whole point: what the Results view shows and what you
    # see when you open the folder are the same thing, so a figure you filed
    # under "Figure 3" is at Results/Figure 3/ and can be dragged into a
    # slide deck, emailed, or found by someone who has never opened BARRY.
    #
    # It costs more than a label, because moving a file breaks whatever was
    # holding its old path -- the run that produced it, a storyboard slide
    # pointing at its id. So the move fixes those on the way through, rather
    # than leaving a tidy folder tree and a broken rebuild.
    # ------------------------------------------------------------------
    @staticmethod
    def clean_folder(name):
        """Normalise a folder path: forward slashes, no empty or sneaky bits."""
        parts = []
        for seg in str(name or "").replace("\\", "/").split("/"):
            seg = seg.strip().strip(".")
            seg = "".join(c for c in seg if c not in '<>:"|?*')
            if seg:
                parts.append(seg)
        return "/".join(parts[:6])          # six deep is already too deep

    def folder_of(self, rec):
        return self.clean_folder(rec.get("folder"))

    def folders(self):
        """Every directory under Results/, with how many results are in it.

        Read off the disk rather than off the records, so a folder someone
        made in Explorer shows up here, and one that only exists because a
        record claims it does not.
        """
        counts = {}
        for r in self.catalog():
            f = self.folder_of(r)
            if not f:
                continue
            counts[f] = counts.get(f, 0) + 1
            parts = f.split("/")
            for i in range(1, len(parts)):
                counts.setdefault("/".join(parts[:i]), 0)
        # Empty directories count too: you make a folder before you fill it.
        for root, dirs, _files in os.walk(self.outputs_dir):
            for d in dirs:
                rel = os.path.relpath(os.path.join(root, d),
                                      self.outputs_dir).replace("\\", "/")
                if rel.startswith("."):
                    continue
                counts.setdefault(self.clean_folder(rel), 0)
        out = []
        for path in sorted(x for x in counts if x):
            out.append({
                "path": path,
                "name": path.rsplit("/", 1)[-1],
                "depth": path.count("/"),
                "n": counts[path],
            })
        return out

    def unfiled(self):
        """Results sitting loose in the top of Results/."""
        return sum(1 for r in self.catalog() if not self.folder_of(r))

    def make_folder(self, name):
        folder = self.clean_folder(name)
        if not folder:
            raise ValueError("Give the folder a name.")
        os.makedirs(os.path.join(self.outputs_dir, *folder.split("/")),
                    exist_ok=True)
        self._cache["at"] = 0
        return folder

    def move(self, result_id, folder, store=None):
        """Move a result into a folder, and fix what pointed at it.

        Returns the new record. The id changes with the path -- it is a hash
        of the path, which is what makes it the same id on every machine --
        so anything holding the old one is repointed here rather than being
        left to fail later.
        """
        rec = self.get(result_id)
        if not rec:
            raise ValueError("No such result.")
        src = rec.get("path")
        if not src or not os.path.isfile(src):
            raise ValueError("That result is not on this machine.")
        if not self._inside(src):
            raise ValueError("That file is not in the Results folder.")

        folder = self.clean_folder(folder)
        dest_dir = os.path.join(self.outputs_dir, *folder.split("/")) \
            if folder else self.outputs_dir
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.abspath(dest) == os.path.abspath(src):
            return rec
        if os.path.exists(dest):
            # Never overwrite somebody else's figure to tidy a folder.
            stem, ext = os.path.splitext(os.path.basename(src))
            n = 2
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, "%s_%d%s" % (stem, n, ext))
                n += 1

        old_rel = rec.get("rel")
        old_id = rec.get("id")
        old_key = self.rel_key(src)
        _move_file(src, dest)

        # The tags and notes were keyed on the old path; carry them over.
        side = self._sidecars().get(old_key)
        if side:
            carried = {k: v for k, v in side.items()
                       if k in ("title", "tags", "notes", "starred")}
            if carried:
                self.curate(dest, carried)
            try:
                self.tags.erase(self._sidecar_base(old_key))
            except Exception:                    # noqa: BLE001
                pass

        self._cache["at"] = 0
        new = self._from_file(dest, "moved")
        self._repoint(store, old_id, old_rel, new["id"], new["rel"], src, dest)
        # The old path is gone. Say so, or the next sync finds a row whose
        # file is missing locally and downloads it back into the folder you
        # just moved it out of.
        self.tombs.add("result", old_rel, note="moved to " + new["rel"])
        self.tombs.forget("result", new["rel"])
        return self.get(new["id"]) or new

    def _repoint(self, store, old_id, old_rel, new_id, new_rel, src, dest):
        """Follow the file: run outputs, and any deck slide holding its id.

        Without this, filing a figure into a folder is how a storyboard goes
        blank and a rebuild stops finding what it made -- weeks later, with
        nothing to connect it to the tidy-up that caused it.
        """
        for deck_row in self.list_decks():
            deck = self.decks.read(self.deck_base(deck_row["id"]))
            if not deck:
                continue
            touched = False
            for sl in (deck.get("slides") or []):
                for it in (sl.get("items") or []):
                    if it.get("type") != "result":
                        continue
                    if it.get("id") == old_id or it.get("result") == old_id:
                        it["id"] = new_id
                        it["rel"] = new_rel
                        touched = True
                    elif it.get("rel") == old_rel:
                        it["rel"] = new_rel
                        it["id"] = new_id
                        touched = True
            if touched:
                self.decks.write(self.deck_base(deck["id"]), deck)

        if store is None:
            return
        for run in store.all_runs():
            outs = run.get("outputs") or []
            if not outs:
                continue
            changed, fixed = False, []
            for o in outs:
                if isinstance(o, str):
                    if os.path.abspath(o) == os.path.abspath(src):
                        fixed.append(dest)
                        changed = True
                    else:
                        fixed.append(o)
                elif isinstance(o, dict):
                    if o.get("rel") == old_rel or (
                            o.get("path")
                            and os.path.abspath(o["path"])
                            == os.path.abspath(src)):
                        o = dict(o, path=dest, rel=new_rel)
                        changed = True
                    fixed.append(o)
                else:
                    fixed.append(o)
            if changed:
                store.update_run(run["id"], {"outputs": fixed})

    def rename_folder(self, src, dst, store=None):
        """Rename a directory, carrying everything inside it.

        A rename that left the children behind -- "Figure 3" becoming
        "Figure 4" while "Figure 3/Panels" stayed put -- would be worse than
        refusing, so this moves the directory itself.
        """
        src = self.clean_folder(src)
        dst = self.clean_folder(dst)
        if not src:
            raise ValueError("Which folder?")
        src_dir = os.path.join(self.outputs_dir, *src.split("/"))
        if not os.path.isdir(src_dir):
            raise ValueError("There is no folder called %r." % src)

        moved = []
        for r in self.catalog():
            f = self.folder_of(r)
            if f == src or f.startswith(src + "/"):
                moved.append((r["id"], (dst + f[len(src):]) if dst else
                              f[len(src):].lstrip("/")))
        for rid, folder in moved:
            try:
                self.move(rid, folder, store=store)
            except ValueError:
                continue
        # Take the now-empty directory with it.
        try:
            for root, dirs, files in os.walk(src_dir, topdown=False):
                if not os.listdir(root):
                    os.rmdir(root)
        except OSError:
            pass
        self._cache["at"] = 0
        return len(moved)

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
    def deck_base(self, deck_id):
        return shards.safe_base(deck_id)

    def deck_path(self, deck_id):
        return self.decks.mine(self.deck_base(deck_id))

    def list_decks(self):
        out = []
        for d in self.decks.all():
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
        deck = self.decks.read(self.deck_base(deck_id))
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
        return self.decks.write(self.deck_base(deck["id"]), deck)

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
        gone = bool(self.decks.erase(self.deck_base(deck_id)))
        if gone:
            self.tombs.add("deck", deck_id)
        return gone


def _move_file(src, dest, tries=12, wait=0.08):
    """Rename a file, working around Windows holding it open.

    Serving a figure leaves the handle open for a moment after the response,
    and Windows refuses to rename a file anybody has open -- so viewing a
    result and then filing it fails, intermittently, with a permission error
    that says nothing about why. Everywhere else this is a non-issue, which is
    exactly why it goes unnoticed until it is in front of a person.

    A short retry is the whole fix: the handle closes within a few tens of
    milliseconds. If it genuinely will not move, the error says so in words.
    """
    last = None
    for i in range(tries):
        try:
            os.replace(src, dest)
            return dest
        except PermissionError as exc:
            last = exc
            time.sleep(wait * (i + 1))
        except OSError as exc:
            last = exc
            break
    raise OSError(
        "Could not move %s -- something still has it open. Close it (or the "
        "preview showing it) and try again. (%s)"
        % (os.path.basename(src), last))


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
