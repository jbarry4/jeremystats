# -*- coding: utf-8 -*-
"""cells.py -- the Cells: a recording's curated Kilosort units, read back.

PROJECT EVOLVE phase 7 (2026-11-21). A soft launch: Jarvis READS the sorts
the lab has already made, it does not make new ones. What the user decided:

  * Cells are Isabella's curated cells only -- the `timestamps\\<id>.mat`
    export beside a recording. A recording sorted and never curated says so
    and banks nothing.
  * Which cells exist is kept as CURATION VERSIONS: every source -- the
    export, Phy's labels once somebody has curated in Phy, any later
    re-curation -- is read into a version of the recording's cell set. Two
    versions are compared cell by cell through the spikes they share, and
    the comparison says which cells were kept, added, removed, merged or
    split. The version banked is the one a person picked.
  * The sort read is the NON-inverted run (`kilosort_tl6_tu7_fs30000.0`);
    its `invert_True` twin is named, and a polarity check says whether the
    cells' spikes swing the way the non-inverted run expects.

WHAT IS ON DISK (D:\\PTEN, 2026-11-21: 39 such runs, 32 curated)
  <session>\\binary\\CSC_Raw.dat           int16, 64 channels, 30 kHz, on
                                          CONCATENATED time (pauses
                                          squeezed out)
  <session>\\binary\\kilosort_tl6_tu7_fs30000.0\\
      spike_times.npy  spike_clusters.npy  spike_templates.npy
      templates.npy  channel_map.npy  channel_positions.npy  amplitudes.npy
      cluster_group.tsv  (KSLabel until Phy writes `group`)
  <session>\\timestamps\\<cluster>.mat     (or units\\timestamps) the export:
                                          `cluster_<id>_timestamp`, int64
                                          sample indices of that run

Checked 2026-11-21 on all 32 curated recordings on D:\\PTEN
(tools/test_cells.py): each of the 519 exported cells' samples equals
`spike_times[spike_clusters == id]` of the non-inverted run exactly. In 13
of them some cells also equal the inverted twin's cluster of the same id
(the twin sorted those identically); in the rest, none do.

Samples become seconds of the recording through the continuity map
(continuity.sample_to_true, vectorised here and checked against it): the
binary is concatenated time, and a pause left in would put every spike
after it early (memory: ied-hand-sorts-are-on-concat-time).

The spikes themselves never go into the Bank or the shared tables -- a
recording's curated cells fire 10^4 to 10^5 spikes, past the shared table's
4 MB row and far past what belongs in a public repo. A version names each
cell's spikes by digest; the spikes are read from the sort folder and kept
in this machine's cache.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import time

import numpy as np

PLAIN_RUN = "kilosort_tl6_tu7_fs30000.0"
N_CHAN = 64
FS = 30000.0
WAVE_MS = 1.5          # each side of the spike, for the mean waveform
WAVE_SPIKES = 500      # spikes averaged, evenly through the recording
WAVE_HP = 300.0        # Hz, the high-pass a spike's shape is read through
NEIGHBOURS = 3         # contacts each side of the best one
ACG_MS = 50
ISI_MS = 50
RATE_BIN_S = 10.0
PETH_HALF_S = 0.5
PETH_BIN_S = 0.01
REFRACTORY_MS = 2.0


class CellsError(Exception):
    pass


# --------------------------------------------------------------------------
# Finding the sort and its curations
# --------------------------------------------------------------------------
def _ls(d):
    try:
        return sorted(os.listdir(d))
    except OSError:
        return []


def _mtime(p):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S",
                             time.localtime(os.path.getmtime(p)))
    except OSError:
        return None


def binary_dir(session_path):
    return os.path.join(session_path or "", "binary")


def runs(session_path):
    """Every finished Kilosort run beside a recording, plain ones first."""
    out = []
    b = binary_dir(session_path)
    for name in _ls(b):
        p = os.path.join(b, name)
        if not name.lower().startswith("kilosort") or not os.path.isdir(p):
            continue
        if not os.path.isfile(os.path.join(p, "spike_times.npy")):
            continue
        out.append({"name": name, "path": p, "at": _mtime(p),
                    "inverted": "invert_true" in name.lower()})
    out.sort(key=lambda r: (r["inverted"], r["name"] != PLAIN_RUN,
                            r["name"]))
    return out


def pick_run(session_path):
    """The non-inverted run Jarvis reads, and its inverted twin, if any."""
    rs = runs(session_path)
    plain = [r for r in rs if not r["inverted"]]
    if not plain:
        return None, None
    run = plain[0]
    twin = next((r for r in rs if r["inverted"]
                 and r["name"].lower().startswith(run["name"].lower())), None)
    return run, twin


def export_dir(session_path):
    for rel in ("timestamps", os.path.join("units", "timestamps")):
        p = os.path.join(session_path or "", rel)
        if os.path.isdir(p) and any(n.lower().endswith(".mat")
                                    for n in _ls(p)):
            return p
    return None


def phy_state(run_dir):
    """Whether Phy has written its labels: cluster_group.tsv with a `group`
    column (Kilosort writes the same file with `KSLabel`)."""
    p = os.path.join(run_dir, "cluster_group.tsv")
    try:
        with open(p, "r", encoding="utf-8") as fh:
            head = fh.readline().strip().split("\t")
    except OSError:
        return {"edited": False, "path": None, "at": None}
    return {"edited": len(head) > 1 and head[1].strip().lower() == "group",
            "path": p, "at": _mtime(p)}


def sources(session_path, run_dir):
    """The places a curation can be read from, newest information first."""
    out = []
    ex = export_dir(session_path)
    if ex:
        mats = [n for n in _ls(ex) if n.lower().endswith(".mat")]
        newest = max((os.path.getmtime(os.path.join(ex, n)) for n in mats),
                     default=0)
        out.append({"kind": "export", "name": "Isabella's export",
                    "path": ex, "n": len(mats),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S",
                                        time.localtime(newest))
                    if newest else None})
    ph = phy_state(run_dir)
    if ph["edited"]:
        out.append({"kind": "phy", "name": "Phy's labels", "path": ph["path"],
                    "at": ph["at"], "n": None})
    return out


def describe(session_path):
    """What a recording has, for the Kilosort tool's steps."""
    run, twin = pick_run(session_path)
    raw = os.path.join(binary_dir(session_path), "CSC_Raw.dat")
    return {
        "binary": os.path.isfile(raw),
        "binary_path": raw if os.path.isfile(raw) else None,
        "run": run, "twin": twin,
        "sources": sources(session_path, run["path"]) if run else [],
        "export": export_dir(session_path),
    }


# --------------------------------------------------------------------------
# Reading a source into cells
# --------------------------------------------------------------------------
def _load(run_dir, name, mmap=True):
    return np.load(os.path.join(run_dir, name),
                   mmap_mode="r" if mmap else None)


def _digest(samples):
    a = np.ascontiguousarray(np.sort(np.asarray(samples, dtype=np.int64)))
    return hashlib.sha1(a.tobytes()).hexdigest()[:16]


def _mat_samples(path):
    import scipy.io as sio
    try:
        m = sio.loadmat(path)
        keys = [k for k in m if not k.startswith("__")]
        if not keys:
            raise CellsError("%s holds no variable." % path)
        return np.asarray(m[keys[0]]).ravel().astype(np.int64)
    except NotImplementedError:
        import h5py
        with h5py.File(path, "r") as f:
            k = [k for k in f.keys() if not k.startswith("#")][0]
            return np.asarray(f[k]).ravel().astype(np.int64)


def read_source(session_path, run_dir, kind):
    """{cell id: sorted int64 samples} from one source."""
    out = {}
    if kind == "export":
        ex = export_dir(session_path)
        if not ex:
            raise CellsError("There is no export (timestamps folder) beside "
                             "this recording.")
        for n in _ls(ex):
            if not n.lower().endswith(".mat"):
                continue
            stem = os.path.splitext(n)[0]
            try:
                cid = int(stem.split("_")[-1] if not stem.isdigit() else stem)
            except ValueError:
                continue
            out[cid] = np.sort(_mat_samples(os.path.join(ex, n)))
        return out
    if kind == "phy":
        ph = phy_state(run_dir)
        if not ph["edited"]:
            raise CellsError("Phy has not written its labels for this sort "
                             "(cluster_group.tsv still holds Kilosort's).")
        good = []
        with open(ph["path"], "r", encoding="utf-8") as fh:
            for row in csv.reader(fh, delimiter="\t"):
                if len(row) > 1 and row[1].strip().lower() == "good":
                    try:
                        good.append(int(row[0]))
                    except ValueError:
                        pass
        st = np.asarray(_load(run_dir, "spike_times.npy")).ravel()
        sc = np.asarray(_load(run_dir, "spike_clusters.npy")).ravel()
        for cid in good:
            out[cid] = np.sort(st[sc == cid].astype(np.int64))
        return out
    raise CellsError("Jarvis does not know a curation source %r." % kind)


def check_against_run(run_dir, cells):
    """How many of a source's cells are exactly that run's clusters."""
    st = np.asarray(_load(run_dir, "spike_times.npy")).ravel()
    sc = np.asarray(_load(run_dir, "spike_clusters.npy")).ravel()
    same = 0
    for cid, s in cells.items():
        mine = st[sc == cid].astype(np.int64)
        if len(mine) == len(s) and np.array_equal(np.sort(mine), s):
            same += 1
    return same


# --------------------------------------------------------------------------
# Where each cell is
# --------------------------------------------------------------------------
def best_channels(run_dir, cells):
    """{cell id: (template-channel index, binary row, depth um)} -- the
    contact where the cell's dominant template is biggest peak to peak
    (Isabella's extract_cluster_channels.py). The CSC is row + 1."""
    tm = _load(run_dir, "templates.npy")
    cmap = np.asarray(_load(run_dir, "channel_map.npy", False)).ravel()
    pos = np.asarray(_load(run_dir, "channel_positions.npy", False))
    stt = None
    try:
        stt = np.asarray(_load(run_dir, "spike_templates.npy")).ravel()
        st = np.asarray(_load(run_dir, "spike_times.npy")).ravel()
    except OSError:
        stt = None
    out = {}
    for cid, s in cells.items():
        t = cid
        if stt is not None and len(s):
            idx = np.searchsorted(st, s[:: max(1, len(s) // 200)])
            idx = idx[idx < len(st)]
            got = stt[idx]
            if got.size:
                t = int(np.bincount(got.astype(np.int64)).argmax())
        if t < 0 or t >= tm.shape[0]:
            t = min(max(cid, 0), tm.shape[0] - 1)
        w = np.asarray(tm[t])
        ptp = w.max(axis=0) - w.min(axis=0)
        k = int(np.argmax(ptp))
        out[cid] = (k, int(cmap[k]), float(pos[k][1]) if pos.ndim == 2
                    else float(k))
    return out


def neighbours(run_dir, k, n=NEIGHBOURS):
    """The template-channel indices around index `k` by depth, best first
    then outward, as binary rows with their depths."""
    cmap = np.asarray(_load(run_dir, "channel_map.npy", False)).ravel()
    pos = np.asarray(_load(run_dir, "channel_positions.npy", False))
    y = pos[:, 1] if pos.ndim == 2 else np.arange(len(cmap), dtype=float)
    order = np.argsort(np.abs(y - y[k]) + 1e-6 * np.arange(len(y)))
    pick = sorted(order[: 2 * n + 1], key=lambda i: y[i])
    return [(int(i), int(cmap[i]), float(y[i])) for i in pick]


# --------------------------------------------------------------------------
# Concatenated samples -> seconds of the recording
# --------------------------------------------------------------------------
def true_seconds(report, samples):
    """Vectorised continuity.sample_to_true. NaN off the end of the data."""
    s = np.asarray(samples, dtype=np.int64)
    marks = (report or {}).get("breaks") or []
    if not marks:
        return s / FS
    t0 = int(report.get("t0_us") or 0)
    fall = 1e6 / (float(report.get("fs") or 0) or FS)
    bi = np.array([int(r[0]) for r in marks], dtype=np.int64)
    bu = np.array([int(r[1]) for r in marks], dtype=np.float64)
    per = np.array([float(r[2]) if len(r) > 2 else fall for r in marks])
    order = np.argsort(bi)
    bi, bu, per = bi[order], bu[order], per[order]
    k = np.searchsorted(bi, s, side="right") - 1
    out = np.full(s.shape, np.nan)
    ok = (k >= 0) & (s < int(report.get("total_samples") or 0))
    kk = k[ok]
    out[ok] = (bu[kk] - t0) / 1e6 + (s[ok] - bi[kk]) * per[kk] / 1e6
    return out


# --------------------------------------------------------------------------
# A version's cell table
# --------------------------------------------------------------------------
def layer_of(sheet, csc):
    """(region id, name, colour) of a CSC from a layer sheet, or Nones."""
    if not sheet:
        return None, None, None
    lab = (sheet.get("labels") or {}).get(str(csc))
    if not lab:
        return None, None, None
    regs = {r.get("id"): r for r in sheet.get("regions") or []}
    r = regs.get(lab) or {}
    return lab, r.get("name") or lab, r.get("color")


def cell_table(run_dir, cells, report, sheet=None):
    """One row per cell: where it is, how much it fired, when."""
    best = best_channels(run_dir, cells)
    dur = None
    if report and report.get("total_samples"):
        dur = true_seconds(report, [int(report["total_samples"]) - 1])[0]
    rows = []
    for cid in sorted(cells):
        s = cells[cid]
        k, row, depth = best[cid]
        tt = true_seconds(report, s[[0, -1]]) if len(s) else [None, None]
        lid, lname, lcol = layer_of(sheet, row + 1)
        rows.append({
            "id": int(cid), "n": int(len(s)), "digest": _digest(s),
            "csc": row + 1, "ch_index": k, "depth_um": round(depth, 1),
            "layer": lid, "layer_name": lname, "layer_color": lcol,
            "first_s": None if tt[0] is None or np.isnan(tt[0])
            else round(float(tt[0]), 6),
            "last_s": None if tt[1] is None or np.isnan(tt[1])
            else round(float(tt[1]), 6),
            "rate_hz": (round(len(s) / float(dur), 3)
                        if dur and dur > 0 else None),
        })
    return rows


def payload_for(source, run, rows, session_label=None, polarity=None):
    """A curation version's payload. Digest-stable: nothing in it says when
    it was read, so reading the same source twice confirms the version."""
    return {"source": {k: source.get(k) for k in ("kind", "name", "path")},
            "run": run.get("name"), "run_dir": run.get("path"),
            "session_label": session_label, "cells": rows,
            "polarity": polarity}


# --------------------------------------------------------------------------
# Comparing two versions
# --------------------------------------------------------------------------
KEEP = 0.9     # share of both cells' spikes for "kept"
MOSTLY = 0.5   # share of a cell's spikes for "went into"


def diff(a, b):
    """Compare two curations {id: samples}, through the spikes they share.

    Each A cell's spikes are looked up among B's. A cell whose spikes go
    mostly (>= 50%) into one B cell went there; two or more A cells going
    into one B cell were MERGED; one A cell spread mostly over two or more B
    cells (each holding >= 25% of it) was SPLIT; an A cell whose spikes went
    nowhere was REMOVED; a B cell nothing went into was ADDED. A one-to-one
    pair sharing >= 90% of both is KEPT, otherwise CHANGED (spikes gained or
    lost). Returns {rows, counts}."""
    if not b:
        return {"rows": [{"kind": "removed", "a": [int(c)], "b": [],
                          "shared": 0, "n_a": int(len(s)), "n_b": 0}
                         for c, s in sorted(a.items())],
                "counts": {"removed": len(a)}}
    b_ids = sorted(b)
    allb = np.concatenate([b[c] for c in b_ids])
    owner = np.concatenate([np.full(len(b[c]), j) for j, c in
                            enumerate(b_ids)])
    order = np.argsort(allb, kind="stable")
    allb, owner = allb[order], owner[order]
    share = {}                       # a id -> {b id: shared}
    for cid, s in a.items():
        i = np.searchsorted(allb, s)
        i[i >= len(allb)] = len(allb) - 1
        hit = allb[i] == s
        got = np.bincount(owner[i[hit]], minlength=len(b_ids))
        share[cid] = {b_ids[j]: int(n) for j, n in enumerate(got) if n}
    into = {}                        # b id -> [a ids that went mostly into it]
    rows = []
    for cid, m in share.items():
        n = len(a[cid]) or 1
        main = [bc for bc, k in m.items() if k >= MOSTLY * n]
        big = [bc for bc, k in m.items() if k >= 0.25 * n]
        if len(big) >= 2 and not main:
            rows.append({"kind": "split", "a": [int(cid)],
                         "b": sorted(int(x) for x in big),
                         "shared": int(sum(m[x] for x in big)),
                         "n_a": int(len(a[cid])),
                         "n_b": int(sum(len(b[x]) for x in big))})
            continue
        if not main:
            rows.append({"kind": "removed", "a": [int(cid)], "b": [],
                         "shared": int(sum(m.values())),
                         "n_a": int(len(a[cid])), "n_b": 0})
            continue
        into.setdefault(main[0], []).append(cid)
    for bc, acs in into.items():
        nb = len(b[bc]) or 1
        if len(acs) >= 2:
            rows.append({"kind": "merged", "a": sorted(int(x) for x in acs),
                         "b": [int(bc)],
                         "shared": int(sum(share[x].get(bc, 0)
                                           for x in acs)),
                         "n_a": int(sum(len(a[x]) for x in acs)),
                         "n_b": int(len(b[bc]))})
            continue
        ac = acs[0]
        k = share[ac].get(bc, 0)
        kept = k >= KEEP * (len(a[ac]) or 1) and k >= KEEP * nb
        rows.append({"kind": "kept" if kept else "changed", "a": [int(ac)],
                     "b": [int(bc)], "shared": int(k),
                     "n_a": int(len(a[ac])), "n_b": int(len(b[bc])),
                     "same_id": int(ac) == int(bc)})
    went = {x for r in rows for x in r["b"]}
    for bc in b_ids:
        if bc not in went:
            rows.append({"kind": "added", "a": [], "b": [int(bc)],
                         "shared": 0, "n_a": 0, "n_b": int(len(b[bc]))})
    order = {"kept": 0, "changed": 1, "merged": 2, "split": 3,
             "removed": 4, "added": 5}
    rows.sort(key=lambda r: (order[r["kind"]], (r["a"] or r["b"])[0]))
    counts = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return {"rows": rows, "counts": counts}


# --------------------------------------------------------------------------
# One cell, closely
# --------------------------------------------------------------------------
def isi(samples, fs=FS):
    """ISI histogram 0-50 ms in 0.5 ms bins, and the share under 2 ms."""
    s = np.asarray(samples, dtype=np.int64)
    if len(s) < 2:
        return {"edges_ms": [], "counts": [], "refractory": None}
    d = np.diff(s) / fs * 1000.0
    edges = np.arange(0, ISI_MS + 0.5, 0.5)
    c, _ = np.histogram(d, bins=edges)
    return {"edges_ms": edges.tolist(), "counts": c.tolist(),
            "refractory": round(float(np.mean(d < REFRACTORY_MS)), 5),
            "refractory_ms": REFRACTORY_MS}


def acg(samples, fs=FS, half_ms=ACG_MS, cap=20000):
    """Autocorrelogram, 1 ms bins out to +-50 ms (acg1ms.m): every pair of
    spikes within the window, the zero bin left out. A cell over `cap`
    spikes is counted on an even subset of reference spikes, said."""
    s = np.asarray(samples, dtype=np.int64)
    n = len(s)
    if n < 2:
        return {"lags_ms": [], "counts": [], "of": n}
    ref = s if n <= cap else s[:: int(np.ceil(n / cap))]
    w = int(round(half_ms / 1000.0 * fs))
    lo = np.searchsorted(s, ref - w)
    hi = np.searchsorted(s, ref + w, side="right")
    bins = np.zeros(2 * half_ms, dtype=np.int64)
    for r, a, b_ in zip(ref, lo, hi):
        d = (s[a:b_] - r) / fs * 1000.0
        d = d[d != 0]
        k = np.floor(d).astype(np.int64) + half_ms
        k = k[(k >= 0) & (k < 2 * half_ms)]
        bins += np.bincount(k, minlength=2 * half_ms)
    return {"lags_ms": list(range(-half_ms, half_ms)),
            "counts": bins.tolist(), "of": int(len(ref)), "n": n}


def rate(seconds, duration, bin_s=RATE_BIN_S):
    t = np.asarray(seconds, dtype=float)
    t = t[np.isfinite(t)]
    if not duration or duration <= 0:
        duration = float(t.max()) if len(t) else 0.0
    edges = np.arange(0, duration + bin_s, bin_s)
    if len(edges) < 2:
        return {"bin_s": bin_s, "t": [], "hz": []}
    c, _ = np.histogram(t, bins=edges)
    return {"bin_s": bin_s, "t": edges[:-1].tolist(),
            "hz": (c / bin_s).round(3).tolist()}


def amplitudes(run_dir, samples, seconds, keep=3000):
    """Kilosort's per-spike amplitude over time, thinned to `keep`."""
    try:
        st = np.asarray(_load(run_dir, "spike_times.npy")).ravel()
        amp = np.asarray(_load(run_dir, "amplitudes.npy")).ravel()
    except OSError:
        return {"t": [], "a": []}
    s = np.asarray(samples, dtype=np.int64)
    i = np.searchsorted(st, s)
    i = np.clip(i, 0, len(st) - 1)
    ok = st[i] == s
    pick = np.nonzero(ok)[0]
    if len(pick) > keep:
        pick = pick[np.linspace(0, len(pick) - 1, keep).astype(int)]
    tt = np.asarray(seconds)[pick]
    return {"t": np.round(tt, 3).tolist(),
            "a": np.round(amp[i[pick]], 3).tolist()}


def waveform(raw_path, run_dir, samples, k, uv_per_bit, sign=1.0,
             n=WAVE_SPIKES, fs=FS):
    """Mean waveform on the best contact and its neighbours, high-passed at
    300 Hz, from up to `n` spikes spread evenly through the recording.
    Read straight off CSC_Raw.dat (concatenated samples, as the spikes
    are); `sign` -1 draws it the way Jarvis draws the traces when the
    recording is inverted."""
    from scipy.signal import butter, sosfiltfilt
    s = np.asarray(samples, dtype=np.int64)
    nb = neighbours(run_dir, k)
    if not len(s):
        return None
    total = os.path.getsize(raw_path) // (N_CHAN * 2)
    data = np.memmap(raw_path, dtype=np.int16, mode="r",
                     shape=(total, N_CHAN))
    pick = s[np.linspace(0, len(s) - 1, min(n, len(s))).astype(int)]
    half = int(round(WAVE_MS / 1000.0 * fs))
    pad = int(round(0.006 * fs))
    rows = [r for _i, r, _y in nb]
    sos = butter(3, WAVE_HP / (fs / 2.0), btype="high", output="sos")
    ok = pick[(pick - half - pad >= 0) & (pick + half + pad + 1 <= total)]
    if not len(ok):
        return None
    span = np.arange(-half - pad, half + pad + 1)
    # One gather and one filter for every spike at once: (spikes, time,
    # contacts) -> filtered along time.
    seg = np.asarray(data[(ok[:, None] + span[None, :]).ravel()][:, rows],
                     dtype=np.float64).reshape(len(ok), len(span), len(rows))
    seg = sosfiltfilt(sos, seg, axis=1)
    acc = seg[:, pad: pad + 2 * half + 1, :].sum(axis=0).T
    used = len(ok)
    mean = acc / used * uv_per_bit * sign
    best = [i for i, (ki, _r, _y) in enumerate(nb) if ki == k][0]
    w = mean[best]
    trough = float(w.min())
    peak = float(w.max())
    return {"ms": (np.arange(-half, half + 1) / fs * 1000.0).round(4).tolist(),
            "channels": [{"csc": r + 1, "depth_um": round(y, 1),
                          "best": i == best,
                          "uv": mean[i].round(2).tolist()}
                         for i, (_k, r, y) in enumerate(nb)],
            "n": used, "trough_uv": round(trough, 2),
            "peak_uv": round(peak, 2),
            "down": abs(trough) >= abs(peak)}


def peth(spike_s, event_s, half=PETH_HALF_S, bin_s=PETH_BIN_S, raster=60):
    """Firing around events: rate per bin (Hz) and the first `raster`
    events' spikes (seconds relative to the event)."""
    sp = np.sort(np.asarray(spike_s, dtype=float))
    ev = np.asarray(event_s, dtype=float)
    edges = np.arange(-half, half + bin_s / 2, bin_s)
    counts = np.zeros(len(edges) - 1)
    rows = []
    for j, e in enumerate(ev):
        a = np.searchsorted(sp, e - half)
        b_ = np.searchsorted(sp, e + half, side="right")
        rel = sp[a:b_] - e
        counts += np.histogram(rel, bins=edges)[0]
        if j < raster:
            rows.append(np.round(rel, 4).tolist())
    n = max(1, len(ev))
    base = counts[: max(1, int(len(counts) * 0.4))]
    return {"edges_s": np.round(edges, 4).tolist(),
            "hz": (counts / n / bin_s).round(3).tolist(),
            "n_events": int(len(ev)), "raster": rows,
            "baseline_hz": round(float(base.mean() / n / bin_s), 3)}


def polarity(waves, input_inverted=None):
    """Which way the cells swing in the binary Kilosort sorted (`waves`
    each {down}: its biggest deflection is downward in the BINARY's own
    sign), read against Neuralynx's InputInverted. A spike is a downward
    swing of true voltage; with the input inverted it is upward in the
    binary, and Xplorefinder's Invert turns it back."""
    ws = [w for w in waves if w]
    if not ws:
        return None
    down = sum(1 for w in ws if w.get("down"))
    n = len(ws)
    true_down = (n - down) if input_inverted else down
    ok = true_down >= n / 2.0
    side = "up" if input_inverted else "down"
    if ok:
        words = ("%d of %d cells swing %s in the binary%s, so they swing "
                 "down in true voltage, as a spike should. The sort read is "
                 "the non-inverted run, made on the binary as written."
                 % ((n - down) if input_inverted else down, n, side,
                    " (Neuralynx recorded it with its input inverted)"
                    if input_inverted else ""))
    else:
        words = ("Only %d of %d cells swing down in true voltage. The "
                 "inverted twin may be the sort that matches this "
                 "recording." % (true_down, n))
    return {"binary_down": down, "of": n, "true_down": true_down,
            "input_inverted": input_inverted, "ok": ok, "words": words}


# --------------------------------------------------------------------------
# The cache: one npz per recording, run and source digest
# --------------------------------------------------------------------------
def cache_path(cache_dir, gid, run_name, src_digest):
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_"
                   for ch in "%s__%s__%s" % (gid, run_name, src_digest))
    return os.path.join(cache_dir, safe + ".npz")


def save_cells(path, cells, seconds):
    ids = sorted(cells)
    arr = {"ids": np.array(ids, dtype=np.int64),
           "lens": np.array([len(cells[c]) for c in ids], dtype=np.int64),
           "samples": (np.concatenate([cells[c] for c in ids])
                       if ids else np.zeros(0, np.int64)),
           "seconds": (np.concatenate([seconds[c] for c in ids])
                       if ids else np.zeros(0))}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez(tmp, **arr)
    os.replace(tmp, path)


def load_cells(path):
    """({id: samples}, {id: seconds}) or (None, None)."""
    try:
        with np.load(path) as z:
            ids, lens = z["ids"], z["lens"]
            s, t = z["samples"], z["seconds"]
    except (OSError, KeyError, ValueError):
        return None, None
    cells, secs, at = {}, {}, 0
    for cid, n in zip(ids.tolist(), lens.tolist()):
        cells[cid] = s[at: at + n]
        secs[cid] = t[at: at + n]
        at += n
    return cells, secs


def source_digest(cells):
    h = hashlib.sha1()
    for cid in sorted(cells):
        h.update(("%d:%s;" % (cid, _digest(cells[cid]))).encode())
    return h.hexdigest()[:16]


def jsonsafe(x):
    return json.loads(json.dumps(x, default=lambda o: (
        o.item() if hasattr(o, "item") else str(o))))
