"""
artifacts.py -- Jarvis Artifacts: the versioned things a stage makes and a
later stage reads.

A figure is something to look at. An artifact is something to BUILD ON: a
Circuit (one recording, one cue type, one analysis kind, every cue pair's
value in every cell) is what a Drift averages, and a Drift is only as good as
its ability to say which circuit, at which version, with which bytes, it was
made from. So this store has three jobs and they are all about that:

  1. **Identity.** An artifact has a minted `id` that never changes, an
     automatic `name` worked out from its metadata, and an optional
     `nickname` somebody gave it. The same subject -- the same recording, cue
     type and kind -- always finds the same artifact (`find`), so re-running
     a circuit adds a VERSION rather than minting a second artifact that
     nobody can tell from the first.

  2. **Versions that stay put.** Every version's payload is written once, as
     `snap/<id>/v<v>__<digest>.json`, and is never rewritten and never
     pruned. The bank prunes old snapshots; this store cannot, because a
     version a Drift cites has to stay restorable for as long as the Drift
     exists. Re-running and getting byte-for-byte the same answer is not a
     new version -- it is a confirmation, stamped on the version that already
     says it.

  3. **Citations that hold.** A Drift cites the exact circuit versions it
     read. A cited version cannot be deleted, and the refusal says who cites
     it, because "cannot delete" with no reason sends somebody hunting.

Modelled on the Event Bank (eventbank.py): the record is sharded per machine
through shards.Book, versions are merged BYID on a stable per-version `id`
(two machines can both mint "v2", and the union rightly keeps both), and the
cloud copy is add-only with a digest mismatch reported as a conflict rather
than resolved. Two deliberate differences from the bank: snapshots are never
pruned, and there is no retime or dedupe -- an artifact is computed, not
curated.

Record (the whitelist -- nothing else is written):

    id, kind, schema, subject, subject_key, name, nickname, version,
    versions, cited, added, deleted

See the contract (arc_contracts.md section 2) for each field.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone

from . import shards

SCHEMA = "arc.artifact/1"
FIELDS = ("id", "kind", "schema", "subject", "subject_key", "name",
          "nickname", "version", "versions", "cited", "added", "deleted")
# The fields a version row may carry. `confirmed` is a list: each time a
# re-run reproduced this version exactly, who, when and where.
VERSION_FIELDS = ("v", "id", "digest", "at", "by", "machine", "app_version",
                  "commit", "params", "params_hash", "inputs", "note",
                  "n_summary", "confirmed")

# Left out of the digest. A payload's digest says what it IS, and when it was
# made or on which computer is not that -- a VACC run that reproduces a local
# one to the last digit is the same answer, and should confirm it rather than
# mint a second version that differs only in where it ran. `made` anywhere in
# the tree (the contract's "no made/timestamps"); `computed_on` only at the
# top, where the payload contract puts it.
DIGEST_SKIP_TOP = ("made", "computed_on", "computed_at")
DIGEST_SKIP_ANY = ("made",)

_LOCK = threading.RLock()

CUE_LABELS = {
    "Click_Noise": "Click → Noise",
    "HighTone_LowTone": "High tone → Low Tone",
}


class ArtifactError(Exception):
    """A refusal the user should read, not a crash."""


# ==========================================================================
# Canonical form and the digest
# ==========================================================================
def plain(x):
    """The payload as plain JSON: numpy scalars and arrays unwrapped, tuples
    as lists, and NaN or infinity as null.

    Null rather than the NaN token Python's json module writes, because
    JSON.parse in the browser refuses that token outright -- a payload with
    one NaN in it would load here and fail to open in Results.
    """
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [plain(v) for v in x]
    tolist = getattr(x, "tolist", None)          # numpy array or scalar
    if callable(tolist):
        return plain(tolist())
    item = getattr(x, "item", None)
    if callable(item):
        return plain(item())
    return str(x)


def _canon(x, top=False):
    """What the digest is taken over.

    Floats to ten significant figures, and an integral float as the integer:
    `0.30000000000000004` and `0.3`, or `6` and `6.0`, are one answer written
    down by two arithmetic paths, not two answers. Ten figures is well past
    anything a connectivity value means and well short of the last-bit noise
    two BLAS builds disagree about -- the same idea as the bank rounding its
    times to the microsecond in `snap_sha`.
    """
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, int):
        return int(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            return None
        f = float("%.10g" % x)
        if f == 0:
            return 0
        return int(f) if f.is_integer() and abs(f) < 1e15 else f
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            k = str(k)
            if k in DIGEST_SKIP_ANY or (top and k in DIGEST_SKIP_TOP):
                continue
            out[k] = _canon(v)
        return out
    if isinstance(x, (list, tuple)):
        return [_canon(v) for v in x]
    return _canon(plain(x))


def digest(payload):
    """sha1 over the canonical JSON of the payload, first 12 hex characters.

    Sorted keys, compact separators, and the when-and-where keys left out
    (see DIGEST_SKIP_*). Two machines computing the same thing agree on this,
    which is what makes "the same answer" a check rather than an assumption.
    """
    blob = json.dumps(_canon(plain(payload), top=True), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _hash_of(obj):
    blob = json.dumps(_canon(plain(obj or {})), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def _now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


# ==========================================================================
# Kinds: how each one is keyed, named and summarised
# ==========================================================================
def cue_label(cue_type, subject=None):
    if subject and subject.get("cue_label"):
        return str(subject["cue_label"])
    return CUE_LABELS.get(cue_type or "", cue_type or "")


def _need(subject, keys, kind):
    missing = [k for k in keys if subject.get(k) in (None, "")]
    if missing:
        raise ArtifactError(
            "A %s's subject has to say %s, and this one does not say %s. "
            "Without them the same recording cannot find the same %s again."
            % (kind, ", ".join(keys), " or ".join(missing), kind))


def _circuit_key(subject):
    _need(subject, ("gid", "cue_type", "window_kind"), "circuit")
    key = "circuit|%s|%s|%s" % (subject["gid"], subject["cue_type"],
                                subject["window_kind"])
    # One artifact per band (arc_contracts.md 7.1); the same rule as
    # `circuit.subject_key`. Appended only when the subject has a band, so
    # every circuit filed before bands keeps its key.
    if subject.get("band") not in (None, ""):
        key += "|%s" % subject["band"]
    return key


def _circuit_name(subject):
    """`DEWEY r4 s1 Precon1 SPC · High tone → Low Tone · state`.

    A part nobody filled in is left out rather than printed as "None" -- a
    name that says `rNone` is worse than a shorter one.
    """
    def part(prefix, v):
        return "%s%s" % (prefix, v) if v not in (None, "") else None
    phase = subject.get("phase")
    phase_n = subject.get("phase_n")
    ph = ("%s%s" % (phase, phase_n if phase_n not in (None, "") else "")
          if phase not in (None, "") else None)
    head = " ".join(p for p in (
        part("", subject.get("project")),
        part("r", subject.get("mouse")),
        part("s", subject.get("session")),
        ph,
        part("", subject.get("run"))) if p)
    if not head:
        head = subject.get("session_label") or subject.get("gid") or "circuit"
    bits = [head, cue_label(subject.get("cue_type"), subject),
            subject.get("window_kind")]
    return " · ".join(str(b) for b in bits if b)


def _ref_id(ref):
    if isinstance(ref, dict):
        return str(ref.get("id") or ref.get("artifact_id") or "")
    return str(ref or "")


def _drift_side(subject, side):
    refs = subject.get(side) or []
    if not isinstance(refs, list) or not refs:
        raise ArtifactError(
            "A drift compares two groups of circuits, and its %s group is "
            "empty." % side)
    ids = sorted(_ref_id(r) for r in refs)
    if not all(ids):
        raise ArtifactError(
            "Every member of a drift's %s group has to name the circuit "
            "artifact it is." % side)
    return ids


def _drift_pins(subject, side):
    """The side's members as `id@version_id` (or `id` alone for a ref that
    carries no version id), sorted. Drift pins circuits by version id
    (arc_contracts.md 0b), so the same members at the same versions find
    the same drift and a re-run confirms; a member at a NEW version is a
    different comparison and a different drift."""
    _drift_side(subject, side)                  # the refusals, as before
    out = []
    for r in subject.get(side) or []:
        vid = r.get("version_id") if isinstance(r, dict) else None
        out.append(_ref_id(r) + ("@" + str(vid) if vid else ""))
    return sorted(out)


def _drift_key(subject):
    left = _drift_pins(subject, "left")
    right = _drift_pins(subject, "right")
    h = lambda ids: hashlib.sha1(",".join(ids).encode("utf-8")).hexdigest()[:12]
    key = "drift|%s|%s|%s|%s" % (h(left), h(right),
                                 subject.get("cue_type") or "",
                                 subject.get("window_kind") or "")
    # A comparison made under a recorded cue equivalence is not the same
    # comparison as one made without it (arc_contracts.md 0a).
    eq = sorted("%s=%s" % tuple(sorted((str(e.get("from")), str(e.get("to")))))
                for e in (subject.get("cue_equivalence") or [])
                if isinstance(e, dict))
    if eq:
        key += "|eq:" + hashlib.sha1(",".join(eq).encode("utf-8")) \
            .hexdigest()[:12]
    # Nor is one made with other analysis choices -- within rat, another
    # test, BH scope or contrast, or other baseline circuits (arc_contracts.md
    # 7.4): the same circuits, a different comparison, so a different drift
    # rather than a new version of the default one. A default drift's
    # subject has neither field, so its key is unchanged.
    if subject.get("analysis") or subject.get("baseline"):
        blob = json.dumps({"analysis": subject.get("analysis") or {},
                           "baseline": sorted(
                               "%s@%s>%s" % (b.get("id"), b.get("version_id"),
                                             b.get("for"))
                               for b in subject.get("baseline") or []
                               if isinstance(b, dict))},
                          sort_keys=True, separators=(",", ":"))
        key += "|an:" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
    return key


def _drift_name(subject):
    def side(s):
        label = subject.get(s + "_label")
        if label:
            return str(label)
        n = len(subject.get(s) or [])
        return "%d circuit%s" % (n, "" if n == 1 else "s")
    bits = ["%s vs %s" % (side("left"), side("right")),
            cue_label(subject.get("cue_type"), subject),
            subject.get("window_kind")]
    # A band drift (7.1) and a contrast (7.4) say so; a default drift's
    # subject has neither, so its name is what it always was.
    bits.append(subject.get("band_label") or subject.get("band"))
    bits.append({"baseline": "cue − baseline",
                 "roles": "food − no-food"}.get(
        (subject.get("analysis") or {}).get("contrast")))
    return " · ".join(str(b) for b in bits if b)


def _count_cells(cells):
    n = 0
    for per_method in (cells or {}).values():
        for per_pair in (per_method or {}).values():
            n += len(per_pair or {})
    return n


def _circuit_summary(payload):
    try:
        from . import circuit as circuitmod
        got = circuitmod.summary(payload)
        if isinstance(got, dict):
            return plain(got)
    except Exception:                                    # noqa: BLE001
        pass
    p = payload or {}
    return {"n_pairs": p.get("n_pairs"),
            "cells": _count_cells(p.get("cells")),
            "grey": len(p.get("grey") or []),
            "windows": len(p.get("windows") or [])}


def _drift_summary(payload):
    try:
        from . import drift as driftmod
        fn = getattr(driftmod, "summary", None)
        if callable(fn):
            got = fn(payload)
            if isinstance(got, dict):
                return plain(got)
    except Exception:                                    # noqa: BLE001
        pass
    p = payload or {}
    return {"left_k": len(((p.get("left") or {}).get("members")) or []),
            "right_k": len(((p.get("right") or {}).get("members")) or []),
            "cells": _count_cells(p.get("cells"))}


def _circuit_gids(subject):
    return [subject.get("gid")] if subject.get("gid") else []


def _drift_gids(subject):
    out = []
    for side in ("left", "right"):
        for r in (subject.get(side) or []):
            if isinstance(r, dict) and r.get("gid"):
                out.append(r["gid"])
    return out


# The registry of kinds. Open -- a later tool calls register_kind -- and
# closed to anything unregistered, because an artifact nobody can key, name
# or summarise is one nobody can find again.
KINDS = {}


def register_kind(kind, key, name, summary=None, gids=None, noun=None):
    KINDS[kind] = {"key": key, "name": name,
                   "summary": summary or (lambda p: {}),
                   "gids": gids or (lambda s: []),
                   "noun": noun or kind}


register_kind("circuit", _circuit_key, _circuit_name, _circuit_summary,
              _circuit_gids, "circuit")
register_kind("drift", _drift_key, _drift_name, _drift_summary,
              _drift_gids, "drift")


# The Monolith (backend/monolith.py): one sweep of every coupling measure,
# 1-55 Hz, pooled over rats. One artifact per analysis; each build of it is
# a version. The payload is what the page needs to say what it shows -- the
# points of interest, the counts, what went in -- and names the data files
# beside it by digest; the arrays themselves are tens of megabytes and stay
# on the machine that built them.
def _monolith_key(subject):
    _need(subject, ("analysis",), "monolith")
    return "monolith|%s" % subject["analysis"]


def _monolith_name(subject):
    return subject.get("name") or "Monolith · %s" % subject["analysis"]


def _monolith_summary(payload):
    p = payload or {}
    c = p.get("counts") or {}
    return {"rats": len(p.get("rats") or []),
            "tested": c.get("tested"), "p05": c.get("p05"),
            "points": len((p.get("top") or {}).get("raw") or [])}


def _monolith_gids(subject):
    return [g for g in (subject.get("gids") or []) if g]


register_kind("monolith", _monolith_key, _monolith_name, _monolith_summary,
              _monolith_gids, "monolith")


# Root Canal's Pooled view (backend/rootcanalpool.py): several recordings'
# Root Canal answers pooled and re-clustered, asking whether dentate spikes
# and IEDs are two groups or one spectrum. A pool is its own subject: its key
# is a MINTED `pool_key`, not derived from the members, because the same
# members pooled twice on purpose -- two different questions somebody wants
# to keep apart -- must be two artifacts. Saving the same pool again with
# other members or overrides is a version of it. The person's label is the
# artifact's nickname, and the name is worked out from what is in it.
def _rcpool_key(subject):
    _need(subject, ("pool_key",), "Root Canal pool")
    return "rootcanal_pool|%s" % subject["pool_key"]


def _rcpool_name(subject):
    return subject.get("name") or "Root Canal pool"


def _rcpool_summary(payload):
    p = payload or {}
    mem = p.get("members") or []
    g = p.get("gmm") or {}
    return {"members": len(mem),
            "unbanked": sum(1 for m in mem if not m.get("banked")),
            "events": p.get("n"),
            "mice": len({m.get("mouse_key") for m in mem}),
            "delta_bic": g.get("delta"),
            "switch_rate": (p.get("switches") or {}).get("rate")}


def _rcpool_gids(subject):
    return [g for g in (subject.get("gids") or []) if g]


register_kind("rootcanal_pool", _rcpool_key, _rcpool_name, _rcpool_summary,
              _rcpool_gids, "Root Canal pool")


# A Root Canal MARGIN: a set of k cluster centres and their DS / IED calls,
# saved under a name so the same boundary can be applied to any other
# Single or Pooled analysis. Its own subject, like a pool: the same group
# can be cut twice on purpose, so the identity is a minted key.
def _rcmargin_key(subject):
    _need(subject, ("margin_key",), "Root Canal margin")
    return "rootcanal_margin|%s" % subject["margin_key"]


def _rcmargin_name(subject):
    return subject.get("name") or "Root Canal margin"


def _rcmargin_summary(payload):
    p = payload or {}
    cl = p.get("clusters") or []
    src = p.get("source") or {}
    return {"k": p.get("k"),
            "ied": sum(1 for c in cl if c.get("call") == "ied"),
            "ds": sum(1 for c in cl if c.get("call") == "ds"),
            "source": src.get("kind"), "events": src.get("n_events"),
            "filter": (p.get("measure") or {}).get("filter_label")}


def _rcmargin_gids(subject):
    return [g for g in (subject.get("gids") or []) if g]


register_kind("rootcanal_margin", _rcmargin_key, _rcmargin_name,
              _rcmargin_summary, _rcmargin_gids, "Root Canal margin")


def subject_key(kind, subject):
    if kind not in KINDS:
        raise ArtifactError(
            "Jarvis does not know what a %r artifact is. The kinds it keeps "
            "are %s." % (kind, ", ".join(sorted(KINDS))))
    if not isinstance(subject, dict):
        raise ArtifactError("An artifact's subject has to be a dict.")
    return KINDS[kind]["key"](subject)


# ==========================================================================
# The store
# ==========================================================================
class Artifacts:
    def __init__(self, logs_dir, store):
        self.root = os.path.join(os.path.abspath(logs_dir), "artifacts")
        self.snap_root = os.path.join(self.root, "snap")
        self.store = store
        os.makedirs(self.snap_root, exist_ok=True)
        self._books = {}
        # Push bookkeeping for cloudsync: set when a pull brought in
        # something that means the cloud copy is behind this one.
        self.cloud_dirty = False

    # -- books ------------------------------------------------------------
    def book(self, kind):
        if kind not in KINDS:
            raise ArtifactError(
                "Jarvis does not know what a %r artifact is. The kinds it "
                "keeps are %s." % (kind, ", ".join(sorted(KINDS))))
        b = self._books.get(kind)
        if b is None:
            b = shards.Book(os.path.join(self.root, kind), {
                # Per version, not whole-list: two machines re-running the
                # same circuit both mint "v2", and last-write-wins would lose
                # one of them outright. Each row carries its own `id`.
                "versions": shards.BYID,
                # Every citation anyone has made. A Drift made on the rig and
                # one made on the desktop both protect what they cite.
                "cited": shards.UNION,
                # Birth facts never move.
                "added": shards.FIRST,
            }, self.store)
            self._books[kind] = b
        return b

    def _kinds_on_disk(self):
        out = list(KINDS)
        try:
            for name in os.listdir(self.root):
                if (name != "snap" and name not in out
                        and os.path.isdir(os.path.join(self.root, name))):
                    out.append(name)
        except OSError:
            pass
        return [k for k in out if k in KINDS]

    def signature(self):
        """Changes whenever any record or snapshot here does."""
        sig = []
        for kind in self._kinds_on_disk():
            sig.append((kind, self.book(kind).signature()))
        try:
            for d in sorted(os.listdir(self.snap_root)):
                try:
                    sig.append((d, tuple(sorted(
                        os.listdir(os.path.join(self.snap_root, d))))))
                except OSError:
                    continue
        except OSError:
            pass
        return tuple(sig)

    def _kind_of(self, artifact_id):
        artifact_id = str(artifact_id or "")
        for kind in self._kinds_on_disk():
            if artifact_id in self.book(kind).bases():
                return kind
        return None

    def _read(self, artifact_id):
        """The merged record WITH its `_sync` block, for writing back."""
        kind = self._kind_of(artifact_id)
        if not kind:
            return None, None
        return kind, self.book(kind).read(str(artifact_id))

    @staticmethod
    def _clean(rec):
        if not rec:
            return None
        out = {k: rec.get(k) for k in FIELDS}
        out["versions"] = [dict(v) for v in (rec.get("versions") or [])
                           if isinstance(v, dict)]
        out["versions"].sort(key=lambda v: (v.get("v") or 0, v.get("at") or "",
                                            v.get("id") or ""))
        out["cited"] = [dict(c) for c in (rec.get("cited") or [])
                        if isinstance(c, dict)]
        return out

    def _write(self, kind, rec):
        body = {k: rec.get(k) for k in FIELDS}
        if rec.get("_sync"):
            body["_sync"] = rec["_sync"]
        with _LOCK:
            out = self.book(kind).write(str(rec["id"]), body)
        return self._clean(out)

    def _prov(self):
        try:
            return dict(self.store.provenance() or {}) if self.store else {}
        except Exception:                                # noqa: BLE001
            return {}

    # -- snapshots --------------------------------------------------------
    def snap_path(self, artifact_id, v, dig):
        return os.path.join(self.snap_root, str(artifact_id),
                            "v%d__%s.json" % (int(v), dig))

    def _write_snap(self, artifact_id, v, dig, payload):
        """Write one version's payload, once.

        Never rewritten. If the file is already there it is compared, not
        replaced: the same name with different content means something is
        wrong upstream, and overwriting it would destroy the only evidence.
        """
        path = self.snap_path(artifact_id, v, dig)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    have = json.load(fh)
            except (OSError, ValueError):
                have = None
            if have is not None and digest(have) == dig:
                return path
            # A file that does not read at all is a torn write -- the
            # computer went off between the rename and the bytes -- not
            # evidence of a different answer, so it is written again.
            if have is not None:
                raise ArtifactError(
                    "The stored payload for %s v%d already exists and does "
                    "not match digest %s. Nothing was overwritten." % (
                        artifact_id, int(v), dig))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True,
                      ensure_ascii=False, allow_nan=False)
            # To the disk before the rename, as shards.py does for the
            # records: a record that names this version must never outlive
            # the payload it names.
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        if self.store:
            try:
                self.store._stage(path)
            except Exception:                            # noqa: BLE001
                pass
        return path

    def has_payload(self, artifact_id, ver):
        try:
            return os.path.isfile(self.snap_path(artifact_id, ver.get("v"),
                                                 ver.get("digest")))
        except (TypeError, ValueError):
            return False

    # -- versions ---------------------------------------------------------
    @staticmethod
    def _current_row(rec):
        vs = [v for v in (rec.get("versions") or []) if isinstance(v, dict)]
        if not vs:
            return None
        return max(vs, key=lambda v: (v.get("v") or 0, v.get("at") or "",
                                      v.get("id") or ""))

    def _pick(self, rec, version=None):
        """One version row, by number, by `v3`, or by its version id.

        None is the current version. A NUMBER that two machines both minted
        is refused rather than answered: there is no defensible way to pick
        between them, and a wrong pick here hands a Drift somebody else's
        numbers. Ask by the version id instead, which is unique.
        """
        vs = [v for v in (rec.get("versions") or []) if isinstance(v, dict)]
        if version in (None, ""):
            row = self._current_row(rec)
            if row is None:
                raise ArtifactError("This artifact has no versions.")
            return row
        if isinstance(version, str) and not re.fullmatch(r"v?\d+", version):
            hit = [v for v in vs if v.get("id") == version]
            if not hit:
                raise ArtifactError("This artifact has no version %r."
                                    % version)
            return hit[0]
        try:
            num = int(str(version).lstrip("v"))
        except (TypeError, ValueError):
            raise ArtifactError("%r is not a version." % (version,))
        hit = [v for v in vs if v.get("v") == num]
        if not hit:
            raise ArtifactError("This artifact has no version %d." % num)
        if len(hit) > 1:
            raise ArtifactError(
                "Two machines both made a v%d of this artifact (%s). Ask for "
                "one by its version id." % (
                    num, ", ".join("%s on %s" % (h.get("id"), h.get("machine"))
                                   for h in hit)))
        return hit[0]

    def _version_row(self, payload, params, inputs, by, note, v, kind):
        prov = self._prov()
        params = plain(params or {})
        row = {
            "v": int(v),
            "id": uuid.uuid4().hex[:12],
            "digest": digest(payload),
            "at": prov.get("at") or _now_utc(),
            "by": by or prov.get("user"),
            "machine": prov.get("machine"),
            "app_version": prov.get("app_version"),
            "commit": prov.get("commit"),
            "params": params,
            "params_hash": _hash_of(params),
            "inputs": plain(inputs or []),
            "note": note,
        }
        try:
            row["n_summary"] = plain(KINDS[kind]["summary"](payload))
        except Exception:                                # noqa: BLE001
            row["n_summary"] = {}
        return row

    # ======================================================================
    # The contract
    # ======================================================================
    def create(self, kind, subject, payload, params=None, inputs=None,
               name=None, nickname=None, by=None, note=None):
        """A new artifact, at version 1.

        Refuses when one already exists for this subject: re-running a
        circuit on the same recording, cue type and kind must add a version
        to the artifact that is there (`find`, then `add_version` -- or
        `put`, which does both), not mint a second one nobody could tell
        from the first.
        """
        if not isinstance(payload, dict):
            raise ArtifactError("An artifact's payload has to be a dict.")
        subject = plain(subject or {})
        key = subject_key(kind, subject)
        with _LOCK:
            have = self.find(kind, key)
            if have:
                raise ArtifactError(
                    "There is already a %s for this subject (%s, %s). "
                    "Add a version to it instead." % (
                        KINDS[kind]["noun"], have.get("nickname")
                        or have.get("name"), have.get("id")))
            payload = plain(payload)
            prov = self._prov()
            aid = uuid.uuid4().hex[:12]
            row = self._version_row(payload, params, inputs, by, note, 1, kind)
            self._write_snap(aid, 1, row["digest"], payload)
            nick = (str(nickname).strip() or None) if nickname else None
            rec = {
                "id": aid,
                "kind": kind,
                "schema": SCHEMA,
                "subject": subject,
                "subject_key": key,
                "name": name or KINDS[kind]["name"](subject),
                "nickname": nick,
                "version": 1,
                "versions": [row],
                "cited": [],
                "added": {"by": row["by"], "at": row["at"],
                          "machine": prov.get("machine")},
                "deleted": None,
            }
            return self._write(kind, rec)

    def add_version(self, artifact_id, payload, params=None, inputs=None,
                    by=None, note=None):
        """A re-run's answer.

        If it is byte-for-byte the current version's answer (by digest),
        there is no new version: the current one is stamped `confirmed` --
        who reproduced it, when, where -- and the record comes back
        otherwise unchanged. Only a different answer makes a new version.
        """
        if not isinstance(payload, dict):
            raise ArtifactError("An artifact's payload has to be a dict.")
        with _LOCK:
            kind, rec = self._read(artifact_id)
            if not rec:
                raise ArtifactError("There is no artifact %r." % artifact_id)
            if rec.get("deleted"):
                raise ArtifactError(
                    "That %s was deleted, so it takes no new versions. Run "
                    "it again to make a new one." % KINDS[kind]["noun"])
            payload = plain(payload)
            dig = digest(payload)
            cur = self._current_row(rec)
            prov = self._prov()
            if cur is not None and cur.get("digest") == dig:
                confirmed = list(cur.get("confirmed") or [])
                confirmed.append({
                    "at": prov.get("at") or _now_utc(),
                    "by": by or prov.get("user"),
                    "machine": prov.get("machine"),
                    "app_version": prov.get("app_version"),
                    "commit": prov.get("commit"),
                    "params_hash": _hash_of(plain(params or {})),
                    "note": note,
                })
                cur["confirmed"] = confirmed
                # Whatever the machine that made it, a confirmation means
                # the payload is here now too.
                self._write_snap(rec["id"], cur["v"], dig, payload)
                return self._write(kind, rec)
            top = max([v.get("v") or 0 for v in (rec.get("versions") or [])]
                      or [0])
            row = self._version_row(payload, params, inputs, by, note,
                                    top + 1, kind)
            self._write_snap(rec["id"], row["v"], dig, payload)
            rec["versions"] = list(rec.get("versions") or []) + [row]
            rec["version"] = row["v"]
            return self._write(kind, rec)

    def put(self, kind, subject, payload, params=None, inputs=None,
            by=None, note=None, name=None, nickname=None):
        """`find`, then `add_version` or `create`. What a producer calls."""
        with _LOCK:
            have = self.find(kind, subject_key(kind, plain(subject or {})))
            if have:
                return self.add_version(have["id"], payload, params=params,
                                        inputs=inputs, by=by, note=note)
            return self.create(kind, subject, payload, params=params,
                               inputs=inputs, name=name, nickname=nickname,
                               by=by, note=note)

    def find(self, kind, subject_key_or_subject):
        """The one live artifact for this subject, or None.

        Takes the key string or the subject dict. A deleted artifact is not
        found: re-running after a deletion starts a new one rather than
        quietly resurrecting what somebody chose to remove.
        """
        key = subject_key_or_subject
        if isinstance(key, dict):
            key = subject_key(kind, key)
        hits = [r for r in self._all(kind)
                if r.get("subject_key") == key and not r.get("deleted")]
        if not hits:
            return None
        # Two machines minting the same subject offline is possible; the
        # older one is THE artifact, as FIRST settles a gid.
        hits.sort(key=lambda r: ((r.get("added") or {}).get("at") or "",
                                 r.get("id") or ""))
        return hits[0]

    def _all(self, kind):
        return [self._clean(r) for r in self.book(kind).all()]

    def get(self, artifact_id):
        """The record, without payloads, or None."""
        _kind, rec = self._read(artifact_id)
        return self._clean(rec) if rec else None

    def payload(self, artifact_id, version=None):
        """That version's payload, or None when it is not on this machine.

        Verified on the way out: a stored payload whose digest no longer
        matches its version is refused, because handing a Drift numbers that
        are not what the version says it holds is the failure this store
        exists to prevent.
        """
        rec = self.get(artifact_id)
        if not rec:
            return None
        row = self._pick(rec, version)
        path = self.snap_path(rec["id"], row["v"], row["digest"])
        try:
            with open(path, "r", encoding="utf-8") as fh:
                got = json.load(fh)
        except OSError:
            return None
        except ValueError:
            raise ArtifactError("The stored payload for v%d is not readable "
                                "JSON." % row["v"])
        if digest(got) != row["digest"]:
            raise ArtifactError(
                "The stored payload for v%d does not match its digest (%s "
                "on disk, %s on the version). It has been changed since it "
                "was written." % (row["v"], digest(got), row["digest"]))
        return got

    def payload_version(self, artifact_id, version=None):
        """(record, version row) -- what the payload route reports beside
        the payload."""
        rec = self.get(artifact_id)
        if not rec:
            return None, None
        return rec, self._pick(rec, version)

    def list(self, kind=None, gid=None, include_deleted=False):
        """Summaries: the record plus `current`, `n_versions` and
        `cited_active`, with each version marked `here` when its payload is
        on this machine. No payloads."""
        kinds = [kind] if kind else self._kinds_on_disk()
        live = {}
        for k in kinds:
            for r in self._all(k):
                live[r["id"]] = r
        # Every kind, for resolving who cites what, not only the one asked for.
        known = dict(live)
        if kind:
            for k in self._kinds_on_disk():
                if k != kind:
                    for r in self._all(k):
                        known[r["id"]] = r
        out = []
        for r in live.values():
            if r.get("deleted") and not include_deleted:
                continue
            if gid and gid not in KINDS[r["kind"]]["gids"](r.get("subject")
                                                            or {}):
                continue
            out.append(self._summary(r, known))
        out.sort(key=lambda r: (r.get("kind") or "",
                                ((r.get("current") or {}).get("at") or "")),
                 reverse=False)
        return out

    def _summary(self, r, known=None):
        s = dict(r)
        s["versions"] = [dict(v, here=self.has_payload(r["id"], v))
                         for v in r.get("versions") or []]
        s["current"] = next((v for v in s["versions"]
                             if v.get("id") == (self._current_row(r) or {})
                             .get("id")), None)
        s["n_versions"] = len(s["versions"])
        s["cited_active"] = len(self._active_cites(r, known=known))
        return s

    def summary(self, artifact_id):
        rec = self.get(artifact_id)
        return self._summary(rec) if rec else None

    def set_nickname(self, artifact_id, nickname, by=None):
        """The user's own name for it. Empty clears it back to the name."""
        with _LOCK:
            kind, rec = self._read(artifact_id)
            if not rec:
                raise ArtifactError("There is no artifact %r." % artifact_id)
            nick = str(nickname or "").strip() or None
            if nick and len(nick) > 160:
                raise ArtifactError("A nickname is a name, not a note: keep "
                                    "it under 160 characters.")
            if nick == rec.get("nickname"):
                return self._clean(rec)
            rec["nickname"] = nick
            return self._write(kind, rec)

    def cite(self, artifact_id, version, by_artifact_id, by_version):
        """Record that `by_artifact_id` at `by_version` read this version.

        Written on the CITED artifact, which is where the delete refusal
        has to look. Idempotent: citing the same thing twice is one citation.
        """
        with _LOCK:
            kind, rec = self._read(artifact_id)
            if not rec:
                raise ArtifactError("There is no artifact %r to cite."
                                    % artifact_id)
            row = self._pick(rec, version)
            if not self._kind_of(by_artifact_id):
                raise ArtifactError("There is no artifact %r doing the citing."
                                    % by_artifact_id)
            try:
                bv = int(str(by_version).lstrip("v"))
            except (TypeError, ValueError):
                raise ArtifactError("%r is not a version." % (by_version,))
            cid = "%s:%s>%s:%d" % (rec["id"], row["id"], by_artifact_id, bv)
            cited = list(rec.get("cited") or [])
            if any(c.get("id") == cid for c in cited):
                return None
            cited.append({"id": cid, "version": row["v"],
                          "version_id": row["id"], "digest": row["digest"],
                          "by_id": str(by_artifact_id), "by_version": bv,
                          "at": _now_utc()})
            rec["cited"] = cited
            self._write(kind, rec)
            return None

    def _active_cites(self, rec, version_row=None, known=None):
        """Citations that still protect: the citing artifact exists and has
        not been deleted. One this machine has never seen still counts --
        absent is not the same as deleted."""
        out = []
        for c in rec.get("cited") or []:
            if version_row is not None and not (
                    c.get("version_id") == version_row.get("id")
                    or (not c.get("version_id")
                        and c.get("version") == version_row.get("v"))):
                continue
            by = (known or {}).get(c.get("by_id")) if known is not None \
                else self.get(c.get("by_id"))
            if by and by.get("deleted"):
                continue
            out.append(dict(c, by=by))
        return out

    def cited_by(self, artifact_id, version=None):
        """Who cites this artifact (or one version of it), with the citing
        artifact's name, nickname and kind where this machine knows it."""
        rec = self.get(artifact_id)
        if not rec:
            return []
        row = self._pick(rec, version) if version not in (None, "") else None
        out = []
        for c in self._active_cites(rec, row):
            by = c.pop("by", None) or {}
            c["by_kind"] = by.get("kind")
            c["by_name"] = by.get("name")
            c["by_nickname"] = by.get("nickname")
            c["by_known"] = bool(by)
            out.append(c)
        return out

    def _cite_sentence(self, rec, cites):
        noun = KINDS.get(rec.get("kind"), {}).get("noun", "artifact")
        parts = []
        for c in cites:
            by = c.get("by") or {}
            what = by.get("nickname") or by.get("name")
            if what:
                parts.append("%s “%s” v%s cites v%s" % (
                    KINDS.get(by.get("kind"), {}).get("noun", "artifact")
                    .capitalize(), what, c.get("by_version"), c.get("version")))
            else:
                parts.append("artifact %s v%s (not on this machine yet) "
                             "cites v%s" % (c.get("by_id"), c.get("by_version"),
                                            c.get("version")))
        return ("This %s cannot be deleted: %s. A version something cites "
                "has to stay restorable, so delete %s first."
                % (noun, "; ".join(parts),
                   "that" if len(parts) == 1 else "those"))

    def delete(self, artifact_id, by=None):
        """Soft delete. Refused, with a sentence naming them, while anything
        live cites any of its versions. The payloads stay on disk either
        way -- a snapshot is never removed."""
        with _LOCK:
            kind, rec = self._read(artifact_id)
            if not rec:
                raise ArtifactError("There is no artifact %r." % artifact_id)
            if rec.get("deleted"):
                return self._clean(rec)
            cites = self._active_cites(rec)
            if cites:
                raise ArtifactError(self._cite_sentence(rec, cites))
            prov = self._prov()
            rec["deleted"] = {"by": by or prov.get("user"),
                              "at": prov.get("at") or _now_utc()}
            return self._write(kind, rec)

    # ======================================================================
    # Harness only: removal without trace
    # ======================================================================
    def erase(self, artifact_id):
        """Remove an artifact everywhere this clone can see it, snapshots
        included. NOT part of the contract and never reached from the
        interface: app.py only lets a harness call it, on artifacts whose
        subject it made. A real artifact is deleted softly and its payloads
        are kept for ever."""
        with _LOCK:
            kind = self._kind_of(artifact_id)
            gone = 0
            if kind:
                gone = self.book(kind).erase(str(artifact_id))
            snap = os.path.join(self.snap_root, str(artifact_id))
            if os.path.isdir(snap):
                shutil.rmtree(snap, ignore_errors=True)
                gone += 1
            return gone

    # ======================================================================
    # Cloud: what cloudsync sends and takes
    # ======================================================================
    def cloud_fingerprint(self, rec):
        """What the cloud row has to agree with for this machine to have
        nothing to send: which versions, how often each was confirmed, who
        cites what, the nickname and whether it is deleted."""
        return _hash_of({
            "versions": sorted("%s:%d" % (v.get("id"),
                                          len(v.get("confirmed") or []))
                               for v in rec.get("versions") or []),
            "cited": sorted(c.get("id") or "" for c in rec.get("cited") or []),
            "nickname": rec.get("nickname"),
            "deleted": bool(rec.get("deleted")),
        })

    def records_for_cloud(self):
        """(record, nickname stamp) for every artifact on this machine,
        deleted ones included -- a deletion has to travel too."""
        out = []
        for kind in self._kinds_on_disk():
            for raw in self.book(kind).all():
                stamp = ((raw.get("_sync") or {}).get("fstamps") or {}) \
                    .get("nickname")
                out.append((self._clean(raw), stamp))
        return out

    def snapshots(self):
        """(artifact_id, version row, payload) for every version whose
        payload is on this machine."""
        out = []
        for kind in self._kinds_on_disk():
            for rec in self._all(kind):
                for ver in rec.get("versions") or []:
                    if not self.has_payload(rec["id"], ver):
                        continue
                    try:
                        with open(self.snap_path(rec["id"], ver["v"],
                                                 ver["digest"]),
                                  "r", encoding="utf-8") as fh:
                            out.append((rec["id"], ver, json.load(fh)))
                    except (OSError, ValueError):
                        continue
        return out

    def absorb_record(self, row):
        """Take on what another machine knows about an artifact.

        Only ever ADDS versions and citations, by id -- a version this
        machine has is left exactly as it is. The nickname follows the newer
        stamp. A deletion is taken unless something here still cites it, in
        which case it is refused and reported: the other machine deleted it
        without knowing about the citation, and the citation wins.

        Returns "added", "merged", "same", "refused" or a conflict string.
        """
        kind = row.get("kind")
        if kind not in KINDS or not row.get("id"):
            return "refused"
        with _LOCK:
            _k, rec = self._read(row["id"])
            if not rec:
                body = {k: plain(row.get(k)) for k in FIELDS}
                body["versions"] = [
                    {k: v.get(k) for k in VERSION_FIELDS if k in v}
                    for v in (row.get("versions") or []) if isinstance(v, dict)]
                body["cited"] = [c for c in (row.get("cited") or [])
                                 if isinstance(c, dict)]
                body["schema"] = body.get("schema") or SCHEMA
                if not body["versions"]:
                    return "refused"
                self._write(kind, body)
                return "added"

            changed = False
            have = {v.get("id") for v in rec.get("versions") or []}
            versions = list(rec.get("versions") or [])
            for v in row.get("versions") or []:
                if isinstance(v, dict) and v.get("id") and v["id"] not in have:
                    versions.append({k: v.get(k) for k in VERSION_FIELDS
                                     if k in v})
                    have.add(v["id"])
                    changed = True
                elif isinstance(v, dict) and v.get("id") in have:
                    # More confirmations over there: take the longer list.
                    mine = next(x for x in versions if x.get("id") == v["id"])
                    theirs = v.get("confirmed") or []
                    if len(theirs) > len(mine.get("confirmed") or []):
                        mine["confirmed"] = theirs
                        changed = True
            if changed:
                rec["versions"] = versions
                top = self._current_row(rec)
                if top and (rec.get("version") or 0) < top.get("v", 0):
                    rec["version"] = top["v"]

            cids = {c.get("id") for c in rec.get("cited") or []}
            cited = list(rec.get("cited") or [])
            for c in row.get("cited") or []:
                if isinstance(c, dict) and c.get("id") and c["id"] not in cids:
                    cited.append(c)
                    cids.add(c["id"])
                    changed = True
            rec["cited"] = cited

            ours_at = _parse_ts(((rec.get("_sync") or {}).get("fstamps") or {})
                                .get("nickname"))
            theirs_at = _parse_ts(row.get("nickname_at"))
            if (row.get("nickname") or None) != (rec.get("nickname") or None) \
                    and theirs_at and (ours_at is None or theirs_at > ours_at):
                rec["nickname"] = row.get("nickname") or None
                changed = True

            clash = None
            if row.get("deleted") and not rec.get("deleted"):
                live = self._active_cites(rec)
                if live:
                    clash = ("conflict: %s was deleted on another machine, and "
                             "is still cited here (%d citation%s), so it was "
                             "kept." % (row["id"], len(live),
                                        "" if len(live) == 1 else "s"))
                    # This machine's copy is ahead of the cloud's.
                    self.cloud_dirty = True
                else:
                    rec["deleted"] = row["deleted"]
                    changed = True
            if changed:
                self._write(kind, rec)
            if clash:
                return clash
            return "merged" if changed else "same"

    def absorb_snapshot(self, artifact_id, version_id, v, dig, payload):
        """Fill in one version's payload from another machine.

        "added", "already", "unknown" or a conflict string. Never overwrites
        -- see `_write_snap` -- and checks the payload against the digest it
        arrived with AND the digest the version says, so a truncated or
        altered transfer is reported rather than filed.
        """
        rec = self.get(artifact_id)
        if not rec or payload is None:
            return "unknown"
        row = next((x for x in rec.get("versions") or []
                    if x.get("id") == version_id), None)
        if row is None:
            return "unknown"
        got = digest(payload)
        if got != row.get("digest") or (dig and got != dig):
            return ("conflict: %s v%s arrived with content whose digest is %s, "
                    "and the version says %s. Not filed." % (
                        artifact_id, row.get("v"), got, row.get("digest")))
        path = self.snap_path(artifact_id, row["v"], row["digest"])
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    have = json.load(fh)
            except (OSError, ValueError):
                have = None
            if have is not None and digest(have) == row["digest"]:
                return "already"
            return ("conflict: %s v%s is on this machine with different "
                    "content from its digest. Nothing was overwritten."
                    % (artifact_id, row.get("v")))
        self._write_snap(artifact_id, row["v"], row["digest"], plain(payload))
        return "added"
