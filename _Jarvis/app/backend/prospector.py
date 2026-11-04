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
import json
import os
import re
import time

import numpy as np

from . import aibeta, retime, shards
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


def _is_pass(ver):
    """A person's curation pass: their calls, not something a tool made of
    them (an alignment, a model's sweep, Root Canal, X-ray, a re-timing)."""
    if ver.get("aligned") or aibeta._is_model(ver):
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
        if aibeta._is_model(ver):
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
    """Prospector's run records (small, committed) and models (cache)."""

    def __init__(self, logs_dir):
        self.dir = os.path.join(logs_dir, "prospector", "runs")
        self.models = os.path.join(logs_dir, ".cache", "prospector")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.models, exist_ok=True)

    def new_id(self):
        return "pr" + time.strftime("%Y%m%d-%H%M%S")

    def save(self, rec, model=None):
        rid = rec["id"]
        if model is not None:
            import joblib
            path = os.path.join(self.models, rid + ".joblib")
            joblib.dump(model, path, compress=3)
            rec["model_file"] = os.path.relpath(path, os.path.dirname(
                os.path.dirname(self.dir)))
        path = os.path.join(self.dir, "%s@%s.json" % (rid, shards.machine_id()))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1, default=str)
        os.replace(tmp, path)
        return path
