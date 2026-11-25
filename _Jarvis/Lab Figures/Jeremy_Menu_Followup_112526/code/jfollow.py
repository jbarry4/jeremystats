"""Jeremy menu follow-up (2026-11-25): what a held-out call is, and the DS / BT / IED counts per mouse and group.
python jfollow.py  -> Lab Figures/Jeremy_Menu_Followup_112526 (two pages, merged PDF via j_merge-style pymupdf, CSVs)."""
import glob
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
from matplotlib import patches

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figlib as F  # noqa: E402
import jpages as J  # noqa: E402
import menu_data as D  # noqa: E402
import stats_lib as S  # noqa: E402
from pages_a import textcol  # noqa: E402

DEST = r"C:\Users\Z390\Desktop\jeremystats\_Jarvis\Lab Figures\Jeremy_Menu_Followup_112526"
RUN = os.path.join(J.RUNS, "r006")
LABS, CTL = J.LABS, J.CTL
PT = [l for l in LABS if l not in CTL]
DATE = "2026-11-25"
VIEW_WORD = {"core": "DS shape and depth", "context": "+ timing context", "filters": "+ six other filters",
             "before_after": "+ power before/after", "events_all": "every event feature", "everything": "everything"}
MODEL_WORD = {"linear": "linear", "lasso": "lasso", "forest": "forest", "boosting": "boosting", "mlp": "small network",
              "deepsets": "set network", "attention": "attention network"}


def header(num, asked, results):
    fig = F.plt.figure(figsize=(8.5, 11))
    F.put(fig, 0.5, 0.42, "JEREMY MENU \u00b7 FOLLOW-UP %d" % num, 7.5, size=7, color=F.C_POS, weight="bold")
    y = 0.62
    y += F.put(fig, 0.5, y, "Asked: \u201c%s\u201d" % asked, 7.5, size=8.6, color=F.SOFT, style="italic") + 0.06
    y += F.put(fig, 0.5, y, "Results show: " + results, 7.5, size=12, weight="bold")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, str(num), fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, "Jeremy menu follow-up \u00b7 exploratory \u00b7 %s" % DATE, fontsize=6.5, color=F.FAINT,
             ha="left", va="bottom")
    return fig, y + 0.15


def save(fig, name):
    os.makedirs(os.path.join(DEST, "pages"), exist_ok=True)
    F.finish(fig)
    fig.savefig(os.path.join(DEST, "pages", name + ".png"), dpi=300)
    fig.savefig(os.path.join(DEST, "pages", name + ".pdf"), dpi=600)
    F.plt.close(fig)


# ---------------------------------------------------------------- page 1: held-out calls
def page_heldout():
    res = [json.load(open(f)) for f in glob.glob(os.path.join(RUN, "results", "*.json"))]
    ied = [r for r in res if r["target"] == "iedpos_vs_iedneg"]
    good = sorted([r for r in ied if r["passes"]], key=lambda r: (-r["score"]["main"], r["view"], r["model"]))
    calls = {(r["view"], r["model"]): {c["lab"]: c["call"] for c in r["calls"]} for r in good}
    mean = {l: float(np.mean([calls[k][l] for k in calls])) for l in PT}
    right = [l for l in PT if (mean[l] > 0.5) == (F.subgroup(l) == "IED+")]
    miss = [l for l in PT if l not in right]
    close = [l for l in right if abs(mean[l] - 0.5) < 0.1]
    fig, y = header(1, "What are the held-out features/models here? ... define held-out call more, not sure what that means, "
                       "held out from 1 mouse, or held out from a specific group",
                    "A held-out call is one mouse's prediction from models that never saw that mouse: each PTEN mouse in turn is "
                    "set aside, the models learn IED+ against IED\u2212 from the other eight, then guess the one left out. "
                    "Averaged over the %d models that cleared the bar, the calls are right for %d of 9 mice; %s is the miss."
                    % (len(good), len(right), ", ".join(miss)))
    F.letter(fig, 0.4, y + 0.08, "a", "One mouse out at a time: nine rounds, one per PTEN mouse; controls are not part of this question",
             width=7.6)
    a = F.axes_in(fig, 1.2, y + 0.45, 3.2, 1.55)
    for i, held in enumerate(PT):
        for j, l in enumerate(PT):
            col = F.C_POS if F.subgroup(l) == "IED+" else F.C_NEG
            if l == held:
                a.add_patch(patches.Rectangle((j - 0.42, i - 0.38), 0.84, 0.76, facecolor="white", edgecolor=F.INK, lw=1.2,
                                              hatch="////"))
            else:
                a.add_patch(patches.Rectangle((j - 0.42, i - 0.38), 0.84, 0.76, facecolor=col, edgecolor="white", lw=0.5,
                                              alpha=0.9))
    a.set_xlim(-0.6, len(PT) - 0.4)
    a.set_ylim(len(PT) - 0.4, -0.6)
    a.set_xticks(range(len(PT)))
    a.set_xticklabels(["%s\n%.0f%%" % (l, F.ko(l)) for l in PT], fontsize=5.6)
    for t, l in zip(a.get_xticklabels(), PT):
        t.set_color(F.C_POS if F.subgroup(l) == "IED+" else "#b5508a")
    a.set_yticks(range(len(PT)))
    a.set_yticklabels(["round %d" % (i + 1) for i in range(len(PT))], fontsize=5.6)
    a.tick_params(length=0)
    for s_ in a.spines.values():
        s_.set_visible(False)
    a.xaxis.tick_top()
    F.put(fig, 4.6, y + 0.6, "Filled: the eight mice the models learn from (dark IED+, light IED\u2212). Hatched: the mouse held "
          "out and called. Nothing about the held-out mouse (its events, its per-mouse numbers, even the scaling and the "
          "choice of features) is used to train that round's models. The seven controls sit this question out; they are "
          "used only in the questions that involve controls (PTEN against control, the three IED groups, % knockout).",
          3.4, size=6.6)
    y2 = y + 2.25
    F.letter(fig, 0.4, y2 + 0.08, "b", "Every model that cleared the bar, and its call for every held-out mouse", width=7.6)
    keys = list(calls)
    b = F.axes_in(fig, 2.25, y2 + 0.5, 4.2, 0.165 * (len(keys) + 1))
    M = np.array([[calls[k][l] for l in PT] for k in keys] + [[mean[l] for l in PT]])
    b.imshow(M, cmap="RdPu", vmin=0, vmax=1, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            b.text(j, i, "%.2f" % M[i, j], ha="center", va="center", fontsize=5.0,
                   color="white" if M[i, j] > 0.6 else F.INK, weight="bold" if i == M.shape[0] - 1 else "normal")
    b.axhline(len(keys) - 0.5, color="white", lw=2.5)
    b.set_xticks(range(len(PT)))
    b.set_xticklabels(["%s\n%s" % (l, "IED+" if F.subgroup(l) == "IED+" else "IED\u2212") for l in PT], fontsize=5.6)
    b.xaxis.tick_top()
    b.set_yticks(range(M.shape[0]))
    b.set_yticklabels(["%s \u00b7 %s  (AUC %.2f)" % (VIEW_WORD[v], MODEL_WORD[m], next(r["score"]["main"] for r in good
                       if (r["view"], r["model"]) == (v, m))) for v, m in keys] + ["Mean of the %d: the held-out call" % len(keys)],
                      fontsize=5.6)
    b.tick_params(length=0)
    for s_ in b.spines.values():
        s_.set_visible(False)
    yt = y2 + 0.5 + 0.165 * (len(keys) + 1) + 0.25
    textcol(fig, yt, [
        ("What the models see (features)", "Only the dentate spikes (the Halo set's DS events) and per-mouse summaries of them; "
         "no BTs or IED-class events, and not the Root Canal fast power. 'DS shape and depth' is 29 measures per event "
         "(sink and source size, width, timing, where the sink sits along the dendrites, blade balance, LFP shape) plus the "
         "DS1/DS2 type. The other views add timing context (intervals, time in the recording, theta), the same measures under "
         "the six other filters, or power before and after each DS (7 bands, 11 depths). A 'nuisance' view (probe placement, "
         "year, recording length, event count) is the baseline that tells us a score is about the spikes, not the recording: "
         "for IED status it reaches only AUC %.2f." % max(r["score"]["main"] for r in ied if r["view"] == "nuisance")),
        ("The models", "Seven kinds: five that first summarize each mouse's spikes as distributions (linear, lasso, forest, "
         "boosting, a small network) and two that read the events themselves (a set network and an attention network). "
         "Every view x model pair was run: %d for this question. The %d shown are those whose held-out AUC reached the bar "
         "of 0.80; their calls are averaged into the held-out call plotted in the DS menu (Story 8b)." % (len(ied), len(good))),
        ("Reading", "m3 is called IED\u2212 by all 14 models (one sits at exactly 0.50). %s sit%s close to "
         "0.5, so the models are least sure about them. m7, the high-knockout mouse without IEDs, is called IED\u2212 by every "
         "model." % (" and ".join(close) if close else "No mouse", "" if len(close) == 1 else "")),
        ("Caveats", "Choosing the models at the bar uses the same held-out scores, so the averaged call is slightly optimistic; "
         "with 9 mice one wrong call moves AUC by 0.05. The other questions use the same rule (one mouse out), except PTEN "
         "against control, which holds out one control and one PTEN mouse together (all 63 pairs)."),
    ], x=0.5, w=7.5)
    save(fig, "01_held_out_calls")
    rows = []
    for r in res:
        for c in r["calls"]:
            rows.append({"question": r["target"], "view": r["view"], "model": r["model"], "scheme": r["scheme"],
                         "held_out_auc_or_rho": r["score"]["main"], "passes_bar": r["passes"], "fold": c["fold"], "mouse": c["lab"],
                         "truth": c["truth"], "call": c["call"]})
    return pd.DataFrame(rows), calls, mean


# ---------------------------------------------------------------- page 2: counts
def counts():
    rc = D.rc()
    h = rc[rc.wf == "halo"]
    T, _c = J.strict_table()
    T = T.set_index("mouse")
    rows = []
    for l in LABS:
        q = h[h.lab == l].kind.value_counts()
        mins = S.M[l]["dur_min"]
        rows.append({"mouse": l, "group": {"CTL": "Control", "IED-": "PTEN IED\u2212", "IED+": "PTEN IED+"}[F.subgroup(l)],
                     "knockout_pct": F.ko(l), "minutes": round(mins, 1),
                     "DS": int(q.get("DS", 0)), "BT": int(q.get("TZ", 0)), "IED_class": int(q.get("IED", 0)),
                     "outside_both_halos": int(q.get("far", 0) + q.get("none", 0)),
                     "DS_per_min": q.get("DS", 0) / mins, "BT_per_min": q.get("TZ", 0) / mins, "IED_per_min": q.get("IED", 0) / mins,
                     "strict_DS": int(T.loc[l, "ds"]), "strict_IED_class": int(T.loc[l, "ied"]),
                     "strict_undecided": int(T.loc[l, "und"])})
    return pd.DataFrame(rows)


def page_counts(C):
    g = C.groupby("group", sort=False)
    tot = g[["DS", "BT", "IED_class", "outside_both_halos", "strict_DS", "strict_IED_class", "strict_undecided"]].sum()
    mins = g["minutes"].sum()
    ied_bt = int(C[C.group == "PTEN IED+"][["BT", "IED_class"]].sum().sum())
    other = int(C[C.group != "PTEN IED+"][["BT", "IED_class"]].sum().sum())
    fig, y = header(2, "Do we have the number of DSs, BTs, and IEDs per group and per mouse?",
                    "Yes. The Halo set has %d events, %d of them DS. Of the %d BTs and IED-class events, %d come from the five "
                    "IED+ mice; the other eleven mice have %d in all." % (
                        int(C[["DS", "BT", "IED_class", "outside_both_halos"]].sum().sum()), int(C.DS.sum()), ied_bt + other, ied_bt, other))
    cols = [("mouse", "Mouse", "{}"), ("knockout_pct", "KO %", "{:.1f}"), ("minutes", "Min", "{:.0f}"), ("DS", "DS", "{}"),
            ("BT", "BT", "{}"), ("IED_class", "IED", "{}"), ("outside_both_halos", "Outside", "{}"),
            ("DS_per_min", "DS/min", "{:.2f}"), ("BT_per_min", "BT/min", "{:.2f}"), ("IED_per_min", "IED/min", "{:.2f}"),
            ("strict_DS", "DS", "{}"), ("strict_IED_class", "IED", "{}"), ("strict_undecided", "Undec.", "{}")]
    xs = np.array([0.55, 1.1, 1.62, 2.12, 2.62, 3.07, 3.55, 4.18, 4.78, 5.38, 6.15, 6.65, 7.25])
    F.letter(fig, 0.4, y + 0.08, "a", "Per mouse, in order of knockout within each group", width=7.6)
    yy = y + 0.3
    F.put(fig, 2.1, yy, "Halo set (the menu's main set): events", 2.0, size=6.3, color=F.SOFT, weight="bold")
    F.put(fig, 4.15, yy, "per minute", 1.6, size=6.3, color=F.SOFT, weight="bold")
    F.put(fig, 6.1, yy, "Strict set (appendix)", 1.6, size=6.3, color=F.SOFT, weight="bold")
    yy += 0.2
    for (k, w, _f), x in zip(cols, xs):
        F.put(fig, x, yy, w, 0.6, size=6.6, weight="bold", color=F.INK)
    yy += 0.2
    fig.add_artist(F.Line2D([0.5 / 8.5, 8.0 / 8.5], [1 - yy / 11] * 2, color=F.INK, lw=0.6))
    yy += 0.05
    hl = {"m7"}
    for grp in ["Control", "PTEN IED\u2212", "PTEN IED+"]:
        sub = C[C.group == grp].sort_values(["knockout_pct", "mouse"])
        F.put(fig, 0.55, yy, grp, 2, size=6.6, weight="bold", color={"Control": F.SOFT, "PTEN IED\u2212": "#b5508a",
                                                                       "PTEN IED+": F.C_POS}[grp])
        yy += 0.17
        for _i, r in sub.iterrows():
            if r["mouse"] in hl:
                fig.add_artist(patches.Rectangle((0.5 / 8.5, 1 - (yy + 0.15) / 11), 7.5 / 8.5, 0.16 / 11, facecolor="#fbe8f2",
                                                 edgecolor="none", transform=fig.transFigure, zorder=0))
            for (k, _w, f), x in zip(cols, xs):
                F.put(fig, x, yy, f.format(r[k]), 0.6, size=6.4)
            yy += 0.16
        t = tot.loc[grp]
        vals = {"mouse": "total", "knockout_pct": np.nan, "minutes": mins[grp], "DS": t.DS, "BT": t.BT, "IED_class": t.IED_class,
                "outside_both_halos": t.outside_both_halos, "DS_per_min": t.DS / mins[grp], "BT_per_min": t.BT / mins[grp],
                "IED_per_min": t.IED_class / mins[grp], "strict_DS": t.strict_DS, "strict_IED_class": t.strict_IED_class,
                "strict_undecided": t.strict_undecided}
        for (k, _w, f), x in zip(cols, xs):
            v = vals[k]
            s_ = "" if (isinstance(v, float) and np.isnan(v)) else f.format(int(v) if (f == "{}" and not isinstance(v, str)) else v)
            F.put(fig, x, yy, s_, 0.6, size=6.4, weight="bold")
        yy += 0.2
        fig.add_artist(F.Line2D([0.5 / 8.5, 8.0 / 8.5], [1 - (yy - 0.03) / 11] * 2, color=F.GRID, lw=0.6))
        yy += 0.04
    allt = C[["minutes", "DS", "BT", "IED_class", "outside_both_halos", "strict_DS", "strict_IED_class", "strict_undecided"]].sum()
    vals = {"mouse": "all 16", "knockout_pct": np.nan, "minutes": allt.minutes, "DS": allt.DS, "BT": allt.BT,
            "IED_class": allt.IED_class, "outside_both_halos": allt.outside_both_halos, "DS_per_min": allt.DS / allt.minutes,
            "BT_per_min": allt.BT / allt.minutes, "IED_per_min": allt.IED_class / allt.minutes, "strict_DS": allt.strict_DS,
            "strict_IED_class": allt.strict_IED_class, "strict_undecided": allt.strict_undecided}
    for (k, _w, f), x in zip(cols, xs):
        v = vals[k]
        s_ = "" if (isinstance(v, float) and np.isnan(v)) else f.format(int(v) if (f == "{}" and not isinstance(v, str)) else v)
        F.put(fig, x, yy, s_, 0.6, size=6.4, weight="bold")
    yy += 0.35
    textcol(fig, yy, [
        ("What the columns are", "Halo set = the Root Canal Halo workflow, the set every menu page used. DS, BT (borderline "
         "transients, the Twilight Zone class in Jarvis) and IED (the IED-class, red events) are its three classes; 'Outside' "
         "is events beyond both halos, left unclassed. Per minute divides by the length of the one baseline recording each "
         "mouse has. Strict set = the appendix's Strict workflow (no halo): DS, IED class, and undecided (inside both borders "
         "plus outside both). One recording per mouse; m6 is left out."),
        ("Reading", "BTs and IED-class events are almost all in the five IED+ mice. A control or IED\u2212 mouse has at most a "
         "handful (m26 has 1 IED-class event, m1 1). m7 (highlighted, 24%% knockout without IEDs) has none "
         "of either. DS rates vary widely within every group (%.1f to %.1f per minute), so per-minute rates are the fairer "
         "comparison across mice." % (C.DS_per_min.min(), C.DS_per_min.max())),
    ], x=0.5, w=7.5)
    save(fig, "02_counts_per_mouse_and_group")
    G = C.groupby("group", sort=False).agg(mice=("mouse", "count"), minutes=("minutes", "sum"), DS=("DS", "sum"), BT=("BT", "sum"),
                                           IED_class=("IED_class", "sum"), outside_both_halos=("outside_both_halos", "sum"),
                                           strict_DS=("strict_DS", "sum"), strict_IED_class=("strict_IED_class", "sum"),
                                           strict_undecided=("strict_undecided", "sum")).reset_index()
    for k in ("DS", "BT", "IED_class"):
        G[k + "_per_min"] = G[k] / G.minutes
    return G


# ---------------------------------------------------------------- page 3: when the power is measured
WINDOWS = [  # (label, used in, [(start, end, kind)]) ; kind: "event", "base", "search"
    ("Fast power, 240–420 Hz (Root Canal)", "Story 1; questions 1, 6, 7; the classes",
     [(-170, -130, "base"), (-25, 25, "event")]),
    ("Amplitude and half-width (Root Canal)", "the classes; question 7",
     [(-75, 75, "search"), (-33, 33, "event")]),
    ("Fast-power center and gain (2 kHz reads)", "questions 4, 5, 7, 8",
     [(-100, -50, "base"), (-25, 25, "event")]),
    ("Dominant frequency (2 kHz reads)", "questions 4, 5", [(-50, 50, "event")]),
    ("Sink at the DS peak (CSD)", "questions 1, 3, 7, 8", [(-3, 3, "event")]),
]


def envelopes():
    """Per mouse and class: mean 240-420 Hz power (dB over -100 to -50 ms) on each event's best contact, from the 2 kHz reads."""
    from scipy.signal import butter, sosfiltfilt
    out = {}
    # reads_ds holds the DS of the eleven non-IED+ mice; reads holds every class of the IED+ mice and the few BT/IED
    # events of the others. Take each mouse's DS from reads_ds when it is there, everything else from reads.
    todo = [(l, os.path.join(HERE, d, l + ".npz")) for l in LABS for d in ("reads_ds", "reads")]
    for l, f in todo:
        if not os.path.exists(f):
            continue
        z = np.load(f, allow_pickle=True)
        fs = float(z["fs"])
        X = z["notch"].astype(np.float64)
        t = (np.arange(X.shape[2]) - X.shape[2] // 2) / fs * 1000.0
        good = np.array([i for i in range(X.shape[1]) if (i + 1) not in set(int(b) for b in z["bad"])])
        sos = butter(3, [240, 420], btype="band", fs=fs, output="sos")
        Y = sosfiltfilt(sos, X[:, good], axis=-1) ** 2
        k = int(round(0.005 * fs))
        Y = np.apply_along_axis(lambda v: np.convolve(v, np.ones(k) / k, mode="same"), -1, Y)
        ev, bl = np.abs(t) <= 25, (t >= -100) & (t <= -50)
        base = Y[..., bl].mean(-1)
        ratio = Y[..., ev].mean(-1) / base
        best = np.nanargmax(ratio, axis=1)
        D = 10 * np.log10(Y[np.arange(Y.shape[0]), best] / base[np.arange(Y.shape[0]), best][:, None])
        for c in ("DS", "TZ", "IED"):
            m = z["kind"] == c
            if m.sum() >= 3 and (l, c) not in out:
                out[(l, c)] = D[m].mean(0)
    return t, out


def page_window():
    t, E = envelopes()
    offs = np.concatenate([np.load(f, allow_pickle=True)["offset_ms"] for f in glob.glob(os.path.join(HERE, "reads*", "m*.npz"))])
    med_off, p90 = np.median(np.abs(offs)), np.percentile(np.abs(offs), 90)
    fig, y = header(3, "For Jeremy menu story 1... we need to know what the time window of when the power was measured. "
                       "For example before, after, the DS, how relative to the peak, what time window etc.",
                    "Fast power is measured during the DS, not before or after it: the 50 ms centered on the DS peak "
                    "(−25 to +25 ms), against a quiet 40 ms on the same contact that ends 130 ms before the peak, "
                    "and reported in dB.")
    F.letter(fig, 0.4, y + 0.08, "a", "Every window the menu uses, on one clock: 0 is the DS peak", width=7.6)
    # the mean DS of one IED+ mouse, deepest contact, as the clock's picture
    z = np.load(os.path.join(HERE, "reads", "m13.npz"), allow_pickle=True)
    tt = (np.arange(z["notch"].shape[2]) - z["notch"].shape[2] // 2) / float(z["fs"]) * 1000.0
    mds = z["band"][z["kind"] == "DS"].mean(0)
    deep = int(np.argmin(mds[:, np.argmin(np.abs(tt))]))
    tr = mds[deep] / np.abs(mds[deep]).max()
    a = F.axes_in(fig, 2.9, y + 0.45, 4.9, 0.75)
    a.plot(tt, tr, color=F.C_DS, lw=1.2)
    a.plot([-200, -100], [0, 0], color=F.FAINT, lw=0.8, ls=":")
    a.text(-150, 0.12, "not stored in the\n2 kHz reads", fontsize=5.2, color=F.FAINT, ha="center", va="bottom")
    a.axvline(0, color=F.INK, lw=0.6, ls="--")
    a.set_xlim(-200, 105)
    a.set_yticks([])
    a.spines["left"].set_visible(False)
    a.set_xticks([])
    a.spines["bottom"].set_visible(False)
    a.text(2, 0.95, "DS peak", fontsize=5.6, color=F.INK, va="top")
    F.put(fig, 0.5, y + 0.6, "The mean DS of one IED+ mouse (m13), deepest sink contact", 2.3, size=6.0, color=F.SOFT)
    g = F.axes_in(fig, 2.9, y + 1.5, 4.9, 0.32 * len(WINDOWS))
    colors = {"event": F.C_IED, "base": F.SOFT, "search": "#e6e8ec"}
    for i, (lab, used, ws) in enumerate(WINDOWS):
        for s0, s1, kind in ws:
            g.add_patch(patches.Rectangle((s0, i - 0.32), s1 - s0, 0.64, facecolor=colors[kind],
                                          alpha=0.9 if kind != "search" else 1.0, edgecolor="none"))
            if kind != "search":
                g.text(s1 + 2, i, "%+d to %+d" % (s0, s1) if s0 != -s1 else "±%d" % s1, fontsize=5.0,
                       ha="left", va="center", color=F.INK,
                       bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.85))
        F.put(fig, 0.5, y + 1.5 + 0.32 * i + 0.04, lab, 2.35, size=6.2, weight="bold")
        F.put(fig, 0.5, y + 1.5 + 0.32 * i + 0.17, used, 2.35, size=5.6, color=F.SOFT)
    g.axvline(0, color=F.INK, lw=0.6, ls="--")
    g.set_xlim(-200, 105)
    g.set_ylim(len(WINDOWS) - 0.4, -0.6)
    g.set_yticks([])
    g.spines["left"].set_visible(False)
    g.set_xlabel("Time from the DS peak (ms)", fontsize=6.4)
    hs = [patches.Patch(color=F.C_IED, label="measured (event)"), patches.Patch(color=F.SOFT, label="baseline (same contact)"),
          patches.Patch(color="#e6e8ec", label="search range (half-width)")]
    g.legend(handles=hs, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=3, frameon=False, fontsize=5.6, handlelength=1.2)
    yb = y + 1.5 + 0.32 * len(WINDOWS) + 0.6
    F.letter(fig, 0.4, yb + 0.08, "b", "In time, the 240–420 Hz power rises and falls inside the ±25 ms window; it is "
             "largest for the IED+ mice's BTs and IED-class events", width=7.6)
    b = F.axes_in(fig, 0.95, yb + 0.5, 3.2, 2.0)
    curves = [("Control DS", [E[(l, "DS")] for l in CTL if (l, "DS") in E], F.C_CTL, "-"),
              ("IED− DS", [E[(l, "DS")] for l in PT if F.subgroup(l) == "IED-" and (l, "DS") in E], F.C_NEG, "-"),
              ("IED+ DS", [E[(l, "DS")] for l in J.IEDP if (l, "DS") in E], F.C_DS, "-"),
              ("IED+ BT", [E[(l, "TZ")] for l in J.IEDP if (l, "TZ") in E], F.C_PDS, "-"),
              ("IED+ IED class", [E[(l, "IED")] for l in J.IEDP if (l, "IED") in E], F.C_IED, "-")]
    b.axvspan(-25, 25, color=F.C_IED, alpha=0.08, lw=0)
    b.axvspan(-100, -50, color=F.SOFT, alpha=0.12, lw=0)
    for name, cs, col, ls in curves:
        M = np.array(cs)
        mu = M.mean(0)
        se = M.std(0, ddof=1) / np.sqrt(len(M)) if len(M) > 1 else np.zeros_like(mu)
        b.fill_between(t, mu - se, mu + se, color=col, alpha=0.18, lw=0)
        b.plot(t, mu, color=col, lw=1.2, ls=ls, label="%s (%d mice)" % (name, len(M)) if len(M) > 1 else "%s (1 mouse)" % name)
    b.axhline(0, color=F.FAINT, lw=0.5)
    b.axvline(0, color=F.INK, lw=0.5, ls="--")
    b.set_xlim(-100, 100)
    b.set_xlabel("Time from the DS peak (ms)")
    b.set_ylabel("240–420 Hz power\n(dB over −100 to −50 ms)")
    b.legend(frameon=False, fontsize=5.6, loc="upper right")
    b.text(0, b.get_ylim()[1], "measured", fontsize=5.4, color=F.C_IED, ha="center", va="bottom")
    b.text(-75, b.get_ylim()[1], "baseline here", fontsize=5.4, color=F.SOFT, ha="center", va="bottom")
    F.put(fig, 4.55, yb + 0.55, "Mean of each mouse's events, then of the mice (band: s.e.m. across mice). Each event is "
          "taken on its own best contact (the contact where the ±25 ms window rises most), as Root Canal does. These "
          "curves use the 2 kHz reads, whose window stops at −100 ms, so their baseline is −100 to −50 ms; "
          "Root Canal's own number uses −170 to −130 ms from a 5 kHz read. The shape in time is the point here, "
          "not the exact dB.", 3.3, size=6.3)
    textcol(fig, yb + 2.95, [
        ("How Story 1's fast power is made, step by step", "1. Time zero is the event's stamp, which sits on the DS peak "
         "(median %.1f ms from the peak the 2 kHz reader finds; 90%% within %.1f ms). 2. The recording is read at 5 kHz "
         "around every event. 3. On every good contact, two windows are cut: the event, −25 to +25 ms, and the "
         "baseline, −170 to −130 ms (40 ms centered 150 ms before the peak). 4. Each window's power spectrum "
         "(Welch) is summed over 240–420 Hz. 5. The number is 10·log10(event / baseline) in dB, so every contact is "
         "compared with itself a moment earlier. 6. The event keeps its largest value across contacts. A mouse's value in "
         "Story 1 is the median over its DS." % (med_off, p90)),
        ("So, before, during or after?", "During. Nothing after the DS (beyond +25 ms) enters the number, and the time before "
         "it is used only as the quiet reference. The band and windows are fixed settings of the Root Canal workflow "
         "(Optimized Parameters/Snap), the same for every mouse and class. Questions 4, 5, 7 and 8 use the same ±25 ms "
         "event window on the 2 kHz reads, with the closer baseline shown in panel a."),
    ], x=0.5, w=7.5)
    save(fig, "03_when_fast_power_is_measured")
    return pd.DataFrame([{"measure": lab, "used_in": used, "windows_ms": "; ".join("%s %+d to %+d" % (k, s0, s1) for s0, s1, k in ws)}
                         for lab, used, ws in WINDOWS])


# ---------------------------------------------------------------- page 4: how the layers are defined
C_MML, C_OML = "#fbeadb", "#f6d3b8"
SPANS = {"MML": (0.7, 1.3), "OML": (1.3, 2.0)}


def layer_rows(k, blade, lo, hi):
    """Row range (fractional) of a v span on one blade."""
    if blade == "upper":
        d = k["GU"] - k["U"]
        return k["GU"] - hi * d, k["GU"] - lo * d
    d = k["L"] - k["GL"]
    return k["GL"] + lo * d, k["GL"] + hi * d


def profile_rows(r):
    k = r["landmarks"]
    UG = J.UP()["UGRID"] if "UGRID" in J.UP() else None
    rows = k["U"] + np.asarray(UG) * (k["L"] - k["U"])
    return rows, np.asarray(r["u_peak"], float)


def draw_profile(ax, r, big=False):
    k = r["landmarks"]
    rows, prof = profile_rows(r)
    for blade in ("upper", "lower"):
        for nm, (lo, hi) in SPANS.items():
            a0, a1 = layer_rows(k, blade, lo, hi)
            ax.axhspan(a0, a1, color=C_MML if nm == "MML" else C_OML, lw=0, zorder=0)
            if big:
                ax.text(1.02, (a0 + a1) / 2, "%s %s" % ("Upper" if blade == "upper" else "Lower", nm), transform=ax.get_yaxis_transform(),
                        fontsize=6.0, va="center", ha="left", color=F.INK)
    ok = np.isfinite(prof)
    ax.plot(prof[ok], rows[ok], color=F.INK, lw=1.0 if big else 0.7)
    ax.axvline(0, color=F.FAINT, lw=0.5)
    for key, col, word in (("U", F.C_DS, "upper sink (v = 1)"), ("L", F.C_DS, "lower sink (v = 1)"),
                           ("GU", "#c0392b", "cell-layer source (v = 0)"), ("GL", "#c0392b", "")):
        ax.axhline(k[key], color=col, lw=0.6 if big else 0.4, ls="--")
        if big and word and not (key == "GL" and abs(k["GL"] - k["GU"]) < 0.5):
            ax.text(-1.55, k[key] - 0.3, word, fontsize=5.6, color=col, va="bottom", ha="left")
    lo_r = layer_rows(k, "upper", 0, 2.0)[0] - 2
    hi_r = layer_rows(k, "lower", 0, 2.0)[1] + 2
    ax.set_ylim(min(hi_r, 64), max(lo_r, -1))
    ax.set_xlim(-1.6, 1.3)


def page_layers():
    UP = J.UP()
    recs = {l: UP["recs"][("v6", l)] for l in LABS if ("v6", l) in UP["recs"]}
    fig, y = header(4, "For these instances add to the supplemental how upper MML, and all these different regions were "
                       "determined. Along with illustrative figures",
                    "The layers come from each recording's own dentate spike, not from hand labels: on the mean CSD at the DS "
                    "peak, each blade runs from its cell-layer source (0) to its main sink (1); the MML spans 0.7 to 1.3 of that "
                    "distance and the OML 1.3 to 2.0.")
    F.letter(fig, 0.4, y + 0.08, "a", "One recording (m13): find the two sinks and the source between them, then measure each "
             "blade in its own units", width=7.6)
    r = recs["m13"]
    a = F.axes_in(fig, 0.95, y + 0.45, 1.9, 2.4)
    draw_profile(a, r, big=True)
    a.set_xlabel("CSD at the DS peak\n(−1 = this mouse's deepest sink)", fontsize=6.3)
    a.set_ylabel("Contact (top of the probe = 0)", fontsize=6.3)
    a.text(-1.5, a.get_ylim()[1] + 0.5, "sink ←", fontsize=5.6, color=F.C_DS, va="top")
    a.text(1.25, a.get_ylim()[1] + 0.5, "→ source", fontsize=5.6, color="#c0392b", va="top", ha="right")
    # the v axis, drawn as two mirrored rulers
    b = F.axes_in(fig, 4.4, y + 0.45, 1.1, 2.4)
    k = r["landmarks"]
    for blade, x0 in (("upper", 0.0), ("lower", 0.0)):
        for v in np.arange(0, 2.01, 0.5):
            rr = layer_rows(k, blade, v, v)[0]
            b.plot([0.35, 0.55], [rr, rr], color=F.INK, lw=0.6)
            b.text(0.6, rr, "v = %g" % v, fontsize=5.6, va="center")
    b.plot([0.45, 0.45], [layer_rows(k, "upper", 2.0, 2.0)[0], layer_rows(k, "lower", 2.0, 2.0)[0]], color=F.INK, lw=0.6)
    b.set_ylim(a.get_ylim())
    b.set_xlim(0, 1.6)
    b.axis("off")
    F.put(fig, 5.65, y + 0.6, "How v is set, per recording and per blade", 2.4, size=6.6, weight="bold")
    F.put(fig, 5.65, y + 0.82, "1. Average every DS's CSD over ±3 ms around its peak, contact by contact (bad contacts filled "
          "from their neighbors).\n2. The two deepest sinks, one on each side of the hilus, are the blades' main sinks (sub-contact "
          "position: the centroid of the sink's lobe).\n3. Between them, the source next to each sink is that blade's "
          "cell-layer side (v = 0); with one source in the hilus both blades share it, as here.\n4. v counts outward from that "
          "source in units of the source-to-sink distance: 1 is the sink, 2 is as far again beyond it.\n5. MML = v 0.7 to 1.3 "
          "(around the sink); OML = v 1.3 to 2.0 (beyond it). A layer's value is the CSD averaged over the contacts in that "
          "span.", 2.45, size=6.2)
    yb = y + 3.3
    F.letter(fig, 0.4, yb + 0.08, "b", "The same rule on all 16 recordings: the spans follow each probe's track and each "
             "mouse's blade size", width=7.6)
    for i, l in enumerate(LABS):
        col, row = i % 8, i // 8
        ax = F.axes_in(fig, 0.6 + col * 0.95, yb + 0.5 + row * 1.45, 0.72, 1.05)
        draw_profile(ax, recs[l])
        ax.set_xticks([])
        ax.tick_params(labelsize=5.0)
        ax.set_title(l, fontsize=6.3, color=F.color_of(l) if F.subgroup(l) != "IED-" else "#b5508a", pad=2)
        if col:
            ax.set_yticklabels([])
    hs = [patches.Patch(color=C_MML, label="MML (v 0.7–1.3)"), patches.Patch(color=C_OML, label="OML (v 1.3–2.0)"),
          F.Line2D([], [], color=F.C_DS, ls="--", lw=0.8, label="main sinks"),
          F.Line2D([], [], color="#c0392b", ls="--", lw=0.8, label="cell-layer source(s)")]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.6 / 8.5, 1 - (yb + 3.4) / 11), ncol=4, frameon=False, fontsize=6.0)
    textcol(fig, yb + 3.7, [
        ("Why not the lab's layer labels", "Hand labels put the boundaries where the histology or the eye placed them, and "
         "they differ between people and recordings. Measured from the DS itself, every recording is cut by the same rule, and "
         "the cut moves with the probe's track and the mouse's anatomy. 'Upper' and 'lower' are the two blades on either side "
         "of the hilus along the probe (upper = the one nearer CA1)."),
        ("What this means for reading the layer panels", "The MML span is centered on each blade's main DS sink by "
         "construction, so it is where the DS current is largest; the OML span is the stretch beyond it, toward the "
         "hippocampal fissure (upper blade) or the far edge of the lower blade. In the layer figures, depth runs on the "
         "vertical axis with 0 at the cell layer and 1 at the sink, mirrored for the two blades. The spans are fixed fractions of "
         "each blade's own source-to-sink distance, not histological boundaries."),
    ], x=0.5, w=7.5)
    save(fig, "04_how_the_layers_are_defined")


if __name__ == "__main__":
    os.makedirs(os.path.join(DEST, "tables"), exist_ok=True)
    page_layers()
    page_window().to_csv(os.path.join(DEST, "tables", "measurement_windows.csv"), index=False)
    allcalls, calls, mean = page_heldout()
    allcalls.to_csv(os.path.join(DEST, "tables", "held_out_calls_every_model_r006.csv"), index=False)
    pd.DataFrame([{"mouse": l, "truth": F.subgroup(l), "held_out_call_mean": mean[l], "models": len(calls),
                   **{"%s/%s" % k: calls[k][l] for k in calls}} for l in PT]).to_csv(
        os.path.join(DEST, "tables", "held_out_calls_ied_models_at_bar.csv"), index=False)
    C = counts()
    C.to_csv(os.path.join(DEST, "tables", "counts_per_mouse.csv"), index=False)
    page_counts(C).to_csv(os.path.join(DEST, "tables", "counts_per_group.csv"), index=False)
    print(C[["mouse", "group", "DS", "BT", "IED_class", "outside_both_halos", "strict_DS", "strict_IED_class", "strict_undecided"]])
    print({l: round(v, 2) for l, v in mean.items()})
