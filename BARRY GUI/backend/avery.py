"""
avery.py -- Avery sweeps a Checkup set.

Avery is AI Beta's model, put to work (named by the user, 2026-10-02). A
sweep reads one curation set's candidates the way training read them -- the
first read for shape, the second for physiology -- scores every one with the
run that was made Avery, and calls each of them one of four things:

    DS, Flag for Deep Review, Flag, Garbage

by the bars that run set on mice it never saw (see `aibeta.POLICY`). Nothing
is written by a sweep. What happens to its calls is the person's choice,
made on the summary: accepting puts Avery's calls on the candidates nobody
has decided -- a person's decision is never overwritten -- and banks every
call as a version of its own, tagged `avery` and made by "Avery (AI)", so
the calls a model made and the calls people then made can be compared later.
Training never learns from an Avery version (`aibeta.dataset`).

THE SAMPLES. A sweep also hands back a dozen candidates, one from each
twelfth of the set in time order and picked at random within it, with their
waveforms -- for the scanning screen. They are real candidates and, at the
end, their real verdicts; nothing on that screen is invented.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time

import numpy as np

from . import aibeta as AI
from . import aibetaphys as phys
from . import braces, continuity, retime

READ_WORKERS = 6
N_SAMPLES = 12

# HOW MANY REAL SPIKES MAY BE CALLED GARBAGE, chosen in the sweep dialog
# (the user, 2026-10-03: "minimise the number of flags with a more flexible
# tolerance of real DS loss, and an emphasis on cleaning up as much garbage
# as possible" -- so people sift through as little garbage as possible).
# The DS bar does not move with it: it stays where the run put it, keeping
# 99% of garbage out of DS. Only the Garbage bar does, and with it how much
# is left in Flag. Worked out from the run's held-out scores, so every row
# is what that bar did on mice the model never saw.
TOLERANCES = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)
DEFAULT_TOLERANCE = 0.20

_SWEEPS = {}
_LOCK = threading.Lock()
MAX_SWEEPS = 8


def remember(sid, rec):
    with _LOCK:
        _SWEEPS[sid] = rec
        while len(_SWEEPS) > MAX_SWEEPS:
            _SWEEPS.pop(next(iter(_SWEEPS)))


def recall(sid):
    with _LOCK:
        return _SWEEPS.get(sid)


def forget(sid):
    with _LOCK:
        _SWEEPS.pop(sid, None)


def set_basis(cur, bank, gid, kind):
    """Which clock this set's times are on, and how that is known."""
    tb = (cur.get("time_basis") or {}).get("kind")
    if tb:
        return tb, "the set's own record"
    best = None
    for ent in bank.all():
        if ent.get("gid") != gid or (ent.get("type") or "") != kind:
            continue
        if best is None or len(ent.get("versions") or []) > \
                len(best.get("versions") or []):
            best = ent
    if best:
        vers = best.get("versions") or []
        v = max([x.get("v") or 0 for x in vers] or [0])
        b = bank.basis_at(best, v) or (retime.basis_of(best) or {}).get("basis")
        return b, "its Event Bank entry"
    return None, "nothing recorded; taken as the recording's own clock"


def status(runs, slot="avery"):
    """What a model is, in the terms the confirm dialog states."""
    name = AI.SLOT_NAMES.get(slot, slot)
    av = runs.avery(slot)
    if not av:
        return {"ready": False, "slot": slot, "name": name,
                "why": "%s has not been chosen yet. In Checkup's AI Beta, "
                       "open a run trained with its bars and press Make "
                       "this %s." % (name, name)}
    rec = runs.get(av["run_id"])
    if not rec:
        return {"ready": False, "why": "Avery is run %s, which is not on "
                                       "this machine yet." % av["run_id"]}
    res = rec.get("results") or {}
    pol = res.get("policy") or {}
    c99 = next((c for c in (res.get("catch") or [])
                if abs(c.get("target", 0) - 0.99) < 1e-9), {})
    fams = (rec.get("settings") or {}).get("families") or []
    ho = pol.get("held_out") or {}
    n_ds = sum((b or {}).get("n_ds", 0) for b in ho.values())
    n_g = sum((b or {}).get("n_garbage", 0) for b in ho.values())
    return {
        "ready": True, "slot": slot, "name": name,
        "run_id": av["run_id"], "chosen_at": av.get("at"),
        # In its four calls, on mice it never saw: garbage it called Garbage,
        # real spikes it called Garbage, and garbage it let into DS.
        "garbage_called_garbage": ((ho.get("garbage") or {}).get(
            "n_garbage", 0) / n_g) if n_g else None,
        "ds_called_garbage": ((ho.get("garbage") or {}).get("n_ds", 0)
                              / n_ds) if n_ds else None,
        "garbage_into_ds": ((ho.get("spike") or {}).get("n_garbage", 0)
                            / n_g) if n_g else None,
        "flagged_share": (((ho.get("flag") or {}).get("n", 0)
                           + (ho.get("review") or {}).get("n", 0))
                          / max(1, n_ds + n_g)),
        "chosen_by": av.get("by"), "trained_at": rec.get("at"),
        "model": (rec.get("settings") or {}).get("model"),
        "families": fams,
        "needs_second_read": bool(set(fams) & AI.PHYS_IDS),
        "n_recordings": (rec.get("data") or {}).get("n_recordings"),
        "n_events": (rec.get("data") or {}).get("n_events"),
        "garbage_caught": c99.get("garbage_caught_frac"),
        "ds_flagged": c99.get("ds_flagged_frac"),
        "policy": pol,
        "model_file": (rec.get("model") or {}).get("file"),
        "tolerances": tolerance_table(runs, av["run_id"], pol),
        "default_tolerance": DEFAULT_TOLERANCE,
    }


def _held_out(runs, run_id):
    """The run's held-out scores and answers, or (None, None)."""
    rec = runs.get(run_id) or {}
    oof = (rec.get("results") or {}).get("oof") or {}
    if not oof.get("p"):
        return None, None
    return np.asarray(oof["p"], float), np.asarray(oof["y"], int)


def policy_for(runs, run_id, base, ds_loss):
    """The run's bars with the Garbage bar moved to `ds_loss`."""
    p, y = _held_out(runs, run_id)
    if p is None or ds_loss is None:
        return base
    t = dict((base or {}).get("targets") or AI.POLICY_PLUS)
    t["garbage_ds_loss"] = float(ds_loss)
    t.pop("garbage_purity", None)
    return AI.label_policy(p, y, t)


def tolerance_table(runs, run_id, base):
    """What each tolerance does, on mice the model never saw."""
    p, y = _held_out(runs, run_id)
    if p is None:
        return []
    g, d = y == 0, y == 1
    out = []
    for loss in TOLERANCES:
        pol = policy_for(runs, run_id, base, loss)
        lab = AI.apply_policy(p, pol)
        flagged = np.isin(lab, ["flag", "review"])
        out.append({
            "ds_loss": loss,
            "garbage_cleaned": round(float(((lab == "garbage") & g).sum()
                                           / max(1, g.sum())), 4),
            "garbage_left": round(float((flagged & g).sum()
                                        / max(1, g.sum())), 4),
            "garbage_into_ds": round(float(((lab == "spike") & g).sum()
                                           / max(1, g.sum())), 4),
            "ds_called_garbage": round(float(((lab == "garbage") & d).sum()
                                             / max(1, d.sum())), 4),
            "flagged": round(float(flagged.mean()), 4),
        })
    return out


def _cache_path(runs, gid, key):
    return os.path.join(runs.cache, "avery_%s__%s.npz" % (gid, key))


def _samples(order_ok, n=N_SAMPLES, seed=None):
    """One candidate from each n-th of the set, in time order."""
    rng = random.Random(seed)
    if not order_ok:
        return []
    chunks = np.array_split(np.asarray(order_ok), min(n, len(order_ok)))
    return [int(rng.choice(list(c))) for c in chunks if len(c)]


def sweep(runs, curate, bank, open_recording, gid, kind, job=None,
          slot="avery", ds_loss=None):
    """Score every candidate in one set. Returns the sweep record."""
    st = status(runs, slot)
    if not st["ready"]:
        raise AI.AiBetaError(st["why"])
    run_rec, bundle = runs.load_model(st["run_id"])
    pol = bundle.get("policy") or st["policy"]
    if ds_loss is not None and st.get("tolerances"):
        pol = policy_for(runs, st["run_id"], pol, ds_loss)
    if not pol:
        raise AI.AiBetaError("Avery's run has no bars to sort by.")
    fams = list(bundle["families"])

    cur = curate.get(gid, kind)
    if not cur:
        raise AI.AiBetaError("No %s set for that recording." % kind)
    events = sorted(cur.get("events") or [], key=lambda e: float(e["start"]))
    if not events:
        raise AI.AiBetaError("That set has no candidates.")
    basis, basis_from = set_basis(cur, bank, gid, kind)
    # The channels the model was trained on, and only those.
    which = (run_rec.get("settings") or {}).get("channels") \
        or bundle.get("channels") or "all"
    rec = AI.subset_channels(open_recording(gid), which)
    sess = rec["session"]
    report = None
    try:
        report = continuity.check(sess.get("path"))
    except Exception:                                    # noqa: BLE001
        report = None
    times = []
    for e in events:
        t = float(e["start"])
        if basis == retime.CONCAT and report and report.get("ok"):
            t, _seg = continuity.concat_to_true(report, t)
        times.append(None if t is None else float(t))

    want_phys = bool(set(fams) & AI.PHYS_IDS)
    key = hashlib.sha1(json.dumps({
        "t": [None if t is None else round(t, 6) for t in times],
        "probe": rec["probe"], "bad": sorted(rec["bad"]),
        "fv": AI.FEATURE_VERSION, "pv": phys.PHYS_VERSION if want_phys
        else None, **({"channels": which} if which != "all" else {})})
        .encode("utf-8")).hexdigest()[:20]
    path = _cache_path(runs, gid, key)
    # Which candidates the scanning screen will draw, chosen before the read
    # so the read can keep their channels: one from each twelfth of the set
    # in time order, at random within it.
    picks = _samples([i for i in range(len(events)) if times[i] is not None],
                     seed=key)
    fam, ok, cached, traces = None, None, False, {"chans": [], "by_event": {}}
    if os.path.exists(path):
        try:
            with np.load(path, allow_pickle=False) as z:
                fam = {k[4:]: z[k] for k in z.files if k.startswith("fam_")}
                ok = z["ok"].astype(bool)
                # A read from before one of the model's inputs existed is
                # read again rather than scored without it.
                if any(f not in fam for f in fams if f not in AI.DERIVED):
                    raise KeyError("an input this read does not hold")
                if "trace_idx" in z.files:
                    traces = {"chans": [int(c) for c in z["trace_chans"]],
                              "by_event": {int(i): z["trace_arr"][n]
                                           for n, i in enumerate(z["trace_idx"])}}
                    picks = [int(i) for i in z["trace_idx"]]
                cached = True
        except Exception:                                # noqa: BLE001
            fam = None

    stamps = [t for t in times if t is not None]
    if fam is None and job and picks:
        # The scanning screen's candidates, read on their own first -- a
        # second or two -- so it has something real to sweep while the
        # whole set is read. Centred on the stamp, before any clock
        # correction; the read below replaces them with corrected ones.
        def show(early):
            job.set_preview({"stage": "read", "samples": [
                {"i": int(i), "id": events[i]["id"],
                 "t": round(float(times[i]), 4), "channels": tr,
                 "channel_numbers": chans, "wave": [], "csd": [],
                 "profile": [], "readouts": {"peak_uv": pk, "best_ch": bc},
                 "p": None, "label": None}
                for i, (tr, chans, pk, bc) in early.items()]})
        # Shown after the first, then again with all of them: the screen
        # has a candidate to scan in a second or so.
        _quick_traces(sess, rec["channels"], rec["probe"], rec["bad"],
                      times, picks, on_some=show)
    if fam is None:
        n1 = len(braces.spans(stamps, window_ms=AI.SEARCH_MS + AI.HALF_MS,
                              pad_s=AI.PAD_S))
        if job:
            job.begin("avery read", of=n1, unit="stretches")

        def tick1(k, n):
            if job:
                job.tick("avery read", k)
        got1 = AI.read_entry(sess, rec["channels"], rec["probe"], rec["bad"],
                             times, spacing=rec.get("spacing"),
                             report=report, job=job, on_span=tick1,
                             workers=READ_WORKERS, trace_ids=picks)
        fam = dict(got1["fam"])
        ok = got1["ok"].astype(bool)
        traces = got1.get("traces") or traces
        picks = [i for i in picks if i in traces.get("by_event", {})]
        if want_phys:
            n2 = len(phys.spans(stamps, phys.REACH_MS / 1000.0, phys.PAD_S))
            if job:
                job.begin("avery physio", of=n2, unit="stretches")
                # The first read already holds every waveform, so the
                # scanning screen has something real to show while the
                # longer read runs.
                job.set_preview({"stage": "physio", "samples": [
                    _sample_row(i, events, times, fam, None, None, traces)
                    for i in picks if ok[i]]})

            def tick2(k, n):
                if job:
                    job.tick("avery physio", k)
            got2 = phys.read_physio(sess, rec["channels"], rec["probe"],
                                    rec["bad"], times, report=report,
                                    folder=sess.get("path"), job=job,
                                    on_span=tick2, aibeta=AI,
                                    workers=READ_WORKERS,
                                    spacing=rec.get("spacing"),
                                    want_filt=bool(set(fams)
                                                   & set(phys.FILT_IDS)))
            fam.update(got2["fam"])
            ok = ok & got2["ok"].astype(bool)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tr_idx = [i for i in picks if i in traces.get("by_event", {})]
        extra = {}
        if tr_idx:
            extra = {"trace_idx": np.array(tr_idx, dtype=int),
                     "trace_chans": np.array(traces["chans"], dtype=int),
                     "trace_arr": np.stack([traces["by_event"][i]
                                            for i in tr_idx])}
        np.savez_compressed(path + ".part.npz", ok=ok, **extra,
                            **{"fam_" + k: v for k, v in fam.items()})
        os.replace(path + ".part.npz", path)

    if job:
        job.begin("avery score", of=len(events), unit="candidates")
    if "recording" in fams:
        fam["recording"] = AI.derive_recording(fam, ok)
    if "wavebits" in fams:
        fam["wavebits"] = AI.derive_wavebits(fam, ok)
    X = np.hstack([fam[f] for f in fams]).astype(np.float64)
    X[~np.isfinite(X)] = np.nan
    if X.shape[1] != len(bundle.get("feature_names") or []):
        raise AI.AiBetaError(
            "Avery's model expects %d inputs and this read made %d -- the "
            "inputs have changed since it was trained. Train it again."
            % (len(bundle.get("feature_names") or []), X.shape[1]))
    p = np.full(len(events), np.nan)
    if ok.any():
        p[ok] = bundle["model"].predict_proba(X[ok])[:, 1]
    labels = np.full(len(events), "flag", dtype=object)
    labels[ok] = AI.apply_policy(p[ok], pol)
    if job:
        job.tick("avery score", len(events))

    names = {l["id"]: l.get("name") or l["id"]
             for l in (cur.get("labels") or [])}
    rows, counts, agree, compared = [], {}, 0, 0
    for i, e in enumerate(events):
        lab = str(labels[i])
        counts[lab] = counts.get(lab, 0) + 1
        human = e.get("label")
        if human:
            hc = AI._cls(human)
            ac = 1 if lab == "spike" else 0 if lab == "garbage" else None
            if hc is not None and ac is not None:
                compared += 1
                agree += int(hc == ac)
        rows.append({"id": e["id"], "start": float(e["start"]),
                     "p": None if not np.isfinite(p[i]) else round(float(p[i]), 4),
                     "label": lab, "readable": bool(ok[i]),
                     "human": human, "human_by": e.get("by")})
    samples = [_sample_row(i, events, times, fam, p, labels, traces)
               for i in picks if ok[i]]
    out = {
        "gid": gid, "kind": kind, "set_name": cur.get("name"),
        "session_label": cur.get("session_label"),
        "run_id": st["run_id"], "model": st["model"], "families": fams,
        "slot": slot, "model_name": st["name"],
        "ds_loss": ds_loss if st.get("tolerances") else None,
        "policy": {k: pol[k] for k in ("t_ds", "t_review", "t_garbage")},
        "held_out": pol.get("held_out"),
        "basis": basis, "basis_from": basis_from, "cached": cached,
        "n": len(events), "n_readable": int(ok.sum()),
        "counts": counts,
        "label_names": {k: names.get(k, k) for k in AI.POLICY_LABELS},
        "label_colors": {l["id"]: l.get("color")
                         for l in (cur.get("labels") or [])},
        "already_decided": sum(1 for e in events if e.get("label")),
        "agreement": {"compared": compared, "agree": agree},
        "samples": samples,
        "rows": rows,
        "at": AI._now(),
    }
    return out


def _quick_traces(session, channels, probe, bad, times, picks,
                  on_some=None, first=1):
    """Every even channel, +-50 ms around each picked stamp, read alone.

    `on_some(out)` is called once `first` of them are in and again at the
    end, so a screen can start on the first while the rest are read.

    Only the even channels -- the ones the screen draws -- and a quarter
    second either side, a few at a time: measured on KCNT1 m78 s1 with the
    machine busy, every channel over +-0.45 s one after another took 11 s
    for the first two and 35 s for twelve, which is the wait the user saw.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from . import dspca
    try:
        prm = dspca.Params(probe=probe, invert=True,
                           bad=sorted(int(b) for b in bad or []))
        prm.spacing = dspca.spacing_for(prm.probe)
        spec = prm.spec()
    except Exception:                                    # noqa: BLE001
        return {}
    even = [ch for ch in channels if int(ch["number"]) % 2 == 0]         or list(channels)
    chans = [int(ch["number"]) for ch in even]
    badd = {int(b): "marked" for b in (bad or [])}

    def one(i):
        t = times[i]
        if t is None:
            return i, None
        try:
            got = AI._read_matrix(session, even, t - 0.25, t + 0.25,
                                  spec, prm.lfp_fs)
        except Exception:                                # noqa: BLE001
            got = None
        if not got:
            return i, None
        _w, band, anchor, fs = got
        band = braces.repair(band, even, badd)
        c = int(round((t - anchor) * fs))
        h = int(round(0.05 * fs))
        st_ = max(1, int(round(0.002 * fs)))
        if c - h < 0 or c + h + 1 > band.shape[1]:
            return i, None
        blk = band[:, c - h:c + h + 1:st_]
        k = int(np.argmax(np.abs(blk[:, blk.shape[1] // 2])))
        return i, (np.round(blk, 1).tolist(), chans,
                   round(float(blk[k, blk.shape[1] // 2]), 1), chans[k])

    out, told = {}, False
    with ThreadPoolExecutor(max_workers=4) as pool:
        for fut in as_completed([pool.submit(one, i) for i in picks]):
            i, got = fut.result()
            if got is None:
                continue
            out[i] = got
            if on_some and not told and len(out) >= first:
                told = True
                on_some(dict(out))
    if on_some and out and (not told or len(out) > first):
        on_some(dict(out))
    return out


def _sample_row(i, events, times, fam, p, labels, traces=None):
    """One candidate for the scanning screen: its traces and a few readouts.

    `channels` is every even channel's trace, stacked in probe order, which
    is what the screen draws; `wave` and `csd` are the single best-channel
    and shank-CSD traces the model measured, kept for anything smaller."""
    waves = fam.get("waves")
    half = (waves.shape[1] - AI.PROFILE_ROWS) // 2 if waves is not None else 0

    def val(f, name):
        arr = fam.get(f)
        if arr is None or name not in AI._NAMES.get(f, []):
            return None
        v = arr[i, AI._NAMES[f].index(name)]
        return None if not np.isfinite(v) else round(float(v), 3)
    return {
        "i": int(i), "id": events[i]["id"],
        "t": round(float(times[i] if times[i] is not None
                         else events[i]["start"]), 4),
        "wave": [round(float(x), 3) for x in waves[i, :half]]
        if waves is not None else [],
        "csd": [round(float(x), 3) for x in waves[i, half:2 * half]]
        if waves is not None else [],
        "profile": [round(float(x), 3) for x in waves[i, 2 * half:]]
        if waves is not None else [],
        "channels": (traces or {}).get("by_event", {}).get(int(i)).tolist()
        if (traces or {}).get("by_event", {}).get(int(i)) is not None else [],
        "channel_numbers": (traces or {}).get("chans") or [],
        "readouts": {
            "amp_uv": val("incisor", "amp_uv"),
            "half_width_ms": val("incisor", "half_width_ms"),
            "csd_peak": val("shank", "csd_peak_rel"),
            "common_mode": val("shank", "common_mode_band"),
            "mua": val("mua", "mua_peak_ch"),
            "rise_ms": val("shape", "rise_ms"),
            "likeness": val("template", "patch_vs_typical"),
        },
        "p": None if p is None or not np.isfinite(p[i])
        else round(float(p[i]), 4),
        "label": None if labels is None else str(labels[i]),
    }
