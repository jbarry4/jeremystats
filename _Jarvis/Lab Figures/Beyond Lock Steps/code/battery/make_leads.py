"""Each lead from the UNCORRECTED battery, explained from the waveform up
(asked 2026-11-17: "figures leading up to the figure ... where on the
waveform that is true ... I am not sure what the Y axis is").
  battery_reports/uncorrected/Leads_explained_UNCORRECTED.pdf
One page a lead:
  a  where on the dentate spike the number is read (mean CSD, example recording)
  b  one event, step by step
  c  every event of two example recordings (one per side of the contrast)
  d  every event of every recording, with the per-recording number marked
  e  the result: one number per recording, by group and against knockout
  then the numbers, what speaks against it, and what would test it.
The list and the words are in leads.json.
  python make_leads.py
"""
import json
import os
import textwrap

import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

import dsdata
import house as Hs
import measures as MS
from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, RED, C_DS1, C_DS2, CSD_CMAP, FS, FS_S, W
from house import C_DS3 as C_DS3_
from make_reports import CNAME

HERE = dsdata.HERE
OUT = os.path.join(os.path.dirname(HERE), "battery_reports", "uncorrected")
os.makedirs(OUT, exist_ok=True)
MERGED = os.environ.get("BATTERY_MERGED", "merged")     # the filter battery's leads: merged_filters
T = pd.read_pickle(os.path.join(HERE, MERGED, "tests.pkl"))
Mdf = pd.read_pickle(os.path.join(HERE, MERGED, "measures.pkl")).set_index("id")
LEADS = json.load(open(os.path.join(HERE, "leads.json"), encoding="utf-8"))
class _Recs(dict):
    """Event sets, loaded when first asked for (the filter sets are seven)."""
    def __missing__(self, es):
        self[es] = [r for r in dsdata.load(es) if r.ok]
        return self[es]


RECS = _Recs()
BAND_ORDER = ["b_none", "b_1_300", "b_1_100", "b_5_300", "b_ds", "b_5_50", "b_10_40"]
BAND_SHORT = {"b_none": "none", "b_1_300": "1–300", "b_1_100": "1–100", "b_5_300": "5–300", "b_ds": "5–100 (DS)", "b_5_50": "5–50", "b_10_40": "10–40"}
SET_NAME = {"v6": "Halo set", "v7": "10% grace set", "v8": "Strict set"}
SET_NAME.update({k: "Halo events, %s" % v.replace(" (60 Hz notch only)", "").replace(" (the DS filter)", "") for k, v in dsdata.BANDS.items()})
FEATS = {}
STAT_WORD = {"median": "median over events", "mean": "mean over events", "cv": "CV over events (SD / mean)", "sd": "SD over events",
             "skew": "skew over events", "p90p10": "90th / 10th percentile over events"}
SIDE = {"PTEN_vs_CTL": ("CTL", "PTEN"), "IEDpos_vs_CTL": ("CTL", "IED+"), "IEDneg_vs_CTL": ("CTL", "IED-"), "IEDpos_vs_IEDneg": ("IED-", "IED+"),
        "highKO_vs_CTL": ("CTL", "high"), "lowKO_vs_CTL": ("CTL", "low"), "KO_dose_PTEN": ("low", "high"), "KO_dose_all": ("CTL", "high"),
        "trend_CTL_IEDneg_IEDpos": ("CTL", "IED+"), "trend_CTL_lowKO_highKO": ("CTL", "high"), "variance_PTEN_vs_CTL": ("CTL", "PTEN")}


def in_side(r, side):
    return {"CTL": r.group == "CTL", "PTEN": r.group == "PTEN", "IED+": r.subgroup == "IED+", "IED-": r.subgroup == "IED-",
            "high": r.group == "PTEN" and r.ko >= 15, "low": r.group == "PTEN" and r.ko < 10}[side]


def feats(r):
    key = (r.lab, r.n)
    if key not in FEATS:
        FEATS[key] = MS.event_features(r)
    return FEATS[key]


def parse(mid):
    fam, name, es, clf, var = mid.split("|")
    feat, stat = None, None
    for f in sorted(MS.EVENT_FEATURES, key=len, reverse=True):
        if name.startswith(f + "_") and name[len(f) + 1:] in STAT_WORD:
            feat, stat = f, name[len(f) + 1:]
            break
    return dict(fam=fam, name=name, es=es, clf=clf, var=var, feat=feat, stat=stat)


def mask_of(r, P):
    """The events a measure is taken over."""
    if P["var"] in ("all", "") or not P["clf"]:
        return np.ones(r.n, bool)
    clf = r.used if P["clf"] == "used" else P["clf"]
    if "_over_" in P["var"]:
        # a ratio of two types (DS1 over DS2): show the first type's events
        P = dict(P, var=P["var"].split("_over_")[0])
    if not (clf and r.has(clf) and r.eligible(clf)):
        return None
    return MS.masks_of(r).get((clf, P["var"]))


def events_word(P):
    if P["var"] in ("all", "") or not P["clf"]:
        return "all events"
    v = {"ds1": "DS1 events", "ds2": "DS2 events", "ds1x": "DS1 events (DS3 taken out)", "ds2x": "DS2 events (DS3 taken out)", "ds3": "DS3 events",
         "minor": "the smaller type's events", "major": "the larger type's events", "ds1n": "DS1 events (no minimum type size)",
         "ds2n": "DS2 events (no minimum type size)", "ds1nx": "DS1 events (DS3 taken out, no minimum type size)", "ds2nx": "DS2 events (DS3 taken out, no minimum type size)"}.get(P["var"], P["var"])
    if P["clf"] == "winner":
        return "%s under each recording's winning classifier" % v
    return "%s under the %s classifier" % (v, {"used": "best eligible", "best_nocut": "best (no minimum)"}.get(P["clf"], P["clf"].replace("_", " ")))


# ---------------------------------------------------------------- places
def place(r, feat):
    """Rows (with a word and a color) and the time window a feature reads."""
    k = r.landmarks
    src = sorted({k["rowGU"], k["rowGL"]})
    S = [(k["rowU"], "upper sink row", C_DS1), (k["rowL"], "lower sink row", C_DS1)]
    O = [(x, "source row", RED) for x in src]
    peak = (-3, 3)
    if feat in ("sink_upper",):
        return S[:1], peak, "sink"
    if feat in ("sink_lower",):
        return S[1:], peak, "sink"
    if feat in ("sink_amp", "blade_balance", "sink_area"):
        return S, peak if feat != "sink_area" else (-10, 10), "sink"
    if feat in ("source_amp", "lfp_src"):
        return O, peak, "source"
    if feat in ("source_over_sink",):
        return S + O, peak, "ratio"
    if feat == "net_between":
        rows = [(x, "", "#7A5195") for x in r.good(np.array(k["src_rows"], int))]
        return S + rows, peak, "between"
    if feat in ("source_fwhm",):
        return O, None, "source_time"
    if feat in ("sink_pre", "sink_post"):
        return S, ((-30, -10) if feat == "sink_pre" else (10, 30)), "sink_time"
    if feat in ("sink_fwhm", "sink_asym"):
        return S, None, "sink_time"
    if feat in ("lat_source_minus_sink",):
        return S + O, None, "latency"
    if feat in ("lat_lower_minus_upper",):
        return S, None, "latency_blades"
    if feat in ("lfp_fwhm", "lfp_asym", "lfp_pre", "lfp_post", "lat_sink_minus_lfp"):
        return O, ((-30, -10) if feat == "lfp_pre" else ((10, 30) if feat == "lfp_post" else None)), "lfp_time"
    if feat == "lfp_pos_u":
        return S, peak, "lfp_depth"
    if feat in ("cen_um", "cen_v", "sink_width_um", "outer_share"):
        rows = [(x, "", "#7A5195") for b in ("upper", "lower") for x in r.good(r.blade_rows(b, 5))]
        return S + rows, peak, "csd_depth"
    return S + O, peak, "other"


def trace(r, rows, kind="csd"):
    X = r.csd if kind == "csd" else r.lfp
    return X[:, rows, :].mean(axis=1)


# ---------------------------------------------------------------- panels
def panel_where(fig, H, x, y, r, P):
    rows, win, kind = place(r, P["feat"])
    ax = ax_mm(fig, H, x, y, 40, 52)
    k = r.landmarks
    lo, hi = max(0, k["rowU"] - 7), min(63, k["rowL"] + 7)
    if kind in ("lfp_time", "lfp_depth"):
        M = dsdata.fill_bad(r.lfp.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
        v = np.nanpercentile(np.abs(M), 99)
        ax.imshow(M, aspect="auto", cmap="PuOr_r", vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25], interpolation="bilinear")
        ax.text(-39, -15, "mean LFP (brown +, purple −)", fontsize=4.4, color=INK, va="top")
    else:
        M = dsdata.fill_bad(r.csd.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
        v = np.nanpercentile(np.abs(M), 99)
        ax.imshow(M, aspect="auto", cmap=CSD_CMAP, vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25], interpolation="bilinear")
        ax.text(-39, -15, "mean CSD (blue sink, red source)", fontsize=4.4, color=INK, va="top")
    seen = set()
    for row, word, col in rows:
        yy = (row - lo) * 50
        ax.plot([-40, 40], [yy, yy], color=col, lw=0.9 if word else 0.4, alpha=0.95 if word else 0.6)
        if word and word not in seen:
            ax.text(41.5, yy, word, fontsize=4.6, color=col, va="center", ha="left")
            seen.add(word)
    if kind == "between":
        ax.text(41.5, ((k["rowU"] + k["rowL"]) / 2 - lo) * 50, "every row\nbetween", fontsize=4.6, color="#7A5195", va="center")
    if kind == "csd_depth":
        ax.text(41.5, ((k["rowU"] + k["rowL"]) / 2 - lo) * 50, "every row\nof each\nblade", fontsize=4.6, color="#7A5195", va="center")
    if kind == "lfp_depth":
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
        ax.plot([3.5, 3.5], [(a_ - lo) * 50, (b_ - lo) * 50], color="#7A5195", lw=2.0)
        ax.text(41.5, ((a_ + b_) / 2 - lo) * 50, "searched\nfor the\nlargest\nLFP", fontsize=4.6, color="#7A5195", va="center")
    if win is not None:
        ax.axvspan(win[0], win[1], color="black", alpha=0.12, lw=0)
        ax.axvline(win[0], color=INK, lw=0.4, ls=(0, (2, 1.5)))
        ax.axvline(win[1], color=INK, lw=0.4, ls=(0, (2, 1.5)))
    ax.set_xlim(-40, 40)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS_S)
    ax.set_ylabel("Depth below contact %d (µm)" % (lo + 1), fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    return ax


def panel_landmarks(fig, H, x, y, r):
    k = r.landmarks
    ax = ax_mm(fig, H, x, y, 40, 56)
    lo, hi = max(0, k["rowU"] - 7), min(63, k["rowL"] + 7)
    rows = np.arange(lo, hi + 1)
    p = r.mean_csd_peak[rows]
    dep = (rows - lo) * 50.0
    ax.plot(p, dep, color=INK, lw=1.0)
    ax.axvline(0, color=HAIR, lw=0.5)
    span = np.abs(p).max() * 1.1
    ax.set_xlim(-span, span * 1.9)
    for a_, b_, nm in ((k["U"], k["GU"], k["gcl_to_sink_upper_um"]), (k["GL"], k["L"], k["gcl_to_sink_lower_um"])):
        ya, yb = (a_ - lo) * 50, (b_ - lo) * 50
        ax.annotate("", xy=(span * 1.25, ya), xytext=(span * 1.25, yb), arrowprops=dict(arrowstyle="<->", lw=0.8, color="#7A5195", shrinkA=0, shrinkB=0))
        ax.text(span * 1.32, (ya + yb) / 2, "%.0f µm" % nm, fontsize=5, color="#7A5195", va="center")
    for key, col, wd in (("U", C_DS1, "sink"), ("L", C_DS1, "sink"), ("GU", RED, "source"), ("GL", RED, "source")):
        yy = (k[key] - lo) * 50
        ax.plot([span * 1.0, span * 1.18], [yy, yy], color=col, lw=1.2)
    ax.text(span * 1.0, (k["U"] - lo) * 50 - 30, "deepest sink", fontsize=4.4, color=C_DS1, va="bottom")
    ax.set_ylim(dep[-1] + 25, -25)
    ax.set_title("%s (%s): mean of the blades %.0f µm" % (r.lab, Hs.GROUP_NAME[r.subgroup], 0.5 * (k["gcl_to_sink_upper_um"] + k["gcl_to_sink_lower_um"])),
                 fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
    ax.set_xlabel("CSD at the DS peak (left = sink)", fontsize=FS_S)
    ax.set_ylabel("Depth below contact %d (µm)" % (lo + 1), fontsize=FS_S)
    ax.tick_params(labelsize=4.8)


def pick_event(vals):
    ok = np.where(np.isfinite(vals))[0]
    if not ok.size:
        return None
    return int(ok[np.argmin(np.abs(vals[ok] - np.nanmedian(vals[ok])))])


def panel_event(fig, H, x, y, r, P, m):
    """One event at the rows the feature reads, with the reading drawn on."""
    f = feats(r)
    feat = P["feat"]
    vals = np.where(m, f[feat], np.nan)
    i = pick_event(vals)
    if i is None:
        i = pick_event(np.asarray(f[feat], float))
    ax = ax_mm(fig, H, x, y, 42, 40)
    k = r.landmarks
    t = r.t_ms
    rows, win, kind = place(r, feat)
    src = sorted({k["rowGU"], k["rowGL"]})
    up, lw_, so = -r.csd[i, k["rowU"]], -r.csd[i, k["rowL"]], r.csd[i, src].mean(axis=0)
    ax.axhline(0, color=HAIR, lw=0.5)
    if win is not None:
        ax.axvspan(win[0], win[1], color="black", alpha=0.1, lw=0)
    note = ""
    if kind in ("sink", "ratio", "between", "other") or feat in ("blade_balance",):
        ax.plot(t, up, color=C_DS1, lw=1.0, label="sink, upper row")
        ax.plot(t, lw_, color="#56B4E9", lw=1.0, label="sink, lower row")
        w = np.abs(t) <= 3
        a_, b_ = up[w].mean(), lw_[w].mean()
        ax.plot([-3, 3], [a_, a_], color=C_DS1, lw=2.2)
        ax.plot([-3, 3], [b_, b_], color="#56B4E9", lw=2.2)
        if kind in ("ratio", "other"):
            ax.plot(t, so, color=RED, lw=1.0, label="source rows")
            c_ = so[w].mean()
            ax.plot([-3, 3], [c_, c_], color=RED, lw=2.2)
        if kind == "between":
            bt = r.csd[i, r.good(np.array(k["src_rows"], int))].mean(axis=0)
            ax.plot(t, bt, color="#7A5195", lw=1.0, label="mean of rows between")
        note = event_note(r, feat, i)
    elif kind in ("source", "source_time"):
        ax.plot(t, so, color=RED, lw=1.0, label="source rows")
        if kind == "source_time":
            draw_fwhm(ax, t, so, RED)
        note = event_note(r, feat, i)
    elif kind == "sink_time":
        sk = 0.5 * (up + lw_)
        ax.plot(t, sk, color=C_DS1, lw=1.0, label="sink, mean of the two rows")
        draw_fwhm(ax, t, sk, C_DS1)
        note = event_note(r, feat, i)
    elif kind in ("latency", "latency_blades"):
        sk = 0.5 * (up + lw_)
        c0 = int(np.argmin(np.abs(t)))
        if kind == "latency":
            ax.plot(t, sk, color=C_DS1, lw=1.0, label="sink, mean of the two rows")
            ax.plot(t, so, color=RED, lw=1.0, label="source rows")
            for tr, col in ((sk, C_DS1), (so, RED)):
                p = c0 - 6 + int(np.argmax(tr[c0 - 6:c0 + 7]))
                ax.plot([t[p]], [tr[p]], "o", color=col, ms=3)
                ax.axvline(t[p], color=col, lw=0.6, ls=(0, (2, 1.5)))
        else:
            ax.plot(t, up, color=C_DS1, lw=1.0, label="sink, upper row")
            ax.plot(t, lw_, color="#56B4E9", lw=1.0, label="sink, lower row")
            for tr, col in ((up, C_DS1), (lw_, "#56B4E9")):
                p = c0 - 6 + int(np.argmax(tr[c0 - 6:c0 + 7]))
                ax.plot([t[p]], [tr[p]], "o", color=col, ms=3)
                ax.axvline(t[p], color=col, lw=0.6, ls=(0, (2, 1.5)))
        note = event_note(r, feat, i)
    elif kind == "csd_depth":
        ax.remove()
        ax = ax_mm(fig, H, x + 8, y, 30, 40)
        lo_, hi_ = max(0, k["rowU"] - 8), min(63, k["rowL"] + 8)
        rows_ = np.arange(lo_, hi_ + 1)
        pr = -dsdata.fill_bad(r.csd_peak[i], r.bad_rows)[rows_]
        dep = (rows_ - lo_) * 50.0
        ax.plot(pr, dep, color=INK, lw=1.0)
        ax.axvline(0, color=HAIR, lw=0.5)
        for blade, row in (("upper", k["rowU"]), ("lower", k["rowL"])):
            br = r.good(r.blade_rows(blade, 5))
            Sb = np.maximum(-r.csd_peak[i, br], 0)
            ax.axhline((row - lo_) * 50, color=C_DS1, lw=0.7, ls=(0, (3, 2)))
            if Sb.sum() > 0:
                c_ = (Sb * br).sum() / Sb.sum()
                ax.plot([pr.max() * 0.9], [(c_ - lo_) * 50], marker="<", color="#7A5195", ms=4)
                ax.annotate("", xy=(pr.max() * 0.82, (c_ - lo_) * 50), xytext=(pr.max() * 0.82, (row - lo_) * 50),
                            arrowprops=dict(arrowstyle="->", lw=0.7, color="#7A5195", shrinkA=0, shrinkB=0))
        ax.text(pr.max() * 0.95, -20, "dashed: usual sink row\n◄ this event's sink center", fontsize=4.2, color="#7A5195", ha="right", va="bottom")
        ax.set_ylim(dep[-1] + 25, -25)
        ax.set_xlabel("Sink at the DS peak (−CSD)", fontsize=FS_S)
        ax.set_ylabel("Depth below contact %d (µm)" % (lo_ + 1), fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
        return event_note(r, feat, i)
    elif kind == "lfp_depth":
        ax.remove()
        ax = ax_mm(fig, H, x + 8, y, 30, 40)
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
        rows_ = np.arange(a_, b_ + 1)
        pr = dsdata.fill_bad(r.lfp_peak[i], r.bad_rows)[rows_]
        uu = r.u(rows_)
        ax.plot(pr, uu, color=INK, lw=1.0)
        j = int(np.argmax(pr))
        ax.plot([pr[j]], [uu[j]], "o", color="#7A5195", ms=3.5)
        ax.text(pr[j], uu[j] - 0.06, " most positive: %.2f" % uu[j], fontsize=4.6, color="#7A5195", va="bottom")
        for yv, wd in ((0, "upper sink row"), (1, "lower sink row")):
            ax.axhline(yv, color=HAIR, lw=0.5)
            ax.text(ax.get_xlim()[0], yv, wd, fontsize=4.2, color=MUTE, va="bottom")
        ax.set_ylim(uu[-1] + 0.05, uu[0] - 0.05)
        ax.set_xlabel("LFP at the DS peak (µV)", fontsize=FS_S)
        ax.set_ylabel("Blade-to-blade position", fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
        return event_note(r, feat, i)
    else:
        lf = r.lfp[i, src].mean(axis=0)
        ax.plot(t, lf, color=INK, lw=1.0, label="LFP at the source rows")
        if feat == "lfp_fwhm":
            draw_fwhm(ax, t, lf, INK)
        if feat in ("lfp_pre", "lfp_post"):
            c0 = int(np.argmin(np.abs(t)))
            p = c0 - 6 + int(np.argmax(lf[c0 - 6:c0 + 7]))
            w_ = (t >= -30) & (t <= -10) if feat == "lfp_pre" else (t >= 10) & (t <= 30)
            ax.plot([t[p]], [lf[p]], "o", color=INK, ms=3)
            ax.plot([t[w_][0], t[w_][-1]], [lf[w_].mean()] * 2, color="#7A5195", lw=2.2)
            ax.text(t[w_][0], lf[w_].mean(), "mean here\n", fontsize=4.4, color="#7A5195", va="bottom")
            ax.text(t[p] + 1.5, lf[p], "peak", fontsize=4.4, color=INK, va="center")
        note = event_note(r, feat, i)
    ax.set_xlim(-40, 40)
    ax.set_xlabel("Time from DS peak (ms)", fontsize=FS_S)
    ax.set_ylabel("Sink up (−CSD), source as CSD" if kind not in ("lfp_time",) else "LFP (µV)", fontsize=FS_S - 0.3)
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="upper left", handlelength=1.2, borderaxespad=0.1)
    return note


def draw_fwhm(ax, t, tr, col):
    c0 = int(np.argmin(np.abs(t)))
    _, p, le, ri = MS.half_widths(tr[None, :], c0)
    p, le, ri = int(p[0]), le[0], ri[0]
    if not np.isfinite(le):
        return
    h = tr[p] / 2
    ax.plot([t[p]], [tr[p]], "o", color=col, ms=3)
    ax.annotate("", xy=(t[int(p - le)], h), xytext=(t[int(p + ri)], h), arrowprops=dict(arrowstyle="<->", lw=0.7, color=col, shrinkA=0, shrinkB=0))
    ax.text(t[p], h * 0.75, "width at half height\n%d ms" % (le + ri + 1), fontsize=4.4, color=col, ha="center", va="top")


def event_note(r, feat, i):
    f = feats(r)
    v = f[feat][i]
    desc = MS.EVENT_FEATURES[feat][1]
    return "This event: %s = %s" % (short_name(feat), fmt(v))


def short_name(feat):
    return {"sink_upper": "upper sink", "sink_lower": "lower sink", "sink_amp": "sink size", "blade_balance": "blade balance", "source_amp": "source size",
            "source_over_sink": "source / sink", "net_between": "net CSD between / sink", "source_fwhm": "source duration", "sink_fwhm": "sink duration",
            "lat_source_minus_sink": "source peak time − sink peak time", "lat_lower_minus_upper": "lower − upper sink peak time", "lfp_src": "LFP at the source",
            "lfp_fwhm": "LFP duration", "det_peak": "detector peak", "cen_um": "sink center vs usual sink row (µm)", "lfp_pos_u": "where the LFP is most positive",
            "lfp_pre": "LFP 30–10 ms before / peak"}.get(feat, feat.replace("_", " "))


def fmt(v):
    if not np.isfinite(v):
        return "none"
    if abs(v) >= 100:
        return "%.0f" % v
    if abs(v) >= 10:
        return "%.1f" % v
    return ("%.3f" % v).replace("-", "−")


def panel_examples(fig, H, x, y, P, recs, sides):
    ax = ax_mm(fig, H, x, y, 38, 40)
    out = []
    for side, col in zip(sides, (Hs.C_CTL, Hs.C_IEDP)):
        cand = [r for r in recs if in_side(r, side) and np.isfinite(Mdf.loc[P["id"]].get(r.lab, np.nan))]
        if not cand:
            continue
        vals = np.array([Mdf.loc[P["id"]][r.lab] for r in cand])
        r = cand[int(np.argmin(np.abs(vals - np.median(vals))))]
        m = mask_of(r, P)
        x_ = feats(r)[P["feat"]][m]
        x_ = x_[np.isfinite(x_)]
        out.append((r, x_, col))
    allx = np.concatenate([o[1] for o in out]) if out else np.array([0.0])
    lo, hi = np.percentile(allx, [1, 99])
    bins = np.linspace(lo, hi, 30)
    for r, x_, col in out:
        ax.hist(np.clip(x_, lo, hi), bins=bins, color=Hs.col_of(r), alpha=0.55, lw=0, density=True, label="%s (%s), %d events" % (r.lab, Hs.GROUP_NAME[r.subgroup], x_.size))
        sv = MS.stat_of(x_, P["stat"])
        if P["stat"] in ("median", "mean"):
            ax.axvline(sv, color=Hs.col_of(r), lw=1.2)
        ax.text(0.98, 0.62 - 0.09 * out.index((r, x_, col)), "%s: %s = %s" % (r.lab, P["stat"].replace("p90p10", "90th/10th"), fmt(sv)), transform=ax.transAxes,
                fontsize=4.8, color=Hs.col_of(r), ha="right", va="top", fontweight="bold")
    ax.set_xlabel(short_name(P["feat"]) + " (one value per event)", fontsize=FS_S)
    ax.set_ylabel("Share of events (density)", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="upper left", handlelength=1.0, borderaxespad=0.1)
    return [o[0] for o in out]


def panel_all(fig, H, x, y, P, recs):
    ax = ax_mm(fig, H, x, y, 175 - x + 4, 34)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.subgroup == "IED-"], key=lambda r: r.ko) + \
        sorted([r for r in recs if r.subgroup == "IED+"], key=lambda r: r.ko)
    xs, labs = [], []
    allv = []
    for j, r in enumerate(order):
        m = mask_of(r, P)
        if m is None:
            continue
        v = feats(r)[P["feat"]][m]
        v = v[np.isfinite(v)]
        allv.append(v)
    lo, hi = np.percentile(np.concatenate(allv), [1, 99]) if allv else (0, 1)
    xx = 0
    for r in order:
        m = mask_of(r, P)
        if m is None or m.sum() < MS.MIN_TYPE:
            xs.append(xx)
            labs.append(r.lab)
            xx += 1
            continue
        v = feats(r)[P["feat"]][m]
        v = v[np.isfinite(v)]
        if v.size == 0:
            ax.text(xx, lo, "no value", fontsize=3.8, ha="center", va="bottom", color=MUTE, rotation=90)
            xs.append(xx)
            labs.append(r.lab)
            xx += 1
            continue
        jit = np.random.default_rng(1).uniform(-0.28, 0.28, v.size)
        ax.scatter(xx + jit, np.clip(v, lo, hi), s=0.8, color=Hs.col_of(r), alpha=0.35, lw=0, rasterized=True)
        q1, q2, q3 = np.percentile(v, [25, 50, 75])
        ax.plot([xx - 0.32, xx + 0.32], [q2, q2], color=INK, lw=1.0)
        ax.plot([xx, xx], [q1, q3], color=INK, lw=0.6)
        sv = Mdf.loc[P["id"]].get(r.lab, np.nan)
        if P["stat"] not in ("median",):
            ax.text(xx, hi + (hi - lo) * 0.04, fmt(sv), fontsize=4.2, ha="center", va="bottom", color=INK, rotation=0)
        xs.append(xx)
        labs.append(r.lab)
        xx += 1
    ax.set_xticks(xs)
    ax.set_xticklabels(labs, fontsize=4.8)
    for i_, r in enumerate(order):
        ax.get_xticklabels()[i_].set_color(Hs.GROUP_COL[r.subgroup])
    ax.set_xlim(-0.6, xx - 0.4)
    ax.set_ylim(lo - (hi - lo) * 0.03, hi + (hi - lo) * (0.14 if P["stat"] != "median" else 0.03))
    ax.set_ylabel(short_name(P["feat"]) + "\n(each dot one event)", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    return ax


def outlier_limits(v):
    """y limits that keep the bulk readable: anything beyond 3 IQR past the
    quartiles is drawn at the edge as an arrow with its value."""
    v = v[np.isfinite(v)]
    q1, q3 = np.percentile(v, [25, 75])
    iqr = max(q3 - q1, 1e-12)
    lo_f, hi_f = q1 - 3 * iqr, q3 + 3 * iqr
    inl = v[(v >= lo_f) & (v <= hi_f)]
    a, b = inl.min(), inl.max()
    pad = 0.12 * (b - a if b > a else abs(b) + 1e-9)
    out_hi, out_lo = (v > hi_f).any(), (v < lo_f).any()
    return a - pad * (2.2 if out_lo else 1), b + pad * (2.2 if out_hi else 1), lo_f, hi_f


def draw_points(ax, xs, vals, cols, labs, lims, annotate=True):
    lo, hi, lo_f, hi_f = lims
    k_off = 0
    for xx, v, c, lb in zip(xs, vals, cols, labs):
        if not np.isfinite(v):
            continue
        if v > hi_f or v < lo_f:
            yv = hi - (hi - lo) * 0.035 if v > hi_f else lo + (hi - lo) * 0.035
            ax.scatter([xx], [yv], s=26, marker="^" if v > hi_f else "v", color=c, edgecolor="white", linewidth=0.4, zorder=5, clip_on=False)
            if annotate:
                ax.annotate("%s: %s off scale" % (lb, fmt(v)), (xx, yv), xytext=(4, 0), textcoords="offset points", fontsize=4.2, va="center",
                            color=INK, fontweight="bold")
            else:
                ax.annotate("%s %s" % (lb, fmt(v)), (xx, yv), xytext=(3, -5 * k_off), textcoords="offset points", fontsize=3.8, va="center", color=INK)
                k_off += 1
        else:
            ax.scatter([xx], [v], s=16, color=c, edgecolor="white", linewidth=0.4, zorder=3)
            if annotate:
                ax.annotate(lb, (xx, v), xytext=(3, 0), textcoords="offset points", fontsize=4.0, va="center", color=MUTE)
    ax.set_ylim(lo, hi)
    if np.any(np.asarray(vals)[np.isfinite(vals)] > hi_f):
        ax.plot([-0.02, 0.02], [0.93, 0.95], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
        ax.plot([-0.02, 0.02], [0.905, 0.925], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
    if np.any(np.asarray(vals)[np.isfinite(vals)] < lo_f):
        ax.plot([-0.02, 0.02], [0.05, 0.07], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)
        ax.plot([-0.02, 0.02], [0.075, 0.095], color=INK, lw=0.6, transform=ax.transAxes, clip_on=False)


def theil_sen(x, y):
    from scipy import stats as st_
    if np.unique(x).size < 2:
        return np.nan, np.nan
    sl, ic, _, _ = st_.theilslopes(y, x)
    return sl, ic


def fit_band(ax, x, y, col, ls, grid):
    """Theil-Sen line (robust to the odd recording) and a 95% bootstrap
    band over mice (2,000 resamples)."""
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if x.size < 4 or np.unique(x).size < 2:
        return
    sl, ic = theil_sen(x, y)
    rng = np.random.default_rng(11)
    B = []
    for _ in range(2000):
        i = rng.integers(0, x.size, x.size)
        if np.unique(x[i]).size < 2:
            continue
        b_, a_ = theil_sen(x[i], y[i])
        B.append(a_ + b_ * grid)
    B = np.array(B)
    lo, hi = np.nanpercentile(B, [2.5, 97.5], axis=0)
    ax.fill_between(grid, lo, hi, color=col, alpha=0.13, lw=0, zorder=1)
    ax.plot(grid, ic + sl * grid, color=col, lw=1.0, ls=ls, zorder=2)


def panel_result(fig, H, x, y, L, P):
    m = Mdf.loc[P["id"]]
    recs = RECS["v6"]
    labs = [r.lab for r in recs]
    vals = np.array([m.get(l, np.nan) for l in labs], float)
    sg = np.array([r.subgroup for r in recs])
    ko = np.array([r.ko for r in recs], float)
    cols = [Hs.col_of(r) for r in recs]
    lims = outlier_limits(vals)
    ax = ax_mm(fig, H, x, y, 46, 40)
    rng = np.random.default_rng(3)
    for i, g in enumerate(("CTL", "IED-", "IED+")):
        idx = np.where((sg == g) & np.isfinite(vals))[0]
        xs = i + rng.uniform(-0.17, 0.17, idx.size)
        draw_points(ax, xs, vals[idx], [cols[j] for j in idx], [labs[j] for j in idx], lims)
        if idx.size:
            med = np.median(vals[idx])
            if lims[0] <= med <= lims[1]:
                ax.plot([i - 0.3, i + 0.3], [med] * 2, color=INK, lw=1.0, zorder=4)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Control\n(n = %d)" % ((sg == "CTL") & np.isfinite(vals)).sum(), "PTEN IED−\n(n = %d)" % ((sg == "IED-") & np.isfinite(vals)).sum(),
                        "PTEN IED+\n(n = %d)" % ((sg == "IED+") & np.isfinite(vals)).sum()], fontsize=FS_S - 0.3)
    ax.set_xlim(-0.6, 2.75)
    ax.set_ylim(lims[0], lims[1])
    ax.set_ylabel(L["ylabel"], fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    # against knockout, with the correlation lines and their 95% bands
    ax2 = ax_mm(fig, H, x + 58, y, 36, 40)
    xs = np.where(sg == "CTL", rng.uniform(-1.8, 1.8, ko.size), ko)
    xfit = np.where(sg == "CTL", 0.0, ko)
    inl = np.isfinite(vals) & (vals >= lims[2]) & (vals <= lims[3])
    grid_all, grid_p = np.linspace(0, 30, 60), np.linspace(3, 30, 60)
    fit_band(ax2, xfit[inl], vals[inl], MUTE, (0, (3, 2)), grid_all)
    pm = inl & (sg != "CTL")
    fit_band(ax2, ko[pm], vals[pm], "#C8591A", "-", grid_p)
    draw_points(ax2, xs, vals, cols, labs, lims, annotate=False)
    rows = T[T["id"] == P["id"]].set_index("contrast")
    words = []
    for c, nm in (("KO_dose_PTEN", "PTEN only"), ("KO_dose_all", "all mice")):
        if c in rows.index:
            words.append("%s: rho %s, P = %.3f" % (nm, ("%+.2f" % rows.loc[c]["effect"]).replace("-", "−"), rows.loc[c]["p"]))
    ax2.set_title(chr(10).join(words), fontsize=4.4, loc="left", pad=2, color=INK)
    ax2.set_xticks([0, 10, 20, 30])
    ax2.set_xticklabels(["Control", "10", "20", "30"], fontsize=4.8)
    ax2.set_xlim(-3, 31)
    ax2.set_xlabel("PTEN knockout (% of granule cells)", fontsize=FS_S)
    ax2.tick_params(labelsize=4.8)


def numbers(fig, H, x, y, L, P):
    rows = T[T["id"] == P["id"]].set_index("contrast")
    r = rows.loc[L["contrast"]]
    m = Mdf.loc[P["id"]]
    text_mm(fig, H, x, y, "This contrast: " + CNAME[L["contrast"]], fontsize=FS_S, fontweight="bold")
    lines = ["%s: effect %s, raw P = %s" % (r["test"], ("%+.2f" % r["effect"]).replace("-", "−"), "%.4f" % r["p"])]
    if np.isfinite(r["p_alt"]):
        lines.append("%s: P = %.4f" % (r["alt_kind"], r["p_alt"]))
    other_word = ("Same measure under the DS filter (5–100 Hz)" if P["es"].startswith("b_") else
                  "Other event set (%s)" % ("Strict" if P["es"] == "v6" else "Halo"))
    lines.append(other_word + ": " + ("not available" if not np.isfinite(r["p_other_set"]) else "P = %.3f, %s sign" % (
        r["p_other_set"], "same" if r["same_sign_other_set"] == 1 else "opposite")))
    if r["n_variants"] > 1:
        lines.append("Other classifiers: %.0f%% of %d same sign, %.0f%% also raw P < 0.05" % (100 * r["share_same_sign"], r["n_variants"], 100 * r["share_p05"]))
    lines.append("After correction: q (family) = %.2f, family-wise P = %s" % (r["q_family"], "%.2f" % r["p_maxT"] if np.isfinite(r["p_maxT"]) else "not computed"))
    tr = []
    for key, nm in (("rho_log_events", "event count"), ("rho_minutes", "recording length"), ("rho_year", "year recorded"), ("rho_blade_um", "blade distance")):
        v = m[key]
        if np.isfinite(v):
            tr.append("%s %s" % (nm, ("%+.2f" % v).replace("-", "−")))
    lines.append("Rank correlation with things it should not track:")
    lines.append("    " + ", ".join(tr[:2]))
    if tr[2:]:
        lines.append("    " + ", ".join(tr[2:]))
    for i, s in enumerate(lines):
        text_mm(fig, H, x, y + 3.6 + 3.1 * i, s, fontsize=FS_S - 0.2, color=RED if s.startswith("After") else INK)
    yy = y + 3.6 + 3.1 * len(lines) + 1.5
    cs = [c for c in CNAME if c in rows.index]
    text_mm(fig, H, x, yy, "The same measure in every contrast (raw P):", fontsize=FS_S - 0.2, fontweight="bold")
    for i, c in enumerate(cs):
        rr = rows.loc[c]
        text_mm(fig, H, x + (i % 2) * 92, yy + 3.4 + 3.0 * (i // 2), "%s: %s, P = %.3f" % (CNAME[c], ("%+.2f" % rr["effect"]).replace("-", "−"), rr["p"]),
                fontsize=FS_S - 0.6, color=INK if c == L["contrast"] else MUTE, fontweight="bold" if c == L["contrast"] else "normal")
    return yy + 3.4 + 3.0 * ((len(cs) + 1) // 2)


def wrap(fig, H, x, y, s, width=178, **kw):
    for i, ln in enumerate(textwrap.wrap(s, width)):
        text_mm(fig, H, x, y + 3.1 * i, ln, **kw)
    return y + 3.1 * len(textwrap.wrap(s, width))



# ------------------------------------------------------- other build-ups
def typical(recs, side, mid):
    cand = [r for r in recs if in_side(r, side) and np.isfinite(Mdf.loc[mid].get(r.lab, np.nan))]
    if not cand:
        return None
    vals = np.array([Mdf.loc[mid][r.lab] for r in cand])
    return cand[int(np.argmin(np.abs(vals - np.median(vals))))]


def build_timing(fig, H, y, L, P, recs, sides):
    """Event trains: when the events happen, their intervals, every recording."""
    y0 = y + 5
    ex = [typical(recs, sd, L["id"]) for sd in sides]
    ex = [e for e in ex if e is not None]
    text_mm(fig, H, 2, y0 - 2.5, "a  When the events happen (%s; one row per recording, first 10 minutes)" % events_word(P), fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 1, 100, 18)
    for i, r in enumerate(ex):
        m = mask_of(r, P)
        t = r.times_s[m] if m is not None else r.times_s
        t = t[t <= 600]
        ax.vlines(t / 60.0, i - 0.35, i + 0.35, color=Hs.col_of(r), lw=0.5)
        ax.text(-0.15, i, "%s (%s)" % (r.lab, Hs.GROUP_NAME[r.subgroup]), fontsize=4.6, ha="right", va="center", color=Hs.col_of(r))
    ax.set_ylim(len(ex) - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_xlim(0, 10)
    ax.set_xlabel("Minutes into the recording", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    text_mm(fig, H, 124, y0 - 2.5, "b  Intervals between events", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 132, y0 + 1, 44, 30)
    bins = np.logspace(-1.5, 2.5, 40)
    for r in ex:
        m = mask_of(r, P)
        t = np.sort(r.times_s[m] if m is not None else r.times_s)
        d = np.diff(t)
        ax.hist(d, bins=bins, color=Hs.col_of(r), alpha=0.55, density=True, lw=0, label="%s, %d intervals" % (r.lab, d.size))
    if P["name"].startswith("short_"):
        thr = float(P["name"].split("_")[1].rstrip("s"))
        ax.axvline(thr, color=INK, lw=0.8, ls=(0, (3, 2)))
        ax.text(thr * 1.1, ax.get_ylim()[1] * 0.95, "%g s" % thr, fontsize=4.6, va="top")
    ax.set_xscale("log")
    ax.set_xlabel("Interval (s, log scale)", fontsize=FS_S)
    ax.set_ylabel("Density", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="upper left")
    y1 = y0 + 44
    text_mm(fig, H, 2, y1 - 3, "d  Every recording's intervals (%s): line = median, bar = middle half; number above = the recording's value" % events_word(P), fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y1 + 1, 163, 30)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.subgroup == "IED-"], key=lambda r: r.ko) + \
        sorted([r for r in recs if r.subgroup == "IED+"], key=lambda r: r.ko)
    for j, r in enumerate(order):
        m = mask_of(r, P)
        if m is None or m.sum() < 3:
            continue
        d = np.diff(np.sort(r.times_s[m]))
        jit = np.random.default_rng(1).uniform(-0.28, 0.28, d.size)
        ax.scatter(j + jit, d, s=0.8, color=Hs.col_of(r), alpha=0.35, lw=0, rasterized=True)
        q1, q2, q3 = np.percentile(d, [25, 50, 75])
        ax.plot([j - 0.32, j + 0.32], [q2, q2], color=INK, lw=1.0)
        ax.plot([j, j], [q1, q3], color=INK, lw=0.6)
        ax.text(j, 300, fmt(Mdf.loc[L["id"]].get(r.lab, np.nan)), fontsize=4.2, ha="center", va="bottom")
    ax.set_yscale("log")
    ax.set_ylim(0.02, 600)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=4.8)
    for i_, r in enumerate(order):
        ax.get_xticklabels()[i_].set_color(Hs.GROUP_COL[r.subgroup])
    ax.set_ylabel("Interval (s, log)", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    return y1 + 44


def build_profile(fig, H, y, L, P, recs, sides):
    """Measures read off the average dentate spike's depth profile."""
    import normcurves as NC
    y0 = y + 5
    key = "lfp_u" if P["name"].startswith("lfp_profile") else "prof_u"
    text_mm(fig, H, 2, y0 - 2.5, "a–d  Where it is read: the average dentate spike (all events, %s at the peak) on the normalized depth, typical recordings and group means; "
            "purple band = where the number is read" % ("LFP" if key == "lfp_u" else "CSD"), fontsize=FS_S, fontweight="bold")
    band = L.get("band_u")
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        ax = ax_mm(fig, H, 22 + j * 52, y0 + 4, 34, 56)
        c = NC.curves(r)
        ax.plot(c[key], NC.GRID_U, color=Hs.col_of(r), lw=1.2)
        ax.axvline(0, color=HAIR, lw=0.5)
        for yy in (0, 1):
            ax.axhline(yy, color=HAIR, lw=0.5)
        if band:
            ax.axhspan(band[0], band[1], color="#7A5195", alpha=0.15, lw=0)
        ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["upper blade's\nsink", "lower blade's\nsink"], fontsize=4.6)
        ax.set_xlabel("CSD at the peak\n(1 = average sink)" if key == "prof_u" else "LFP at the peak\n(1 = largest absolute value)", fontsize=FS_S)
        ax.set_title("%s (%s): %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], fmt(Mdf.loc[L["id"]][r.lab])), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.8)
    ax = ax_mm(fig, H, 130, y0 + 4, 40, 56)
    for g in ("CTL", "IED-", "IED+"):
        Y = np.array([NC.curves(r)[key] for r in recs if r.subgroup == g])
        mu = np.nanmean(Y, axis=0)
        se = np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
        ax.fill_betweenx(NC.GRID_U, mu - se, mu + se, color=Hs.GROUP_COL[g], alpha=0.2, lw=0)
        ax.plot(mu, NC.GRID_U, color=Hs.GROUP_COL[g], lw=1.1, label=Hs.GROUP_NAME[g])
    if band:
        ax.axhspan(band[0], band[1], color="#7A5195", alpha=0.15, lw=0)
    ax.axvline(0, color=HAIR, lw=0.5)
    ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper", "lower"], fontsize=4.6)
    ax.set_title("Group means ± s.e.m.", fontsize=FS_S, loc="left", pad=3)
    ax.legend(frameon=False, fontsize=4.4, loc="lower left")
    ax.tick_params(labelsize=4.8)
    return y0 + 76


def build_ds3(fig, H, y, L, P, recs, sides):
    """DS3 measures: every event at the two layer contacts, and the score."""
    y0 = y + 5
    clf_of = lambda r: r.used if P["clf"] in ("", "used") else P["clf"]
    text_mm(fig, H, 2, y0 - 2.5, "a–b  How DS3 is scored: every event's sink at the outer against the middle contact (green wedge = DS3, gray corner = too small to tell)",
            fontsize=FS_S, fontweight="bold")
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        w = r.ds3w.get(clf_of(r)) or {}
        if "score" not in w:
            continue
        ax = ax_mm(fig, H, 18 + j * 50, y0 + 4, 32, 32)
        so, sm = np.maximum(-r.csd_peak[:, w["outer"]], 0), np.maximum(-r.csd_peak[:, w["middle"]], 0)
        top = float(np.percentile(np.concatenate([so, sm]), 99)) * 1.08 or 1.0
        xx = np.linspace(0, top, 50)
        ax.fill_between(xx, xx / 3.0, np.minimum(3.0 * xx, top), color=C_DS3_, alpha=0.13, lw=0)
        ax.fill_between([0, min(w["floor"], top)], [min(w["floor"], top), 0], 0, color="#DADADA", lw=0)
        t = r.types(clf_of(r))
        for k_, col in ((2, C_DS2), (1, C_DS1)):
            ax.scatter(so[t == k_], sm[t == k_], s=2, color=col, lw=0, alpha=0.75)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_xlabel("Sink at outer contact", fontsize=FS_S)
        ax.set_ylabel("Sink at middle contact", fontsize=FS_S)
        ax.set_title("%s (%s): %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], fmt(Mdf.loc[L["id"]][r.lab])), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.6)
    text_mm(fig, H, 120, y0 - 2.5 + 4.5, "c  The score of every event, every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 126, y0 + 6, 52, 30)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.group == "PTEN"], key=lambda r: (r.subgroup != "IED-", r.ko))
    for j, r in enumerate(order):
        w = r.ds3w.get(clf_of(r)) or {}
        if "score" not in w:
            continue
        sc = w["score"][np.isfinite(w["score"])]
        jit = np.random.default_rng(1).uniform(-0.3, 0.3, sc.size)
        ax.scatter(j + jit, sc, s=0.6, color=Hs.col_of(r), alpha=0.4, lw=0, rasterized=True)
    ax.axhspan(-0.5, 0.5, color=C_DS3_, alpha=0.12, lw=0)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=3.8, rotation=90)
    ax.set_ylabel("DS3 score\n(outer − middle) / sum", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    note = ("Too small to tell (gray corner, the 'noise floor'): for each recording, the same two contacts are read 40 ms before and 40 ms after every "
            "dentate spike, when there is no spike, and the sum of the two sinks there is taken; the floor is the 99th percentile of those sums. An event "
            "whose two sinks together are not bigger than that floor cannot be told apart from the background, so it gets no DS3 score. "
            "Score −1 = all of the sink at the middle contact, +1 = all at the outer contact, within ±0.5 = shared (DS3).")
    yy = y0 + 44
    for i_, ln in enumerate(textwrap.wrap(note, 120)):
        text_mm(fig, H, 16, yy + 2.6 * i_, ln, fontsize=4.4, color=MUTE)
    yy += 2.6 * len(textwrap.wrap(note, 120)) + 4
    text_mm(fig, H, 2, yy, "d  What every recording's events are: DS1, DS2 and DS3 (DS3 taken out of DS1 and DS2), and too small to tell", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, yy + 3, 120, 26)
    for j, r in enumerate(order):
        c_ = clf_of(r)
        w = r.ds3w.get(c_) or {}
        if not (c_ and r.has(c_)) or "score" not in w:
            ax.text(j, 0.02, "cannot be scored", fontsize=3.8, ha="center", va="bottom", color=MUTE, rotation=90)
            continue
        t = r.types(c_)
        sc = np.asarray(w["score"], float)
        fin = np.isfinite(sc)
        d3 = fin & (np.abs(sc) <= 0.5)
        parts = [((t == 1) & ~d3 & fin, C_DS1, "DS1"), ((t == 2) & ~d3 & fin, C_DS2, "DS2"), (d3, C_DS3_, "DS3"), (~fin, "#C9C9C9", "too small to tell")]
        b0 = 0.0
        for m_, col, nm in parts:
            ax.bar([j], [m_.mean()], bottom=[b0], color=col, lw=0, width=0.75, label=nm if j == 0 else None)
            b0 += m_.mean()
        ax.text(j, 1.01, "%.0f%%" % (100 * d3.mean()), fontsize=3.9, ha="center", va="bottom", color=C_DS3_)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(["%s\n%s" % (r.lab, {"CTL": "CTL", "IED-": "IED−", "IED+": "IED+"}[r.subgroup]) for r in order], fontsize=3.9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Share of events", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    ax.legend(frameon=False, fontsize=4.2, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    text_mm(fig, H, 16, yy + 37, "Number above a bar = the recording's DS3 share. Gray = events too small to tell (no DS3 score). Cannot be scored = DS1's and DS2's average sinks are deepest at the same contact.", fontsize=4.4, color=MUTE)
    return yy + 46


def build_filter(fig, H, y, L, P, recs, sides):
    """What the stricter event border drops."""
    import measures as MS_
    y0 = y + 5
    R7 = {r.lab: r for r in dsdata.load("v7") if r.ok}
    text_mm(fig, H, 2, y0 - 2.5, "a  Halo events the 10% grace border keeps (dark) and drops (light), every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 2, 90, 34)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.group == "PTEN"], key=lambda r: (r.subgroup != "IED-", r.ko))
    parts = {}
    for j, r in enumerate(order):
        b = R7.get(r.lab)
        if b is None:
            continue
        ink = MS_.match(r.times_s, b.times_s)
        parts[r.lab] = ink
        ax.bar([j], [ink.sum()], color=Hs.col_of(r), lw=0)
        ax.bar([j], [(~ink).sum()], bottom=[ink.sum()], color=Hs.col_of(r), alpha=0.35, lw=0)
        ax.text(j, r.n + 8, "%.0f%%" % (100 * (~ink).mean()), fontsize=4.0, ha="center", va="bottom")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=4.4)
    ax.set_ylabel("Halo events", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    feat = next((f for f in MS_.FILTER_FEATS if P["name"].startswith(f + "_")), None)
    if feat is not None:
        text_mm(fig, H, 114, y0 - 2.5, "b  %s: dropped against kept, two typical recordings" % short_name(feat), fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 124, y0 + 2, 52, 34)
        for j, sd in enumerate(sides):
            r = typical(recs, sd, L["id"])
            if r is None or r.lab not in parts:
                continue
            x = feats(r)[feat]
            ink = parts[r.lab]
            for k_, (mk, nm) in enumerate(((ink, "kept"), (~ink, "dropped"))):
                v = x[mk & np.isfinite(x)]
                xx = j * 2.4 + k_
                jit = np.random.default_rng(2).uniform(-0.3, 0.3, v.size)
                ax.scatter(xx + jit, v, s=1.2, color=Hs.col_of(r), alpha=0.5 if nm == "kept" else 0.9, lw=0)
                if v.size:
                    ax.plot([xx - 0.35, xx + 0.35], [np.median(v)] * 2, color=INK, lw=1.0)
                ax.text(xx, ax.get_ylim()[0], "%s\n%s" % (r.lab, nm), fontsize=4.2, ha="center", va="top")
        ax.set_xticks([])
        ax.set_ylabel(short_name(feat), fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
    return y0 + 50


AROUND = {}


def around_maps(r, band, var):
    """(rows' u, median log2 power over random moments [rows x 101 bins]) for one recording."""
    import around_measures as AM
    key = (r.lab, band, var)
    if key not in AROUND:
        D = AM.load(r)
        if D is None:
            AROUND[key] = None
            return None
        bi = AM.BANDS.index(band)
        m = D["evok"].copy()
        if var in ("ds1x", "ds2x") and r.winner:
            t = r.types("winner")
            m3 = r.ds3("winner")
            m3 = np.zeros(r.n, bool) if m3 is None else m3
            m &= (t == (1 if var == "ds1x" else 2)) & ~m3
        mrd = D["rdE"][:, bi].mean(axis=0)
        mrd[mrd <= 0] = np.nan
        lr = np.log2(np.maximum(D["evE"][m][:, bi], 1e-12) / mrd[None])
        rows = np.array(r.good(np.arange(1, 63)), int)
        AROUND[key] = (r.u(rows), np.nanmedian(lr[:, rows, :], axis=0), int(m.sum()))
    return AROUND[key]


def build_around(fig, H, y, L, P, recs, sides):
    """Before/after measures: where and when the band's power differs from random moments."""
    import around_measures as AM
    A_ = L["around"]
    band, var = A_["band"], P["var"] or "all"
    w = A_.get("window")
    lo_u, hi_u = A_.get("u", (None, None))
    y0 = y + 5
    text_mm(fig, H, 2, y0 - 2.5, "a–b  %s around the DS, two typical recordings: power over random moments (log2; red = more, blue = less), median over %s" % (
        AM.BAND_WORD[band], events_word(P)), fontsize=FS_S, fontweight="bold")
    TB = AM.TB
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        got = around_maps(r, band, var)
        if got is None:
            continue
        u, M, n = got
        ax = ax_mm(fig, H, 16 + j * 58, y0 + 5, 46, 46)
        o = np.argsort(u)
        ax.pcolormesh(TB, u[o], M[o], cmap="RdBu_r", vmin=-1, vmax=1, shading="nearest", rasterized=True)
        for yy in (0, 1):
            ax.axhline(yy, color=INK, lw=0.5, ls=(0, (2, 2)))
        ax.axvline(0, color=INK, lw=0.5)
        if w:
            for x_ in w:
                ax.axvline(x_, color="#7A5195", lw=0.8)
        if lo_u is not None:
            ax.axhspan(lo_u, hi_u, xmin=0, xmax=1, fill=False, ec="#7A5195", lw=0.9)
        ax.set_ylim(min(u.max(), 3.0), max(u.min(), -2.0))
        ax.set_yticks([-2, -1, 0, 1, 2, 3])
        ax.set_yticklabels(["−2", "−1", "0 upper\nblade", "1 lower\nblade", "2", "3"], fontsize=4.4)
        ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
        ax.set_ylabel("Depth (u; toward CA1 is up)", fontsize=FS_S)
        ax.set_title("%s (%s), %d events: %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], n, fmt(Mdf.loc[L["id"]].get(r.lab, np.nan))), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.6)
    # c: the time course at the depth read, every recording
    text_mm(fig, H, 130, y0 - 2.5 + 4.5, "c  At the depth read, every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 136, y0 + 5, 42, 46)
    groups = {}
    for r in recs:
        got = around_maps(r, band, var)
        if got is None:
            continue
        u, M, n = got
        sel = (u >= lo_u) & (u < hi_u) if lo_u is not None else np.ones(u.size, bool)
        if not sel.any():
            continue
        tr = np.nanmean(M[sel], axis=0)
        ax.plot(TB, tr, color=Hs.col_of(r), lw=0.4, alpha=0.6)
        groups.setdefault(r.subgroup, []).append(tr)
    for g, trs in groups.items():
        ax.plot(TB, np.nanmedian(np.array(trs), axis=0), color=Hs.GROUP_COL[g], lw=1.6, label=Hs.GROUP_NAME[g])
    ax.axhline(0, color=HAIR, lw=0.5)
    ax.axvline(0, color=INK, lw=0.5)
    if w:
        ax.axvspan(w[0], w[1], color="#7A5195", alpha=0.12, lw=0)
    ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
    ax.set_ylabel("Power over random moments (log2)", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    ax.legend(frameon=False, fontsize=4.2, loc="upper left")
    note = A_.get("note", "")
    if note:
        for i_, ln in enumerate(textwrap.wrap(note, 125)):
            text_mm(fig, H, 16, y0 + 59 + 2.6 * i_, ln, fontsize=4.4, color=MUTE)
    return y0 + 72


def band_id(mid, es):
    f, n, _e, c, v = mid.split("|")
    return "|".join([f, n, es, c, v])


def build_bands(fig, H, y, L, P):
    """f: the same number under every filter, every recording; g: the average
    dentate spike of one typical recording under the DS filter and this one."""
    y0 = y + 2
    text_mm(fig, H, 2, y0, "f  The same number under every filter (same events and types). Lines = recordings; "
            "bold = group median", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 4, 104, 36)
    recs6 = RECS["v6"]
    ids = [band_id(L["id"], es) for es in BAND_ORDER]
    V = np.array([[Mdf.loc[i].get(r.lab, np.nan) if i in Mdf.index else np.nan for i in ids] for r in recs6], float)
    lims = outlier_limits(V.ravel())
    Vc = np.clip(V, lims[0], lims[1])
    xs = np.arange(len(BAND_ORDER))
    for j, r in enumerate(recs6):
        ax.plot(xs, Vc[j], color=Hs.col_of(r), lw=0.5, alpha=0.55)
    for g in ("CTL", "IED-", "IED+"):
        idx = [j for j, r in enumerate(recs6) if r.subgroup == g]
        ax.plot(xs, np.nanmedian(Vc[idx], axis=0), color=Hs.GROUP_COL[g], lw=1.8, label=Hs.GROUP_NAME[g])
    k_this = BAND_ORDER.index(P["es"])
    ax.axvspan(k_this - 0.35, k_this + 0.35, color="#F2E6A0", alpha=0.5, lw=0, zorder=0)
    ax.set_xticks(xs)
    ax.set_xticklabels([BAND_SHORT[b].replace(" (", chr(10) + "(") for b in BAND_ORDER], fontsize=4.8)
    ax.set_xlabel("Filter (Hz)", fontsize=FS_S)
    ax.set_ylabel(L["ylabel"], fontsize=FS_S - 0.3)
    ax.set_ylim(lims[0], lims[1])
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="best")
    rows = T[T["contrast"] == L["contrast"]].set_index("id")
    ps = ["%s P = %s" % (BAND_SHORT[b], ("%.3f" % rows.loc[i]["p"]) if i in rows.index else "–") for b, i in zip(BAND_ORDER, ids)]
    text_mm(fig, H, 2, y0 + 49, CNAME[L["contrast"]] + ", raw P under each filter:  " + ";  ".join(ps), fontsize=4.5, color=INK)
    # g: the average dentate spike under the DS filter and under this one
    ex = typical(RECS[P["es"]], SIDE[L["contrast"]][1], L["id"])
    if ex is not None and P["feat"] is not None:
        rows_, win, kind = place(ex, P["feat"])
        rr = [q for q, _w, _c in rows_][:2]
        text_mm(fig, H, 128, y0 + 0, "g  %s's average event at %s" % (ex.lab, "the read rows"), fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 136, y0 + 4, 42, 36)
        ds = {r_.lab: r_ for r_ in RECS["b_ds"]}[ex.lab]
        for rec_, nm, ls in ((ds, "5–100 Hz (DS filter)", (0, (3, 2))), (ex, dsdata.BANDS[P["es"]], "-")):
            X = rec_.lfp if kind in ("lfp_time", "lfp_depth") else rec_.csd
            for q, col in zip(rr, (C_DS1, RED)):
                ax.plot(rec_.t_ms, X[:, q, :].mean(axis=0) * (1 if kind in ("lfp_time", "lfp_depth") else -1), color=col, lw=0.9, ls=ls,
                        label="%s, contact %d" % (nm, rec_.contacts[q]))
        ax.axvline(0, color=HAIR, lw=0.5)
        ax.set_xlim(-50, 50)
        ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
        ax.set_ylabel("LFP (µV)" if kind in ("lfp_time", "lfp_depth") else "Sink up (−CSD)", fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
        ax.legend(frameon=False, fontsize=3.9, loc="upper right")
    return y0 + 53


def lead_page(k, L, prefix="Lead"):
    P = parse(L["id"])
    P["id"] = L["id"]
    is_ds3 = P["fam"] == "structure" and P["feat"] is None and ("ds3" in P["name"] or "relsink" in P["name"] or "unscorable" in P["name"])
    H = 318.0 if (P["es"].startswith("b_") or is_ds3) else 262.0
    fig = Hs.page(H)
    Hs.stamp(fig)
    text_mm(fig, H, 4, 5, ("%s %d.  %s" % (prefix, k, L["title"])) if not L["title"].startswith("NOT A LEAD") else ("Appendix.  " + L["title"]), fontsize=9, fontweight="bold")
    y = wrap(fig, H, 4, 10.5, "In one sentence: " + L["plain"], 175, fontsize=FS_S + 0.3, color=INK)
    y = wrap(fig, H, 4, y + 0.4, "How the number is made: " + L["how"], 182, fontsize=FS_S, color=MUTE) + 2
    recs = RECS[P["es"]]
    sides = SIDE[L["contrast"]]
    if P["feat"] is not None:
        ex = None
        cand = [r for r in recs if in_side(r, sides[1]) and np.isfinite(Mdf.loc[L["id"]].get(r.lab, np.nan))]
        vals = np.array([Mdf.loc[L["id"]][r.lab] for r in cand])
        ex = cand[int(np.argmin(np.abs(vals - np.median(vals))))]
        y0 = y + 5
        for xx, s in ((2, "a  Where it is read (%s, mean of all events)" % ex.lab), (74, "b  One event of %s, step by step" % ex.lab),
                      (128, "c  Every event of two typical recordings")):
            text_mm(fig, H, xx, y0 - 2.5, s, fontsize=FS_S, fontweight="bold")
        panel_where(fig, H, 14, y0 + 1, ex, P)
        note = panel_event(fig, H, 84, y0 + 1, ex, P, mask_of(ex, P))
        text_mm(fig, H, 84, y0 + 48.5, note, fontsize=4.8, color=INK)
        panel_examples(fig, H, 141, y0 + 1, P, recs, sides)
        y1 = y0 + 66
        text_mm(fig, H, 2, y1 - 3, "d  Every event of every recording (%s): line = median, bar = middle half; %s" % (
            events_word(P), "number above = the recording's %s" % STAT_WORD[P["stat"]] if P["stat"] != "median" else "the recording's number is the median line"),
            fontsize=FS_S, fontweight="bold")
        panel_all(fig, H, 16, y1 + 1, P, recs)
        y2 = y1 + 50
    elif P["fam"] == "around":
        y2 = build_around(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "timing":
        y2 = build_timing(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "filter" and not P["es"].startswith("b_"):
        y2 = build_filter(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "structure" and ("ds3" in P["name"] or "relsink" in P["name"] or "unscorable" in P["name"]):
        y2 = build_ds3(fig, H, y, L, P, recs, sides)
    elif P["name"].startswith(("profile_u", "net_u", "mean_sink_asym", "mean_source_over", "main_sink_fwhm", "lfp_profile_u")):
        y2 = build_profile(fig, H, y, L, P, recs, sides)
    elif P["name"].startswith("gcl_to_sink"):
        y0 = y + 5
        text_mm(fig, H, 2, y0 - 2.5, "a–d  Where the distance is read: the average dentate spike (CSD at the peak) down the probe, one typical recording per side", fontsize=FS_S, fontweight="bold")
        for j, side in enumerate(sides):
            cand = [r for r in recs if in_side(r, side)]
            vals = np.array([Mdf.loc[L["id"]][r.lab] for r in cand])
            r = cand[int(np.argmin(np.abs(vals - np.median(vals))))]
            panel_landmarks(fig, H, 22 + j * 88, y0 + 4, r)
        y2 = y0 + 76
    else:
        y2 = y + 6
        for i, s in enumerate(L.get("steps", [])):
            y2 = wrap(fig, H, 6, y2, "%d.  %s" % (i + 1, s), 175, fontsize=FS_S) + 0.8
        y2 += 4
    text_mm(fig, H, 2, y2 - 3, "e  The result: one number per recording (%s)" % SET_NAME[P["es"]], fontsize=FS_S, fontweight="bold")
    panel_result(fig, H, 16, y2 + 1, L, P)
    note_ = ("Right: lines are Theil–Sen fits (robust to a single odd mouse) with 95% bootstrap bands over mice; orange solid = PTEN mice only, "
             "gray dashed = all mice with controls at 0. ▲▼ = a recording off the scale (more than 3 interquartile ranges out), drawn at the edge "
             "with its value and left out of the lines.")
    for i_, ln in enumerate(textwrap.wrap(note_, 118)):
        text_mm(fig, H, 16, y2 + 49.5 + 2.6 * i_, ln, fontsize=4.3, color=MUTE)
    yN = numbers(fig, H, 116, y2 + 1, L, P)
    y3 = max(y2 + 61, yN + 4)
    if P["es"].startswith("b_"):
        y3 = build_bands(fig, H, y3, L, P)
    for head, key in (("Why it is interesting", "why"), ("What speaks against it", "against"), ("What would test it", "test")):
        text_mm(fig, H, 4, y3, head, fontsize=FS, fontweight="bold")
        y3 = wrap(fig, H, 4, y3 + 3.5, L[key], 178, fontsize=FS_S) + 2.0
    return fig


SETS_OUT = [("leads.json", "Leads_explained_UNCORRECTED.pdf", "Lead", "Lead"), ("leads_ds3.json", "Leads_DS3_UNCORRECTED.pdf", "DS3_lead", "DS3 lead"),
            ("leads_band.json", "Leads_filter_UNCORRECTED.pdf", "Filter_lead", "Filter lead"),
            ("leads_general.json", "Leads_not_DS_type_UNCORRECTED.pdf", "General_lead", "Lead (no DS type)"),
            ("leads_around.json", "Leads_before_after_UNCORRECTED.pdf", "Before_after_lead", "Before/after lead")]

if __name__ == "__main__":
    import sys as _sys
    only = _sys.argv[1:]
    for js, pdfname, stem, prefix in SETS_OUT:
        if only and js not in only:
            continue
        path = os.path.join(HERE, js)
        if not os.path.isfile(path):
            continue
        LL = json.load(open(path, encoding="utf-8"))
        with PdfPages(os.path.join(OUT, pdfname)) as pdf:
            for k, L in enumerate(LL, 1):
                fig = lead_page(k, L, prefix)
                pdf.savefig(fig)
                fig.savefig(os.path.join(OUT, "%s_%02d.png" % (stem, k)), dpi=170)
                plt.close(fig)
                print(js, k, flush=True)
        print("saved", pdfname, len(LL))
