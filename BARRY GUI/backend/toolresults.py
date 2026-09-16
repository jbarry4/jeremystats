"""
toolresults.py -- what a tool has already worked out, kept.

A tool that reads a recording and produces numbers has two things to file, and
they do not belong in the same place:

    the answer   the numbers a figure or a statistic is made from. Thirty
                 kilobytes a recording, small enough to commit and to sync,
                 and impossible to get back without the recording and the
                 time it takes to read it. This is the record.

    the picture  a rendering of that answer. Megabytes, and regenerable from
                 the answer in milliseconds. This is cache.

`Results/` used to hold both, which is how it became a folder of pictures with
no numbers behind them: a figure you could look at and could not do anything
with, because everything that made it answerable had been thrown away.

KEYED ON THE QUESTION, NOT ON WHO ASKED IT

A record's name is `<gid>__<params_hash>` -- the recording, and a short hash of
the settings that change the numbers. Not the run, not the set, not the file
path. Three consequences, and they are the whole point:

  * Asking the same question of the same recording twice costs nothing the
    second time. A bulk run over forty recordings that dies halfway resumes by
    skipping what is already there, and a colleague running the other half is
    not doing your half again.

  * Two sets that happen to ask the same thing share the answer.

  * Re-running with a different frequency range does not overwrite the old
    numbers. It writes different ones beside them, under a different hash, and
    both remain answerable.

The hash is deterministic, so two machines computing the same thing write the
same filename -- which is what makes the shard merge mean something. A minted
id would have produced two records for one computation.

WHICH SETTINGS COUNT

Each tool says. The colormap and the picture's scale are deliberately not in
Panorama's list: re-colouring a spectrogram does not make the histogram behind
it a different measurement, and including them would split the store into
copies that differ by nothing.

This is lifted out of panoramaset.py, which got here first and got it right.
Panorama passes exactly the field list it always used, so every record already
on disk keeps its name.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from . import shards

# The merge rules every tool's result record needs. A result is written once
# and not edited, so there is little to merge -- but `created`, `gid` and
# `params_hash` are what the record *is*, and must never be taken from a later
# writer who happened to recompute it.
RESULT_SPEC = {
    "created": shards.FIRST,
    "gid": shards.FIRST,
    "params_hash": shards.FIRST,
}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def params_hash(params, keys):
    """A short name for one question, from the settings that change answers.

    `keys` is the tool's list of which settings those are. A field that is
    absent or None is left out entirely rather than hashed as null, so adding
    an optional setting does not rename every record that predates it.
    """
    keep = {k: params.get(k) for k in keys if params.get(k) is not None}
    blob = json.dumps(keep, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


class ToolResults:
    """One tool's vault: the answers, and the regenerable pictures beside it.

        vault = ToolResults(logs_dir, "incisor", store, keys=(...))
        rec = vault.get(gid, vault.hash_of(params))
        if rec is None:
            rec = compute(...)
            vault.put(rec)
    """

    def __init__(self, logs_dir, tool, store, keys=(), spec=None):
        self.tool = tool
        self.store = store
        self.keys = tuple(keys)
        self.root = os.path.join(logs_dir, tool)
        self.results_dir = os.path.join(self.root, "results")
        # Under .cache, which git ignores, because it is regenerable by
        # definition -- see the module docstring.
        self.cache = os.path.join(logs_dir, ".cache", tool)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.cache, exist_ok=True)
        self.book = shards.Book(self.results_dir, spec or RESULT_SPEC, store)

    # -- naming ---------------------------------------------------------
    def hash_of(self, params):
        return params_hash(params, self.keys)

    def base(self, gid, ph):
        return shards.safe_base(gid, ph)

    # -- the records ----------------------------------------------------
    def get(self, gid, ph):
        return self.book.read(self.base(gid, ph))

    def put(self, rec):
        """File one answer. `gid` and `params_hash` must already be on it."""
        gid = rec.get("gid")
        ph = rec.get("params_hash")
        if not gid or not ph:
            raise ValueError(
                "A %s result must say which recording and which question it "
                "answers before it can be filed." % self.tool)
        rec.setdefault("tool", self.tool)
        rec.setdefault("created", self._who())
        rec["updated"] = self._who()
        return self.book.write(self.base(gid, ph), rec)

    def all(self):
        return self.book.all()

    def for_gid(self, gid):
        """Every question this recording has been asked, newest first."""
        out = [r for r in self.all() if r.get("gid") == gid]
        out.sort(key=lambda r: (r.get("computed") or {}).get("at") or "",
                 reverse=True)
        return out

    def have(self, gids, ph):
        """Which of these recordings already have an answer to this question.

        The whole of resume, and the reason a re-run of a forty-recording set
        takes seconds rather than an hour.
        """
        return {g for g in gids if self.get(g, ph)}

    def pending(self, gids, ph, force=False):
        """And which still need doing, in the order given."""
        if force:
            return list(gids)
        done = self.have(gids, ph)
        return [g for g in gids if g not in done]

    # -- the pictures ---------------------------------------------------
    def cached_path(self, gid, ph, ext=".png"):
        """Where a rendering lives. Cache, not record: safe to delete."""
        return os.path.join(self.cache, "%s__%s%s"
                            % (shards.safe_base(gid), ph, ext))

    def has_cached(self, gid, ph, ext=".png"):
        p = self.cached_path(gid, ph, ext)
        return os.path.exists(p) and os.path.getsize(p) > 0

    def forget_cached(self, gid, ph, ext=".png"):
        try:
            os.remove(self.cached_path(gid, ph, ext))
            return True
        except OSError:
            return False

    # -- provenance -----------------------------------------------------
    def _who(self):
        return self.store.provenance() if self.store else {"at": _now()}
