# -*- coding: utf-8 -*-
"""precon_drift_report.py -- the write-up of the DEWEY Precon1 -> Precon4 run.

    python tools\\precon_drift_report.py --from docs\\dewey-precon-drift.runlog.json

Reads the drift artifacts the run log names (tools/run_precon_drift.py wrote
it), each at the exact version filed, and writes:

  docs/dewey-precon-drift.md       short; leads with the answer
  docs/dewey-precon-drift.csv      one row per drift cell
  docs/dewey-precon-drift/*.png    a delta matrix per drift (band x windows x
                                   methods), q < .05 outlined; the sanity plot

EVERY NUMBER NAMES ITS ARTIFACT. Each figure, each row of the CSV and each
number in the text carries the drift's artifact id and version, so any of them
can be opened in Results and checked.

READ, NEVER WRITTEN. A payload is read from its snapshot
(GUI_logs/artifacts/snap/<id>/v<v>__<digest>.json) and its digest recomputed
and compared; a mismatch stops the report. With --base it is fetched from a
running Jarvis instead. Nothing here writes to the artifact store.

WHAT "CHANGED" MEANS HERE. q < 0.05, where q is Benjamini-Hochberg across
every tested cell of the drift -- one band, all its windows and all three
methods -- and p is Hartung-Knapp's t on k - 1 df over the rats' own
Precon4 - Precon1 changes. Uncorrected p is in the CSV for anyone who wants
another correction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                        # noqa: BLE001
    pass

LOGS = os.path.join(APP, "GUI_logs")
DOCS = os.path.join(APP, "docs")
Q = 0.05

BAND_ORDER = ("theta", "beta", "gamma_low")
BAND_SAY = {"theta": "theta (4–12 Hz)", "beta": "beta (13–30 Hz)",
            "gamma_low": "low gamma (30–55 Hz)"}
BAND_SHORT = {"theta": "theta", "beta": "beta", "gamma_low": "low gamma"}
KIND_ORDER = ("state", "transition", "rest")
ROLE_SAY = {"food": "food pair", "no_food": "no-food pair", None: ""}
CONTRAST_SAY = {None: "raw", "baseline": "cue − baseline",
                "roles": "food − no-food"}
WINDOW_SAY = {
    "pre": "baseline", "cue1": "cue 1", "cue2": "cue 2",
    "post": "after cue 2", "onset": "cue 1 onset",
    "switch": "cue 1 → cue 2", "offset": "cue 2 offset",
    "cue1-pre": "cue 1 − baseline", "cue2-pre": "cue 2 − baseline",
    "post-pre": "after cue 2 − baseline",
    "onset-pre": "cue 1 onset − baseline",
    "switch-pre": "cue 1 → cue 2 − baseline",
    "offset-pre": "cue 2 offset − baseline",
    "rest": "rest (FP1 + FP2)",
}
METHOD_SAY = {"coherence": "coherence (band mean)",
              "raw_cc": "band-passed cross-correlation (peak |r|)",
              "amp_cc": "envelope correlation (peak r)"}
METHOD_SHORT = {"coherence": "coherence", "raw_cc": "raw cc",
                "amp_cc": "envelope cc"}

CSV_COLUMNS = ("band", "kind", "pair role", "contrast", "window", "method",
               "region pair", "delta", "se", "t", "df", "p", "q", "k", "n",
               "artifact_id", "version")

# Diverging blue (down) / red (up) around a neutral grey that means "no
# change" -- the dataviz reference pair. Absent cells are hatched on the
# chart surface, never grey, because grey is zero.
DIVERGING = ["#1c5cab", "#86b6ef", "#f0efec", "#f0a3a2", "#c63a39"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]      # slots 1-3, one per band


class ReportError(Exception):
    pass


# ==========================================================================
# Reading
# ==========================================================================
def load_runlog(path):
    with open(path, "r", encoding="utf-8") as fh:
        log = json.load(fh)
    drifts = []
    for key, d in (log.get("drifts") or {}).items():
        if not d.get("artifact_id"):
            continue
        drifts.append(dict(d, key=key))

    def order(d):
        return (BAND_ORDER.index(d["band"]) if d["band"] in BAND_ORDER else 9,
                KIND_ORDER.index(d["kind"]) if d["kind"] in KIND_ORDER else 9,
                {None: 0, "baseline": 1, "roles": 2}.get(d.get("contrast"), 3),
                {"food": 0, "no_food": 1, None: 2}.get(d.get("role"), 3))
    drifts.sort(key=order)
    return log, drifts


def _get_json(base, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base.rstrip("/") + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def payload_of(d, runlog_dir, base=None):
    """The drift's payload at the version the run log pinned."""
    if d.get("payload_file"):
        path = d["payload_file"]
        if not os.path.isabs(path):
            path = os.path.join(runlog_dir, path)
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if base:
        got = _get_json(base, "/api/artifacts/%s/payload?v=%s" % (
            urllib.parse.quote(d["artifact_id"]),
            urllib.parse.quote(str(d.get("version_id") or d["version"]))))
        if got.get("digest") != d.get("digest"):
            raise ReportError("%s: Jarvis serves digest %s, the run log "
                              "pinned %s." % (d["artifact_id"],
                                              got.get("digest"),
                                              d.get("digest")))
        return got["payload"]
    from backend.artifacts import digest
    path = os.path.join(LOGS, "artifacts", "snap", d["artifact_id"],
                        "v%d__%s.json" % (int(d["version"]), d["digest"]))
    if not os.path.isfile(path):
        raise ReportError("%s v%s: no snapshot at %s (made on another machine "
                          "and not synced yet?)" % (d["artifact_id"],
                                                    d["version"], path))
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if digest(payload) != d["digest"]:
        raise ReportError("%s v%s: the snapshot's digest is %s, the run log "
                          "pinned %s." % (d["artifact_id"], d["version"],
                                          digest(payload), d["digest"]))
    return payload


def cite(d):
    return "[%s v%s]" % (d["artifact_id"], d["version"])


# ==========================================================================
# Cells
# ==========================================================================
def stat_of(c):
    """(stat, df, name): Hartung-Knapp's t when there is one, else z."""
    if c.get("t") is not None:
        return c["t"], c.get("df"), "t"
    if c.get("z") is not None:
        return c["z"], None, "z"
    return None, None, None


def cells(payload):
    """(window, method, pair, cell) in the payload's order."""
    for w in payload.get("windows") or []:
        byw = (payload.get("cells") or {}).get(w) or {}
        for m in payload.get("methods") or []:
            for pair, c in (byw.get(m) or {}).items():
                yield w, m, pair, c


def _k(c):
    if c.get("k") is not None:
        return c["k"]
    ks = [s.get("k") for s in (c.get("left") or {}, c.get("right") or {})
          if s.get("k") is not None]
    return min(ks) if ks else None


def _n(c):
    if c.get("n") is not None:
        return c["n"]
    ns = [s.get("n") for s in (c.get("left") or {}, c.get("right") or {})
          if s.get("n") is not None]
    return sum(ns) if ns else None


def role_col(d):
    if d.get("contrast") == "roles":
        return "food − no_food"
    return d.get("role") or ""


def csv_rows(d, payload):
    out = []
    for w, m, pair, c in cells(payload):
        t, df, name = stat_of(c)
        out.append({
            "band": d["band"], "kind": d["kind"], "pair role": role_col(d),
            "contrast": d.get("contrast") or "raw", "window": w,
            "method": m, "region pair": pair.replace("|", " – "),
            "delta": c.get("delta"), "se": c.get("se"),
            "t": t if name == "t" else None, "df": df,
            "p": c.get("p"), "q": c.get("q"), "k": _k(c), "n": _n(c),
            "artifact_id": d["artifact_id"], "version": d["version"],
            "_z": t if name == "z" else None,
        })
    return out


def sig_cells(payload):
    out = []
    for w, m, pair, c in cells(payload):
        if c.get("q") is not None and c["q"] < Q:
            out.append((w, m, pair, c))
    out.sort(key=lambda x: (x[3]["q"], -abs(stat_of(x[3])[0] or 0)))
    return out


def tally(payload):
    n = tested = sig = up = down = frag = 0
    by_window = {}
    for w, m, pair, c in cells(payload):
        n += 1
        bw = by_window.setdefault(w, {"tested": 0, "sig": 0})
        if c.get("p") is not None:
            tested += 1
            bw["tested"] += 1
        if c.get("q") is not None and c["q"] < Q:
            sig += 1
            bw["sig"] += 1
            if fragile(c):
                frag += 1
            if (c.get("delta") or 0) > 0:
                up += 1
            else:
                down += 1
    return {"cells": n, "tested": tested, "sig": sig, "up": up,
            "down": down, "fragile": frag, "by_window": by_window}


def smallest_q(payload):
    best = None
    for w, m, pair, c in cells(payload):
        if c.get("q") is None:
            continue
        if best is None or c["q"] < best[3]["q"]:
            best = (w, m, pair, c)
    return best


def fmt(x, nd=3):
    if x is None:
        return "–"
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return "–"
    if abs(x) != 0 and (abs(x) < 10 ** -nd or abs(x) >= 1e4):
        return "%.2g" % x
    return ("%%.%df" % nd) % x


def fmt_q(x):
    if x is None:
        return "–"
    if x < 0.001:
        return "%.1e" % x
    return "%.3f" % x


#: A discovery resting on this few rats is flagged. Untruncated
#: Hartung-Knapp on k = 2 is a t on 1 df whose SE is the gap between two
#: rats' changes: two rats that happen to agree closely give an enormous t
#: (measured on synthetic null data: t(1) = -13910, q = 0.025, two rats).
FRAGILE_K = 2


def fragile(c):
    k = _k(c)
    return k is not None and k <= FRAGILE_K


def say_cell(w, m, pair, c):
    t, df, name = stat_of(c)
    stat = ("t(%s) = %.2f" % (fmt(df, 0), t) if name == "t"
            else ("z = %.2f" % t if name == "z" else "untested"))
    out = ("%s, %s, %s: Δ = %s (SE %s), %s, q = %s, k = %s rats" % (
        pair.replace("|", " – "), WINDOW_SAY.get(w, w), METHOD_SHORT.get(m, m),
        fmt(c.get("delta")), fmt(c.get("se")), stat, fmt_q(c.get("q")),
        _k(c)))
    if fragile(c):
        out += (" — FRAGILE: %s rats, so the SE is how closely they happen "
                "to agree (Hartung–Knapp factor %s)" % (
                    _k(c), fmt(c.get("hk_factor"), 3)))
    return out


def pearson(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 3:
        return None, n
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    if sxx <= 0 or syy <= 0:
        return None, n
    return sxy / math.sqrt(sxx * syy), n


# ==========================================================================
# Regions: which the result can speak to
# ==========================================================================
def region_usability(drift_payloads):
    """{region: (usable rats, of rats)} from the grey detail of the raw
    drifts: a region grey in any member of a rat is lost for that rat."""
    rats_all, grey = set(), {}
    order = []
    for p in drift_payloads:
        order = order or list(p.get("region_order") or [])
        name_to_rat = {}
        for side in ("left", "right"):
            for mem in (p.get(side) or {}).get("members") or []:
                rat = mem.get("rat")
                if rat is not None:
                    name_to_rat[mem.get("name")] = str(rat)
                    rats_all.add(str(rat))
        for region, rows in (p.get("grey_detail") or {}).items():
            for r in rows:
                rat = name_to_rat.get(r.get("member"))
                if rat is not None:
                    grey.setdefault(region, set()).add(rat)
    out = {}
    for region in order:
        lost = grey.get(region, set()) & rats_all
        out[region] = (len(rats_all) - len(lost), len(rats_all))
    return out


def structures(usable):
    """{"POR": "0/8 (left 0, right 0)"...} -- the two hemispheres together."""
    by = {}
    for region, (u, of) in usable.items():
        side, _, struct = region.partition(" ")
        by.setdefault(struct, {})[side] = (u, of)
    out = []
    for struct, sides in by.items():
        us = [v[0] for v in sides.values()]
        of = max(v[1] for v in sides.values())
        rng = ("%d" % us[0]) if min(us) == max(us) else "%d–%d" % (min(us),
                                                                  max(us))
        out.append((struct, rng, of, sides))
    out.sort(key=lambda x: -min(v[0] for v in x[3].values()))
    return out


# ==========================================================================
# Figures
# ==========================================================================
def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5,
                         "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                         "xtick.color": MUTED, "ytick.color": MUTED,
                         "text.color": INK})
    cmap = LinearSegmentedColormap.from_list("drift", DIVERGING, N=255)
    return plt, cmap


def slug(s):
    keep = []
    for ch in s.lower():
        if ch.isalnum():
            keep.append(ch)
        elif keep and keep[-1] != "-":
            keep.append("-")
    return "".join(keep).strip("-")


def fig_name(d):
    parts = [d["band"], d["kind"]]
    if d.get("contrast") == "roles":
        parts.append("food-minus-nofood")
    else:
        if d.get("role"):
            parts.append(d["role"].replace("_", ""))
        if d.get("contrast") == "baseline":
            parts.append("minus-baseline")
    return slug("-".join(parts)) + ".png"


def drift_figure(d, payload, path):
    """Windows across, methods down; each panel the 12-region lower
    triangle, Δ in the diverging scale (one scale per method row), q < .05
    outlined in ink, absent cells hatched."""
    plt, cmap = _mpl()
    from matplotlib.patches import Rectangle
    order = list(payload.get("region_order") or [])
    windows = list(payload.get("windows") or [])
    methods = list(payload.get("methods") or [])
    grey = set(payload.get("grey") or [])
    n = len(order)
    ncol, nrow = len(windows), len(methods)
    cell_in = 0.19
    panel = n * cell_in
    fig_w = 1.9 + ncol * (panel + 0.35) + 1.0
    fig_h = 1.5 + nrow * (panel + 0.45)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    left, top = 1.75 / fig_w, 1 - 1.2 / fig_h
    pw, ph = panel / fig_w, panel / fig_h
    gapx, gapy = 0.35 / fig_w, 0.45 / fig_h
    title = d.get("nickname") or d["key"]
    fig.text(0.012, 1 - 0.18 / fig_h, title, fontsize=12, weight="bold",
             color=INK, va="top")
    kr = payload.get("rats") or "?"
    sub = ("Δ = Precon4 − Precon1 within rat, pooled over %s rats "
           "(DerSimonian–Laird); outlined: q < %.2f (Hartung–Knapp t, BH "
           "across all windows and methods of this drift). Hatched: no cell "
           "(a region grey in every rat, or no usable pair). Muted labels: "
           "a region grey in at least one rat (fewer rats behind its cells; "
           "k per cell in the CSV). %s" % (kr, Q, cite(d)))
    if d.get("contrast") == "roles":
        sub = ("food-pair change − no-food-pair change, within rat, over %s "
               "rats; outlined: q < %.2f. %s" % (kr, Q, cite(d)))
    fig.text(0.012, 1 - 0.48 / fig_h, sub, fontsize=7.6, color=INK2,
             va="top", wrap=True)
    idx = {r: i for i, r in enumerate(order)}
    for mi, m in enumerate(methods):
        vals = []
        for w in windows:
            for c in ((payload.get("cells") or {}).get(w) or {}).get(
                    m, {}).values():
                if c.get("delta") is not None:
                    vals.append(abs(c["delta"]))
        vmax = max(vals) if vals else 1.0
        vmax = vmax or 1.0
        for wi, w in enumerate(windows):
            x0 = left + wi * (pw + gapx)
            y0 = top - (mi + 1) * ph - mi * gapy
            ax = fig.add_axes([x0, y0, pw, ph])
            ax.set_facecolor(SURFACE)
            ax.set_xlim(0, n)
            ax.set_ylim(n, 0)
            ax.set_aspect("equal")
            panel_cells = ((payload.get("cells") or {}).get(w) or {}).get(
                m, {})
            for i in range(n):
                for j in range(i):
                    a, b = order[j], order[i]
                    c = panel_cells.get("%s|%s" % (a, b))
                    if c is None or c.get("delta") is None:
                        ax.add_patch(Rectangle((j, i), 1, 1,
                                               facecolor=SURFACE,
                                               edgecolor=GRID, hatch="////",
                                               linewidth=0.0))
                        continue
                    col = cmap(0.5 + 0.5 * max(-1, min(1, c["delta"]
                                                       / vmax)))
                    ax.add_patch(Rectangle((j, i), 1, 1, facecolor=col,
                                           edgecolor=SURFACE,
                                           linewidth=0.6))
                    if c.get("q") is not None and c["q"] < Q:
                        ax.add_patch(Rectangle((j + 0.06, i + 0.06), 0.88,
                                               0.88, facecolor="none",
                                               edgecolor=INK,
                                               linewidth=1.3))
            ax.set_xticks([k + 0.5 for k in range(n)])
            ax.set_yticks([k + 0.5 for k in range(n)])
            short = [r.replace("Left ", "L ").replace("Right ", "R ")
                     for r in order]
            if mi == nrow - 1:
                ax.set_xticklabels(short, rotation=90, fontsize=6.4)
            else:
                ax.set_xticklabels([])
            if wi == 0:
                ax.set_yticklabels(short, fontsize=6.4)
                for lab, r in zip(ax.get_yticklabels(), order):
                    lab.set_color(MUTED if r in grey else INK2)
                ax.set_ylabel(METHOD_SHORT.get(m, m), fontsize=8.5,
                              color=INK, labelpad=6)
            else:
                ax.set_yticklabels([])
            if mi == nrow - 1:
                for lab, r in zip(ax.get_xticklabels(), order):
                    lab.set_color(MUTED if r in grey else INK2)
            ax.tick_params(length=0, pad=1.5)
            for s in ax.spines.values():
                s.set_visible(False)
            if mi == 0:
                ax.set_title(WINDOW_SAY.get(w, w), fontsize=9, color=INK,
                             pad=4)
        # One scale per method row: coherence and correlations are not in
        # the same unit, so they do not share a colour bar.
        cx = left + ncol * (pw + gapx) + 0.05 / fig_w
        y0 = top - (mi + 1) * ph - mi * gapy
        cax = fig.add_axes([cx, y0 + ph * 0.1, 0.12 / fig_w, ph * 0.8])
        import numpy as np
        grad = np.linspace(1, -1, 128).reshape(-1, 1)
        cax.imshow(grad, aspect="auto", cmap=cmap, vmin=-1, vmax=1,
                   extent=(0, 1, -vmax, vmax))
        cax.set_xticks([])
        cax.yaxis.tick_right()
        cax.set_yticks([-vmax, 0, vmax])
        cax.set_yticklabels(["−%s" % fmt(vmax, 2), "0", "+%s" % fmt(vmax, 2)],
                            fontsize=6.6, color=INK2)
        for s in cax.spines.values():
            s.set_visible(False)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def sanity_figure(pairs_rows, rest_rows, methods, path):
    """Per-cell Δ scatters, one column per method (their units differ):
    row 1 food vs no-food pair change, row 2 rest change vs cue change. One
    colour per band (three slots). Δ, not t: an untruncated Hartung-Knapp t
    on two rats can be in the thousands and would flatten every other point
    onto the origin."""
    plt, _cmap = _mpl()
    ncol = max(1, len(methods))
    fig, axes = plt.subplots(2, ncol, figsize=(3.3 * ncol + 0.6, 7.4),
                             dpi=150, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    rowdefs = ((pairs_rows, "no-food pair Δ", "food pair Δ",
                "1. Do the two cue pairs change alike?",
                "One point per region pair × window (state and transition). "
                "On the diagonal: the same change in both pairs."),
               (rest_rows, "cue-window Δ (state cue 1 + cue 2, both pairs)",
                "rest Δ (FP1 + FP2)",
                "2. Is the change about the cues?",
                "One point per region pair. On the diagonal: the no-cue "
                "recordings changed as much as the cue windows did."))
    for ri, (rows, xl, yl, ti, sub) in enumerate(rowdefs):
        y_title = 1 - (0.02 + ri * 0.49)
        fig.text(0.015, y_title, ti, fontsize=10.5, weight="bold",
                 color=INK, va="top")
        fig.text(0.015, y_title - 0.03, sub, fontsize=7.8, color=INK2,
                 va="top")
        for mi, m in enumerate(methods):
            ax = axes[ri][mi]
            ax.set_facecolor(SURFACE)
            lim = 0.0
            for bi, band in enumerate(BAND_ORDER):
                pts = [(x, y) for b, mm, x, y in rows
                       if b == band and mm == m
                       and x is not None and y is not None]
                if not pts:
                    continue
                lim = max(lim, max(max(abs(x), abs(y)) for x, y in pts))
                ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=12,
                           color=SERIES[bi], alpha=0.8, linewidths=0.5,
                           edgecolors=SURFACE, label=BAND_SHORT[band],
                           zorder=3)
            lim = (lim or 1.0) * 1.08
            ax.plot([-lim, lim], [-lim, lim], color=GRID, lw=1, zorder=1)
            ax.axhline(0, color=GRID, lw=0.8, zorder=1)
            ax.axvline(0, color=GRID, lw=0.8, zorder=1)
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim, lim)
            ax.set_aspect("equal")
            ax.set_xlabel(xl, fontsize=7.8)
            if mi == 0:
                ax.set_ylabel(yl, fontsize=7.8)
            ax.set_title(METHOD_SHORT.get(m, m), fontsize=8.8, color=INK,
                         pad=4)
            ax.tick_params(labelsize=7)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            if mi == ncol - 1:
                ax.legend(frameon=False, fontsize=7.6, loc="lower right",
                          labelcolor=INK2, handletextpad=0.3)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.08,
                        hspace=0.62, wspace=0.32)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ==========================================================================
# The write-up
# ==========================================================================
def build_report(runlog_path, out_md, out_csv, fig_dir, base=None,
                 figures=True):
    log, drifts = load_runlog(runlog_path)
    if not drifts:
        raise ReportError("The run log names no drift artifacts yet.")
    rdir = os.path.dirname(os.path.abspath(runlog_path))
    for d in drifts:
        d["payload"] = payload_of(d, rdir, base)
        d["tally"] = tally(d["payload"])

    def get(band, kind, role, contrast):
        for d in drifts:
            if (d["band"], d["kind"], d.get("role"), d.get("contrast")) == (
                    band, kind, role, contrast):
                return d
        return None

    # ---- the CSV: every cell of every drift -----------------------------
    rows = []
    for d in drifts:
        rows.extend(csv_rows(d, d["payload"]))
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(CSV_COLUMNS)
        for r in rows:
            wr.writerow(["" if r[c] is None else
                         (repr(r[c]) if isinstance(r[c], float) else r[c])
                         for c in CSV_COLUMNS])

    # ---- figures ----------------------------------------------------------
    figs = {}
    if figures:
        os.makedirs(fig_dir, exist_ok=True)
        for d in drifts:
            p = os.path.join(fig_dir, fig_name(d))
            drift_figure(d, d["payload"], p)
            figs[d["key"]] = p

    # ---- sanity data ------------------------------------------------------
    # Δ per cell, compared within a method (the three are in different
    # units): (band, method, x, y).
    pairs_rows, rest_rows = [], []
    methods = []
    for d in drifts:
        for m in d["payload"].get("methods") or []:
            if m not in methods:
                methods.append(m)
    for band in BAND_ORDER:
        for kind in ("state", "transition"):
            f = get(band, kind, "food", None)
            o = get(band, kind, "no_food", None)
            if not (f and o):
                continue
            fc = {(w, m, k): c for w, m, k, c in cells(f["payload"])}
            for w, m, k, c in cells(o["payload"]):
                cf = fc.get((w, m, k))
                if cf is None:
                    continue
                pairs_rows.append((band, m, c.get("delta"), cf.get("delta")))
        rest = get(band, "rest", None, None)
        if rest:
            rc = {(m, k): c for w, m, k, c in cells(rest["payload"])}
            acc = {}
            for role in ("food", "no_food"):
                s = get(band, "state", role, None)
                if not s:
                    continue
                for w, m, k, c in cells(s["payload"]):
                    if w in ("cue1", "cue2") and c.get("delta") is not None:
                        acc.setdefault((m, k), []).append(c["delta"])
            for (m, k), ds in acc.items():
                c = rc.get((m, k))
                if c is None:
                    continue
                rest_rows.append((band, m, sum(ds) / len(ds),
                                  c.get("delta")))
    pair_r = {(b, m): pearson([x for bb, mm, x, y in pairs_rows
                               if bb == b and mm == m],
                              [y for bb, mm, x, y in pairs_rows
                               if bb == b and mm == m])
              for b in BAND_ORDER for m in methods}
    rest_r = {(b, m): pearson([x for bb, mm, x, y in rest_rows
                               if bb == b and mm == m],
                              [y for bb, mm, x, y in rest_rows
                               if bb == b and mm == m])
              for b in BAND_ORDER for m in methods}
    if figures:
        figs["_sanity"] = sanity_figure(pairs_rows, rest_rows, methods,
                                        os.path.join(fig_dir,
                                                     "sanity-checks.png"))

    raw = [d for d in drifts if d.get("contrast") is None]
    usable = region_usability([d["payload"] for d in raw])
    md = write_md(log, drifts, get, figs, fig_dir, out_md, out_csv, rows,
                  pair_r, rest_r, usable, methods)
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(md)
    return {"rows": len(rows), "drifts": len(drifts), "md": out_md,
            "csv": out_csv, "figures": sorted(figs.values())}


def _rel(path, out_md):
    return os.path.relpath(path, os.path.dirname(os.path.abspath(out_md))) \
        .replace("\\", "/")


def _say_r(rs, band, methods):
    """"r = 0.12 / 0.08 / 0.10 (coherence / raw cc / envelope cc; n = 120
    cells each)" -- one r per method, never pooled across units."""
    got = [(m, rs.get((band, m), (None, 0))) for m in methods]
    got = [(m, r, n) for m, (r, n) in got if r is not None]
    if not got:
        return None
    return "r = %s (%s; n = %s cells)" % (
        " / ".join("%.2f" % r for _, r, _ in got),
        " / ".join(METHOD_SHORT.get(m, m) for m, _, _ in got),
        "/".join(str(n) for _, _, n in got))


def write_md(log, drifts, get, figs, fig_dir, out_md, out_csv, rows, pair_r,
             rest_r, usable, methods):
    L = []
    design = log.get("design") or {}
    rats = design.get("rats") or []
    n_rats = len(rats) or "?"

    # ---- the answer -------------------------------------------------------
    cue_raw = [d for d in drifts if d.get("contrast") is None
               and d["kind"] in ("state", "transition")]
    tot_tested = sum(d["tally"]["tested"] for d in cue_raw)
    tot_sig = sum(d["tally"]["sig"] for d in cue_raw)
    L.append("# DEWEY: what changed in coupling from Precon1 to Precon4")
    L.append("")
    if tot_sig == 0:
        best = None
        for d in cue_raw:
            b = smallest_q(d["payload"])
            if b and (best is None or b[3]["q"] < best[1][3]["q"]):
                best = (d, b)
        head = ("**The answer: after correction, no region pair's coupling "
                "changed detectably from Precon1 to Precon4** — 0 of %d "
                "tests in the cue windows (state and transition, both cue "
                "pairs, three bands) reach q < %.2f." % (tot_tested, Q))
        if best:
            d, (w, m, k, c) = best
            head += (" The closest was %s in %s %s: %s %s." % (
                BAND_SHORT[d["band"]], d["kind"], ROLE_SAY[d.get("role")],
                say_cell(w, m, k, c), cite(d)))
        L.append(head)
    else:
        up = sum(d["tally"]["up"] for d in cue_raw)
        down = tot_sig - up
        where = {}
        for d in cue_raw:
            for w, s in d["tally"]["by_window"].items():
                if s["sig"]:
                    where[(d["band"], w)] = where.get((d["band"], w), 0) \
                        + s["sig"]
        top = sorted(where.items(), key=lambda kv: -kv[1])[:3]
        frag = sum(d["tally"]["fragile"] for d in cue_raw)
        L.append("**The answer: after correction, %d of %d region-pair tests "
                 "in the cue windows changed from Precon1 to Precon4** "
                 "(q < %.2f; %d up, %d down), most in %s.%s" % (
                     tot_sig, tot_tested, Q, up, down, "; ".join(
                         "%s %s (%d)" % (BAND_SHORT[b], WINDOW_SAY.get(w, w),
                                         n) for (b, w), n in top),
                     (" %d of them rest on %d or fewer rats and are marked "
                      "fragile below." % (frag, FRAGILE_K)) if frag else ""))
    L.append("")
    L.append("Within rat, %s rats (%s), each rat's Precon4 − Precon1 change "
             "pooled by DerSimonian–Laird and tested by Hartung–Knapp t on "
             "k − 1 df; Benjamini–Hochberg per band across all windows and "
             "methods. Every number below names the drift artifact it comes "
             "from, as [artifact id vN]; the CSV has every cell." % (
                 n_rats, ", ".join("r%s" % r for r in rats)))
    L.append("")

    # ---- per band and window ----------------------------------------------
    L.append("## What changed, per band and window")
    L.append("")
    L.append("Cells reaching q < %.2f, of those tested, per window. *Raw* is "
             "the change in the window itself; *cue − baseline* is the "
             "change in (window − the same cue pair's baseline), so a change "
             "that is only in the baseline, or everywhere alike, drops out."
             % Q)
    L.append("")
    for band in BAND_ORDER:
        bd = [d for d in drifts if d["band"] == band]
        if not bd:
            continue
        L.append("### %s" % BAND_SAY[band])
        L.append("")
        L.append("| drift | window | q < %.2f / tested | artifact |" % Q)
        L.append("|---|---|---|---|")
        for d in bd:
            if d.get("contrast") == "roles":
                continue
            what = "%s · %s%s" % (
                d["kind"], ROLE_SAY[d.get("role")] or "no cue",
                " · cue − baseline" if d.get("contrast") == "baseline"
                else "")
            for w in d["payload"].get("windows") or []:
                s = d["tally"]["by_window"].get(w) or {"sig": 0, "tested": 0}
                L.append("| %s | %s | %d / %d | %s |" % (
                    what, WINDOW_SAY.get(w, w), s["sig"], s["tested"],
                    cite(d)))
                what = ""
        L.append("")
        shown = 0
        for d in bd:
            if d.get("contrast") == "roles":
                continue
            sig = sig_cells(d["payload"])
            if not sig:
                continue
            L.append("- **%s · %s%s** %s:" % (
                d["kind"], ROLE_SAY[d.get("role")] or "rest",
                " · cue − baseline" if d.get("contrast") == "baseline"
                else "", cite(d)))
            for w, m, k, c in sig[:8]:
                L.append("  - %s" % say_cell(w, m, k, c))
                shown += 1
            if len(sig) > 8:
                L.append("  - and %d more in the CSV" % (len(sig) - 8))
        if not shown:
            L.append("Nothing in %s reaches q < %.2f." % (BAND_SHORT[band], Q))
        L.append("")
        for d in bd:
            if (d.get("contrast") is None and d["key"] in figs
                    and d["kind"] in ("state", "rest")):
                L.append("![%s](%s)" % (d.get("nickname") or d["key"],
                                        _rel(figs[d["key"]], out_md)))
                L.append("")

    # ---- sanity checks ----------------------------------------------------
    L.append("## Two sanity checks")
    L.append("")
    L.append("**1. Do the two cue pairs agree?** Nothing about Precon1 → "
             "Precon4 should depend on which pair will later be fed — the "
             "rats have not been conditioned yet. The food − no-food contrast "
             "tests, per rat, the food pair's change minus the no-food "
             "pair's change:")
    L.append("")
    for band in BAND_ORDER:
        parts = []
        for kind in ("state", "transition"):
            d = get(band, kind, None, "roles")
            if not d:
                continue
            t = d["tally"]
            parts.append("%s %d of %d at q < %.2f %s" % (
                kind, t["sig"], t["tested"], Q, cite(d)))
        r = _say_r(pair_r, band, methods)
        if parts or r is not None:
            L.append("- %s: %s%s" % (
                BAND_SHORT[band], "; ".join(parts) or "no contrast filed",
                "; across cells the two pairs' changes (Δ) correlate %s, "
                "from the raw drifts %s" % (
                    r, " ".join(cite(x) for x in (
                        get(band, k, ro, None) for k in ("state", "transition")
                        for ro in ("food", "no_food")) if x))
                if r is not None else ""))
    L.append("")
    L.append("**2. Is the change about the cues?** The FP1 + FP2 recordings "
             "of the same days hold no cues. A change that shows up there as "
             "strongly as in the cue windows is a change in the rat or the "
             "electrodes across days, not in how the cues are processed:")
    L.append("")
    for band in BAND_ORDER:
        d = get(band, "rest", None, None)
        if not d:
            continue
        t = d["tally"]
        r = _say_r(rest_r, band, methods)
        cue = [x for x in (get(band, "state", ro, None)
                           for ro in ("food", "no_food")) if x]
        L.append("- %s: rest %d of %d at q < %.2f %s%s" % (
            BAND_SHORT[band], t["sig"], t["tested"], Q, cite(d),
            "; the rest change (Δ) against the cue windows' change %s "
            "correlates %s" % (" ".join(cite(x) for x in cue), r)
            if r is not None else ""))
    L.append("")
    if "_sanity" in figs:
        L.append("![Sanity checks](%s)" % _rel(figs["_sanity"], out_md))
        L.append("")

    # ---- regions ----------------------------------------------------------
    L.append("## Which regions it can speak to")
    L.append("")
    L.append("A region is computed in a rat only where histology puts the "
             "probe where it was aimed (a relocated, missed or unscored probe "
             "is grey — not computed). Rats in which each region is usable, "
             "counted from the drifts' own grey lists:")
    L.append("")
    L.append("| region | usable in | left | right |")
    L.append("|---|---|---|---|")
    for struct, rng, of, sides in structures(usable):
        L.append("| %s | %s of %d | %s | %s |" % (
            struct, rng, of,
            "%d/%d" % sides["Left"] if "Left" in sides else "–",
            "%d/%d" % sides["Right"] if "Right" in sides else "–"))
    L.append("")
    L.append("So the result is about the regions usable in most rats; a "
             "pair involving a region usable in few rats has a small k (in "
             "the CSV) and Hartung–Knapp needs k ≥ 2 to test at all.")
    L.append("")

    # ---- method, artifacts ------------------------------------------------
    L.append("## How it was made")
    L.append("")
    ex = design.get("excluded") or {}
    L.append("- Rats %s; %s. Precon1 and Precon4 SPC recordings, re-banked "
             "with the transition check (1.0 s before, 2.0 s after each "
             "boundary)." % (", ".join("r%s" % r for r in rats),
                              "; ".join("%s left out: %s" % kv
                                        for kv in ex.items()) or
                              "none left out"))
    roles = log.get("roles") or {}
    if roles:
        L.append("- Cue roles from each rat's own conditioning (Con SPC "
                 "TTLs, backend/cueroles.py): the pair whose second cue is "
                 "followed by a Pellet Delivery within 15 s is the food pair. "
                 "%s." % "; ".join(
                     "r%s %s" % (rat, t.get("food_pair"))
                     for rat, t in sorted(roles.items(),
                                          key=lambda kv: int(kv[0]))))
    L.append("- Bands: theta 4–12 Hz (lag ±500 ms), beta 13–30 Hz (±150 ms), "
             "low gamma 30–55 Hz (±60 ms); coherence averaged over the band; "
             "cross-correlation on band-passed signals.")
    L.append("- Windows: state (baseline, cue 1, cue 2, after cue 2; 10 s "
             "each), transition (cue 1 onset, cue 1 → cue 2, cue 2 offset; "
             "1 s before to 2 s after), rest (10 s epochs over FP1 + FP2, as "
             "many as the day's cue pairs).")
    L.append("- A cell's k is the number of rats that contribute; n the cue "
             "pairs (or epochs) behind it.")
    L.append("")
    L.append("### The drift artifacts")
    L.append("")
    L.append("| drift | artifact | version | version id | digest | cells | "
             "tested | q < %.2f |" % Q)
    L.append("|---|---|---|---|---|---|---|---|")
    for d in drifts:
        t = d["tally"]
        L.append("| %s | %s | v%s | %s | %s | %d | %d | %d |" % (
            d.get("nickname") or d["key"], d["artifact_id"], d["version"],
            d.get("version_id") or "–", d.get("digest") or "–", t["cells"],
            t["tested"], t["sig"]))
    L.append("")
    L.append("CSV: `%s` — %d rows, one per drift cell (columns: %s)." % (
        _rel(out_csv, out_md), len(rows), ", ".join(CSV_COLUMNS)))
    others = [d for d in drifts if d["key"] in figs and not (
        d.get("contrast") is None and d["kind"] in ("state", "rest"))]
    if others:
        L.append("")
        L.append("Other figures: " + ", ".join(
            "[%s](%s)" % (d.get("nickname") or d["key"],
                          _rel(figs[d["key"]], out_md)) for d in others) + ".")
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="runlog",
                    default=os.path.join(DOCS,
                                         "dewey-precon-drift.runlog.json"))
    ap.add_argument("--md", default=os.path.join(DOCS, "dewey-precon-drift.md"))
    ap.add_argument("--csv", default=os.path.join(DOCS,
                                                  "dewey-precon-drift.csv"))
    ap.add_argument("--figures", default=os.path.join(DOCS,
                                                      "dewey-precon-drift"))
    ap.add_argument("--base", default=None,
                    help="read payloads from this Jarvis instead of the "
                         "snapshots on disk")
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args(argv)
    try:
        got = build_report(args.runlog, args.md, args.csv, args.figures,
                           base=args.base, figures=not args.no_figures)
    except ReportError as exc:
        print("REFUSED: %s" % exc)
        return 2
    print("%d drifts, %d CSV rows" % (got["drifts"], got["rows"]))
    print("md  -> %s" % got["md"])
    print("csv -> %s" % got["csv"])
    print("figures: %d under %s" % (len(got["figures"]), args.figures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
