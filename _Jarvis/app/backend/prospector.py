"""
prospector.py -- Prospector: Panning's spike-or-not model, trained.

Tooth Fairy's sibling (aibeta.py, toothfairy.py) for The Confluence. Tooth
Fairy learned Checkup's calls on Incisor's candidates, where P-spikes and
TZSs were often thrown out as garbage because they were not dentate spikes;
Panning keeps them, so the pooled sets need a model of their own (the user,
Rain and the PI, 2026-11-03). Training and testing only, here: nothing in
this module writes a label, a curation set or a bank version.

WHAT A TRAINING EXAMPLE IS
--------------------------
A KCNT1 pool is Junction run on the raw detectors: every Incisor candidate
and every Doppler event, merged at 20 ms. The finished PTEN pools were not
made that way -- Junction pooled Checkup's dentate spikes after Braces had
moved them, and Doppler's raw events -- so each finished PTEN recording is
rebuilt as the pool KCNT1 will look like (`consolidate`):

  the Incisor half   Checkup's last PERSON pass before the Braces version
                     Junction read (not the alignment, not a model's sweep,
                     not Root Canal's or X-ray's), every candidate at its
                     own stamp, before Braces moved it -- plus the garbage
                     any earlier person pass held that this one dropped,
                     Toothy's era included ("it's the same detector");
  the Doppler half   the Doppler version Junction read, every event;
  merged             one to one, nearest first, within Junction's 20 ms.

Each event's answer (the user's rules, 2026-11-03):
  - Panning's call before Lock wherever Panning saw it -- a Checkup
    candidate that reached the pool (traced back through Braces), or the
    Doppler half of one. Panning wins every disagreement.
  - Checkup's call otherwise: the garbage Junction never pooled, and the
    spikes a Root Canal version took out before Junction read it.
  - Tooth Fairy-accepted Checkup calls count: "they are all valid spikes at
    the end of the day".
  - A Doppler event Panning has no call for (merged away by hand) is left
    out, as is anything still flagged.

A Doppler-only event's stamp is Doppler's; everything with an Incisor half
is at Incisor's, before Braces -- the stamps a KCNT1 pool carries.

TESTED ON RECORDINGS IT NEVER SAW
---------------------------------
Leave one recording out (the user, 2026-11-03), with the garbage bar set
inside the training recordings by a second split, never by the recording
being tested. The bar for a Spike call is the most spike-like garbage the
training recordings held ("0 is the goal"): `aibeta.CATCH` target 1.0.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import os
import re
import threading
import time

import numpy as np

from . import aibeta, braces, retime, shards
from . import aibetaphys as phys
from . import continuity
from . import versions as versionsmod

SCHEMA = 1
MERGE_S = 0.020          # Junction's window
BRACES_REACH_S = 0.200   # the furthest Braces moves a stamp (Braces' +-200)
SAME_S = 0.002           # one event recorded twice (aibeta.SAME_EVENT_S)
SPIKE_LABELS = {"spike", "dentate spike", "ds1", "ds2"}
GARBAGE_LABELS = {"garbage"}

ORIGINS = ("incisor", "doppler", "both")

# WHO IT IS when it writes (2026-11-04): a sweep accepted in Panning banks
# every call as a version of the pool tagged `TAG` and made by `BY`, and puts
# its calls on the candidates nobody has decided with `BY` as the decider.
# Training never learns from either (`_is_ai`).
TAG = "prospector"
BY = "Prospector (AI)"
# ITS THREE CALLS (the user, 2026-11-03): Spike, very pure, and two flags it
# alone can give -- `computed` labels in the pooled vocabulary
# (curation.KINDS), so no button or key offers them to a person. Never
# Garbage.
CALLS = ("spike", "likely_spike", "likely_garbage")
# Under the Spike bar, a score of at least this leans spike.
LEAN = 0.5
# THE SPIKE BAR (the user, 2026-11-04, choosing from the run's table: "0.99
# 8,114 51% 57 (0.7%)"): above 99% of the training recordings' garbage, as
# scored by models that had not seen it -- set for the model on every
# recording the way each test's bar was set (`deploy_bar`).
DEFAULT_TARGET = 0.99

ORIGIN_FAMILY = {"id": "origin", "name": "Which detector found it",
                 "default": False, "prospector": True,
                 "blurb": "Incisor only, Doppler only, or both within "
                          "Junction's 20 ms -- as a KCNT1 pool says."}


def _register_origin():
    """Prospector's one input that is not read off the recording, known to
    aibeta's trainer. Idempotent; only Prospector's own runs ask for it."""
    if "origin" in aibeta.FAMILY_IDS:
        return
    aibeta.FAMILIES.append(dict(ORIGIN_FAMILY))
    aibeta.FAMILY_IDS.append("origin")
    aibeta._NAMES["origin"] = ["origin_" + o for o in ORIGINS]
    aibeta.NOT_FIRST = aibeta.NOT_FIRST | {"origin"}


_register_origin()

# The inputs. Tooth Fairy's, as its slot was trained (run
# ai20261007-231323-671d), then Rain's list (2026-11-03): the voltage
# through 5-100 Hz and through the notch alone, the CSD through 5-100 Hz
# (Tooth Fairy's fwhole_5_100) and above 1 Hz, and a spectrogram.
TF_FAMILIES = ["incisor", "shank", "waves", "context", "context500", "dipole",
               "latency", "mua", "ripple", "state", "template", "clipping",
               "polarity", "braces", "aligned15", "shape", "fwhole_10_40",
               "fwhole_5_100"]
RAIN_FAMILIES = ["fwhole_hp1", "fthin_notch", "ftrace_notch", "fthin_5_100",
                 "ftrace_5_100"]
SPEC_FAMILIES = list(phys.SPEC_IDS)


def _lab(e):
    s = str(e.get("label_id") or e.get("label") or "").strip().lower()
    if s in SPIKE_LABELS:
        return "spike"
    if s in GARBAGE_LABELS:
        return "garbage"
    return s or "undecided"


def _evs(bank, rec, ver):
    try:
        return bank.events_at(rec, bank.version_key(ver))[0]
    except Exception:                                    # noqa: BLE001
        return None


def _nearest(ts, t, w):
    k = bisect.bisect_left(ts, t)
    best = None
    for q in (k - 1, k):
        if 0 <= q < len(ts) and abs(ts[q] - t) <= w:
            if best is None or abs(ts[q] - t) < abs(ts[best] - t):
                best = q
    return best


def _pair(a, b, w):
    """Junction's pairing of two sorted lists: one to one, nearest first,
    within `w`. {index in a: index in b}."""
    cand = []
    for i, t in enumerate(a):
        k = bisect.bisect_left(b, t - w)
        while k < len(b) and b[k] <= t + w:
            cand.append((abs(b[k] - t), i, k))
            k += 1
    cand.sort()
    ua, ub, out = set(), set(), {}
    for _d, i, k in cand:
        if i in ua or k in ub:
            continue
        ua.add(i)
        ub.add(k)
        out[i] = k
    return out


def _is_ai(ver):
    """A version a model wrote: Tooth Fairy's, an older model's, or
    Prospector's own (banked by an accepted sweep, `TAG`/`BY`)."""
    return (aibeta._is_model(ver)
            or str(ver.get("tag") or "").lower() == TAG
            or ver.get("by") == BY)


def _is_pass(ver):
    """A person's curation pass: their calls, not something a tool made of
    them (an alignment, a model's sweep, Root Canal, X-ray, a re-timing)."""
    if ver.get("aligned") or _is_ai(ver):
        return False
    if str(ver.get("tag") or "").lower() in ("rootcanal", "junction",
                                             "dspca", "xray"):
        return False
    note = str(ver.get("note") or "")
    if note.startswith(("Root Canal", "Re-timed", "DS1/DS2", "Imported")):
        return False
    bl = {str(k).strip().lower(): n for k, n in (ver.get("by_label") or {}).items()
          if n}
    if any(k in ("ds1", "ds2") for k in bl):
        return False
    return any(k in SPIKE_LABELS | GARBAGE_LABELS for k in bl)


def _panning_version(rec):
    """The last person pass before Lock first aligned the pool."""
    named = versionsmod.label_rows(rec.get("versions") or [])
    first_lock = next((k for k, (v, _n) in enumerate(named)
                       if v.get("aligned")), None)
    if first_lock is None:
        return None, None
    for ver, nm in reversed(named[:first_lock]):
        if _is_ai(ver):
            continue
        bl = {str(k).lower(): n for k, n in (ver.get("by_label") or {}).items()}
        if any(k in ("spike", "garbage") and n for k, n in bl.items()):
            return ver, nm
    return None, None


_RETIMED_NOTE = re.compile(r"^Re-timed from (\S+) to ([^\s.,]+)")


def _basis_at(bank, rec, ver):
    """`bank.basis_at`, also reading a re-time made before versions carried
    their `retimed` marker (jarvis.retime/1, September 2026). Such a version
    says so only in its note, and the bank then reads every later version
    as still on Toothy's clock: shifted a second time, a PTEN pool's whole
    Incisor half lands 58-126 ms off its own events (m34 s8, m60 s1 and two
    more, 2026-11-03)."""
    v = ver.get("v") or 0
    last = None
    for x in sorted(rec.get("versions") or [], key=lambda x: x.get("v") or 0):
        if (x.get("v") or 0) > v:
            break
        if x.get("retimed"):
            last = (x["retimed"] or {}).get("to")
        else:
            m = _RETIMED_NOTE.match(x.get("note") or "")
            if m:
                last = m.group(2)
    return last or bank.basis_at(rec, v)


def consolidate(bank, curate=None, report_of=None, projects=("PTEN",)):
    """Every finished pool, rebuilt and answered. See the module docstring.

    `report_of(gid)` -> the recording's continuity report, for Toothy's
    clock; without it, a Toothy-era stamp is left out (and counted) rather
    than guessed onto the real clock. Returns {"entries", "skipped"}, the
    entries in `aibeta.dataset`'s shape plus `origin` per event and the
    counts of where each answer came from.
    """
    by_id = {r["id"]: r for r in bank.all()}
    entries, skipped = [], []
    for rec in bank.all():
        if (rec.get("type") or "") != "pooled":
            continue
        proj = str(rec.get("project") or "")
        label = rec.get("session_label") or rec.get("name") or rec["id"]
        if not any(proj.startswith(p) for p in projects) \
                or proj.startswith("KCNT1"):
            continue
        pver, pname = _panning_version(rec)
        if pver is None:
            continue                      # not finished: no Lock yet
        par = (rec.get("source") or {}).get("parameters") or {}
        why = None
        d = by_id.get(par.get("ds_entry"))
        di = by_id.get(par.get("ied_entry"))
        if not d or not di:
            why = "an input Junction pooled is not in the bank here"
        pan = sorted((float(e["start"]), _lab(e))
                     for e in (_evs(bank, rec, pver) or []))
        if not pan:
            why = why or "its Panning version has no snapshot here"
        if why:
            skipped.append({"label": label, "entry_id": rec["id"], "why": why})
            continue
        pan_t = [t for t, _l in pan]

        # The Incisor half: Checkup's last person pass before the version
        # Junction read.
        dn = versionsmod.label_rows(d.get("versions") or [])
        ji = next((k for k, (v, nm) in enumerate(dn)
                   if str(nm) == str(par.get("ds_version"))), None)
        k = (ji - 1) if ji is not None else -1
        while k >= 0 and not _is_pass(dn[k][0]):
            k -= 1
        if ji is None or k < 0:
            skipped.append({"label": label, "entry_id": rec["id"],
                            "why": "no person's Checkup pass before the "
                                   "version Junction read"})
            continue
        sv, sname = dn[k]
        s_ev = _evs(bank, d, sv)
        if not s_ev:
            skipped.append({"label": label, "entry_id": rec["id"],
                            "why": "Checkup pass v%s has no snapshot here"
                                   % sname})
            continue
        gid = rec.get("gid")
        report = report_of(gid) if report_of else None

        def on_true(ver, ts):
            """Stamps of `ver` on the recording's own clock, or None each."""
            basis = _basis_at(bank, d, ver) or ""
            if basis != retime.CONCAT:
                return ts
            if not (report and report.get("ok")):
                return [None] * len(ts)
            out = []
            for t in ts:
                tt, _seg = continuity.concat_to_true(report, t)
                out.append(None if tt is None else float(tt))
            return out

        s_ev = sorted(s_ev, key=lambda e: float(e["start"]))
        s_t = on_true(sv, [float(e["start"]) for e in s_ev])
        inc = [(t, _lab(e), "checkup") for t, e in zip(s_t, s_ev)
               if t is not None]
        n_lost_clock = sum(1 for t in s_t if t is None)
        # Garbage an earlier person pass held that this one does not. Within
        # Junction's 20 ms of a candidate this pass holds, it is that
        # candidate, and this pass's call stands: a Toothy-era pass is
        # Toothy's detections even after it was re-timed onto the
        # recording's clock, and its stamp sits a few ms off Incisor's for
        # the same event (m59 s4, 2026-11-03).
        have = sorted(t for t, _l, _s in inc)
        n_earlier = n_toothy = 0
        for v, _nm in dn[:k]:
            if not _is_pass(v):
                continue
            ev2 = _evs(bank, d, v) or []
            concat = (_basis_at(bank, d, v) or "") == retime.CONCAT
            ts2 = on_true(v, [float(e["start"]) for e in ev2])
            for e, t in zip(ev2, ts2):
                if _lab(e) != "garbage":
                    continue
                if t is None:
                    n_lost_clock += 1
                    continue
                if _nearest(have, t, MERGE_S) is not None:
                    continue
                bisect.insort(have, t)
                inc.append((t, "garbage", "toothy" if concat else "earlier"))
                if concat:
                    n_toothy += 1
                else:
                    n_earlier += 1
        inc.sort()
        # One event recorded twice is one event.
        ded = []
        for x in inc:
            if ded and x[0] - ded[-1][0] <= SAME_S:
                continue
            ded.append(x)
        inc = ded
        inc_t = [x[0] for x in inc]

        # Which Checkup candidates reached the pool, through Braces: the
        # version Junction read holds the pass's spikes, moved.
        jread = sorted(float(e["start"]) for e in (_evs(bank, d, dn[ji][0]) or []))
        chk_sp = [i for i, x in enumerate(inc) if x[2] == "checkup"
                  and x[1] == "spike"]
        if len(jread) == len(chk_sp):
            to_pool = {chk_sp[j]: jread[j] for j in range(len(chk_sp))}
        else:
            m = _pair([inc_t[i] for i in chk_sp], jread, BRACES_REACH_S)
            to_pool = {chk_sp[a]: jread[b] for a, b in m.items()}

        # The Doppler half, raw, as Junction read it.
        dv = next((v for v, nm in versionsmod.label_rows(di.get("versions") or [])
                   if str(nm) == str(par.get("ied_version"))), None)
        dop_t = sorted(float(e["start"]) for e in (_evs(bank, di, dv) or [])) \
            if dv is not None else []
        m = _pair(inc_t, dop_t, MERGE_S)

        rows, tally = [], {"conflict_checkup_garbage_panning_spike": 0,
                           "conflict_checkup_spike_panning_garbage": 0,
                           "from_panning": 0, "from_checkup": 0,
                           "agree": 0, "dropped_flag": 0,
                           "dropped_doppler_no_call": 0}
        for i, (t, l, src) in enumerate(inc):
            origin = "both" if i in m else "incisor"
            pi = None
            if i in to_pool:
                pi = _nearest(pan_t, to_pool[i], 0.001)
            if pi is None and i in m:
                pi = _nearest(pan_t, dop_t[m[i]], 0.001)
            ans = l
            if pi is not None and pan[pi][1] in ("spike", "garbage"):
                pl = pan[pi][1]
                if l in ("spike", "garbage") and pl != l:
                    tally["conflict_checkup_%s_panning_%s" % (l, pl)] += 1
                    tally["from_panning"] += 1
                elif l == pl:
                    tally["agree"] += 1
                else:
                    tally["from_panning"] += 1
                ans = pl
            elif l in ("spike", "garbage"):
                tally["from_checkup"] += 1
            if ans not in ("spike", "garbage"):
                tally["dropped_flag"] += 1
                continue
            rows.append((t, origin, ans))
        used = set(m.values())
        for j, t in enumerate(dop_t):
            if j in used:
                continue
            pi = _nearest(pan_t, t, 0.001)
            if pi is None or pan[pi][1] not in ("spike", "garbage"):
                tally["dropped_doppler_no_call"] += 1
                continue
            tally["from_panning"] += 1
            rows.append((t, "doppler", pan[pi][1]))
        rows.sort()
        # Two answers on one instant (a merge Panning made by hand) are one.
        ded = []
        for x in rows:
            if ded and x[0] - ded[-1][0] <= SAME_S:
                continue
            ded.append(x)
        rows = ded
        if not rows:
            continue
        events = [{"t_bank": t, "y": 1 if l == "spike" else 0}
                  for t, _o, l in rows]
        entries.append({
            "entry_id": rec["id"], "gid": gid, "label": label,
            "project": proj, "mouse": rec.get("mouse"),
            "session": rec.get("session"),
            # Folds are whole RECORDINGS (the user, 2026-11-03), so the key
            # the trainer groups by is the recording.
            "mouse_key": label,
            "mouse_of": aibeta.mouse_key(rec),
            "pipeline": "Prospector: rebuilt pool",
            "source": "PTEN pool",
            "version": "prospector:%s:%s:%s" % (
                bank.version_key(pver), bank.version_key(sv),
                par.get("ied_version")),
            "version_name": "Panning v%s + Checkup v%s" % (pname, sname),
            "events_from": "rebuilt pool",
            "basis": "neuralynx_true",
            "n": len(events),
            "n_ds": sum(e["y"] for e in events),
            "n_garbage": sum(1 - e["y"] for e in events),
            "events": events,
            "origin": [o for _t, o, _l in rows],
            "first_pass": None,
            "checkup_entry": d["id"], "checkup_pass": sname,
            "doppler_entry": di["id"], "doppler_version": par.get("ied_version"),
            "panning_version": pname,
            "tally": dict(tally, earlier_garbage=n_earlier,
                          toothy_garbage=n_toothy, lost_to_clock=n_lost_clock),
        })
    entries.sort(key=lambda e: str(e["label"]))
    return {"entries": entries, "skipped": skipped}


def origin_block(entry):
    out = np.zeros((len(entry["events"]), len(ORIGINS)), dtype=np.float32)
    for i, o in enumerate(entry.get("origin") or []):
        if o in ORIGINS:
            out[i, ORIGINS.index(o)] = 1.0
    return out


# --------------------------------------------------------------------------
# Reading and training
# --------------------------------------------------------------------------
def _read_one(e, rec, path, phys_path, want, want_filt, want_spec,
              logs_dir=None):
    """One recording's two reads, into the cache. At module level so a
    worker process can run it (`read_all(processes=...)`); `logs_dir` points
    such a process's continuity cache where Jarvis keeps it."""
    if logs_dir and not continuity.CACHE_DIR:
        continuity.configure(logs_dir)
    t0 = time.time()
    report = None
    try:
        report = continuity.check(rec["session"].get("path"))
    except Exception:                                    # noqa: BLE001
        report = None
    times = aibeta.true_times(e, report)
    if not os.path.exists(path):
        got = aibeta.read_entry(rec["session"], rec["channels"],
                                rec["probe"], rec["bad"], times,
                                spacing=rec.get("spacing"), report=report)
        aibeta.save_features(path, e, got)
    if not phys.has(phys_path, want):
        got = phys.read_physio(
            rec["session"], rec["channels"], rec["probe"], rec["bad"],
            times, report=report, folder=rec["session"].get("path"),
            aibeta=aibeta, spacing=rec.get("spacing"),
            want_filt=set(want_filt), want_spec=want_spec)
        phys.save(phys_path, got)
    return time.time() - t0


# A worker process's numpy and FFTs on one core each. Threads were no faster
# than one read at a time (six reads in parallel took ~1,250 s each against
# ~170 s alone, 2026-11-03): the reads hold the GIL between numpy calls.
_ONE_THREAD = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")


def read_all(entries, open_recording, runs, want_filt, want_spec=True,
             workers=aibeta.READ_WORKERS, log=print, processes=0,
             logs_dir=None):
    """Both of Tooth Fairy's reads for every entry, cached. Returns
    [(entry, features)] for the ones that could be read, and the failures.

    `processes` > 0 reads in that many worker processes instead of threads;
    the caller's main module must then be safe to import (a spawned worker
    imports it), and `logs_dir` gives the workers the continuity cache."""
    from concurrent.futures import (ProcessPoolExecutor, ThreadPoolExecutor,
                                    as_completed)

    def opener(e):
        return aibeta.subset_channels(open_recording(e), "even")

    rows = aibeta.plan(entries, opener, runs)
    by_id = {e["entry_id"]: e for e in entries}
    failed = {r["entry_id"]: r.get("why") for r in rows if not r["ok"]}
    # What the second read must hold, so a cached one missing any is read
    # again (`aibetaphys.has`).
    want = [f for f in TF_FAMILIES + RAIN_FAMILIES
            + (SPEC_FAMILIES if want_spec else []) if f in phys.FAMILY_IDS]
    for r in rows:
        if r["ok"]:
            r["phys_path"] = aibeta.phys_path(runs, by_id[r["entry_id"]], r)

    todo = [r for r in rows if r["ok"]
            and not (os.path.exists(r["path"])
                     and phys.has(r["phys_path"], want))]
    if len(todo) < len(rows):
        log("%d of %d recordings already read" % (
            sum(1 for r in rows if r["ok"]) - len(todo), len(rows)))
    done = 0
    saved_env = {k: os.environ.get(k) for k in _ONE_THREAD}
    if processes:
        os.environ.update({k: "1" for k in _ONE_THREAD})
        pool = ProcessPoolExecutor(max_workers=processes)
    else:
        pool = ThreadPoolExecutor(max_workers=workers)
    with pool:
        futs = {pool.submit(_read_one, by_id[r["entry_id"]], r["rec"],
                            r["path"], r["phys_path"], want, sorted(want_filt),
                            want_spec, logs_dir): r for r in todo}
        for fut in as_completed(futs):
            r = futs[fut]
            done += 1
            try:
                secs = fut.result()
                log("read %d/%d  %-30s %5.0f s" % (done, len(todo),
                                                  r["label"], secs))
            except Exception as exc:                     # noqa: BLE001
                failed[r["entry_id"]] = str(exc)[:300]
                log("read %d/%d  %-30s FAILED: %s" % (done, len(todo),
                                                     r["label"], exc))
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    data = []
    for r in rows:
        if r["entry_id"] in failed or not r["ok"]:
            continue
        feat = aibeta.load_features(r["path"])
        ph = phys.load(r.get("phys_path") or "")
        if feat is None or ph is None:
            failed[r["entry_id"]] = "its features could not be read back"
            continue
        feat["fam"].update(ph["fam"])
        feat["ok"] = feat["ok"].astype(bool) & ph["ok"]
        e = by_id[r["entry_id"]]
        feat["fam"]["origin"] = origin_block(e)
        data.append((e, feat))
    return data, failed


def _groups_summary(oof_p, y, thr, rec_idx, data):
    """Calls at one bar: Spike when the score clears its own fold's bar;
    under it, leaning spike (score >= 0.5) or leaning garbage."""
    call = oof_p >= thr
    out = {
        "spike_called": int(call.sum()),
        "spike_called_true": int((call & (y == 1)).sum()),
        "garbage_into_spike": int((call & (y == 0)).sum()),
        "spike_recall": round(float((call & (y == 1)).sum()
                                    / max(1, (y == 1).sum())), 4),
        "lean_spike": int((~call & (oof_p >= 0.5)).sum()),
        "lean_spike_true": int((~call & (oof_p >= 0.5) & (y == 1)).sum()),
        "lean_garbage": int((~call & (oof_p < 0.5)).sum()),
        "lean_garbage_true": int((~call & (oof_p < 0.5) & (y == 0)).sum()),
    }
    by_origin = {}
    origins = np.concatenate([np.array(e.get("origin"))[f["ok"].astype(bool)]
                              for e, f in data])
    for o in ORIGINS:
        s = origins == o
        if not s.any():
            continue
        by_origin[o] = {
            "n": int(s.sum()), "n_spike": int((y[s] == 1).sum()),
            "n_garbage": int((y[s] == 0).sum()),
            "spike_called": int((call & s).sum()),
            "garbage_into_spike": int((call & s & (y == 0)).sum()),
            "spike_recall": round(float((call & s & (y == 1)).sum()
                                        / max(1, (s & (y == 1)).sum())), 4)}
    out["by_origin"] = by_origin
    by_rec = []
    for k, (e, _f) in enumerate(data):
        s = rec_idx == k
        if not s.any():
            continue
        by_rec.append({
            "label": e["label"], "n": int(s.sum()),
            "n_spike": int((y[s] == 1).sum()), "n_garbage": int((y[s] == 0).sum()),
            "spike_called": int((call & s).sum()),
            "garbage_into_spike": int((call & s & (y == 0)).sum()),
            "spike_recall": round(float((call & s & (y == 1)).sum()
                                        / max(1, (s & (y == 1)).sum())), 4)})
    out["by_recording"] = by_rec
    return out


def train(data, families, model_id="hgb", folds=None, inner=2, seed=0):
    """Tooth Fairy's cross-validation, grouped by recording, with the
    garbage-catch bars reported per group. `folds` None = leave one
    recording out."""
    aibeta.OOF_EXTRA = True
    aibeta.CATCH = (1.0, 0.999, 0.998, 0.995, 0.99, 0.98, 0.95, 0.90)
    n_rec = len({e["mouse_key"] for e, _f in data})
    k_out = n_rec if folds is None else min(folds, n_rec)
    t0 = time.time()
    results, model, names, _thr = aibeta.train_and_test(
        data, families, model_id, folds=k_out, inner=inner, seed=seed)
    secs = time.time() - t0
    extra = results.pop("oof_extra")
    p = extra["p"]
    y = np.asarray(results["oof"]["y"])
    rec_idx = np.asarray(results["oof"]["rec"])
    bars = {}
    for c_, thr in extra["thr_catch"].items():
        bars[repr(c_)] = _groups_summary(p, y, thr, rec_idx, data)
    results["bars"] = bars
    # The raw held-out numbers stay out of the record; the summaries above
    # are what is read. Each event's own score goes back to the caller
    # (`held_out`), so the garbage that clears a bar can be found and looked
    # at one by one.
    results.pop("oof", None)
    held = []
    for k, (e, f) in enumerate(data):
        ok = np.asarray(f["ok"]).astype(bool)
        held += [(e["label"], ev["t_bank"], o_)
                 for ev, o_, keep in zip(e["events"], e["origin"], ok) if keep]
    held_out = None
    if len(held) == p.size:
        held_out = {
            "rows": [{"recording": lab, "t": t, "origin": o_, "y": int(y[i]),
                      "p": round(float(p[i]), 5),
                      "bars": {repr(c_): round(float(np.asarray(thr)[i]), 5)
                               for c_, thr in extra["thr_catch"].items()}}
                     for i, (lab, t, o_) in enumerate(held)]}
    return {"results": results, "model": model, "names": names,
            "seconds": round(secs, 1), "folds": k_out, "inner": inner,
            "model_id": model_id, "families": list(families),
            "held_out": held_out}


class Store:
    """Prospector's records, under GUI_logs/prospector and travelling by git
    as Tooth Fairy's do (aibeta.Runs):

      runs/     one record per training run, written once by its machine
      models/   the model each run made, named like its record
      model/    which run is Prospector, and at what bar (`set_model`)
      sweeps/   every sweep somebody accepted: each candidate's score and
                call beside what a person had said -- the AI's first calls,
                kept to hold against what people decide afterwards

    The reads, which do not travel, are under GUI_logs/.cache/prospector.
    """

    SLOT = "prospector"

    def __init__(self, logs_dir, store=None):
        self.logs = logs_dir
        self.root = os.path.join(logs_dir, "prospector")
        self.dir = os.path.join(self.root, "runs")
        self.models = os.path.join(self.root, "models")
        self.cache = os.path.join(logs_dir, ".cache", "prospector")
        for d in (self.dir, self.models, self.cache):
            os.makedirs(d, exist_ok=True)
        self.model_book = shards.Book(os.path.join(self.root, "model"), {},
                                      store)
        self.sweeps = shards.Book(os.path.join(self.root, "sweeps"), {}, store)

    def new_id(self):
        return "pr" + time.strftime("%Y%m%d-%H%M%S")

    def _mine(self, folder, rid, ext):
        return os.path.join(folder, "%s%s%s%s" % (rid, shards.SIGIL,
                                                  shards.machine_id(), ext))

    def save(self, rec, model=None):
        rid = rec["id"]
        if model is not None:
            import joblib
            path = self._mine(self.models, rid, ".joblib")
            joblib.dump(model, path, compress=3)
            rec["model_file"] = os.path.relpath(path, self.logs) \
                .replace("\\", "/")
            rec["model_bytes"] = os.path.getsize(path)
        path = self._mine(self.dir, rid, ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1, default=str)
        os.replace(tmp, path)
        return path

    def get(self, run_id):
        """A run's record, whichever machine trained it."""
        head = str(run_id) + shards.SIGIL
        try:
            names = sorted(os.listdir(self.dir))
        except OSError:
            return None
        for name in names:
            if name.startswith(head) and name.endswith(".json"):
                try:
                    with open(os.path.join(self.dir, name),
                              encoding="utf-8") as fh:
                        return json.load(fh)
                except (OSError, ValueError):
                    return None
        return None

    def model(self):
        """{run_id, target, t_spike, t_lean, at, by} for the run that is
        Prospector, or None."""
        rec = self.model_book.read(self.SLOT) or {}
        return rec if rec.get("run_id") else None

    def set_model(self, run_id, t_spike, target=DEFAULT_TARGET, prov=None,
                  how=None):
        """Make a run Prospector, sweeping with Spike at `t_spike`."""
        rec = self.get(run_id)
        if not rec or not (rec.get("final") or {}).get("results"):
            raise aibeta.AiBetaError("No finished Prospector run %s here."
                                     % run_id)
        prov = prov or {}
        return self.model_book.write(self.SLOT, {
            "run_id": run_id, "target": float(target),
            "t_spike": round(float(t_spike), 6), "t_lean": LEAN,
            "how": how, "at": aibeta._now(), "by": prov.get("user"),
            "machine": prov.get("machine")})

    def load_model(self, run_id):
        """The trained bundle a run saved, from this machine's disk."""
        rec = self.get(run_id)
        if not rec:
            raise aibeta.AiBetaError("No Prospector run %s here." % run_id)
        rel = rec.get("model_file")
        path = os.path.join(self.logs, rel) if rel else None
        if not path or not os.path.exists(path):
            raise aibeta.AiBetaError(
                "Run %s's model is not on this machine yet (%s). It is "
                "filed with the run, so it arrives on the next pull."
                % (run_id, rel or "no file"))
        import joblib
        return rec, joblib.load(path)


def deploy_bar(data, families, model_id, target=DEFAULT_TARGET, inner=2,
               seed=0):
    """The Spike bar for the model trained on every recording, set the way
    each held-out test's bar was (`aibeta.train_and_test`): the recordings
    split `inner` ways by recording, each part scored by a model trained on
    the rest, and the bar put above `target` of the garbage's scores.

    Not the held-out scores' own quantile. A model trained on half the
    recordings scores garbage higher than one trained on all but one, so
    the run's bars sat higher than that quantile would (median 0.973 against
    0.958 at 0.99, 2026-11-04), and every number the user chose from was
    measured at the higher ones. Returns (bar, n_garbage)."""
    from sklearn.model_selection import GroupKFold
    fams = [f for f in aibeta.FAMILY_IDS if f in families]
    Xs, ys, gs = [], [], []
    for entry, feat in data:
        ok = feat["ok"].astype(bool)
        Xs.append(np.hstack([feat["fam"][f] for f in fams])[ok])
        ys.append(np.asarray(feat["y"])[ok].astype(int))
        gs.extend([entry["mouse_key"]] * int(ok.sum()))
    X = np.vstack(Xs).astype(np.float64)
    X[~np.isfinite(X)] = np.nan
    y = np.concatenate(ys)
    groups = np.array(gs)
    p = np.full(y.size, np.nan)
    for a, b in GroupKFold(n_splits=inner).split(X, y, groups):
        m = aibeta._fit(model_id, X[a], y[a], seed)
        p[b] = aibeta._proba(m, X[b])
    pg = p[np.isfinite(p) & (y == 0)]
    if target >= 1.0:
        bar = float(pg.max()) + 1e-9
    else:
        bar = float(np.quantile(pg, target)) + 1e-9
    return bar, int(pg.size)


# --------------------------------------------------------------------------
# Prospector at work: sweeping a pool (2026-11-04)
# --------------------------------------------------------------------------
# Tooth Fairy's sweep (toothfairy.py), for Panning ("integrate into panning
# in the same way tooth fairy is in check up", the user, 2026-11-04). A
# sweep reads every candidate of one pooled set as training read them --
# both reads, the even channels -- scores each with the run that is
# Prospector, and calls it one of its three things. Nothing is written by a
# sweep. Accepting it (app.py) puts the calls on the candidates no person
# has decided -- and on the ones only Prospector has, so a newer model can
# replace an older one's calls -- and banks every call as a version of the
# pool tagged `TAG`, so what it said can be held against what people then
# decided.
_SWEEPS = {}
_SWEEP_LOCK = threading.Lock()
MAX_SWEEPS = 64
READ_WORKERS = 6

# The sweep's job stages, declared the way Tooth Fairy's are in aibeta.py:
# `cfc.Job` keeps only stages its STAGES list names and drops the rest
# without a word. Until 2026-11-05 these were not declared, so a sweep ran
# with no stages at all -- its screen said "Working" over an empty bar from
# start to finish. Seeds are Tooth Fairy's, the same two reads.
STAGES = (("pr read", "stretches", 0.3),
          ("pr physio", "stretches", 1.2),
          ("pr score", "candidates", 0.001))
READ_STAGES = ("pr read", "pr physio")


def register_stages(cfcmod):
    """Declare the sweep's job stages to the job machinery. Idempotent."""
    have = {name for name, _unit in cfcmod.STAGES}
    for name, unit, seed in STAGES:
        if name not in have:
            cfcmod.STAGES.append((name, unit))
        cfcmod._RATES.setdefault(name, seed)
        cfcmod._FLAT.add(name)


def read_block(sess, rec, times, report, picks, read_fams, job=None,
               stages=READ_STAGES, workers=READ_WORKERS, on_first=None):
    """Both reads of one pool's events -- what a sweep scores.

    Returns (fam, ok, traces). On this computer for a recording it has, and
    on a compute node (`read_node`) for one only the cluster has: one
    function, so the two cannot read differently and the cache a node fills
    is the cache a local sweep would have filled. `on_first(fam, ok,
    traces)` is called between the two reads, for the scanning screen.
    """
    want_phys = bool(set(read_fams) & aibeta.PHYS_IDS)
    want_filt = phys.filters_for(read_fams)
    want_xray = bool(set(read_fams) & set(phys.XR_IDS))
    want_spec = bool(set(read_fams) & set(phys.SPEC_IDS))
    stamps = [t for t in times if t is not None]
    n1 = len(braces.spans(stamps, window_ms=aibeta.SEARCH_MS
                          + aibeta.HALF_MS, pad_s=aibeta.PAD_S))
    if job:
        job.begin(stages[0], of=n1, unit="stretches")

    def tick1(k, n):
        if job:
            job.tick(stages[0], k)
    got1 = aibeta.read_entry(sess, rec["channels"], rec["probe"],
                             rec["bad"], times, spacing=rec.get("spacing"),
                             report=report, job=job, on_span=tick1,
                             workers=workers, trace_ids=picks)
    fam = dict(got1["fam"])
    ok = got1["ok"].astype(bool)
    traces = got1.get("traces") or {"chans": [], "by_event": {}}
    if on_first:
        on_first(fam, ok, traces)
    if want_phys:
        n2 = len(phys.spans(stamps, phys.REACH_MS / 1000.0, phys.PAD_S))
        if job:
            job.begin(stages[1], of=n2, unit="stretches")

        def tick2(k, n):
            if job:
                job.tick(stages[1], k)
        got2 = phys.read_physio(sess, rec["channels"], rec["probe"],
                                rec["bad"], times, report=report,
                                folder=sess.get("path"), job=job,
                                on_span=tick2, aibeta=aibeta,
                                workers=workers,
                                spacing=rec.get("spacing"),
                                want_filt=want_filt, want_xray=want_xray,
                                want_spec=want_spec)
        fam.update(got2["fam"])
        ok = ok & got2["ok"].astype(bool)
    return fam, ok, traces


def save_block(path, fam, ok, traces, picks=None):
    """A read, as the sweep's cache keeps it. Written whole or not at all.
    The traces in `picks` order, which is the order the screen shows."""
    by_event = (traces or {}).get("by_event") or {}
    tr_idx = [int(i) for i in (picks if picks is not None
                                else sorted(by_event)) if i in by_event]
    extra = {}
    if tr_idx:
        extra = {"trace_idx": np.array(tr_idx, dtype=int),
                 "trace_chans": np.array(traces["chans"], dtype=int),
                 "trace_arr": np.stack([by_event[i] for i in tr_idx])}
    np.savez_compressed(path + ".part.npz", ok=ok, **extra,
                        **{"fam_" + k: v for k, v in fam.items()})
    os.replace(path + ".part.npz", path)


def load_block(path, read_fams):
    """(fam, ok, traces, picks) from a kept read, or None when it is not
    there or does not hold every input asked for."""
    if not os.path.exists(path):
        return None
    try:
        with np.load(path, allow_pickle=False) as z:
            fam = {k[4:]: z[k] for k in z.files if k.startswith("fam_")}
            ok = z["ok"].astype(bool)
            if any(f not in fam for f in read_fams):
                return None
            traces, picks = {"chans": [], "by_event": {}}, None
            if "trace_idx" in z.files:
                traces = {"chans": [int(c) for c in z["trace_chans"]],
                          "by_event": {int(i): z["trace_arr"][n]
                                       for n, i in enumerate(z["trace_idx"])}}
                picks = [int(i) for i in z["trace_idx"]]
            return fam, ok, traces, picks
    except Exception:                                    # noqa: BLE001
        return None


def read_node(spec, session, path, out_dir, job):
    """A pool's reads on a compute node (vacc_run.py, tool `prospector`).

    For a recording only the cluster has: Isabella's laptop, 2026-11-05,
    swept KCNT1 m1606 s1 -- opened off the cluster -- and the reads, which
    open the files on this computer, said "[WinError 2] The system cannot
    find the file specified: 'vacc:s9a8f6138b49e'". The SAME `read_block`
    runs here, over the channels the desk chose, and its .npz is written
    beside the run; the desk brings it home into the sweep's cache and
    scores it there, where the model is. The segmentation is made here, as
    Incisor's node makes its own.
    """
    use = braces.channels_by_number(session, spec.get("channels"))
    if not use:
        raise ValueError("None of the channels asked for are in the "
                         "cluster's copy of this recording.")
    report = None
    if session.get("source") == "ncs":
        report = continuity.check(path)
        if not report or not report.get("ok"):
            report = None
    rec = {"channels": use, "probe": spec.get("probe"),
           "bad": [int(b) for b in (spec.get("bad") or [])],
           "spacing": spec.get("spacing")}
    fam, ok, traces = read_block(
        session, rec, list(spec.get("times") or []), report,
        [int(i) for i in (spec.get("picks") or [])],
        list(spec.get("read_fams") or []), job=job,
        stages=tuple(spec.get("stages") or READ_STAGES),
        workers=int(spec.get("workers") or READ_WORKERS))
    name = "sweep_read.npz"
    dest = os.path.join(out_dir, name)
    save_block(dest, fam, ok, traces,
               picks=[int(i) for i in (spec.get("picks") or [])])
    return {"file": name, "bytes": os.path.getsize(dest),
            "n": len(spec.get("times") or []), "n_readable": int(ok.sum())}


def remember(sid, rec):
    with _SWEEP_LOCK:
        _SWEEPS[sid] = rec
        while len(_SWEEPS) > MAX_SWEEPS:
            _SWEEPS.pop(next(iter(_SWEEPS)))


def recall(sid):
    with _SWEEP_LOCK:
        return _SWEEPS.get(sid)


def forget(sid):
    with _SWEEP_LOCK:
        _SWEEPS.pop(sid, None)


def _bar_summary(bar):
    """What one of the run's bars did on recordings it never saw."""
    b = bar or {}
    out = {k: b.get(k) for k in ("spike_called", "spike_called_true",
                                 "garbage_into_spike", "spike_recall",
                                 "lean_spike", "lean_spike_true",
                                 "lean_garbage", "lean_garbage_true")}
    out["by_origin"] = {o: {k: v.get(k) for k in ("n_spike", "spike_called",
                                                 "garbage_into_spike",
                                                 "spike_recall")}
                        for o, v in (b.get("by_origin") or {}).items()}
    return out


def status(store):
    """Whether Prospector can sweep here, and what it was shown to do."""
    name = "Prospector"
    av = store.model()
    if not av:
        return {"ready": False, "name": name, "slot": TAG,
                "why": "Prospector has not been chosen yet. Train it with "
                       "tools/prospector_train.py, then choose its run with "
                       "tools/prospector_train.py choose <run>."}
    rec = store.get(av["run_id"])
    if not rec:
        return {"ready": False, "name": name, "slot": TAG,
                "why": "Prospector is run %s, which is not on this machine "
                       "yet. It arrives with the next pull." % av["run_id"]}
    rel = rec.get("model_file")
    if not rel or not os.path.exists(os.path.join(store.logs, rel)):
        return {"ready": False, "name": name, "slot": TAG,
                "why": "Prospector's model (%s) is not on this machine yet. "
                       "It arrives with the next pull." % (rel or "no file")}
    fin = rec.get("final") or {}
    res = fin.get("results") or {}
    target = float(av.get("target") or DEFAULT_TARGET)
    data = rec.get("data") or {}
    return {
        "ready": True, "name": name, "slot": TAG,
        "run_id": av["run_id"], "chosen_at": av.get("at"),
        "chosen_by": av.get("by"), "trained_at": rec.get("at"),
        "model": fin.get("model"), "families": fin.get("families") or [],
        "n_recordings": data.get("n_recordings"),
        "n_events": data.get("n_events"),
        "target": target, "t_spike": av.get("t_spike"),
        "t_lean": av.get("t_lean", LEAN),
        "auc": (res.get("pooled") or {}).get("auc"),
        # The bar chosen, as measured on recordings each model never saw.
        "held_out": _bar_summary((res.get("bars") or {}).get(repr(target))),
        "tolerances": [],
    }


def _call(p, ok, t_spike, t_lean=LEAN):
    """Spike at or over the bar; under it, leaning spike or leaning garbage.
    Nothing for a candidate that could not be read."""
    labels = np.full(p.size, None, dtype=object)
    good = np.asarray(ok, bool) & np.isfinite(p)
    labels[good & (p >= t_spike)] = "spike"
    labels[good & (p < t_spike) & (p >= t_lean)] = "likely_spike"
    labels[good & (p < t_lean)] = "likely_garbage"
    return labels


def a_person_decided(ev):
    """A candidate somebody decided -- not one only Prospector has."""
    return bool(ev.get("label")) and ev.get("by") != BY


def sweep(store, curate, bank, open_recording, gid, kind, job=None,
          read_remote=None):
    """Score every candidate in one pooled set. Returns the sweep record.

    `read_remote(spec, dest, job)` is how a recording only the cluster has
    is read (app.py `_pr_read_vacc`): it runs `read_node` on a compute node
    and leaves the read at `dest`, which is where a local read is kept."""
    from . import curation as curmod
    from . import toothfairy as tf
    from . import vaccio
    st = status(store)
    if not st["ready"]:
        raise aibeta.AiBetaError(st["why"])
    if curmod.kind_of(kind) != "pooled":
        raise aibeta.AiBetaError("Prospector sorts pooled sets only.")
    run_rec, bundle = store.load_model(st["run_id"])
    # The model's inputs in the order it learned them, checked against the
    # names it was trained with.
    fams = [f for f in aibeta.FAMILY_IDS if f in bundle["families"]]
    if aibeta.feature_names(fams) != list(bundle.get("feature_names") or []):
        raise aibeta.AiBetaError(
            "Prospector's inputs have changed since run %s was trained. "
            "Train it again." % st["run_id"])
    t_spike = float(st["t_spike"])
    t_lean = float(st.get("t_lean") or LEAN)

    cur = curate.get(gid, kind)
    if not cur:
        raise aibeta.AiBetaError("No pooled set for that recording.")
    events = sorted(cur.get("events") or [], key=lambda e: float(e["start"]))
    if not events:
        raise aibeta.AiBetaError("That pool has no events.")
    basis, basis_from = tf.set_basis(cur, bank, gid, kind)
    rec = aibeta.subset_channels(open_recording(gid),
                                 bundle.get("channels") or "even")
    which = rec.get("subset") or "all"
    sess = rec["session"]
    remote = vaccio.is_vacc(sess.get("path"))
    if remote and basis == retime.CONCAT:
        # Putting these stamps on the recording's clock needs its
        # segmentation, which only the cluster can make, and a sweep that
        # went ahead would read every one in the wrong place.
        raise aibeta.AiBetaError(
            "This pool's times are on the old joined-up clock, and its "
            "recording is only on the cluster, so they cannot be put on the "
            "recording's own clock here. Sweep it on a computer that has "
            "the recording.")
    report = None
    try:
        report = None if remote else continuity.check(sess.get("path"))
    except Exception:                                    # noqa: BLE001
        report = None
    times = []
    for e in events:
        t = float(e["start"])
        if basis == retime.CONCAT and report and report.get("ok"):
            t, _seg = continuity.concat_to_true(report, t)
        times.append(None if t is None else float(t))

    read_fams = [f for f in fams if f != "origin"
                 and f not in aibeta.DERIVED]
    want_phys = bool(set(read_fams) & aibeta.PHYS_IDS)
    want_filt = phys.filters_for(read_fams)
    want_xray = bool(set(read_fams) & set(phys.XR_IDS))
    want_spec = bool(set(read_fams) & set(phys.SPEC_IDS))
    key = hashlib.sha1(json.dumps({
        "t": [None if t is None else round(t, 6) for t in times],
        "probe": rec["probe"], "bad": sorted(rec["bad"]),
        "fv": aibeta.FEATURE_VERSION,
        "pv": phys.PHYS_VERSION if want_phys else None,
        "filt": sorted(want_filt), "xray": want_xray, "spec": want_spec,
        "channels": which}, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    path = os.path.join(store.cache, "sweep_%s__%s.npz"
                        % (shards.safe_base(gid), key))
    picks = tf._samples([i for i in range(len(events))
                         if times[i] is not None], seed=key)
    fam, ok, cached, traces = None, None, False, {"chans": [], "by_event": {}}
    kept = load_block(path, read_fams)
    if kept is not None:
        fam, ok, traces, kept_picks = kept
        if kept_picks is not None:
            picks = kept_picks
        cached = True

    if fam is None and remote:
        # Only the cluster has this recording: the reads run on a compute
        # node and come home as the read a local sweep would have kept.
        if read_remote is None:
            raise aibeta.AiBetaError(
                "This recording is only on the cluster, and this Prospector "
                "cannot send its reads there.")
        read_remote({
            "channels": [int(c["number"]) for c in rec["channels"]],
            "probe": rec["probe"], "bad": sorted(int(b) for b in rec["bad"]),
            "spacing": rec.get("spacing"), "times": times,
            "picks": [int(i) for i in picks], "read_fams": read_fams,
            "stages": list(READ_STAGES), "workers": READ_WORKERS,
            "n_events": len(events)}, path, job)
        kept = load_block(path, read_fams)
        if kept is None:
            raise aibeta.AiBetaError(
                "The cluster read this pool, but what came home does not "
                "hold every input Prospector scores. Sweep it again.")
        fam, ok, traces, kept_picks = kept
        if kept_picks is not None:
            picks = kept_picks

    if fam is None and job and picks:
        # The scanning screen's candidates first, read on their own, so it
        # has something real to sweep while the whole pool is read.
        def show(early):
            job.set_preview({"stage": "read", "samples": [
                {"i": int(i), "id": events[i]["id"],
                 "t": round(float(times[i]), 4), "channels": tr,
                 "channel_numbers": chans, "wave": [], "csd": [],
                 "profile": [], "readouts": {"peak_uv": pk, "best_ch": bc},
                 "p": None, "label": None}
                for i, (tr, chans, pk, bc) in early.items()]})
        tf._quick_traces(sess, rec["channels"], rec["probe"], rec["bad"],
                         times, picks, on_some=show)
    if fam is None:
        def first(fam1, ok1, traces1):
            # The screen's candidates are the ones the first read traced.
            picks[:] = [i for i in picks if i in traces1.get("by_event", {})]
            if job and want_phys:
                job.set_preview({"stage": "physio", "samples": [
                    tf._sample_row(i, events, times, fam1, None, None,
                                   traces1)
                    for i in picks if ok1[i]]})
        picks = list(picks)
        fam, ok, traces = read_block(sess, rec, times, report, picks,
                                     read_fams, job=job, on_first=first)
        save_block(path, fam, ok, traces, picks=picks)

    if job:
        job.begin("pr score", of=len(events), unit="candidates")
    fam["origin"] = origin_block({"events": events,
                                  "origin": [e.get("origin") for e in events]})
    if "recording" in fams:
        fam["recording"] = aibeta.derive_recording(fam, ok)
    if "wavebits" in fams:
        fam["wavebits"] = aibeta.derive_wavebits(fam, ok)
    X = np.hstack([fam[f] for f in fams]).astype(np.float64)
    X[~np.isfinite(X)] = np.nan
    p = np.full(len(events), np.nan)
    if ok.any():
        p[ok] = bundle["model"].predict_proba(X[ok])[:, 1]
    labels = _call(p, ok, t_spike, t_lean)
    if job:
        job.tick("pr score", len(events))

    vocab = {l["id"]: l for l in curmod.vocabulary("pooled")}
    vocab.update({l["id"]: l for l in (cur.get("labels") or [])})
    good = {k for k, l in vocab.items() if l.get("good")}
    bad = {k for k, l in vocab.items()
           if not l.get("good") and not l.get("flagged")}
    rows, counts = [], {c: 0 for c in CALLS + ("unread",)}
    agree = {"spike": {"compared": 0, "agree": 0},
             "lean": {"compared": 0, "agree": 0}}
    for i, e in enumerate(events):
        lab = labels[i]
        counts[lab or "unread"] += 1
        human = e.get("label") if a_person_decided(e) else None
        hc = 1 if human in good else 0 if human in bad else None
        if hc is not None and lab:
            side = "spike" if lab == "spike" else "lean"
            agree[side]["compared"] += 1
            agree[side]["agree"] += int(
                hc == 1 if lab in ("spike", "likely_spike") else hc == 0)
        row = {"id": e["id"], "start": float(e["start"]),
               "p": None if not np.isfinite(p[i]) else round(float(p[i]), 4),
               "label": lab, "readable": bool(ok[i]),
               "human": human, "human_by": e.get("by") if human else None,
               "mine": e.get("by") == BY and bool(e.get("label"))}
        for k in ("origin", "stamp", "pair_t", "channel", "end"):
            if e.get(k) is not None:
                row[k] = e[k]
        rows.append(row)
    samples = [tf._sample_row(i, events, times, fam, p, labels, traces)
               for i in picks if ok[i]]
    return {
        "gid": gid, "kind": kind, "set_name": cur.get("name"),
        "session_label": cur.get("session_label"),
        "run_id": st["run_id"], "model": st["model"], "families": fams,
        "slot": TAG, "model_name": st["name"],
        "channels": which, "channels_note": rec.get("subset_note"),
        "policy": {"t_spike": t_spike, "t_lean": t_lean,
                   "target": st["target"]},
        "held_out": st["held_out"],
        "basis": basis, "basis_from": basis_from, "cached": cached,
        "n": len(events), "n_readable": int(ok.sum()),
        "counts": counts,
        "label_names": {c: (vocab.get(c) or {}).get("name", c) for c in CALLS},
        "label_colors": {k: l.get("color") for k, l in vocab.items()},
        "already_decided": sum(1 for e in events if a_person_decided(e)),
        "open_to_it": sum(1 for e in events if not a_person_decided(e)),
        "agreement": agree,
        "samples": samples,
        "rows": rows,
        "at": aibeta._now(),
    }
