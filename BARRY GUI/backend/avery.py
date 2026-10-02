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


def status(runs):
    """What Avery is, in the terms the confirm dialog states."""
    av = runs.avery()
    if not av:
        return {"ready": False,
                "why": "Avery has not been chosen yet. In Checkup's AI Beta, "
                       "open a run trained with Avery's four bars and press "
                       "Make this Avery."}
    rec = runs.get(av["run_id"])
    if not rec:
        return {"ready": False, "why": "Avery is run %s, which is not on "
                                       "this machine yet." % av["run_id"]}
    res = rec.get("results") or {}
    pol = res.get("policy") or {}
    c99 = next((c for c in (res.get("catch") or [])
                if abs(c.get("target", 0) - 0.99) < 1e-9), {})
    fams = (rec.get("settings") or {}).get("families") or []
    return {
        "ready": True, "run_id": av["run_id"], "chosen_at": av.get("at"),
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
    }


def _cache_path(runs, gid, key):
    return os.path.join(runs.cache, "avery_%s__%s.npz" % (gid, key))


def _samples(order_ok, n=N_SAMPLES, seed=None):
    """One candidate from each n-th of the set, in time order."""
    rng = random.Random(seed)
    if not order_ok:
        return []
    chunks = np.array_split(np.asarray(order_ok), min(n, len(order_ok)))
    return [int(rng.choice(list(c))) for c in chunks if len(c)]


def sweep(runs, curate, bank, open_recording, gid, kind, job=None):
    """Score every candidate in one set. Returns the sweep record."""
    st = status(runs)
    if not st["ready"]:
        raise AI.AiBetaError(st["why"])
    run_rec, bundle = runs.load_model(st["run_id"])
    pol = bundle.get("policy") or st["policy"]
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
    rec = open_recording(gid)
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
        else None}).encode("utf-8")).hexdigest()[:20]
    path = _cache_path(runs, gid, key)
    fam, ok, cached = None, None, False
    if os.path.exists(path):
        try:
            with np.load(path, allow_pickle=False) as z:
                fam = {k[4:]: z[k] for k in z.files if k.startswith("fam_")}
                ok = z["ok"].astype(bool)
                cached = True
        except Exception:                                # noqa: BLE001
            fam = None

    stamps = [t for t in times if t is not None]
    if fam is None:
        n1 = len(braces.spans(stamps, window_ms=AI.SEARCH_MS + AI.HALF_MS,
                              pad_s=AI.PAD_S))
        if job:
            job.begin("avery read", of=n1, unit="stretches")

        def tick1(k, n):
            if job:
                job.tick("avery read", k)
        got1 = AI.read_entry(sess, rec["channels"], rec["probe"], rec["bad"],
                             times, report=report, job=job, on_span=tick1,
                             workers=READ_WORKERS)
        fam = dict(got1["fam"])
        ok = got1["ok"].astype(bool)
        if want_phys:
            n2 = len(phys.spans(stamps, phys.REACH_MS / 1000.0, phys.PAD_S))
            if job:
                job.begin("avery physio", of=n2, unit="stretches")
                # The first read already holds every waveform, so the
                # scanning screen has something real to show while the
                # longer read runs.
                job.set_preview({"stage": "physio", "samples": [
                    _sample_row(i, events, times, fam, None, None)
                    for i in _samples([i for i in range(len(events))
                                       if ok[i]], seed=key)]})

            def tick2(k, n):
                if job:
                    job.tick("avery physio", k)
            got2 = phys.read_physio(sess, rec["channels"], rec["probe"],
                                    rec["bad"], times, report=report,
                                    folder=sess.get("path"), job=job,
                                    on_span=tick2, aibeta=AI,
                                    workers=READ_WORKERS)
            fam.update(got2["fam"])
            ok = ok & got2["ok"].astype(bool)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez_compressed(path + ".part.npz", ok=ok,
                            **{"fam_" + k: v for k, v in fam.items()})
        os.replace(path + ".part.npz", path)

    if job:
        job.begin("avery score", of=len(events), unit="candidates")
    if "recording" in fams:
        fam["recording"] = AI.derive_recording(fam, ok)
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
    picks = _samples([i for i in range(len(events)) if ok[i]], seed=key)
    samples = [_sample_row(i, events, times, fam, p, labels) for i in picks]
    out = {
        "gid": gid, "kind": kind, "set_name": cur.get("name"),
        "session_label": cur.get("session_label"),
        "run_id": st["run_id"], "model": st["model"], "families": fams,
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


def _sample_row(i, events, times, fam, p, labels):
    """One candidate for the scanning screen: its trace and a few readouts."""
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
