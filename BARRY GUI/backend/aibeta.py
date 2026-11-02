"""
aibeta.py -- AI Beta: can a model sort dentate spike candidates the way
people did?

A SANDBOX, AND ONLY A SANDBOX
-----------------------------
This trains a model on what Checkup has already decided and tests it on
decisions it was not trained on. That is all it does. Nothing here writes a
label, a curation set, a bank version or anything Braces reads; the only
things it files are its own run records and the model it trained, under
`GUI_logs/aibeta/`. Running it on new, undecided sets is a later step and
deliberately not here yet -- the question this answers first is whether the
model is any good.

WHAT A TRAINING EXAMPLE IS ("watch the versions")
-------------------------------------------------
One Event Bank entry is one recording's candidates and their history. The
pattern on almost every entry is

    v0  undecided           what the detector, Toothy or Incisor, offered
    v1  a first pass        DS, Garbage, and flags
    v2  the settled pass    DS and Garbage only
    v3  aligned by Braces   the garbage gone, the stamps moved
    v4  X-ray's DS1/DS2

The model learns v0 -> the settled pass: the LAST version before Braces first
aligned the entry whose labels are only DS and Garbage. Not the curation
set's merged state, which mixes passes and machines, and not anything after
alignment, where the garbage has been removed and the stamps have moved.

A recording somebody rejected WHOLE -- every candidate Garbage -- is left out
(the user, 2026-10-02): that is a call about the recording, not about any
one event, and see `dataset` for what it did to the model. On the bank as it
stood then that leaves 41 recordings from 23 mice, 10,078 DS and 1,098
Garbage.

THE CLOCK, BEFORE ANYTHING IS READ
----------------------------------
Every feature here is read out of the raw file at a stamp, so a stamp on the
wrong clock is a window on the wrong event. Measured against Incisor, curated
stamps drift through a recording -- PTEN m59 s4 starts 3 ms early and ends
76 ms early -- which is Toothy's concatenated clock (see retime.py). Two
corrections, in order:

  1. Where the bank knows the version is on Toothy's clock, it is converted
     to the recording's own with `continuity.concat_to_true`, the same
     arithmetic Re-time uses.
  2. What is left -- the sample-rate drift Toothy's linear axis also carries,
     and anything nobody recorded -- is measured per RECORDING: for each
     stamp, how far the nearest CSD peak is, and a running median of that
     over neighbouring stamps. Per recording and not per event, so a Garbage
     stamp is never nudged onto a real spike beside it; a median, so it
     follows a step at a gap rather than smearing it.

LABEL-FREE FEATURES
-------------------
Every number that describes an event is computed without its label, and
every per-recording reference (a channel's spread, the usual depth profile,
the usual best channel) is computed over ALL of that recording's candidates,
both kinds together. A reference built from the DS alone would hand the
model the answer.

TESTED ON MICE IT NEVER SAW
---------------------------
Folds are whole mice. Sessions from one animal share a probe placement and
its noise, so a random split would test the model on recordings it had
effectively already seen and report a number nobody could reproduce on a new
animal.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import uuid

import numpy as np

from . import aibetaphys as phys
from . import aiwave
from . import braces, continuity, csc, dspca, incisor, probes, retime, shards
from . import versions as versionsmod

# Loaded on first use, not at start-up; see lazyimp.py for why.
from . import lazyimp  # noqa: E402
HAVE_SCIPY = lazyimp.have("scipy")
_sig = lazyimp.module("scipy.signal") if HAVE_SCIPY else None
HAVE_SKLEARN = lazyimp.have("sklearn")

# Bumped whenever a feature changes meaning, so a cache written by an older
# extraction is never read as if it were this one.
FEATURE_VERSION = 1

# --------------------------------------------------------------------------
# The numbers
# --------------------------------------------------------------------------
# Half-width of the window every feature is read from. A dentate spike is
# 10-20 ms wide; fifty either side holds the whole deflection and its flanks
# without reaching the next event, the same reasoning as X-ray's surround.
HALF_MS = 50.0

# How far the clock correction may look for the event. Braces' window, for
# Braces' reason: wide enough for the jitter actually seen, narrow enough that
# a stamp cannot reach the next spike in a burst.
SEARCH_MS = 100.0

# Where the best channel's peak may be, either side of the corrected stamp.
PEAK_MS = 10.0

# Read margin either side of each merged span, for the filters to settle in.
# Incisor measured the error a filter edge leaves on this band: 0.041 SD at a
# quarter of a second, 0.0015 at half. The nearest sample any feature reads
# is SEARCH_MS further in than this, so 0.35 s puts every one of them past
# half a second -- and reads a third less than X-ray's 0.5 does.
PAD_S = 0.35

# The running median the clock correction is taken over, in events, and how
# scattered those events' offsets may be before the recording is judged to
# have no clock signal to correct by. Set from Braces' measurement on
# M8s9feb8 -- a median move of 5.6 ms -- with room for a noisier recording.
CLOCK_RUN = 31
CLOCK_MAX_MAD_MS = 20.0

# Incisor's own numbers: its threshold (4.5 SD) and its peak-width window.
OVER_SD = 4.5
WLEN_MS = incisor.DS_WLEN_MS

# The fixed sizes everything is resampled to, so a 64-channel H3 and a
# column of an H10-D give the model vectors of one length.
PROFILE_ROWS = 32
WAVE_STEP_MS = 2.0
IMG_ROWS = 16
IMG_STEP_MS = 4.0

# The operating point: keep this share of real dentate spikes. Losing a real
# one is the worse mistake (the user, 2026-10-02), so the threshold is set by
# how many DS it may cost, and garbage it cannot catch at that price is what
# a person looks at.
KEEP_DS = 0.98

# The other bars a run reports, so the price of keeping more spikes can be
# read off one table: each chosen inside the training mice, like the main
# one, and applied to the mice held out.
TRADEOFF = (0.99, 0.98, 0.95, 0.90, 0.80)

# The other way round, which is the way the user asked for it (2026-10-02):
# catch this share of the garbage, and count what it costs in real spikes
# flagged. Chosen inside the training mice the same way. 100% in the
# training mice is a bar above every piece of garbage they hold; on mice it
# never saw it can still let one through, and the table says how often.
CATCH = (1.0, 0.99, 0.98, 0.95, 0.90)

# THE SWEEP'S FOUR CALLS. The model that sweeps a Checkup set (Tooth Fairy,
# toothfairy.py) calls every candidate one of four things. Its bars come
# from the held-out scores of the run it was trained in:
#
#   DS                    at or above the bar that caught 99% of garbage
#   Flag for Deep Review  just under it: between the 98% and 99% bars, the
#                         last stretch before a candidate would be accepted
#   Flag                  the rest of the way down
#   Garbage               below the score under which at least 90% of the
#                         held-out candidates were garbage
#
# So DS is the operating point the user chose -- 98.6% of garbage caught
# and 41.5% of real spikes flagged on mice it never saw -- and the flags are
# split by how close they came.
POLICY = {"ds_catch": 0.99, "review_catch": 0.98, "garbage_purity": 0.90}

# WHO A MODEL'S VERSION IS BY. An accepted sweep banks every call as a
# version of its own, tagged and authored as the model's, so training can
# tell a model's calls from a person's (`_is_model`) and never learns from
# itself. Tooth Fairy writes the first pair; the second is what the models
# before it wrote (until 2026-10-09), and is still recognised because those
# versions are still in the bank.
MODEL_TAG = "tooth_fairy"
MODEL_BY = "Tooth Fairy (AI)"
OLD_MODEL_TAGS = ("avery",)
OLD_MODEL_BY = ("Avery (AI)",)

# THE TOLERANT BARS (the user, 2026-10-02): every garbage marked so, as few real
# spikes lost as that allows, and fewer flags -- "we'd prefer to lose spikes
# than to get garbage in". So the Garbage bar is set by the spikes it may
# cost, 5% of them, instead of by how pure its calls are; the DS bar stays
# where 99% of garbage is under it, and Flag is whatever is left between.
POLICY_PLUS = {"ds_catch": 0.99, "review_catch": 0.98,
               "garbage_ds_loss": 0.05}

# Which model a sweep can use. TOOTH FAIRY (named by the user, 2026-10-07:
# "use all the information you have about what works the best", retrained
# on everything curated since). The models before it were taken out on
# 2026-10-09 at the user's word -- "remove all the Avery stuff" -- and live
# on only as runs in AI Beta and as the history in its report.
SLOTS = ("tooth_fairy",)
SLOT_NAMES = {"tooth_fairy": "Tooth Fairy"}
POLICY_LABELS = ("spike", "review", "flag", "garbage")


def label_policy(p, y, targets=None):
    """The sweep's four bars, from held-out scores and their labels."""
    t = dict(POLICY, **(targets or {}))
    p = np.asarray(p, float)
    y = np.asarray(y).astype(int)
    pg = p[y == 0]
    if not pg.size:
        raise AiBetaError("No garbage in the held-out scores to set bars by.")
    t_ds = float(np.quantile(pg, t["ds_catch"])) + 1e-9
    t_review = min(t_ds, float(np.quantile(pg, t["review_catch"])) + 1e-9)
    if t.get("garbage_ds_loss") is not None and (y == 1).any():
        # Set by the real spikes it may cost, never above the review band.
        t_garbage = min(t_review, float(np.quantile(
            p[y == 1], float(t["garbage_ds_loss"]))))
    else:
        order = np.argsort(p, kind="mergesort")
        ps, ys = p[order], y[order]
        purity = np.cumsum(ys == 0) / np.arange(1, ps.size + 1)
        ok = np.where((purity >= t["garbage_purity"]) & (ps < t_review))[0]
        t_garbage = float(ps[ok.max()]) + 1e-9 if ok.size else 0.0
    pol = {"t_ds": round(t_ds, 6), "t_review": round(t_review, 6),
           "t_garbage": round(t_garbage, 6), "targets": t}
    labs = apply_policy(p, pol)
    pol["held_out"] = {
        lab: {"n": int((labs == lab).sum()),
              "n_ds": int(((labs == lab) & (y == 1)).sum()),
              "n_garbage": int(((labs == lab) & (y == 0)).sum())}
        for lab in POLICY_LABELS}
    return pol


def apply_policy(p, pol):
    """Each score as one of spike / review / flag / garbage."""
    p = np.asarray(p, float)
    out = np.full(p.size, "flag", dtype=object)
    out[p < pol["t_garbage"]] = "garbage"
    out[(p >= pol["t_review"]) & (p < pol["t_ds"])] = "review"
    out[p >= pol["t_ds"]] = "spike"
    return out

N_FOLDS = 5
N_INNER = 3
# Two versions' stamps for one candidate, before Braces moved anything:
# the same time to the microsecond, give or take a rounding.
SAME_EVENT_S = 0.002

# Labels, by id and by display name: older bank entries carry only names.
DS_LABELS = {"spike", "dentate spike"}
GARBAGE_LABELS = {"garbage"}

FAMILIES = [
    {"id": "incisor", "name": "Incisor numbers", "default": True,
     "blurb": "Amplitude, prominence, half-width, asymmetry and the rest of "
              "what Incisor measures, taken on the channel where the event "
              "is largest."},
    {"id": "shank", "name": "Shank and CSD measures", "default": True,
     "blurb": "How the event spreads down the probe: how many contacts see "
              "it, whether its depth profile and CSD sink look like this "
              "recording's usual ones, and whether it is common to every "
              "wire, which an artifact is."},
    {"id": "waves", "name": "Waveforms", "default": True,
     "blurb": "The event itself: its trace on the best channel, the shank's "
              "CSD over time, and its depth profile, each scaled to its own "
              "size."},
    {"id": "context", "name": "Timing context", "default": True,
     "blurb": "How close the other candidates in the set are. Garbage tends "
              "to come in bursts."},
    # Off by default because it made things worse when tried, 2026-10-02:
    # with it the gradient-boosted trees caught 118 of the 1,487 candidates
    # in recordings rejected whole instead of 104, and lost more than that
    # elsewhere -- one fold's ranking fell from 0.82 to 0.61. Twelve
    # rejected recordings are too few to learn "this recording is no good"
    # from, and what it learned instead moved every score.
    {"id": "recording", "name": "Recording context", "default": False,
     "blurb": "What this recording's candidates are like taken together: "
              "their typical size, shape and spacing."},
    {"id": "csdimg", "name": "CSD image, 5-100 Hz", "default": False,
     "blurb": "The current source density around the event as a small "
              "picture, depth against time, in the dentate spike band."},
]
# The second read's inputs (aibetaphys.py): physiology rather than shape.
# Off until asked for, and read only when one of them is.
FAMILIES.extend(dict(f, default=False, phys=True) for f in phys.FAMILIES)
# Last, so a run without it keeps its columns where they always were.
FAMILIES.append(dict(aiwave.FAMILY, default=False))
FAMILY_IDS = [f["id"] for f in FAMILIES]
PHYS_IDS = frozenset(phys.FAMILY_IDS)
# Worked out from the others when features are loaded, never read from the
# recording or stored: a change to how they are summarised then costs a
# retrain, not a re-read.
DERIVED = ("recording", "wavebits")
# Neither read by the first pass nor kept in its cache.
NOT_FIRST = frozenset(DERIVED) | PHYS_IDS

MODELS = [
    {"id": "hgb", "name": "Gradient-boosted trees", "default": True,
     "blurb": "Many small decision trees, each correcting the last. "
              "Handles missing numbers and mixed scales without help."},
    {"id": "forest", "name": "Random forest", "default": False,
     "blurb": "Many independent trees, voted. Slower to overfit, usually "
              "a little less sharp."},
    {"id": "logistic", "name": "Logistic regression", "default": False,
     "blurb": "One weighted sum. A baseline: if the trees cannot beat it, "
              "the inputs are what matter, not the model."},
    {"id": "blend", "name": "Blend of boosted trees", "default": False,
     "blurb": "Five sets of boosted trees, each balanced on its own draw of "
              "the garbage and seeing half the inputs at each split, "
              "averaged. Five times slower to train; steadier on the most "
              "spike-like garbage, which is what sets how much is flagged."},
]
MODEL_IDS = [m["id"] for m in MODELS]
# What "blend" averages. Chosen 2026-10-03 on the 45 recordings of the time,
# whole-mouse CV, against one set of boosted trees on two seeds -- see the
# CHANGELOG for the numbers.
BLEND_MEMBERS = ("hgb_sub",) * 5


class AiBetaError(Exception):
    pass


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# --------------------------------------------------------------------------
# Which entries, which version, which labels
# --------------------------------------------------------------------------
def _is_model(ver):
    """A version a model wrote. Tagged when banked by an accepted sweep;
    the curation set's own version from that accept carries only the author,
    so both are asked -- Tooth Fairy's and the older models'."""
    return (ver.get("tag") in (MODEL_TAG,) + OLD_MODEL_TAGS
            or ver.get("by") in (MODEL_BY,) + OLD_MODEL_BY)


def _model_unreviewed(bank, rec, named, target, events):
    """Which of `events` hold a call a model made that nobody changed.

    An accepted sweep fills every undecided candidate with the model's call,
    and the person then works through the flags. A candidate it called DS or
    Garbage that still holds that call afterwards may never have been looked
    at -- learning from it is the model learning from itself. So such a
    candidate is left out when it was undecided before the sweep. Kept: what
    a person had decided before the sweep, everything it flagged, and
    every call a person changed. Returns a set of indices into `events`, or
    None when the versions needed to tell are not on this machine.
    """
    order = [ver for ver, _n in named]
    try:
        at = next(k for k, v in enumerate(order) if v is target)
    except StopIteration:
        return set()
    av = [k for k in range(at) if _is_model(order[k])]
    if not av:
        return set()
    pre = [k for k in range(av[0]) if not _is_model(order[k])]

    def classes(ver):
        if not ver.get("snap"):
            return None
        try:
            evs, _ = bank.events_at(rec, bank.version_key(ver))
        except Exception:                                # noqa: BLE001
            return None
        return {round(float(e["start"]), 4):
                _cls(e.get("label_id") or e.get("label")) for e in evs}

    calls = classes(order[av[-1]])
    if calls is None:
        return None
    before = classes(order[pre[-1]]) if pre else {}
    if before is None:
        return None
    out = set()
    for j, e in enumerate(events):
        t = round(float(e["t_bank"]), 4)
        a = calls.get(t)
        if a in (0, 1) and before.get(t) not in (0, 1) and e["y"] == a:
            out.add(j)
    return out


def _cls(label):
    """1 for a dentate spike, 0 for garbage, None for anything else."""
    if label is None:
        return None
    s = str(label).strip().lower()
    if s in DS_LABELS:
        return 1
    if s in GARBAGE_LABELS:
        return 0
    return None


def _settled(by_label):
    """(n_ds, n_garbage) if a version holds only DS and Garbage, else None."""
    n_ds = n_g = 0
    for k, n in (by_label or {}).items():
        if not n:
            continue
        c = _cls(k)
        if c is None:
            return None
        if c == 1:
            n_ds += int(n)
        else:
            n_g += int(n)
    if not (n_ds or n_g):
        return None
    return n_ds, n_g


def mouse_key(rec):
    """Project and mouse. Mouse numbers restart per project."""
    return "%s m%s" % (rec.get("project") or "?", rec.get("mouse") or "?")


def _first_pass(bank, rec, named, target, target_events):
    """How a person's first look compared with the settled call.

    The reference the model is measured against: the first version after
    v0 that says anything, against the settled one. Matched by position when
    both hold the same number of events -- a re-timing between them moves
    every stamp but keeps their order -- and by time otherwise.
    """
    first = None
    for ver, _name in named:
        if ver is target:
            break
        if (ver.get("v") or 0) == 0 or not ver.get("snap") \
                or _is_model(ver):
            continue
        bl = ver.get("by_label") or {}
        if any(n and str(k).strip().lower() != "unspecified"
               for k, n in bl.items()):
            first = ver
            break
    if first is None:
        return None
    try:
        evs, _ = bank.events_at(rec, bank.version_key(first))
    except Exception:                                    # noqa: BLE001
        return None
    evs = sorted(evs, key=lambda e: float(e["start"]))
    tgt = sorted(target_events, key=lambda e: e["t_bank"])
    pairs = []
    if len(evs) == len(tgt):
        pairs = [(a.get("label_id") or a.get("label"), b["y"])
                 for a, b in zip(evs, tgt)]
    else:
        at = {round(e["t_bank"], 4): e["y"] for e in tgt}
        for a in evs:
            y = at.get(round(float(a["start"]), 4))
            if y is not None:
                pairs.append((a.get("label_id") or a.get("label"), y))
    called = agree = flagged = 0
    for lab, y in pairs:
        c = _cls(lab)
        if c is None:
            if lab and str(lab).strip().lower() != "unspecified":
                flagged += 1
            continue
        called += 1
        agree += int(c == y)
    return {"called": called, "agree": agree, "flagged": flagged,
            "compared": len(pairs)}


def dataset(bank, curate=None, pin=None):
    """Every entry the model can learn from, and every one it cannot, why.

    `pin` is {entry id: version key}: learn from exactly that version of
    exactly those entries, whatever has been curated since. The bank is
    live -- three recordings were settled, and another moved to a new
    version, during one afternoon's comparison on 2026-10-02 -- so two runs
    meant to differ only in their inputs have to be pinned to one dataset or
    they differ in their data too.

    Returns {"entries": [...], "skipped": [...]}. An entry carries the
    settled version, its events as {t_bank, y}, and how a first pass by a
    person compared with it.
    """
    by_gid, skipped = {}, []
    for rec in bank.all():
        if (rec.get("type") or "") != "ds":
            continue
        pipe = (rec.get("source") or {}).get("pipeline") or ""
        label = rec.get("session_label") or rec.get("name") or rec.get("id")
        # Harness throwaways and the demo are not anybody's decisions.
        if pipe.startswith("harness") or (rec.get("project") or "") == "DEMO" \
                or str(rec.get("gid") or "").startswith(("demo", "harness")):
            continue
        if not rec.get("gid"):
            skipped.append({"label": label, "entry_id": rec.get("id"),
                            "why": "not attached to a recording"})
            continue
        named = versionsmod.label_rows(rec.get("versions") or [])
        if not named:
            continue
        # Everything before Braces first touched it -- and nothing a model
        # wrote. A model's version is its calls, banked for the record;
        # learning from it would be the model learning from itself.
        before = []
        for ver, name in named:
            if ver.get("aligned"):
                break
            if _is_model(ver):
                continue
            before.append((ver, name))
        target = tname = None
        if pin is not None:
            want_ref = pin.get(rec.get("id"))
            if want_ref is None:
                continue
            for ver, name in named:
                if bank.version_key(ver) == want_ref:
                    target, tname = ver, name
                    break
        else:
            for ver, name in reversed(before):
                if _settled(ver.get("by_label")):
                    target, tname = ver, name
                    break
        if target is None:
            skipped.append({"label": label, "entry_id": rec.get("id"),
                            "gid": rec.get("gid"),
                            "why": "no version holds only DS and Garbage "
                                   "before Braces -- not finished yet"})
            continue
        n_ds, n_g = _settled(target.get("by_label"))

        events, source = None, "bank"
        if target.get("snap"):
            try:
                evs, _ = bank.events_at(rec, bank.version_key(target))
                events = [{"t_bank": float(e["start"]),
                           "y": _cls(e.get("label_id") or e.get("label"))}
                          for e in evs]
            except Exception:                            # noqa: BLE001
                events = None
        if events is None and curate is not None:
            # The version's snapshot never reached this machine. The
            # curation set holds the same calls IF its counts agree with
            # what the bank says the version held -- checked, not assumed.
            try:
                cs = curate.get(rec["gid"], "ds") or {}
            except Exception:                            # noqa: BLE001
                cs = {}
            evs = [{"t_bank": float(e["start"]), "y": _cls(e.get("label"))}
                   for e in (cs.get("events") or [])
                   if e.get("start") is not None]
            got_ds = sum(1 for e in evs if e["y"] == 1)
            got_g = sum(1 for e in evs if e["y"] == 0)
            if evs and got_ds == n_ds and got_g == n_g \
                    and len(evs) == got_ds + got_g:
                events, source = evs, "curation set"
        if events is None:
            skipped.append({"label": label, "entry_id": rec.get("id"),
                            "gid": rec.get("gid"),
                            "why": "its settled version (%s) has no snapshot "
                                   "on this machine and the curation set "
                                   "does not match it" % tname})
            continue
        events = [e for e in events if e["y"] is not None]
        # THE GARBAGE A LATER VERSION DROPPED (2026-10-07). Eleven sets go
        # DS + Garbage, then DS alone -- the garbage deleted to make the
        # set Braces aligns -- and the DS-only version is the last settled
        # one, so 429 decided garbage were never learned from. A candidate
        # an earlier settled version called Garbage that the answer no
        # longer holds at all was deleted as garbage, and comes back as
        # garbage. One the answer still holds keeps the answer's call.
        n_restored = 0
        if source == "bank":
            order_ = [v for v, _n in named]
            upto = next((k for k, v in enumerate(order_) if v is target),
                        len(order_))
            richer = None
            for v in order_[:upto]:
                if v.get("aligned"):
                    break
                st_ = _settled(v.get("by_label"))
                if not _is_model(v) and st_ and st_[1] > 0:
                    richer = v
            if richer is not None and richer.get("snap"):
                try:
                    old_evs, _ = bank.events_at(rec, bank.version_key(richer))
                except Exception:                        # noqa: BLE001
                    old_evs = []
                have_t = np.array(sorted(e["t_bank"] for e in events))
                for e2 in old_evs:
                    if _cls(e2.get("label_id") or e2.get("label")) != 0:
                        continue
                    t = float(e2["start"])
                    k = int(np.searchsorted(have_t, t))
                    near = min((abs(have_t[q] - t) for q in (k - 1, k)
                                if 0 <= q < have_t.size), default=np.inf)
                    if near > SAME_EVENT_S:
                        events.append({"t_bank": t, "y": 0})
                        n_restored += 1
                events.sort(key=lambda e: e["t_bank"])
        # A MODEL'S OWN CALLS, where a person finished a set a model swept
        # (2026-10-07: three entries did). See `_model_unreviewed`.
        n_model = 0
        if any(_is_model(v) for v, _n in named):
            drop = _model_unreviewed(bank, rec, named, target, events)
            if drop is None:
                skipped.append({"label": label, "entry_id": rec.get("id"),
                                "gid": rec.get("gid"),
                                "why": "a model swept it, and the "
                                       "versions that tell its calls from a "
                                       "person's are not on this machine"})
                continue
            n_model = len(drop)
            events = [e for j, e in enumerate(events) if j not in drop]
        if not events:
            continue
        # REJECTED WHOLE: left out, by the user's call (2026-10-02).
        #
        # Twelve recordings had every candidate called Garbage -- 1,487
        # candidates, 57% of all the garbage -- and they came in pairs from
        # one mouse (m24, m29, m46, m48), which says the call was about the
        # animal or the placement rather than about any one event. Every
        # candidate in them looks like a dentate spike on its own, so a
        # per-candidate model caught 104 of the 1,487 and was taught that
        # spike-shaped events are garbage. "Is this recording usable" is a
        # different question and is not asked here.
        if not any(e["y"] == 1 for e in events):
            skipped.append({"label": label, "entry_id": rec.get("id"),
                            "gid": rec.get("gid"),
                            "why": "rejected whole: all %d of its candidates "
                                   "are Garbage, so it is left out"
                                   % len(events)})
            continue

        # Which clock the settled version is on. The version's own record
        # first; where it has none, what the pipeline is known to produce.
        basis = bank.basis_at(rec, target.get("v") or 0)
        if not basis:
            basis = (retime.basis_of(rec) or {}).get("basis")

        row = {
            "entry_id": rec["id"], "gid": rec["gid"], "label": label,
            "project": rec.get("project"), "mouse": rec.get("mouse"),
            "session": rec.get("session"), "mouse_key": mouse_key(rec),
            "pipeline": pipe,
            "source": ("Incisor" if pipe.startswith("Incisor")
                       else "Toothy import" if pipe.startswith("ETS")
                       else pipe or "unknown"),
            "version": bank.version_key(target),
            "version_name": tname, "version_v": target.get("v"),
            "events_from": source,
            "basis": basis,
            "n": len(events),
            "n_ds": sum(1 for e in events if e["y"] == 1),
            "n_garbage": sum(1 for e in events if e["y"] == 0),
            "n_model_left_out": n_model,
            "n_garbage_restored": n_restored,
            "events": events,
            "first_pass": _first_pass(bank, rec, named, target, events),
        }
        # One entry per recording. Two entries for one gid are two banks of
        # the same candidates, and counting both would put the same events
        # in the data twice.
        have = by_gid.get(rec["gid"])
        if have is None or row["n"] > have["n"]:
            if have is not None:
                skipped.append({"label": have["label"],
                                "entry_id": have["entry_id"],
                                "gid": have["gid"],
                                "why": "a second entry for a recording "
                                       "already in; the larger one is used"})
            by_gid[rec["gid"]] = row
        else:
            skipped.append({"label": label, "entry_id": rec["id"],
                            "gid": rec["gid"],
                            "why": "a second entry for a recording already "
                                   "in; the larger one is used"})
    # An entry skipped as unfinished whose recording IS in, through another
    # entry, is not an unfinished recording -- and saying so listed m33 s8
    # as both learned from and not finished.
    for s in skipped:
        if s.get("gid") in by_gid and \
                by_gid[s["gid"]]["entry_id"] != s.get("entry_id") and \
                not s["why"].startswith("a second entry"):
            s["why"] = ("a second entry for a recording already in; the one "
                        "with a settled version is used")
    entries = sorted(by_gid.values(), key=lambda r: (r["mouse_key"],
                                                     str(r["label"])))
    return {"entries": entries, "skipped": skipped}


def summary(ds):
    """The counts a panel states before anything is read."""
    ents = ds["entries"]
    fp = [e["first_pass"] for e in ents if e.get("first_pass")]
    called = sum(f["called"] for f in fp)
    return {
        "n_recordings": len(ents),
        "n_mice": len({e["mouse_key"] for e in ents}),
        "n_events": sum(e["n"] for e in ents),
        "n_ds": sum(e["n_ds"] for e in ents),
        "n_garbage": sum(e["n_garbage"] for e in ents),
        "by_source": _count(e["source"] for e in ents),
        "first_pass": ({"called": called,
                        "agree": sum(f["agree"] for f in fp),
                        "flagged": sum(f["flagged"] for f in fp),
                        "compared": sum(f["compared"] for f in fp),
                        "recordings": len(fp)} if fp else None),
    }


def _count(items):
    out = {}
    for it in items:
        out[it] = out.get(it, 0) + 1
    return out


# --------------------------------------------------------------------------
# Reading: the clock, the windows, the features
# --------------------------------------------------------------------------
def true_times(entry, report):
    """Each event's time on the recording's own clock, or None.

    None where a Toothy time falls past the end of the data -- an event that
    has no place on the real clock is dropped and counted, not clamped.
    """
    out = []
    concat = entry.get("basis") == retime.CONCAT
    for e in entry["events"]:
        t = e["t_bank"]
        if concat and report and report.get("ok"):
            t, _seg = continuity.concat_to_true(report, t)
        out.append(None if t is None else float(t))
    return out


# WHICH CHANNELS A RUN IS SHOWN (the user, 2026-10-05: "re run all current
# models and only feed them even channels"). "even" keeps CSC 2, 4 ... 64 --
# the channels Toothy's LL input and the sweep screen use -- and reads them
# as what they are on a linear array: every other contact, so twice the
# pitch apart. The CSD is taken over that pitch, and the second read's
# windows that are counted in contacts are halved so they cover the same
# depth. Only for a single linear array: on the H10-D or the dual array the
# even channels are not a line, so a recording on one is read the way its
# probe is laid out instead -- every channel, one column at a time, as the
# full read always has -- and says so (`subset_note`). Refusing it stopped
# Tooth Fairy sweeping PTEN m3 s7, an H10-D recording, at all.
CHANNEL_SETS = ("all", "even")


def subset_channels(rec, which):
    """`rec` (from an opener) with only the channels `which` asks for."""
    if which in (None, "all"):
        return rec
    if which not in CHANNEL_SETS:
        raise AiBetaError("No channel set %r." % which)
    if (probes.get(rec["probe"]) or {}).get("columns"):
        return dict(rec, subset_note=(
            "This recording's probe (%s) is laid out in columns, so the even "
            "channels are not a line on it; it was read the way the probe is "
            "laid out, every channel, rather than even channels only."
            % ((probes.get(rec["probe"]) or {}).get("name") or rec["probe"])))
    chans = [c for c in rec["channels"] if int(c["number"]) % 2 == 0]
    if len(chans) < 3:
        raise AiBetaError("Fewer than three even channels on this "
                          "recording.")
    pitch = rec.get("spacing") or dspca.spacing_for(rec["probe"])
    return dict(rec, channels=chans,
                bad=[int(b) for b in (rec.get("bad") or []) if int(b) % 2 == 0],
                spacing=2.0 * float(pitch), subset=which)


def cache_key(entry, probe, spacing, bad, subset=None):
    """Everything that changes what is read, and the labels it is filed with."""
    body = {
        "fv": FEATURE_VERSION,
        "entry": entry["entry_id"], "version": entry["version"],
        "basis": entry.get("basis"),
        "probe": probe, "spacing": spacing,
        "bad": sorted(int(b) for b in (bad or [])),
        "events": hashlib.sha1(json.dumps(
            [[round(e["t_bank"], 6), e["y"]] for e in entry["events"]]
        ).encode("utf-8")).hexdigest()[:16],
        "half": HALF_MS, "search": SEARCH_MS, "run": CLOCK_RUN,
    }
    if subset:
        # Only when it is a subset, so every key made before there was a
        # choice is still the key of the same read.
        body["channels"] = subset
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _running_median(off, run=CLOCK_RUN, max_mad=CLOCK_MAX_MAD_MS):
    """The recording's clock offset at each event, from its neighbours.

    Returns (corr, trusted): `corr` in ms per event, and whether each one was
    consistent enough to apply. Where the neighbours scatter -- a recording
    that is mostly garbage has no clock signal in it -- the correction is
    zero rather than a guess.
    """
    n = off.size
    corr = np.zeros(n)
    ok = np.zeros(n, dtype=bool)
    if n < 5:
        return corr, ok
    h = run // 2
    for i in range(n):
        lo, hi = max(0, i - h), min(n, i + h + 1)
        w = off[lo:hi]
        w = w[np.isfinite(w)]
        if w.size < 5:
            continue
        m = float(np.median(w))
        mad = float(np.median(np.abs(w - m))) * 1.4826
        if mad <= max_mad:
            corr[i], ok[i] = m, True
    return corr, ok


def _resample(v, n):
    v = np.asarray(v, dtype=np.float64)
    if v.size == n:
        return v
    if v.size < 2:
        return np.full(n, float(v[0]) if v.size else 0.0)
    x = np.linspace(0.0, 1.0, v.size)
    return np.interp(np.linspace(0.0, 1.0, n), x, v)


def _bin_time(m, step):
    """Average adjacent columns, `step` at a time (the last bin may be short)."""
    cols = [m[..., i:i + step].mean(axis=-1)
            for i in range(0, m.shape[-1], step)]
    return np.stack(cols, axis=-1)


def _mean_corr(x):
    """Mean off-diagonal correlation between rows: 1 is one signal everywhere."""
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean(axis=1, keepdims=True)
    sd = np.sqrt((x * x).sum(axis=1))
    keep = sd > 0
    if keep.sum() < 2:
        return np.nan
    z = x[keep] / sd[keep][:, None]
    c = z @ z.T
    k = c.shape[0]
    return float((c.sum() - np.trace(c)) / (k * (k - 1)))


def _peak_shape(trace, pk, fs):
    """Incisor's prominence, widths and asymmetry for one peak.

    The same calls `incisor._detect` makes -- `peak_prominences`,
    `peak_widths` at half height with Toothy's window, and the asymmetry on
    the INT-CAST edges, which is what Toothy computes.
    """
    import warnings
    wlen = max(3, int(round(fs * WLEN_MS / 1000.0)))
    try:
        # A peak on its own edge has no prominence and no width; scipy says
        # so with a warning per peak, and the answer is the NaN below.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prom = _sig.peak_prominences(trace, [pk], wlen=wlen)
            widths, wh, lo, hi = _sig.peak_widths(
                trace, [pk], rel_height=0.5, prominence_data=prom, wlen=wlen)
    except Exception:                                    # noqa: BLE001
        return np.nan, np.nan, np.nan, np.nan
    i0 = pk - int(lo[0])
    i1 = int(hi[0]) - pk
    asym = ((i1 - i0) / float(min(i0, i1)) * 100.0) if min(i0, i1) > 0 \
        else np.nan
    return (float(prom[0][0]), float(widths[0]) / fs * 1000.0,
            float(wh[0]), float(asym))


def _read_matrix(session, channels, t0, t1, spec, lfp_fs):
    """Every channel over one stretch: decimated, notched, and DS band.

    The arithmetic of `dspca._read_span` -- Incisor's staged decimation,
    Braces' notch, Incisor's bandpass -- applied to the whole [nCh x nSamp]
    block at once rather than a channel at a time. Measured on PTEN m22 s3:
    per channel, more than half the time went on DESIGNING the same three
    filters sixty-four times over (`cheby1`, `zpk2sos`), and the read itself
    was 1.3 ms a channel. One design per block is the same numbers, row for
    row, in a fraction of the time.
    """
    raws, anchor, ch_fs = [], None, None
    for ch in channels:
        raw, got_t0, fs_ = csc._read_channel_window(session, ch, t0, t1)
        if raw.size < 64:
            return None
        if anchor is None:
            anchor, ch_fs = got_t0, fs_
        raws.append(np.asarray(raw, dtype=np.float64))
    keep = min(r.size for r in raws)
    x = np.vstack([r[:keep] for r in raws])
    q = incisor.decimation_for(ch_fs, lfp_fs)
    if q > 1:
        for step in incisor._factor(q):
            x = _sig.decimate(x, step, ftype="iir", zero_phase=True, axis=-1)
    fs = ch_fs / q
    if x.shape[1] < 64:
        return None
    clean = braces._notch(x, fs, spec)
    band = incisor._filtered(clean, fs, spec.get("band") or incisor.DS_BAND)
    return clean, band, anchor, fs


def _robust_sd(x, axis):
    """Spread from the median absolute deviation, so the events in a window
    do not inflate the yardstick they are measured with."""
    med = np.median(x, axis=axis, keepdims=True)
    return np.median(np.abs(x - med), axis=axis) / 0.6745


def feature_names(families):
    out = []
    for fam in families:
        out.extend(_NAMES[fam])
    return out


_NAMES = {
    "incisor": ["amp_uv", "amp_sd", "prominence_uv", "half_width_ms",
                "width_height_uv", "asymmetry", "peak_lag_ms", "near_stitch"],
    "shank": ["frac_contacts_over_4.5sd", "best_row_from_usual",
              "frac_rows_reversed", "profile_vs_usual", "csd_peak_rel",
              "csd_peak_offset_ms", "sink_row_from_usual", "csd_vs_voltage",
              "common_mode_band", "common_mode_broadband", "broadband_rel",
              "broadband_peak_sd"],
    "waves": (["wave_%+d" % int(round(-HALF_MS + i * WAVE_STEP_MS))
               for i in range(int(2 * HALF_MS / WAVE_STEP_MS) + 1)]
              + ["csd_%+d" % int(round(-HALF_MS + i * WAVE_STEP_MS))
                 for i in range(int(2 * HALF_MS / WAVE_STEP_MS) + 1)]
              + ["profile_%02d" % i for i in range(PROFILE_ROWS)]),
    "context": ["log_gap_before_s", "log_gap_after_s", "n_within_1s",
                "n_within_10s"],
    "recording": ["rec_log_candidates", "rec_amp_uv", "rec_amp_sd",
                  "rec_prominence_uv", "rec_half_width_ms",
                  "rec_width_height_uv", "rec_profile_vs_usual",
                  "rec_profile_spread", "rec_rows_reversed",
                  "rec_csd_peak_rel", "rec_common_mode_band",
                  "rec_common_mode_broadband", "rec_broadband_peak_sd",
                  "rec_log_gap_s"],
    "csdimg": ["img_r%02d_%+d" % (r, int(round(-HALF_MS + c * IMG_STEP_MS)))
               for r in range(IMG_ROWS)
               for c in range(int(math.ceil((2 * HALF_MS + 1)
                                            / IMG_STEP_MS)))],
}
_NAMES.update(phys.NAMES)
_NAMES["wavebits"] = list(aiwave.NAMES)


def read_entry(session, channels, probe, bad, times, spacing=None,
               report=None, job=None, stop=None, on_span=None, workers=1,
               trace_ids=None):
    """Read every stamp's surround once, and turn each into features.

    `times` are on the recording's own clock already (None for an event that
    has no place on it). Returns a dict of per-family arrays, one row per
    event in `times` order, with `ok` saying which rows were readable.
    """
    if not HAVE_SCIPY:
        raise AiBetaError("Reading needs scipy, which is not installed here.")
    p = dspca.Params(probe=probe, spacing=spacing, invert=True,
                     bad=sorted(int(b) for b in (bad or [])))
    if p.spacing is None:
        p.spacing = dspca.spacing_for(p.probe)
    spec = p.spec()
    bad = {int(b): "marked" for b in (bad or [])}

    idx_ok = [i for i, t in enumerate(times) if t is not None]
    n_all = len(times)
    reach_ms = SEARCH_MS + HALF_MS
    stamps = [times[i] for i in idx_ok]
    if not stamps:
        raise AiBetaError("None of this set's stamps has a place on the "
                          "recording's clock.")
    runs = braces.spans(stamps, window_ms=reach_ms, pad_s=PAD_S)
    by_time = sorted(idx_ok, key=lambda i: times[i])

    # Which stamps each stretch serves, decided before any is read, so the
    # stretches can be read in any order -- and, for one recording on its
    # own (a sweep), several at once.
    members, at = [], 0
    for a, b in runs:
        mine = []
        while at < len(by_time) and times[by_time[at]] <= b - PAD_S:
            mine.append(by_time[at])
            at += 1
        members.append(mine)

    blocks_b, blocks_w = {}, {}
    fs_box = [None]
    count = [0]

    def one(k):
        if stop:
            stop()
        if job:
            job.check()
        a, b = runs[k]
        mine = members[k]
        if not mine:
            return {}
        got = _read_matrix(session, channels, a, b, spec, p.lfp_fs)
        count[0] += 1
        if on_span:
            on_span(count[0], len(runs))
        if not got:
            return {}
        wide_n, band, anchor, fs = got
        fs_box[0] = fs
        R_ = int(round(reach_ms / 1000.0 * fs))
        wide_n = braces.repair(wide_n, channels, bad)
        band = braces.repair(band, channels, bad)
        out = {}
        for i in mine:
            i0 = int(round((times[i] - anchor) * fs))
            if i0 - R_ < 0 or i0 + R_ + 1 > band.shape[1]:
                continue
            out[i] = (band[:, i0 - R_:i0 + R_ + 1].astype(np.float32),
                      wide_n[:, i0 - R_:i0 + R_ + 1].astype(np.float32))
        return out

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(one, range(len(runs))))
    else:
        parts = [one(k) for k in range(len(runs))]
    for part in parts:
        for i, (bb_, ww_) in part.items():
            blocks_b[i], blocks_w[i] = bb_, ww_
    fs_seen = fs_box[0]
    R = None

    have = sorted(blocks_b)
    if not have:
        raise AiBetaError("None of this set's %d stamps could be read." % n_all)
    fs = float(fs_seen)
    B = np.stack([blocks_b[i] for i in have])          # (n, ch, 2R+1)
    W = np.stack([blocks_w[i] for i in have])
    del blocks_b, blocks_w
    R = (B.shape[2] - 1) // 2

    # Which column of contacts the CSD is taken down. A linear array is one;
    # an H10-D is several, and the one where these events are biggest is the
    # one that sees them.
    geo, _probe = dspca.geometry(p.probe, channels)
    S = int(round(SEARCH_MS / 1000.0 * fs))
    H = int(round(HALF_MS / 1000.0 * fs))
    P = int(round(PEAK_MS / 1000.0 * fs))
    best_run, best_score, csd_all = None, -1.0, None
    for run in geo:
        rows = run["rows"]
        C = np.stack([braces.csd_of(B[j][rows], spec) for j in range(len(have))]
                     ).astype(np.float32)
        score = float(np.median(np.abs(C[:, :, R - P:R + P + 1])
                                .mean(axis=1).max(axis=1)))
        if score > best_score:
            best_run, best_score, csd_all = run, score, C
    rows = best_run["rows"]
    Bb = B[:, rows, :]
    Wb = W[:, rows, :]
    C = csd_all
    A = np.abs(C).mean(axis=1)                          # (n, 2R+1)

    # --- the clock, per recording -----------------------------------------
    t_search = (np.arange(-S, S + 1) / fs) * 1000.0
    off = np.full(len(have), np.nan)
    for j in range(len(have)):
        tr = A[j, R - S:R + S + 1]
        if not np.all(np.isfinite(tr)):
            continue
        off[j] = t_search[dspca.pick_peak(tr, t_search, "nearest")]
    corr, trusted = _running_median(off)
    shift = np.clip(np.round(corr / 1000.0 * fs).astype(int), -S, S)
    centre = R + shift

    # --- per-recording references, from every candidate -------------------
    # Per contact, over every window of every candidate together.
    flat_b = np.moveaxis(Bb, 1, 0).reshape(Bb.shape[1], -1)
    sd_b = _robust_sd(flat_b, axis=1).astype(np.float64)
    sd_b[sd_b <= 0] = np.nan
    flat_w = np.moveaxis(Wb, 1, 0).reshape(Wb.shape[1], -1)
    sd_w = float(np.nanmedian(_robust_sd(flat_w, axis=1)))
    del flat_b, flat_w
    csd_scale = float(np.nanmedian(A)) or 1.0

    n = len(have)
    first = []          # per event: (r, pk, profile, sink, hf)
    for j in range(n):
        c = centre[j]
        win = Bb[j][:, c - P:c + P + 1]
        z = win.max(axis=1) / sd_b
        r = int(np.nanargmax(z)) if np.isfinite(z).any() else 0
        seg = Bb[j][r, c - P:c + P + 1]
        pk = c - P + int(np.argmax(seg))
        prof = Bb[j][:, pk].astype(np.float64)
        csd_col = C[j][:, pk]
        sink = int(np.nanargmax(np.abs(csd_col))) if np.isfinite(
            csd_col).any() else 0
        hf = float(np.sqrt(np.mean((Wb[j][:, c - H:c + H + 1]
                                    - Bb[j][:, c - H:c + H + 1]) ** 2)))
        ratio = float(A[j, pk]) / (float(np.mean(np.abs(prof))) + 1e-9)
        first.append((r, pk, prof, sink, hf, ratio))

    rows_n = len(rows)
    usual_r = int(np.bincount([f[0] for f in first]).argmax())
    usual_sink = int(np.bincount([f[3] for f in first]).argmax())
    profs = np.stack([f[2] / (np.max(np.abs(f[2])) + 1e-9) for f in first])
    usual_prof = np.median(profs, axis=0)
    hf_scale = float(np.median([f[4] for f in first])) or 1.0
    ratio_scale = float(np.median([f[5] for f in first])) or 1.0

    fam = {k: np.full((n_all, len(_NAMES[k])), np.nan, dtype=np.float32)
           for k in FAMILY_IDS if k not in NOT_FIRST}
    ok = np.zeros(n_all, dtype=bool)

    # Context comes from the set's own stamps, readable or not.
    tt = np.array([t if t is not None else np.nan for t in times], float)
    order = np.argsort(np.where(np.isfinite(tt), tt, np.inf))
    srt = tt[order]
    for pos, i in enumerate(order):
        t = tt[i]
        if not np.isfinite(t):
            continue
        before = t - srt[pos - 1] if pos > 0 and np.isfinite(srt[pos - 1]) \
            else np.nan
        after = srt[pos + 1] - t if pos + 1 < len(srt) and np.isfinite(
            srt[pos + 1]) else np.nan
        fin = srt[np.isfinite(srt)]
        n1 = int(np.sum(np.abs(fin - t) <= 1.0)) - 1
        n10 = int(np.sum(np.abs(fin - t) <= 10.0)) - 1
        fam["context"][i] = [
            math.log10(max(before, 1e-3)) if np.isfinite(before) else np.nan,
            math.log10(max(after, 1e-3)) if np.isfinite(after) else np.nan,
            n1, n10]

    n_wave = len(_NAMES["waves"]) - PROFILE_ROWS
    half_wave = n_wave // 2
    step_w = max(1, int(round(WAVE_STEP_MS / 1000.0 * fs)))
    step_i = max(1, int(round(IMG_STEP_MS / 1000.0 * fs)))
    for j, i in enumerate(have):
        r, pk, prof, sink, hf, ratio = first[j]
        c = centre[j]
        tr = Bb[j][r].astype(np.float64)
        amp = float(tr[pk])
        prom, hw, wh, asym = _peak_shape(tr, pk, fs)
        stitch = (1.0 if (report and continuity.near_stitch(report, times[i]))
                  else 0.0)
        fam["incisor"][i] = [amp, amp / sd_b[r] if np.isfinite(sd_b[r])
                             else np.nan,
                             prom, hw, wh, asym, (pk - c) / fs * 1000.0,
                             stitch]

        bw = Bb[j][:, c - H:c + H + 1]
        ww = Wb[j][:, c - H:c + H + 1]
        over = np.nanmean((Bb[j][:, c - P:c + P + 1].max(axis=1) / sd_b)
                          >= OVER_SD)
        reversed_ = float(np.nanmean(prof < -2.0 * sd_b))
        pn = prof / (np.max(np.abs(prof)) + 1e-9)
        pc = float(np.corrcoef(pn, usual_prof)[0, 1]) if np.std(pn) > 0 \
            and np.std(usual_prof) > 0 else np.nan
        fam["shank"][i] = [
            over,
            abs(r - usual_r) / float(rows_n),
            reversed_,
            pc,
            float(A[j, c - P:c + P + 1].max()) / csd_scale,
            (off[j] - corr[j]) if np.isfinite(off[j]) else np.nan,
            abs(sink - usual_sink) / float(max(1, C.shape[1])),
            ratio / ratio_scale,
            _mean_corr(bw),
            _mean_corr(ww),
            hf / hf_scale,
            float(np.max(np.abs(ww))) / (sd_w or 1.0),
        ]

        wave = tr[c - H:c + H + 1:step_w] / (abs(amp) + 1e-9)
        cs = A[j, c - H:c + H + 1:step_w]
        cs = cs / (float(np.max(cs)) + 1e-9)
        fam["waves"][i] = np.concatenate([
            _resample(wave, half_wave), _resample(cs, n_wave - half_wave),
            _resample(pn, PROFILE_ROWS)])

        patch = C[j][:, c - H:c + H + 1].astype(np.float64)
        patch = np.stack([_resample(patch[:, k], IMG_ROWS)
                          for k in range(patch.shape[1])], axis=1)
        patch = _bin_time(patch, step_i)
        patch = patch / (float(np.max(np.abs(patch))) + 1e-9)
        want = len(_NAMES["csdimg"])
        flat = patch.reshape(-1)[:want]
        if flat.size < want:
            flat = np.concatenate([flat, np.zeros(want - flat.size)])
        fam["csdimg"][i] = flat
        ok[i] = True

    for k in fam:
        fam[k][~np.isfinite(fam[k])] = np.nan

    # Every even channel's 5-100 Hz trace, +-50 ms around the corrected
    # stamp at 2 ms steps, for the few candidates a sweep's scanning screen
    # draws (`trace_ids`). Stacked in probe order; microvolts.
    traces = {}
    if trace_ids:
        want = {int(t) for t in trace_ids}
        even = [k for k, ch in enumerate(channels)
                if int(ch["number"]) % 2 == 0] or list(range(len(channels)))
        st_ = max(1, int(round(2 / 1000.0 * fs)))
        for j, i in enumerate(have):
            if i not in want:
                continue
            c = int(centre[j])
            traces[int(i)] = np.round(
                B[j][even][:, c - H:c + H + 1:st_].astype(np.float64), 1)
        traces = {"chans": [int(channels[k]["number"]) for k in even],
                  "by_event": traces}
    clock = {
        "median_ms": float(np.median(corr[trusted])) if trusted.any() else 0.0,
        "max_abs_ms": float(np.max(np.abs(corr[trusted]))) if trusted.any()
        else 0.0,
        "trusted": int(trusted.sum()), "of": int(n),
        "spread_ms": float(np.nanmedian(np.abs(off - corr))),
    }
    return {"fam": fam, "ok": ok, "fs": fs, "clock": clock,
            "run": best_run.get("label"), "n_rows": rows_n,
            "missed": int(n_all - ok.sum()), "traces": traces}


def save_features(path, entry, got):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arrays = {"fam_" + k: v for k, v in got["fam"].items()}
    meta = {k: got[k] for k in ("fs", "clock", "run", "n_rows", "missed")}
    meta["fv"] = FEATURE_VERSION
    tmp = path + ".part.npz"
    np.savez_compressed(
        tmp, ok=got["ok"],
        y=np.array([e["y"] for e in entry["events"]], dtype=np.int8),
        meta=np.asarray([json.dumps(meta)]), **arrays)
    os.replace(tmp, path)


def load_features(path):
    if not os.path.exists(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z["meta"][0]))
            if meta.get("fv") != FEATURE_VERSION:
                return None
            fam = {k: z["fam_" + k] for k in FAMILY_IDS
                   if k not in NOT_FIRST}
            ok = z["ok"].astype(bool)
            y = z["y"]
    except Exception:                                    # noqa: BLE001
        return None
    fam["recording"] = derive_recording(fam, ok)
    fam["wavebits"] = derive_wavebits(fam, ok)
    return {"fam": fam, "ok": ok, "y": y, **meta}


def derive_wavebits(fam, ok):
    """The waveform measures (aiwave.py), from the stored "waves" block."""
    return aiwave.derive(fam["waves"], ok,
                         len(_NAMES["waves"]) - PROFILE_ROWS,
                         WAVE_STEP_MS, PROFILE_ROWS)


def derive_recording(fam, ok):
    """One row per event, the same for every event: the recording as a whole.

    Medians over every readable candidate in the set, DS and garbage alike --
    so it says what the recording's candidates are like, never what its
    labels are. Absolute sizes where the per-event numbers are relative,
    because a recording whose every candidate is small is exactly the one a
    measure relative to its own candidates cannot see.
    """
    names = _NAMES["recording"]
    n = ok.size
    out = np.full((n, len(names)), np.nan, dtype=np.float32)
    if not ok.any():
        return out

    def col(family, name):
        return fam[family][ok, _NAMES[family].index(name)].astype(float)

    def med(v):
        v = v[np.isfinite(v)]
        return float(np.median(v)) if v.size else np.nan

    prof = col("shank", "profile_vs_usual")
    pf = prof[np.isfinite(prof)]
    spread = (float(np.percentile(pf, 75) - np.percentile(pf, 25))
              if pf.size else np.nan)
    gaps = col("context", "log_gap_after_s")
    row = [
        math.log10(max(1, int(ok.sum()))),
        med(col("incisor", "amp_uv")),
        med(col("incisor", "amp_sd")),
        med(col("incisor", "prominence_uv")),
        med(col("incisor", "half_width_ms")),
        med(col("incisor", "width_height_uv")),
        med(prof),
        spread,
        med(col("shank", "frac_rows_reversed")),
        med(col("shank", "csd_peak_rel")),
        med(col("shank", "common_mode_band")),
        med(col("shank", "common_mode_broadband")),
        med(col("shank", "broadband_peak_sd")),
        med(gaps),
    ]
    out[:] = np.asarray(row, dtype=np.float32)
    return out


# --------------------------------------------------------------------------
# Training and testing
# --------------------------------------------------------------------------
def _model(model_id, seed=0):
    from sklearn.pipeline import make_pipeline
    from sklearn.impute import SimpleImputer
    if model_id == "forest":
        from sklearn.ensemble import RandomForestClassifier
        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                   class_weight="balanced_subsample",
                                   n_jobs=-1, random_state=seed))
    if model_id == "logistic":
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=4000,
                               C=0.5))
    # No class_weight here: it is balanced by `_fit` instead. Measured on
    # this machine with scikit-learn 1.9, 12,663 events by 158 inputs, 50
    # rounds: 1.3 s unweighted and 18.9 s with class_weight="balanced" --
    # the weighted histograms are fifteen times slower, which made a run's
    # 21 fits six minutes instead of half of one. Without early stopping,
    # because the balancing repeats rows and a validation split drawn from
    # repeated rows is partly the training set.
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.06, max_leaf_nodes=31,
        l2_regularization=1.0, early_stopping=False, random_state=seed,
        # A blend's members each see a random half of the inputs at every
        # split, so they differ by more than their draw of the garbage.
        max_features=0.5 if model_id == "hgb_sub" else 1.0)


def _fit(model_id, X, y, seed=0):
    """Fit with the classes balanced, as the user asked (2026-10-02).

    Gradient-boosted trees get the rarer class repeated, at random, until
    it is as common as the other: the same thing a balanced weight means,
    on the fast path. The forest and the regression take their own
    `class_weight`, which costs them nothing.
    """
    if model_id == "blend":
        return Blend(BLEND_MEMBERS, seed).fit(X, y)
    m = _model(model_id, seed)
    if model_id not in ("hgb", "hgb_sub"):
        return m.fit(X, y)
    rng = np.random.default_rng(seed)
    idx = np.arange(y.size)
    pos, neg = idx[y == 1], idx[y == 0]
    if pos.size and neg.size and pos.size != neg.size:
        small, big = (pos, neg) if pos.size < neg.size else (neg, pos)
        extra = rng.choice(small, big.size - small.size, replace=True)
        idx = np.concatenate([idx, extra])
    return m.fit(X[idx], y[idx])


class Blend:
    """Several models' scores, averaged: `members` are model ids.

    Each member is fitted the way it would be on its own (`_fit`), the
    gradient-boosted ones on different seeds so their balancing draws
    different garbage. What it is for is the far end of the garbage: the
    DS bar sits above 99% of it, so a handful of the most spike-like
    garbage decide where it goes and with it how many real spikes are left
    flagged. One model puts those few wherever its draw happened to; an
    average of several is steadier there.
    """

    def __init__(self, members, seed=0):
        self.members = list(members)
        self.seed = seed
        self.fitted = []
        self.classes_ = np.array([0, 1])

    def fit(self, X, y):
        self.fitted = [_fit(mid, X, y, self.seed + k)
                       for k, mid in enumerate(self.members)]
        return self

    def predict_proba(self, X):
        p = np.mean([m.predict_proba(X)[:, 1] for m in self.fitted], axis=0)
        return np.column_stack([1.0 - p, p])


def _proba(m, X):
    return m.predict_proba(X)[:, 1]


def _threshold(p_ds, keep=KEEP_DS):
    """The score above which `keep` of the real dentate spikes sit."""
    if p_ds.size == 0:
        return 0.5
    return float(np.quantile(p_ds, 1.0 - keep))


def metrics(y, p, t):
    """What a call at threshold `t` does, in the terms that matter here.

    DS at or above `t`; everything below is FLAGGED for a person, never
    thrown away. So the two numbers are how many real spikes it would have
    sent to a person (DS flagged) and how much garbage it caught.
    """
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    ds, g = y == 1, y == 0
    call = p >= t
    out = {
        "n": int(y.size), "n_ds": int(ds.sum()), "n_garbage": int(g.sum()),
        "threshold": round(float(t), 4),
        "ds_kept": int((call & ds).sum()),
        "ds_flagged": int((~call & ds).sum()),
        "garbage_caught": int((~call & g).sum()),
        "garbage_through": int((call & g).sum()),
        "flagged": int((~call).sum()),
        "flag_likely_garbage": int((p < 0.5).sum()),
        "flag_unsure": int(((p >= 0.5) & ~call).sum()),
        "baseline_all_ds": round(float(ds.mean()), 4) if y.size else None,
    }
    out["ds_kept_frac"] = round(out["ds_kept"] / max(1, out["n_ds"]), 4)
    out["garbage_caught_frac"] = round(out["garbage_caught"]
                                       / max(1, out["n_garbage"]), 4) \
        if out["n_garbage"] else None
    out["flagged_frac"] = round(out["flagged"] / max(1, out["n"]), 4)
    out["agreement"] = round(float(((call & ds) | (~call & g)).mean()), 4) \
        if y.size else None
    # At an even 0.5, as a plain classifier would be read.
    half = p >= 0.5
    out["at_half"] = {
        "accuracy": round(float((half == ds).mean()), 4) if y.size else None,
        "balanced": round(0.5 * (float(half[ds].mean()) if ds.any() else 0)
                          + 0.5 * (float((~half[g]).mean()) if g.any() else 0),
                          4),
        "confusion": {"ds_as_ds": int((half & ds).sum()),
                      "ds_as_garbage": int((~half & ds).sum()),
                      "garbage_as_ds": int((half & g).sum()),
                      "garbage_as_garbage": int((~half & g).sum())},
    }
    out["auc"] = None
    if ds.any() and g.any():
        from sklearn.metrics import roc_auc_score, average_precision_score
        out["auc"] = round(float(roc_auc_score(y, p)), 4)
        # Average precision for GARBAGE, which is the rare class and the one
        # the model is for.
        out["garbage_ap"] = round(float(average_precision_score(1 - y, 1 - p)),
                                  4)
        out["garbage_rate"] = round(float(g.mean()), 4)
    return out


def train_and_test(data, families, model_id="hgb", job=None,
                   keep=KEEP_DS, folds=N_FOLDS, inner=N_INNER, seed=0,
                   policy=None):
    """Whole-mouse cross-validation, then one model on everything.

    `data` is [(entry, features)] with features from `read_entry`/the cache.
    Returns (results, final_model, feature_names, threshold).
    """
    if not HAVE_SKLEARN:
        raise AiBetaError("Training needs scikit-learn, which is not "
                          "installed here.")
    from sklearn.model_selection import GroupKFold
    from sklearn.metrics import roc_auc_score

    fams = [f for f in FAMILY_IDS if f in families]
    if not fams:
        raise AiBetaError("Pick at least one kind of input.")
    if model_id not in MODEL_IDS:
        raise AiBetaError("Unknown model %r." % model_id)
    names = feature_names(fams)

    Xs, ys, gs, es = [], [], [], []
    for k, (entry, feat) in enumerate(data):
        ok = feat["ok"].astype(bool)
        X = np.hstack([feat["fam"][f] for f in fams])[ok]
        y = np.asarray(feat["y"])[ok].astype(int)
        Xs.append(X)
        ys.append(y)
        gs.extend([entry["mouse_key"]] * int(ok.sum()))
        es.extend([k] * int(ok.sum()))
    X = np.vstack(Xs).astype(np.float64)
    y = np.concatenate(ys)
    groups = np.array(gs)
    ent = np.array(es)
    X[~np.isfinite(X)] = np.nan
    mice = sorted(set(gs))
    if len(mice) < 2:
        raise AiBetaError("Testing on unseen mice needs at least two mice.")
    if len(set(y.tolist())) < 2:
        raise AiBetaError("The data holds only one kind of label.")
    k_out = min(folds, len(mice))
    # Columns of each family, for asking afterwards what the model leaned on.
    spans_, at = {}, 0
    for f in fams:
        spans_[f] = (at, at + len(_NAMES[f]))
        at += len(_NAMES[f])

    total_fits = k_out * (min(inner, max(2, len(mice) - 1)) + 1) + 1
    if job:
        job.begin("ai train", of=total_fits, unit="fits")
    done = [0]

    def tick():
        done[0] += 1
        if job:
            job.tick("ai train", done[0])

    oof = np.full(y.size, np.nan)
    fold_of = np.full(y.size, -1)
    thr_of = np.full(y.size, np.nan)
    thr_k = {k_: np.full(y.size, np.nan) for k_ in TRADEOFF}
    thr_c = {c_: np.full(y.size, np.nan) for c_ in CATCH}
    folds_out = []
    drops = {f: [] for f in fams}
    rng = np.random.default_rng(seed)
    gkf = GroupKFold(n_splits=k_out)
    for fi, (tr, te) in enumerate(gkf.split(X, y, groups)):
        # The threshold is chosen INSIDE the training mice, by a second
        # whole-mouse split, so the test fold never sets its own bar.
        tr_mice = sorted(set(groups[tr].tolist()))
        k_in = min(inner, len(tr_mice))
        inner_p = np.full(tr.size, np.nan)
        if k_in >= 2:
            for a, b in GroupKFold(n_splits=k_in).split(X[tr], y[tr],
                                                        groups[tr]):
                if len(set(y[tr][a].tolist())) < 2:
                    tick()
                    continue
                m = _fit(model_id, X[tr][a], y[tr][a], seed)
                inner_p[b] = _proba(m, X[tr][b])
                tick()
        got = np.isfinite(inner_p) & (y[tr] == 1)
        t = _threshold(inner_p[got], keep) if got.any() else 0.5
        for k_ in TRADEOFF:
            thr_k[k_][te] = (_threshold(inner_p[got], k_) if got.any()
                             else 0.5)
        pg = inner_p[np.isfinite(inner_p) & (y[tr] == 0)]
        for c_ in CATCH:
            if not pg.size:
                thr_c[c_][te] = 0.5
            elif c_ >= 1.0:
                thr_c[c_][te] = float(pg.max()) + 1e-9
            else:
                thr_c[c_][te] = float(np.quantile(pg, c_)) + 1e-9
        m = _fit(model_id, X[tr], y[tr], seed)
        tick()
        p = _proba(m, X[te])
        oof[te] = p
        fold_of[te] = fi
        thr_of[te] = t
        row = metrics(y[te], p, t)
        row.update({"fold": fi + 1,
                    "mice": sorted(set(groups[te].tolist())),
                    "n_recordings": int(len(set(ent[te].tolist())))})
        folds_out.append(row)
        # What it leaned on: shuffle one kind of input across the test
        # events and see how much worse it ranks them.
        base = row.get("auc")
        if base is not None:
            for f in fams:
                a, b = spans_[f]
                Xp = X[te].copy()
                Xp[:, a:b] = Xp[rng.permutation(Xp.shape[0])][:, a:b]
                try:
                    drops[f].append(base - float(
                        roc_auc_score(y[te], _proba(m, Xp))))
                except ValueError:
                    pass

    # The pooled picture uses each event's OWN fold threshold, which is what
    # it would have been called with.
    call = oof >= thr_of
    pooled = metrics(y, oof, 0.5)
    pooled_t = {
        "ds_kept": int((call & (y == 1)).sum()),
        "ds_flagged": int((~call & (y == 1)).sum()),
        "garbage_caught": int((~call & (y == 0)).sum()),
        "garbage_through": int((call & (y == 0)).sum()),
        "flagged": int((~call).sum()),
        "flag_likely_garbage": int((oof < 0.5).sum()),
        "flag_unsure": int(((oof >= 0.5) & ~call).sum()),
    }
    pooled.update(pooled_t)
    pooled["threshold"] = None
    pooled["thresholds"] = [round(float(r["threshold"]), 4)
                            for r in folds_out]
    pooled["ds_kept_frac"] = round(pooled["ds_kept"]
                                   / max(1, pooled["n_ds"]), 4)
    pooled["garbage_caught_frac"] = round(
        pooled["garbage_caught"] / max(1, pooled["n_garbage"]), 4)
    pooled["flagged_frac"] = round(pooled["flagged"] / max(1, pooled["n"]), 4)
    pooled["agreement"] = round(float(((call & (y == 1))
                                       | (~call & (y == 0))).mean()), 4)

    by_rec = []
    for k, (entry, feat) in enumerate(data):
        sel = ent == k
        if not sel.any():
            continue
        yy, cc = y[sel], call[sel]
        by_rec.append({
            "label": entry["label"], "entry_id": entry["entry_id"],
            "mouse": entry["mouse_key"], "source": entry["source"],
            "fold": int(fold_of[sel][0]) + 1,
            "n": int(sel.sum()), "n_ds": int((yy == 1).sum()),
            "n_garbage": int((yy == 0).sum()),
            "ds_kept": int((cc & (yy == 1)).sum()),
            "garbage_caught": int((~cc & (yy == 0)).sum()),
            "flagged": int((~cc).sum()),
            "agreement": round(float(((cc & (yy == 1))
                                      | (~cc & (yy == 0))).mean()), 4),
        })

    # Three kinds of recording, because they are three different questions.
    # A recording with both labels asks "which of these is garbage"; one
    # somebody rejected whole asks "is this recording any good", which is a
    # call about all of its candidates at once; one with no garbage only
    # asks whether real spikes are kept.
    kind_of = {}
    for k, (entry, feat) in enumerate(data):
        sel = ent == k
        if not sel.any():
            continue
        has_ds, has_g = bool((y[sel] == 1).any()), bool((y[sel] == 0).any())
        kind_of[k] = ("mixed" if has_ds and has_g
                      else "all_garbage" if has_g else "all_ds")
    kinds = np.array([kind_of.get(int(k), "") for k in ent])
    kind_by_id = {data[k][0]["entry_id"]: v for k, v in kind_of.items()}
    for r in by_rec:
        r["kind"] = kind_by_id.get(r["entry_id"])
    by_kind = {}
    for kd in ("mixed", "all_garbage", "all_ds"):
        sel = kinds == kd
        if not sel.any():
            continue
        yy, cc = y[sel], call[sel]
        row = {
            "n_recordings": sum(1 for v in kind_of.values() if v == kd),
            "n": int(sel.sum()), "n_ds": int((yy == 1).sum()),
            "n_garbage": int((yy == 0).sum()),
            "ds_kept": int((cc & (yy == 1)).sum()),
            "garbage_caught": int((~cc & (yy == 0)).sum()),
            "flagged": int((~cc).sum()),
            "auc": None,
        }
        if (yy == 1).any() and (yy == 0).any():
            row["auc"] = round(float(roc_auc_score(yy, oof[sel])), 4)
        if kd == "mixed":
            # Ranking inside one recording, which is the job a curator does:
            # every candidate in a set compared with the others in that set.
            aucs = []
            for k, v in kind_of.items():
                if v != "mixed":
                    continue
                s_ = ent == k
                if (y[s_] == 1).sum() >= 3 and (y[s_] == 0).sum() >= 3:
                    aucs.append(float(roc_auc_score(y[s_], oof[s_])))
            row["within_auc_median"] = (round(float(np.median(aucs)), 4)
                                        if aucs else None)
            row["within_auc_n"] = len(aucs)
        by_kind[kd] = row

    tradeoff = []
    mixed = kinds == "mixed"
    for k_ in TRADEOFF:
        c = oof >= thr_k[k_]
        ds_, g_ = y == 1, y == 0
        tradeoff.append({
            "keep": k_,
            "ds_kept_frac": round(float((c & ds_).sum() / max(1, ds_.sum())),
                                  4),
            "garbage_caught_frac": round(float((~c & g_).sum()
                                               / max(1, g_.sum())), 4),
            "garbage_caught_mixed_frac": (round(float(
                (~c & g_ & mixed).sum() / max(1, (g_ & mixed).sum())), 4)
                if (g_ & mixed).any() else None),
            "flagged_frac": round(float((~c).sum() / max(1, y.size)), 4),
            "garbage_through": int((c & g_).sum()),
        })

    catch = []
    for c_ in CATCH:
        flag = oof < thr_c[c_]
        ds_, g_ = y == 1, y == 0
        catch.append({
            "target": c_,
            "garbage_caught_frac": round(float((flag & g_).sum()
                                               / max(1, g_.sum())), 4),
            "garbage_missed": int((~flag & g_).sum()),
            "ds_flagged": int((flag & ds_).sum()),
            "ds_flagged_frac": round(float((flag & ds_).sum()
                                           / max(1, ds_.sum())), 4),
            "flagged_frac": round(float(flag.sum() / max(1, y.size)), 4),
        })

    leaned = []
    for f in fams:
        d = drops[f]
        leaned.append({"id": f, "name": next(x["name"] for x in FAMILIES
                                             if x["id"] == f),
                       "auc_drop": round(float(np.mean(d)), 4) if d else None})
    leaned.sort(key=lambda r: -(r["auc_drop"] or 0))

    # The model that would be used: every mouse, with the bar set from the
    # held-out scores above rather than from its own training data.
    final = _fit(model_id, X, y, seed)
    tick()
    t_final = _threshold(oof[y == 1], keep)

    results = {
        "pooled": pooled,
        "folds": folds_out,
        "by_recording": by_rec,
        "leaned_on": leaned,
        "by_kind": by_kind,
        "tradeoff": tradeoff,
        "catch": catch,
        "policy": label_policy(oof, y, policy),
        # Every held-out score with its answer and its recording, so a
        # different set of bars can be tried without training again.
        "oof": {"p": [round(float(v), 4) for v in oof],
                "y": [int(v) for v in y],
                "rec": [int(v) for v in ent]},
        "n_features": len(names),
        "keep_ds": keep,
        "final_threshold": round(t_final, 4),
    }
    return results, final, names, t_final


# --------------------------------------------------------------------------
# One run, end to end
# --------------------------------------------------------------------------
# The job stages, declared the way Root Canal declares its own: `cfc.Job`
# keeps only stages its STAGES list names and drops the rest without a word.
# "ai read" is one recording's candidates read and featurised; "ai train" is
# one model fitted. Flat, because the unit already carries the size of the
# job. Seeds measured here on 2026-10-02 (PTEN m22 s3, 173 stamps, 28 s on
# its own); this machine's own rate replaces them after the first run.
_STAGES = (("ai read", "recordings", 20.0),
           ("ai physio", "recordings", 60.0),
           # Tooth Fairy's sweep of one set (toothfairy.py): the stretches of ONE
           # recording, read several at a time, then every candidate scored.
           ("tf read", "stretches", 0.3),
           ("tf physio", "stretches", 1.2),
           ("tf score", "candidates", 0.001),
           ("ai train", "fits", 3.0))


def register_stages(cfcmod):
    """Declare this tool's job stages to the job machinery. Idempotent."""
    have = {name for name, _unit in cfcmod.STAGES}
    for name, unit, seed in _STAGES:
        if name not in have:
            cfcmod.STAGES.append((name, unit))
        cfcmod._RATES.setdefault(name, seed)
        cfcmod._FLAT.add(name)

# Recordings read at once. Reading is mostly waiting on the disk and in
# scipy's filters, both of which let go of the interpreter: measured here,
# four recordings in four threads took 32 s of wall against 126 s one after
# another. Six of the twelve cores, so the app stays usable while it reads.
READ_WORKERS = 6


def phys_path(runs, entry, row):
    """Where one recording's second read is cached: named by the first
    read's key and the second read's own version."""
    h = hashlib.sha1((row["key"] + str(phys.PHYS_VERSION))
                     .encode("utf-8")).hexdigest()[:16]
    return os.path.join(runs.cache, "%s__phys_%s.npz"
                        % (shards.safe_base(entry["gid"]), h))


def plan(entries, open_recording, runs):
    """Which recordings are already read, and which would be read now.

    `open_recording(entry)` -> {session, channels, probe, bad, spacing} or
    raises with a sentence. Returns rows in `entries` order.
    """
    out = []
    for e in entries:
        row = {"entry_id": e["entry_id"], "label": e["label"], "n": e["n"]}
        try:
            rec = open_recording(e)
            key = cache_key(e, rec["probe"], rec.get("spacing"), rec["bad"],
                            rec.get("subset"))
            path = runs.feature_path(e["gid"], key)
            row.update({"ok": True, "cached": os.path.exists(path),
                        "key": key, "path": path, "rec": rec})
        except Exception as exc:                         # noqa: BLE001
            row.update({"ok": False, "cached": False, "why": str(exc)})
        out.append(row)
    return out


def run(bank, curate, runs, open_recording, settings, prov=None, job=None):
    """Read what is not read yet, train, test, file the run and its model.

    `settings`: {"entries": [entry ids] or None for all, "families": [...],
    "model": id}. Returns the run record.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    started = time.time()
    fams = [f for f in FAMILY_IDS if f in (settings.get("families")
                                          or [f["id"] for f in FAMILIES
                                              if f["default"]])]
    model_id = settings.get("model") or "hgb"
    which = settings.get("channels") or "all"
    if which not in CHANNEL_SETS:
        raise AiBetaError("No channel set %r." % which)
    opener = open_recording
    if which != "all":
        def opener(e):
            return subset_channels(open_recording(e), which)
    ds = dataset(bank, curate, pin=settings.get("pin"))
    want = settings.get("entries")
    ents = [e for e in ds["entries"]
            if not want or e["entry_id"] in set(want)]
    if not ents:
        raise AiBetaError("None of the chosen recordings has a settled "
                          "version to learn from.")

    rows = plan(ents, opener, runs)
    if job:
        job.members_init([{"id": r["entry_id"], "label": r["label"]}
                          for r in rows])
        for r in rows:
            if not r["ok"]:
                job.member(r["entry_id"], status="failed",
                           error=r.get("why"))
            elif r["cached"]:
                job.member(r["entry_id"], status="done", cached=True)
    todo = [r for r in rows if r["ok"] and not r["cached"]]
    if job:
        # Opened even when everything is already read, so the stage the
        # run declared closes as done-with-nothing rather than sitting at
        # "waiting" beside a finished training.
        job.begin("ai read", of=len(todo), unit="recordings")

    failed = {r["entry_id"]: r.get("why") for r in rows if not r["ok"]}
    by_id = {e["entry_id"]: e for e in ents}

    def read_one(r):
        e, rec = by_id[r["entry_id"]], r["rec"]
        if job:
            job.check()
            job.member(r["entry_id"], status="reading")
        report = None
        try:
            report = continuity.check(rec["session"].get("path"))
        except Exception:                                # noqa: BLE001
            report = None
        times = true_times(e, report)

        def on_span(k, n):
            if job:
                job.member(r["entry_id"], done=k, of=n)
        got = read_entry(rec["session"], rec["channels"], rec["probe"],
                         rec["bad"], times, spacing=rec.get("spacing"),
                         report=report, job=job, on_span=on_span)
        save_features(r["path"], e, got)
        return r

    t_read = time.time()
    if todo:
        done = 0
        with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
            futs = {pool.submit(read_one, r): r for r in todo}
            for fut in as_completed(futs):
                r = futs[fut]
                try:
                    fut.result()
                    if job:
                        job.member(r["entry_id"], status="done")
                except Exception as exc:                 # noqa: BLE001
                    if job and job._cancel:
                        for f in futs:
                            f.cancel()
                        raise
                    failed[r["entry_id"]] = str(exc)[:300]
                    if job:
                        job.member(r["entry_id"], status="failed",
                                   error=str(exc)[:200])
                done += 1
                if job:
                    job.tick("ai read", done)
    read_s = time.time() - t_read

    # The second read, only when one of its inputs was asked for -- or when
    # a run without them is to be compared with one that has them, which
    # has to be on the same candidates (`same_events`).
    want_phys = bool(PHYS_IDS & set(fams)) or bool(settings.get("same_events"))
    if want_phys:
        todo2 = []
        for r in rows:
            if r["entry_id"] in failed or not r["ok"]:
                continue
            r["phys_path"] = phys_path(runs, by_id[r["entry_id"]], r)
            if not phys.has(r["phys_path"],
                            [f for f in fams if f in PHYS_IDS]):
                todo2.append(r)
        if job:
            job.begin("ai physio", of=len(todo2), unit="recordings")

        def phys_one(r):
            e, rec = by_id[r["entry_id"]], r["rec"]
            if job:
                job.check()
                job.member(r["entry_id"], status="reading")
            report = None
            try:
                report = continuity.check(rec["session"].get("path"))
            except Exception:                            # noqa: BLE001
                report = None
            times = true_times(e, report)

            def on_span(k, n):
                if job:
                    job.member(r["entry_id"], done=k, of=n)
            got = phys.read_physio(
                rec["session"], rec["channels"], rec["probe"], rec["bad"],
                times, report=report,
                folder=rec["session"].get("path"), job=job,
                on_span=on_span, aibeta=sys.modules[__name__],
                spacing=rec.get("spacing"),
                want_filt=phys.filters_for(fams),
                want_xray=bool(set(fams) & set(phys.XR_IDS)))
            phys.save(r["phys_path"], got)
            return r

        t_phys = time.time()
        if todo2:
            done2 = 0
            with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
                futs = {pool.submit(phys_one, r): r for r in todo2}
                for fut in as_completed(futs):
                    r = futs[fut]
                    try:
                        fut.result()
                        if job:
                            job.member(r["entry_id"], status="done")
                    except Exception as exc:             # noqa: BLE001
                        if job and job._cancel:
                            for f in futs:
                                f.cancel()
                            raise
                        failed[r["entry_id"]] = ("the second read failed: "
                                                 + str(exc)[:280])
                        if job:
                            job.member(r["entry_id"], status="failed",
                                       error=str(exc)[:200])
                    done2 += 1
                    if job:
                        job.tick("ai physio", done2)
        read_s += time.time() - t_phys

    data, used, missed = [], [], 0
    for r in rows:
        if r["entry_id"] in failed or not r["ok"]:
            continue
        feat = load_features(r["path"])
        if feat is None:
            failed[r["entry_id"]] = "its features could not be read back"
            continue
        if want_phys:
            ph = phys.load(r.get("phys_path") or "")
            if ph is None:
                failed[r["entry_id"]] = ("its second read could not be "
                                         "read back")
                continue
            feat["fam"].update(ph["fam"])
            # Only candidates both reads could place: the second reaches a
            # second further either side, so a stamp near either end of a
            # recording is one the first read has and this one does not.
            feat["ok"] = feat["ok"].astype(bool) & ph["ok"]
        e = by_id[r["entry_id"]]
        data.append((e, feat))
        missed += int(feat.get("missed") or 0)
        used.append({k: e[k] for k in (
            "entry_id", "gid", "label", "mouse_key", "source", "pipeline",
            "version", "version_name", "basis", "events_from", "n", "n_ds",
            "n_garbage")})
        used[-1]["clock"] = feat.get("clock")
        used[-1]["missed"] = int(feat.get("missed") or 0)
        used[-1]["features_key"] = r["key"]
    if not data:
        raise AiBetaError("Nothing could be read, so there is nothing to "
                          "train on.")

    t_train = time.time()
    results, model, names, thr = train_and_test(
        data, fams, model_id, job, policy=settings.get("policy"))
    train_s = time.time() - t_train

    rid = runs.new_id()
    prov = prov or {}
    rec = {
        "schema": 1,
        "id": rid,
        "at": _now(),
        "by": prov.get("user"),
        "machine": prov.get("machine"),
        "computed": prov,
        "settings": {"families": fams, "model": model_id,
                     "keep_ds": KEEP_DS, "folds": N_FOLDS, "inner": N_INNER,
                     "feature_version": FEATURE_VERSION,
                     "phys_version": phys.PHYS_VERSION if want_phys else None,
                     "same_events": bool(settings.get("same_events")),
                     "policy": settings.get("policy"),
                     "channels": which,
                     "note": settings.get("note")},
        "data": {
            "entries": used,
            "n_recordings": len(used),
            "n_mice": len({u["mouse_key"] for u in used}),
            "n_events": int(results["pooled"]["n"]),
            "n_ds": int(results["pooled"]["n_ds"]),
            "n_garbage": int(results["pooled"]["n_garbage"]),
            "missed": missed,
            "failed": [{"entry_id": k, "label": (by_id.get(k) or {}).get(
                "label"), "why": v} for k, v in failed.items()],
            "skipped": ds["skipped"],
            "first_pass": summary({"entries": [by_id[u["entry_id"]]
                                               for u in used]})["first_pass"],
        },
        "results": results,
        "model": {"threshold": round(float(thr), 4),
                  "n_features": len(names), "file": None},
        "seconds": {"read": round(read_s, 1), "train": round(train_s, 1),
                    "total": round(time.time() - started, 1)},
    }
    bundle = {"model": model, "feature_names": names, "families": fams,
              "policy": results.get("policy"),
              "threshold": float(thr), "feature_version": FEATURE_VERSION,
              "keep_ds": KEEP_DS, "run_id": rid, "trained_at": rec["at"],
              "channels": which,
              "entries": [(u["entry_id"], u["version"]) for u in used]}
    runs.save(rec, bundle)
    return rec


# --------------------------------------------------------------------------
# Runs: what was trained, on what, and how it did
# --------------------------------------------------------------------------
class Runs:
    """Run records and the models they produced, sharded per machine.

    A run is written once, by the machine that ran it, so its record never
    has two authors. The model beside it is a joblib file named the same.
    """

    def __init__(self, logs_dir, store=None):
        self.root = os.path.join(logs_dir, "aibeta")
        self.dir = os.path.join(self.root, "runs")
        self.models = os.path.join(self.root, "models")
        self.cache = os.path.join(logs_dir, ".cache", "aibeta")
        self.logs = logs_dir
        # Other machines' runs, pulled from the shared database into the
        # cache. The records only: a model file stays on the machine that
        # trained it (see cloudsync's shard_files).
        self.pulled = os.path.join(logs_dir, ".cache", "cloudshards",
                                   "aibeta", "runs")
        self.book = shards.Book(self.dir, {}, store,
                                extra_dirs=[self.pulled])
        # Which run each sweep model is: one record per model, the latest
        # designation winning. Filed under "avery", the first model's name,
        # because that is where the designations already are.
        self.model_book = shards.Book(os.path.join(self.root, "avery"), {},
                                      store)
        # Every sweep somebody accepted: each candidate's score and call,
        # the bars, and the run -- the record the edge cases are mined from.
        self.sweeps = shards.Book(os.path.join(self.root, "sweeps"), {},
                                  store)
        # What has been tried and what it did: one record per question, the
        # summary report AI Beta shows (the user, 2026-10-07: "generate a
        # summary report in the AI Beta tab"). Written by whoever ran the
        # comparison, with the numbers in it, never recomputed on read.
        self.reports = shards.Book(os.path.join(self.root, "reports"), {},
                                   store)
        self.store = store

    def save_report(self, rec):
        """File one report. `rec` needs an `id`; the rest is
        {title, order, at, by, question, how, verdict, tables}."""
        if not rec.get("id"):
            raise AiBetaError("A report needs an id.")
        rec = dict(rec)
        rec.setdefault("at", _now())
        return self.reports.write(rec["id"], rec)

    def all_reports(self):
        out = [r for r in (self.reports.all() or []) if r.get("id")]
        out.sort(key=lambda r: (r.get("order", 999), r.get("at") or ""))
        return out

    def feature_path(self, gid, key):
        return os.path.join(self.cache, "%s__%s.npz"
                            % (shards.safe_base(gid), key))

    def new_id(self):
        return "ai" + time.strftime("%Y%m%d-%H%M%S") + "-" + \
            uuid.uuid4().hex[:4]

    def model_path(self, run_id):
        return os.path.join(self.models, "%s%s%s.joblib"
                            % (run_id, shards.SIGIL, shards.machine_id()))

    def save(self, rec, model=None):
        if model is not None:
            import joblib
            os.makedirs(self.models, exist_ok=True)
            path = self.model_path(rec["id"])
            joblib.dump(model, path, compress=3)
            rec["model"]["file"] = os.path.relpath(
                path, os.path.dirname(self.root)).replace("\\", "/")
            rec["model"]["bytes"] = os.path.getsize(path)
        self.book.write(rec["id"], rec)
        return rec

    def get(self, run_id):
        return self.book.read(run_id)

    def all(self):
        out = [r for r in (self.book.all() or []) if r.get("id")]
        out.sort(key=lambda r: r.get("at") or "", reverse=True)
        return out

    def model(self, slot="tooth_fairy"):
        """{run_id, at, by} for the run a sweep model is, or None."""
        if slot not in SLOTS:
            raise AiBetaError("No such model %r." % slot)
        rec = self.model_book.read(slot) or {}
        return rec if rec.get("run_id") else None

    def set_model(self, run_id, prov=None, slot="tooth_fairy"):
        rec = self.get(run_id)
        if not rec:
            raise AiBetaError("No AI Beta run %s." % run_id)
        if not ((rec.get("results") or {}).get("policy")):
            raise AiBetaError(
                "That run predates the sweep's four bars, so it cannot sort "
                "a set into DS, Flag, Flag for Deep Review and Garbage. "
                "Train it again and use the new run.")
        if slot not in SLOTS:
            raise AiBetaError("No such model %r." % slot)
        prov = prov or {}
        return self.model_book.write(slot, {
            "run_id": run_id, "at": _now(), "by": prov.get("user"),
            "machine": prov.get("machine")})

    def load_model(self, run_id):
        """The trained bundle a run saved, from this machine's disk."""
        rec = self.get(run_id)
        if not rec:
            raise AiBetaError("No AI Beta run %s." % run_id)
        rel = (rec.get("model") or {}).get("file")
        path = os.path.join(self.logs, rel) if rel else None
        if not path or not os.path.exists(path):
            raise AiBetaError(
                "Run %s's model is not on this machine yet (%s). It is "
                "filed with the run, so it arrives on the next pull."
                % (run_id, rel or "no file"))
        import joblib
        return rec, joblib.load(path)


def brief(rec):
    """A run, small enough for a list."""
    res = rec.get("results") or {}
    pooled = res.get("pooled") or {}
    return {
        "id": rec.get("id"), "at": rec.get("at"), "by": rec.get("by"),
        "machine": rec.get("machine"),
        "settings": rec.get("settings"),
        "n_events": (rec.get("data") or {}).get("n_events"),
        "n_mice": (rec.get("data") or {}).get("n_mice"),
        "auc": pooled.get("auc"),
        "ds_kept_frac": pooled.get("ds_kept_frac"),
        "garbage_caught_frac": pooled.get("garbage_caught_frac"),
        "flagged_frac": pooled.get("flagged_frac"),
        # Garbage first: what catching 95% and 99% of it costs in real
        # spikes flagged, on the mice held out.
        "catch": {str(c.get("target")): {
            "caught": c.get("garbage_caught_frac"),
            "ds_flagged": c.get("ds_flagged_frac")}
            for c in (res.get("catch") or [])},
        "seconds": rec.get("seconds"),
    }
