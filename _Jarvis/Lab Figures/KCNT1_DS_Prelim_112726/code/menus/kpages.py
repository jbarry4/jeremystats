"""KCNT1 preliminary dentate spike menu (2026-11-27): Jeremy's eight questions asked of 2 WT, 2 Het and 2 Hom KCNT1
(Y796H) mice, with gene dose (mutant alleles: WT 0, Het 1, Hom 2) in place of % knockout. Each page: kicker, the
question, "Results show", then panels whose headings state the finding. The Jeremy menu's format (PTEN, 2026-11-24).

  python kpages.py            (reads kresults.pkl, rc_events.csv, tight_layers.json, profiles_ds.pkl beside it,
                               and ../battery/data/meta.json; writes pages/ and the merged PDF in OUT)
"""
import json
import os
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from scipy import stats as st

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("KBAT", os.path.join(HERE, "..", "battery"))
import figlib as F  # noqa: E402

OUT = os.environ.get("KOUT", os.path.join(HERE, "out"))
PAGES = os.path.join(OUT, "pages")
DATE = "2026-11-27"
R = pickle.load(open(os.path.join(HERE, "kresults.pkl"), "rb"))
RC = pd.read_csv(os.path.join(HERE, "rc_events.csv"))
TL = json.load(open(os.path.join(HERE, "tight_layers.json"), encoding="utf-8"))
PROF = pickle.load(open(os.path.join(HERE, "profiles_ds.pkl"), "rb"))
IDS = json.load(open(os.path.join(HERE, "..", "k1_ids.json")))
LABS = R["labs"]
GENO, DOSE, SEX = R["geno"], R["dose"], R["sex"]
GCOL = {"WT": "#8c8c8c", "Het": "#f2a25c", "Hom": "#b2401a"}
WTL = [l for l in LABS if GENO[l] == "WT"]
HOML = [l for l in LABS if GENO[l] == "Hom"]
BANDS = ["notch", "1-100", "1-300", "5-300", "5-100", "5-50", "10-40"]
BAND_WORD = {"notch": "open (60 Hz notch only)", "1-100": "1-100", "1-300": "1-300", "5-300": "5-300", "5-100": "5-100 (main)",
             "5-50": "5-50", "10-40": "10-40"}
BSET = {"notch": "b_none", "1-100": "b_1_100", "1-300": "b_1_300", "5-300": "b_5_300", "5-100": "b_ds", "5-50": "b_5_50",
        "10-40": "b_10_40"}
LAYW = {"uMML": "Upper MML", "uOML": "Upper OML", "lMML": "Lower MML", "lOML": "Lower OML"}
QUESTIONS = {
    1: "Does the gene dose cause changes in synaptic efficacy for dentate spikes",
    2: "Are there group differences in DS1 vs DS2 (do they make both)",
    3: "Are there differences in CSD sink for MML/OML by blade in KCNT1 animals by gene dose",
    4: "Are there differences in dominant frequency for MML/OML by blade in KCNT1 animals by gene dose",
    5: "Do results of 3 and 4 change when you open filters",
    6: "Can you predict which mice made the abnormal dentate spikes based on genotype",
    7: "As in 3 or 4, do the results change when you sort the dentate spikes by where they fall in the continuum (does a "
       "mutant mouse's borderline event carry as much current or fast power as one of its own dentate spikes? More than a "
       "WT dentate spike?)",
    8: "Do the results of 7 change when you open the filter",
}


# ============================================================================ numbers
def T(key):
    return R["t"].get(key, {})


def V(key):
    return (R["m"].get(key) or {}).get("values", {})


def dp(key):
    return T(key).get("dose", {}).get("p", np.nan)


def drho(key):
    return T(key).get("dose", {}).get("rho", np.nan)


def hp(key):
    return T(key).get("wt_hom", {}).get("p", np.nan)


def hr(key):
    return T(key).get("wt_hom", {}).get("ratio", np.nan)


def pw(p):
    return F.pnum(p)


def mean_of(vals, labs):
    x = [vals.get(l, np.nan) for l in labs]
    x = [v for v in x if np.isfinite(v)]
    return float(np.mean(x)) if x else np.nan


# ============================================================================ page frame
_PAGE = [0]


def kpage(num, results, kicker=None):
    fig = F.plt.figure(figsize=(8.5, 11))
    _PAGE[0] += 1
    F.put(fig, 0.5, 0.42, kicker or ("KCNT1 MENU · QUESTION %d" % num), 7.5, size=7, color=GCOL["Hom"], weight="bold")
    y = 0.62
    if num in QUESTIONS:
        y += F.put(fig, 0.5, y, "Jeremy Asked (PTEN wording, %% KO read as gene dose): “%s”" % QUESTIONS[num], 7.5,
                   size=8.6, color=F.SOFT, style="italic") + 0.06
    if results:
        y += F.put(fig, 0.5, y, "Results show: " + results, 7.5, size=12, weight="bold")
    fig.text(1 - 0.5 / 8.5, 1 - 10.72 / 11, "%d" % _PAGE[0], fontsize=6.5, color=F.FAINT, ha="right", va="bottom")
    fig.text(0.5 / 8.5, 1 - 10.72 / 11, "KCNT1 dentate spike menu · PRELIMINARY, 2 WT / 2 Het / 2 Hom · exploratory, P values "
             "uncorrected · %s" % DATE, fontsize=6.5, color=F.FAINT, ha="left", va="bottom")
    return fig, y + 0.14


def textcol(fig, y, blocks, x=0.5, w=7.5, size=6.6):
    for head, body in blocks:
        if head:
            y += F.put(fig, x, y, head, w, size=7.2, weight="bold") + 0.03
        y += F.put(fig, x, y, body, w, size=size, color=F.INK) + 0.12
    return y


def save(fig, name):
    os.makedirs(PAGES, exist_ok=True)
    fig.savefig(os.path.join(PAGES, name + ".png"), dpi=200)
    fig.savefig(os.path.join(PAGES, name + ".pdf"))
    F.plt.close(fig)
    print("page", _PAGE[0], name, flush=True)


def legend_geno(fig, x, y):
    W, H = fig.get_size_inches()
    hs = [Line2D([], [], ls="", marker="o", ms=5, mfc=GCOL[g], mec="white", label=lab)
          for g, lab in (("WT", "WT (dose 0)"), ("Het", "Het (dose 1)"), ("Hom", "Hom (dose 2)"))]
    fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(x / W, 1 - y / H), ncol=3, frameon=False, fontsize=6.3,
               handletextpad=0.3, columnspacing=1.2)


OFF = {"m1619": -0.09, "m526": 0.09, "m1609": -0.09, "m576": 0.09, "m1603": -0.09, "m306": 0.09}


def dose_ax(fig, x, y, w, h, key=None, values=None, ylabel="", title=None, log=False, names=True, hline=None, stat=True):
    """One dot per mouse at its gene dose; a short line at each genotype's mean; the dose test and WT against Hom."""
    a = F.axes_in(fig, x, y, w, h)
    v = values if values is not None else V(key)
    if log:
        a.set_yscale("log")
    for g, d in (("WT", 0), ("Het", 1), ("Hom", 2)):
        vs = [v.get(l, np.nan) for l in LABS if GENO[l] == g]
        vs = [q for q in vs if np.isfinite(q)]
        if vs:
            a.plot([d - 0.22, d + 0.22], [np.mean(vs)] * 2, color=F.INK, lw=1.0, zorder=2)
    for l in LABS:
        q = v.get(l, np.nan)
        if not np.isfinite(q):
            continue
        a.scatter([DOSE[l] + OFF[l]], [q], s=24, color=GCOL[GENO[l]], edgecolor="white", lw=0.5, zorder=4)
        if names:
            a.annotate(l, (DOSE[l] + OFF[l], q), xytext=(3 if OFF[l] > 0 else -3, 0), textcoords="offset points",
                       ha="left" if OFF[l] > 0 else "right", va="center", fontsize=4.8, color=F.SOFT)
    if hline is not None:
        a.axhline(hline, color=F.FAINT, lw=0.6, ls=":", zorder=0)
    a.set_xticks([0, 1, 2])
    a.set_xticklabels(["WT", "Het", "Hom"])
    a.set_xlim(-0.75, 2.75)
    a.tick_params(axis="x", length=0)
    a.set_ylabel(ylabel, fontsize=6.2)
    if stat and key is not None:
        t = T(key)
        d, w_ = t.get("dose", {}), t.get("wt_hom", {})
        rt = w_.get("ratio", np.nan)
        s = "dose ρ %+.2f, P %s\nHom/WT %s, P %s" % (d.get("rho", np.nan), pw(d.get("p", np.nan)),
                                                  ("×%.2f" % rt) if np.isfinite(rt) else "(WT all 0)", pw(w_.get("p", np.nan)))
        a.set_title(((title + "\n") if title else "") + s, fontsize=5.6, color=F.SOFT, loc="left", pad=3)
    elif title:
        a.set_title(title, fontsize=6.0, loc="left", color=F.INK, pad=3)
    return a


# ============================================================================ the numbers each page states
K = {}
K["sink"], K["out"] = "q1|sink|v6", "q1|out"
K["slope"] = "q1|slope|v6"
q3keys = ["q3|tight|v6|%s" % k for k in ("uMML", "uOML", "lMML", "lOML")]
q3old = ["q3|old|v6|%s" % k for k in ("uMML", "uOML", "lMML", "lOML")]
q4dom = ["q4|dom|tight|notch|DS|%s" % k for k in ("uMML", "uOML", "lMML", "lOML")]
q4cen = ["q4|cen|tight|notch|DS|%s" % k for k in ("uMML", "uOML", "lMML", "lOML")]
q4gain = ["q4|gain|tight|notch|DS|%s" % k for k in ("uMML", "uOML", "lMML", "lOML")]
n_sig = lambda keys: sum(1 for k in keys if dp(k) < 0.05 or hp(k) < 0.05)  # noqa: E731


def auc(score, positive):
    pos = [score[l] for l in LABS if positive[l]]
    neg = [score[l] for l in LABS if not positive[l]]
    if not pos or not neg:
        return np.nan
    s = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return s / (len(pos) * len(neg))


bt = V("bt_rate")
wt_max_bt = max(bt[l] for l in WTL)
abnormal = {l: bt[l] > wt_max_bt for l in LABS}
AUC_DOSE = auc(DOSE, abnormal)
AUC_HF = auc(V("rc_hf_ds"), abnormal)


def q7_rows(band, kk):
    return [r for r in R["q7"][(band, kk)] if r["n_bt"] >= 5]


def q7_stats(band, kk, what):
    """BT over the same mouse's DS (ratio for sinks; dB difference for fast gain), the mice with 5 BTs or more read."""
    rows = q7_rows(band, kk)
    if what == "sink":
        x = np.array([r["sink_TZ"] / r["sink_DS"] if r["sink_DS"] > 0 else np.nan for r in rows])
        a, b = np.array([r["sink_DS"] for r in rows]), np.array([r["sink_TZ"] for r in rows])
    else:
        x = np.array([r["gain_TZ"] - r["gain_DS"] for r in rows])
        a, b = np.array([r["gain_DS"] for r in rows]), np.array([r["gain_TZ"] for r in rows])
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return {"n": int(ok.sum()), "p": np.nan, "x": x, "labs": [r["lab"] for r in rows]}
    ps = {}
    try:
        ps["paired t"] = float(st.ttest_rel(b[ok], a[ok]).pvalue)
    except Exception:  # noqa: BLE001
        pass
    try:
        ps["Wilcoxon"] = float(st.wilcoxon(b[ok], a[ok]).pvalue)
    except Exception:  # noqa: BLE001
        pass
    ps = {k_: p for k_, p in ps.items() if np.isfinite(p)}
    k_ = min(ps, key=ps.get) if ps else None
    return {"n": int(ok.sum()), "p": ps.get(k_, np.nan), "test": k_, "x": x, "labs": [r["lab"] for r in rows],
            "up": int((b[ok] > a[ok]).sum())}


# ============================================================================ pages
def cover():
    fig, y = kpage(0, "", kicker="KCNT1 DENTATE SPIKE MENU · PRELIMINARY RUN · %s" % DATE)
    y = 0.62
    y += F.put(fig, 0.5, y, "KCNT1 (Y796H) dentate spikes, by gene dose: a first pass on six mice", 7.5, size=15, weight="bold")
    y += 0.08
    y += F.put(fig, 0.5, y, "The PTEN pipeline (Lock → Root Canal → X-ray → Extraction Room → freeze → battery → "
               "menu) run end to end on 2 WT, 2 Het and 2 Hom mice, to show that every step works on KCNT1 and what the first "
               "numbers look like. With two mice a genotype no result here is a finding: the smallest P a two-against-two "
               "rank test can give is 0.33, and a gene-dose trend over six mice is easily moved by one mouse.", 7.5,
               size=7.4, color=F.INK) + 0.16
    # the mice
    W, H = fig.get_size_inches()
    cols = ["Mouse", "Genotype", "Sex", "Recording", "Minutes", "Lock events", "Halo DS", "BT", "IED class", "Strict DS"]
    xs = [0.5, 1.05, 1.65, 2.05, 3.55, 4.1, 4.8, 5.4, 5.8, 6.45]
    for c, x in zip(cols, xs):
        fig.text(x / W, 1 - y / H, c, fontsize=6.4, weight="bold", va="top")
    y += 0.17
    lock_n = {"m1619": 168, "m526": 802, "m1609": 811, "m576": 538, "m1603": 146, "m306": 534}
    for l in LABS:
        m = R["meta"][l]
        c, s = R["counts"][("halo", l)], R["counts"][("strict", l)]
        row = [l, GENO[l], SEX[l], m["label"].replace("KCNT1 ", ""), "%.0f" % m["dur_min"], "%d" % lock_n[l],
               "%d" % c["DS"], "%d" % c["BT"], "%d" % c["IED"], "%d" % s["DS"]]
        for v, x in zip(row, xs):
            fig.text(x / W, 1 - y / H, v, fontsize=6.3, va="top", color=GCOL[GENO[l]] if v == GENO[l] else F.INK)
        y += 0.15
    y += 0.12
    y += F.put(fig, 0.5, y, "The questions, and the one-line answers", 7.5, size=9, weight="bold") + 0.05
    for q, ans in ANSWERS.items():
        y += F.put(fig, 0.5, y, "%d  %s" % (q, QUESTIONS[q]), 7.5, size=6.6,
                   color=F.SOFT, style="italic")
        y += F.put(fig, 0.72, y, ans, 7.28, size=7.0, weight="bold") + 0.07
    y += 0.08
    textcol(fig, y, [
        ("Words and marks", "Gene dose = mutant alleles (WT 0, Het 1, Hom 2). DS = dentate spike. BT = borderline transient (the "
                            "in-between class, “Twilight Zone” in Jarvis). IED class = events inside the P-spike (IED) "
                            "border or its halo. Halo set (main) and Strict set (check), as for PTEN. MML / OML = middle and "
                            "outer molecular layer, found from each recording's own DS, never from layer labels. Each panel "
                            "gives the gene-dose test (Spearman ρ, exact over all 720 orderings, or Kendall or Pearson, "
                            "whichever P is smallest) and Hom against WT (ratio of means; Mann-Whitney or Welch t). Dots: "
                            "grey WT, orange Het, red Hom; a short line at each genotype's mean."),
        ("Read every page with these", "Two mice a genotype. Sex is confounded with genotype: both Het mice are male and every "
                                       "WT and Hom mouse is female, so WT against Hom is also the female-only test. The IED "
                                       "border is PTEN's (39 hand-sorted IEDs), reused unchanged. No mouse separates DS1 "
                                       "from DS2 well (separation index 0.03 to 0.44), so every DS1 / DS2 result is weak "
                                       "and the tight layer rule falls back on PTEN's DS1-to-DS2 distance. One contact looks faulty: CSC 43 runs 10 to 17% "
                                       "below its neighbors in every recording (CSC 44 about 10% above), which draws a narrow "
                                       "false sink and source pair at rows 40 to 43, right where four mice's upper blade sits "
                                       "(page 11). It is not marked bad yet, so read every upper-blade result as unsettled."),
    ])
    save(fig, "01_cover")


def pipeline():
    fig, y = kpage(0, "every step of the PTEN pipeline ran on the six KCNT1 recordings; the reused PTEN IED border puts no "
                      "WT event in the IED class and 3 of %s events overall, and the mutant mice have more events outside "
                      "the WT DS border." % format(int((RC.wf == "halo").sum()), ","), kicker="KCNT1 MENU · WHAT WAS DONE")
    steps = [
        ("Lock", "Each recording's pooled (Incisor + Doppler) Event Bank entry at its newest, committed Lock version."),
        ("Root Canal", "Reads made on the VACC by Root Canal's own batch. Pools: “KCNT1 prelim WT Baseline” (%s) and "
                       "“KCNT1 prelim WT, Het and Hom Baseline” (%s), measured with the PTEN pools' Optimized "
                       "parameters. DS borders (Snap, 5%% and 10%% grace) drawn around the WT events (%s, %s). Halo set: 5%% "
                       "DS border + PTEN P-spike border 4e5ce690d4b1 v2 + halo 2 / 1.5 (%s v%d). Strict set: 10%% DS border, "
                       "no halo (%s v%d). Both banked as Root Canal bundles." % (
                           IDS["pool_wt"], IDS["pool_all"], IDS["ds5"], IDS["ds10"], IDS["halo"], IDS["halo_run_v"],
                           IDS["strict"], IDS["strict_run_v"])),
        ("X-ray", "One X-ray Many folder per set (%s, %s); every kept event read down the whole shank on the VACC with "
                  "Jarvis's own reader, the reads filed back into Jarvis." % (IDS["xm_halo"], IDS["xm_strict"])),
        ("Extraction Room", "A new room, “Dentate Spike KCNT1” (%s): v1 the Halo set, v2 the Strict set; each card's "
                            "depth band the default (the two bottom sinks), split by the Bite line." % IDS["room"]),
        ("Freeze, battery, menu", "On the VACC: the deep round (every split, PCA mixtures, optimized boundaries, DS3), the "
                                  "battery's frozen sets at 20 µm per contact, the Halo set read again under seven "
                                  "filters, every Root Canal event read at 2 kHz, the layers, and this menu."),
    ]
    for h, b in steps:
        y += F.put(fig, 0.5, y, h, 1.3, size=7.0, weight="bold") * 0
        y += F.put(fig, 1.75, y, b, 6.25, size=6.5) + 0.07
    y += 0.1
    F.letter(fig, 0.4, y + 0.1, "a", "Every Root Canal event of the six mice in the three numbers, colored by its Halo-set class")
    h = RC[RC.wf == "halo"].copy()
    kind = {"ds": "DS", "halo_ds": "DS", "both": "BT", "halo_amb": "BT", "pspike": "IED", "halo_pspike": "IED", "neither": "far"}
    h["k"] = h.cls.map(kind)
    for j, (xc, yc, xl, yl) in enumerate((("amp", "hf", "Max amplitude (µV)", "Fast power, 240-420 Hz (dB)"),
                                         ("hw", "hf", "Half-width (ms)", "Fast power, 240-420 Hz (dB)"))):
        a = F.axes_in(fig, 0.85 + j * 2.6, y + 0.35, 2.1, 1.75)
        for k_, col, s_ in (("DS", "#9db7d8", 3), ("far", "#b0b0b0", 6), ("BT", F.C_PDS, 9), ("IED", F.C_IED, 14)):
            d = h[h.k == k_]
            a.scatter(d[xc], d[yc], s=s_, color=col, lw=0, alpha=0.6 if k_ == "DS" else 0.95, label="%s (%d)" % (
                F.KIND_WORD.get(k_, k_), len(d)), zorder=3 if k_ != "DS" else 2)
        if xc == "amp":
            a.set_xscale("log")
        a.set_xlabel(xl, fontsize=6.2)
        a.set_ylabel(yl, fontsize=6.2)
        if j == 0:
            a.legend(frameon=False, fontsize=5.4, loc="lower right", markerscale=1.5)
    F.letter(fig, 5.65, y + 0.1, "b", "Events per mouse by class", width=2.4)
    a = F.axes_in(fig, 6.35, y + 0.35, 1.6, 1.75)
    rows = LABS[::-1]
    for i, l in enumerate(rows):
        c = R["counts"][("halo", l)]
        tot = sum(c.values())
        left = 0
        for k_, col in (("DS", "#9db7d8"), ("BT", F.C_PDS), ("IED", F.C_IED), ("outside", "#b0b0b0")):
            share = c[k_] / tot
            a.barh(i, share, left=left, color=col, height=0.7, lw=0)
            left += share
    a.set_yticks(range(len(rows)))
    a.set_yticklabels(["%s %s\nBT %d, IED %d" % (l, GENO[l], R["counts"][("halo", l)]["BT"], R["counts"][("halo", l)]["IED"])
                       for l in rows], fontsize=5.2)
    a.set_xlim(0.85, 1.0)
    a.set_xlabel("Share of the mouse's events\n(DS fill the first 85%)", fontsize=5.8)
    y += 2.55
    F.letter(fig, 0.4, y + 0.1, "c", "More of the mutant mice's events fall outside the borders drawn around WT dentate spikes")
    dose_ax(fig, 0.85, y + 0.45, 1.6, 1.35, "bt_share", ylabel="BT share of the\nmouse's events (Halo)")
    dose_ax(fig, 3.05, y + 0.45, 1.6, 1.35, "strict_outside_share", ylabel="Share outside both\nborders (Strict)")
    dose_ax(fig, 5.25, y + 0.45, 1.6, 1.35, "bt_rate", ylabel="BTs per minute")
    y += 2.15
    textcol(fig, y, [
        ("Reading", "The WT border is drawn around the WT mice's own events, so by construction about 5%% (Halo) or 10%% "
                    "(Strict) of WT events sit outside it; the mutant mice sit outside it more (Strict: Hom %.0f%% and %.0f%%, "
                    "WT %.0f%% and %.0f%%). The reused PTEN IED border transfers: no WT event is in the IED class, and only 3 "
                    "events of all six mice are (2 in Het m1609, 1 in Hom m306)." % tuple(
                        100 * V("strict_outside_share")[l] for l in ("m1603", "m306", "m1619", "m526"))),
    ])
    save(fig, "02_what_was_done")


def q1():
    fig, y = kpage(1, ANSWERS[1])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "The synaptic current a dentate spike carries does not follow gene dose (ρ %+.2f, P %s; "
             "Hom/WT ×%.2f)" % (drho(K["sink"]), pw(dp(K["sink"])), hr(K["sink"])))
    dose_ax(fig, 0.85, y + 0.55, 1.75, 1.5, K["sink"], ylabel="DS sink at its peak\n(WT average = 1)", hline=1)
    dose_ax(fig, 3.35, y + 0.55, 1.75, 1.5, K["slope"], ylabel="10-90% rise slope\n(WT average sink = 1)")
    dose_ax(fig, 5.85, y + 0.55, 1.75, 1.5, "q1|rise|v6", ylabel="10-90% rise time (ms)")
    y += 2.45
    F.letter(fig, 0.4, y + 0.08, "b", "For the same synaptic current, DS fast power does not follow gene dose either (ρ %+.2f, "
             "P %s)" % (drho(K["out"]), pw(dp(K["out"]))))
    dose_ax(fig, 0.85, y + 0.55, 1.75, 1.5, K["out"], ylabel="Fast power for a\nstandard sink (dB)")
    dose_ax(fig, 3.35, y + 0.55, 1.75, 1.5, "q1|out_ds1", ylabel="DS1 fast power for a\nstandard sink (dB)")
    dose_ax(fig, 5.85, y + 0.55, 1.75, 1.5, "q1|out_ds2", ylabel="DS2 fast power for a\nstandard sink (dB)")
    y += 2.45
    F.letter(fig, 0.4, y + 0.08, "c", "Output grows with input within every mouse", width=3.5)
    a = F.axes_in(fig, 0.85, y + 0.5, 3.0, 1.6)
    bins = np.arange(-2.0, 1.51, 0.5)
    mids = (bins[:-1] + bins[1:]) / 2
    ev = pickle.load(open(os.path.join(HERE, "jeremy_battery.pkl"), "rb"))
    ref = ev["ref"]["v6"]
    for l in LABS:
        e = ev["events_v6"][l]
        x = np.log2(e["sink"] / ref)
        row = [np.nanmean(e["hf"][(x >= lo) & (x < hi)]) if ((x >= lo) & (x < hi)).sum() >= 5 else np.nan
               for lo, hi in zip(bins[:-1], bins[1:])]
        a.plot(mids, row, color=GCOL[GENO[l]], lw=1.1, marker="o", ms=2.2)
        last = [i for i in range(len(row)) if np.isfinite(row[i])]
        if last:
            a.text(mids[last[-1]] + 0.06, row[last[-1]], l, fontsize=4.8, color=F.SOFT, va="center")
    a.axvline(0, color=F.FAINT, lw=0.6, ls=":")
    a.set_xticks([-2, -1, 0, 1])
    a.set_xticklabels(["¼", "½", "1", "2"])
    a.set_xlabel("DS sink (WT average = 1, log scale)", fontsize=6.2)
    a.set_ylabel("Fast power at the DS (dB)", fontsize=6.2)
    textcol(fig, y + 2.55, [
        ("How it was measured", "As in the PTEN menu. Input: each DS's deepest dentate sink at its peak (±3 ms), median per "
                                "mouse, divided by the WT average so WT = 1; its 10-90% rise. Output per input: each DS's "
                                "fast (240-420 Hz) power from Root Canal, fitted against its sink within each mouse "
                                "(Theil-Sen), read at the WT-average sink."),
        ("What it shows", "Sink: m1619 and m1603 (one WT, one Hom) carry the largest sinks, so genotype and sink size do not "
                          "line up (dose P %s; Hom against WT P %s). Fast power for a standard sink: 15.5 to 16.8 dB in every "
                          "mouse (dose P %s; Hom against WT P %s). By type: DS1 P %s, DS2 P %s for dose." % (
                              pw(dp(K["sink"])), pw(hp(K["sink"])), pw(dp(K["out"])), pw(hp(K["out"])),
                              pw(dp("q1|out_ds1")), pw(dp("q1|out_ds2")))),
        ("Caution", "Sink sizes depend on where the probe sits; with two mice a genotype a single placement decides a mean."),
    ])
    save(fig, "03_q1_synaptic_efficacy")


def q2():
    fig, y = kpage(2, ANSWERS[2])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "Every mouse makes both types by the count rule, but none separates them well (index under "
             "0.45 in all six)")
    a = F.axes_in(fig, 0.85, y + 0.5, 3.2, 1.55)
    for i, l in enumerate(LABS):
        t = R["types"][l]
        a.bar(i, t["n1"] / t["n"], color=F.C_DS1, width=0.6, lw=0)
        a.bar(i, t["n2"] / t["n"], bottom=t["n1"] / t["n"], color=F.C_DS, width=0.6, lw=0)
        a.text(i, 1.03, "%d / %d" % (t["n1"], t["n2"]), fontsize=5.0, ha="center", color=F.INK)
    a.set_xticks(range(len(LABS)))
    a.set_xticklabels(["%s\n%s" % (l, GENO[l]) for l in LABS], fontsize=5.6)
    a.set_ylim(0, 1.12)
    a.set_ylabel("Share of the mouse's DS", fontsize=6.2)
    a.legend(handles=[Line2D([], [], color=F.C_DS1, lw=5, label="DS1"), Line2D([], [], color=F.C_DS, lw=5, label="DS2")],
             frameon=False, fontsize=5.6, loc="upper right", bbox_to_anchor=(1.0, 0.92))
    dose_ax(fig, 4.9, y + 0.55, 1.6, 1.5, "q2|si", ylabel="Separation index\n(the winner classifier)", hline=0.45)
    y += 2.45
    F.letter(fig, 0.4, y + 0.08, "b", "Neither type's share or rate follows gene dose")
    dose_ax(fig, 0.85, y + 0.55, 1.6, 1.5, "q2|ds2_share", ylabel="DS2 share")
    dose_ax(fig, 3.05, y + 0.55, 1.6, 1.5, "q2|ds1_rate", ylabel="DS1 per minute")
    dose_ax(fig, 5.25, y + 0.55, 1.6, 1.5, "q2|ds2_rate", ylabel="DS2 per minute")
    y += 2.45
    F.letter(fig, 0.4, y + 0.08, "c", "DS1's sink rises faster in the Hom mice (Hom/WT ×%.2f, P %s; dose P %s); DS2's does not" % (
        hr("q2|rise_ds1"), pw(hp("q2|rise_ds1")), pw(dp("q2|rise_ds1"))))
    dose_ax(fig, 0.85, y + 0.55, 1.6, 1.5, "q2|rise_ds1", ylabel="DS1 rise time (ms),\nat its own sink")
    dose_ax(fig, 3.05, y + 0.55, 1.6, 1.5, "q2|rise_ds2", ylabel="DS2 rise time (ms),\nat its own sink")
    textcol(fig, y + 2.5, [
        ("How it was measured", "DS1 and DS2 by each recording's winner classifier (the PTEN rule of 2026-11-18: the best of "
                                "the room's classifiers, the PCA mixtures and the index-optimized boundary, chosen before any "
                                "group test), named by anatomy (DS1 the type whose sink sits farther from the cell layer). "
                                "“Makes both”: each type at least 5 events and 5%. Separation index = 1 - mean "
                                "overlap between types / mean overlap within types; PTEN called 0.45 and above separable."),
        ("Caution", "With separation indices of 0.03 to 0.44 the two types are not cleanly apart in any mouse, and in two mice "
                    "(m526, m306) the anatomical naming puts 95% of events in DS2. Read DS1 / DS2 results as tentative. The DS1 "
                    "rise result rests on 2 against 2 (Welch t) and on these weak splits."),
    ])
    save(fig, "04_q2_ds1_ds2")


def q3():
    fig, y = kpage(3, ANSWERS[3])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "Tight layers (the main rule): of the four sinks only the upper OML moves with gene dose, "
             "and only under this rule")
    for j, k in enumerate(q3keys):
        dose_ax(fig, 0.85 + j * 1.85, y + 0.6, 1.4, 1.35, k, ylabel="Sink (WT DS = 1)" if j == 0 else "",
                title=LAYW[k.split("|")[-1]], hline=0)
    y += 2.35
    F.letter(fig, 0.4, y + 0.08, "b", "The menu's old rule, beside it: no layer follows gene dose")
    for j, k in enumerate(q3old):
        dose_ax(fig, 0.85 + j * 1.85, y + 0.6, 1.4, 1.35, k, ylabel="Sink (WT DS = 1)" if j == 0 else "",
                title=LAYW[k.split("|")[-1]], hline=0)
    y += 2.35
    textcol(fig, y, [
        ("How the layers were found", "No layer labels. Tight rule (the PTEN layer check of 2026-11-25): in each blade the MML "
                                      "is centered on the DS2 sink and the OML on the DS1 sink, ±2 contacts (±40 µm). "
                                      "No KCNT1 mouse separates its types, so every blade takes the fallback: the all-DS sink "
                                      "as the MML and the OML the PTEN median DS1-to-DS2 distance farther out (53 µm upper, "
                                      "57 µm lower). Old rule: along each blade's own axis (0 = cell-layer source, 1 = the "
                                      "average DS sink), MML 0.7-1.3, OML 1.3-2.0. Sink = minus the CSD at the DS peak "
                                      "(±3 ms) averaged over the layer's contacts, median per mouse, over the WT average "
                                      "deepest sink."),
        ("What it shows", "Tight: upper OML dose ρ %+.2f, P %s (the WT mice show a source there, the Hom mice none); the "
                          "other three P %s, %s, %s. Old rule: P %s, %s, %s, %s. A negative value is a source, not a sink." % (
                              drho(q3keys[1]), pw(dp(q3keys[1])), pw(dp(q3keys[0])), pw(dp(q3keys[2])), pw(dp(q3keys[3])),
                              *[pw(dp(k)) for k in q3old])),
        ("Caution", "The upper OML is one or two contacts on these probes and its tight placement is borrowed from PTEN. "
                    "Worse, the upper-blade landmarks of m1619, m526, m1609 and m576 land on a narrow sink and source pair at "
                    "rows 40 to 43 that comes from one low-gain contact (CSC 43, 10 to 17% below its neighbors in every "
                    "recording; page 11), not from the tissue. The one dose result here should not be read until CSC 43 is "
                    "marked bad and the pipeline run again."),
    ])
    save(fig, "05_q3_mml_oml_sink")


def q4():
    fig, y = kpage(4, ANSWERS[4])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "The DS's own dominant frequency sits at 12 to 18 Hz; in the upper MML it is lower in the "
             "Hom mice (Hom/WT ×%.2f, P %s; dose P %s)" % (hr(q4dom[0]), pw(hp(q4dom[0])), pw(dp(q4dom[0]))))
    for j, k in enumerate(q4dom):
        dose_ax(fig, 0.85 + j * 1.85, y + 0.6, 1.4, 1.3, k, ylabel="Dominant frequency (Hz)" if j == 0 else "",
                title=LAYW[k.split("|")[-1]])
    y += 2.25
    F.letter(fig, 0.4, y + 0.08, "b", "Where the fast power sits does not follow gene dose in any layer")
    for j, k in enumerate(q4cen):
        dose_ax(fig, 0.85 + j * 1.85, y + 0.6, 1.4, 1.3, k, ylabel="Fast-power center (Hz)" if j == 0 else "",
                title=LAYW[k.split("|")[-1]])
    y += 2.25
    F.letter(fig, 0.4, y + 0.08, "c", "Nor does how much fast power the DS adds")
    for j, k in enumerate(q4gain):
        dose_ax(fig, 0.85 + j * 1.85, y + 0.6, 1.4, 1.3, k, ylabel="Fast-power gain (dB)" if j == 0 else "",
                title=LAYW[k.split("|")[-1]])
    y += 2.25
    textcol(fig, y, [
        ("How it was measured", "Every DS read again at 2 kHz through Jarvis's X-ray reader, ±100 ms, the 60 Hz notch only "
                                "(the open band), tight layers. Dominant frequency: the peak of the layer's CSD spectrum over "
                                "±50 ms, 5-300 Hz (on a 1 Hz grid, so the values step). Fast power: the event (±25 ms) "
                                "over the moment before (-100 to -50 ms); its center is the power-weighted frequency of "
                                "what the DS adds between 100 and 500 Hz, its gain the mean dB from 250 to 500 Hz."),
        ("What it shows", "Dominant frequency, dose P: upper MML %s, upper OML %s, lower MML %s, lower OML %s. Fast-power center: "
                          "%s, %s, %s, %s. Gain: %s, %s, %s, %s." % tuple(pw(dp(k)) for k in q4dom + q4cen + q4gain)),
    ])
    save(fig, "06_q4_dominant_frequency")


def p_grid(fig, x, y, w, rows, title, cell_h=0.17, label_w=1.9):
    """rows: (label, {band: key}); cells: dose P (color = direction, darker = smaller P, bold = P < 0.05)."""
    import matplotlib
    cmap = matplotlib.colormaps["RdBu_r"]
    nr, nc = len(rows), len(BANDS)
    cw = (w - label_w) / nc
    a = F.axes_in(fig, x + label_w, y, cw * nc, cell_h * nr)
    a.set_xlim(0, nc)
    a.set_ylim(nr, 0)
    a.axis("off")
    W, H = fig.get_size_inches()
    for i, (lab, keys) in enumerate(rows):
        for j, b in enumerate(BANDS):
            k = keys.get(b)
            p, r = (dp(k), drho(k)) if k else (np.nan, np.nan)
            if not np.isfinite(p):
                a.text(j + 0.5, i + 0.5, "—", ha="center", va="center", fontsize=5.6, color=F.FAINT)
                continue
            strength = min(1.0, -np.log10(max(p, 1e-4)) / 2.5)
            col = cmap(0.5 + 0.45 * strength * np.sign(r if np.isfinite(r) else 0))
            a.add_patch(matplotlib.patches.Rectangle((j + 0.03, i + 0.06), 0.94, 0.88, color=col, lw=0))
            a.text(j + 0.5, i + 0.5, pw(p), ha="center", va="center", fontsize=5.3, color=F.INK,
                   weight="bold" if p < 0.05 else "normal")
        fig.text((x + label_w - 0.06) / W, 1 - (y + (i + 0.5) * cell_h) / H, lab, fontsize=5.7, ha="right", va="center")
    for j, b in enumerate(BANDS):
        fig.text((x + label_w + (j + 0.5) * cw) / W, 1 - (y - 0.04) / H, BAND_WORD[b], fontsize=5.4, ha="center", va="bottom",
                 rotation=0)
    fig.text(x / W, 1 - (y - 0.22) / H, title, fontsize=6.6, weight="bold", ha="left", va="bottom")
    return y + cell_h * nr


def q5():
    rows3 = [("%s sink, tight" % LAYW[k], {b: "q3|tight|%s|%s" % (BSET[b], k) for b in BANDS})
             for k in ("uMML", "uOML", "lMML", "lOML")]
    rows3 += [("%s sink, old rule" % LAYW[k], {b: "q3|old|%s|%s" % (BSET[b], k) for b in BANDS})
              for k in ("uMML", "uOML", "lMML", "lOML")]
    rows4 = []
    for m_, w_ in (("dom", "dominant frequency"), ("cen", "fast-power center"), ("gain", "fast-power gain")):
        for k in ("uMML", "uOML", "lMML", "lOML"):
            rows4.append(("%s %s" % (LAYW[k], w_), {b: "q4|%s|tight|%s|DS|%s" % (m_, b, k) for b in BANDS}))
    keys3 = [k for _l, d in rows3 for k in d.values()]
    keys4 = [k for _l, d in rows4 for k in d.values() if np.isfinite(dp(k))]
    ANS5 = ("No: the answers to 3 and 4 do not settle on any band: %d of %d sink results and %d of %d frequency results reach "
            "P < 0.05 for gene dose, scattered, about what chance gives." % (
                sum(dp(k) < 0.05 for k in keys3), sum(np.isfinite(dp(k)) for k in keys3), sum(dp(k) < 0.05 for k in keys4),
                len(keys4)))
    ANSWERS[5] = ANS5
    fig, y = kpage(5, ANS5)
    y += 0.35
    y = p_grid(fig, 0.5, y + 0.3, 7.5, rows3, "a  Question 3 on every filter band: the dose P of each layer's sink") + 0.35
    y = p_grid(fig, 0.5, y + 0.3, 7.5, rows4, "b  Question 4 on every filter band (tight layers); fast power needs a band that "
                                              "reaches 300 Hz") + 0.3
    textcol(fig, y, [
        ("How to read it", "Each cell is the gene-dose P of one result on one band (the smallest of Spearman exact, Kendall and "
                           "Pearson, over six mice). Red: the value rises with dose; blue: it falls; darker: smaller P; bold: "
                           "P < 0.05. A dash: the band cannot carry the measure. Sinks come from the battery's filter sets "
                           "(the Halo set read again from the raw recordings under each filter); frequencies from the 2 kHz "
                           "reads with the band applied to each ±100 ms window."),
        ("Caution", "%d cells are tested here; at P < 0.05 about %d would turn up by chance alone." % (
            len(keys3) + len(keys4), round(0.05 * (len(keys3) + len(keys4))))),
    ])
    save(fig, "07_q5_open_filters")


def q6():
    fig, y = kpage(6, ANSWERS[6])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "Borderline transients are rarer in WT mice; the Het mouse m1609 makes the most, and IED-class "
             "events appear only in m1609 and m306")
    dose_ax(fig, 0.85, y + 0.55, 1.6, 1.45, "bt_rate", ylabel="BTs per minute")
    dose_ax(fig, 3.05, y + 0.55, 1.6, 1.45, "ied_rate", ylabel="IED-class events\nper minute")
    dose_ax(fig, 5.25, y + 0.55, 1.6, 1.45, "ds_rate", ylabel="DS per minute")
    y += 2.45
    F.letter(fig, 0.4, y + 0.08, "b", "Called abnormal = more BTs per minute than either WT mouse: genotype ranks those mice first "
             "(AUC %.2f); the DS's own fast power does not (AUC %.2f)" % (AUC_DOSE, AUC_HF))
    a = F.axes_in(fig, 0.85, y + 0.5, 3.0, 1.55)
    for i, l in enumerate(LABS):
        a.barh(i, bt[l], color=GCOL[GENO[l]], height=0.6)
        a.text(bt[l] + 0.03, i, ("abnormal" if abnormal[l] else ""), fontsize=5.3, va="center", color=F.INK)
    a.axvline(wt_max_bt, color=F.FAINT, ls=":", lw=0.8)
    a.set_yticks(range(len(LABS)))
    a.set_yticklabels(["%s %s" % (l, GENO[l]) for l in LABS], fontsize=5.8)
    a.invert_yaxis()
    a.set_xlabel("BTs per minute (dotted: the higher WT mouse)", fontsize=6.0)
    dose_ax(fig, 4.9, y + 0.55, 1.6, 1.45, "rc_hf_ds", ylabel="DS fast power\n(Root Canal, dB)")
    y += 2.45
    textcol(fig, y, [
        ("How it was measured", "Root Canal's Halo workflow on all six mice (the WT DS border at 5% grace, the PTEN IED border, "
                                "halo 2 / 1.5). BT = inside both borders or in a halo without a clear side; IED class = inside "
                                "the IED border only, or captured by its halo. Rates per minute of recording. There is no KCNT1 "
                                "IED+ / IED- grouping on the lab sheet yet, so “abnormal” is defined here by BT rate, "
                                "and the ROC asks how well gene dose (0 / 1 / 2) and DS fast power rank those mice above the "
                                "others."),
        ("What it shows", "BT rate, dose ρ %+.2f, P %s; Hom/WT ×%.1f, P %s. Of all six mice, IED-class events: m1609 2, "
                          "m306 1, the rest 0. Abnormal by the rule: %s. The PTEN machine-learning step (Extraction Room 2.0) "
                          "was not part of this page: with two mice a genotype a model leaving one mouse out learns from one." % (
                              drho("bt_rate"), pw(dp("bt_rate")), hr("bt_rate"), pw(hp("bt_rate")),
                              ", ".join(l for l in LABS if abnormal[l]))),
        ("Caution", "The abnormal rule was chosen after seeing the rates, and one WT mouse (m526, 9 BTs) sets the line."),
    ])
    save(fig, "08_q6_predict_abnormal")


def q7_panel(fig, x, y, band, kk, what, title):
    rows = R["q7"][(band, kk)]
    a = F.axes_in(fig, x, y, 1.4, 1.3)
    sel = [r for r in rows if r["n_bt"] >= 5]
    wt_ds = np.mean([r["sink_DS" if what == "sink" else "gain_DS"] for r in rows if GENO[r["lab"]] == "WT"])
    for r in sel:
        l = r["lab"]
        a_, b_ = (r["sink_DS"], r["sink_TZ"]) if what == "sink" else (r["gain_DS"], r["gain_TZ"])
        if what == "sink":
            a_, b_ = a_ / abs(wt_ds), b_ / abs(wt_ds)
        a.plot([0, 1], [a_, b_], color=GCOL[GENO[l]], lw=1.0, marker="o", ms=3)
        a.text(1.06, b_, l, fontsize=4.8, color=F.SOFT, va="center")
    a.axhline(1 if what == "sink" else wt_ds, color=F.FAINT, ls=":", lw=0.7)
    a.set_xticks([0, 1])
    a.set_xticklabels(["own DS", "BT"])
    a.set_xlim(-0.3, 1.45)
    s = q7_stats(band, kk, what)
    a.set_title("%s\nBT > DS in %d of %d, P %s" % (title, s.get("up", 0), s["n"], pw(s["p"])), fontsize=5.6, loc="left",
                color=F.SOFT, pad=3)
    a.set_ylabel(("Sink (WT DS = 1)" if what == "sink" else "Fast-power gain (dB)") if x < 1 else "", fontsize=6.0)
    return s


def q7():
    fig, y = kpage(7, ANSWERS[7])
    legend_geno(fig, 0.55, y)
    y += 0.4
    F.letter(fig, 0.4, y + 0.08, "a", "Within the four mice with five BTs or more, BTs carry more MML current than the same "
             "mouse's DS in 7 of 8 mouse-blade pairs, short of P 0.05; in the upper OML they carry more source")
    for j, kk in enumerate(("uMML", "uOML", "lMML", "lOML")):
        q7_panel(fig, 0.85 + j * 1.85, y + 0.62, "notch", kk, "sink", LAYW[kk])
    y += 2.3
    F.letter(fig, 0.4, y + 0.08, "b", "and more fast power, in every layer (dotted: the WT mice's DS)")
    for j, kk in enumerate(("uMML", "uOML", "lMML", "lOML")):
        q7_panel(fig, 0.85 + j * 1.85, y + 0.62, "notch", kk, "gain", LAYW[kk])
    y += 2.3
    textcol(fig, y, [
        ("How it was measured", "Every Root Canal event of every mouse read at 2 kHz (one pipeline: same contacts, filters and "
                                "alignment), open band, tight layers. Per mouse the median over its BTs and over its DS; "
                                "the line joins the two. Paired over the mice with 5 BTs or more (m526 WT 9, m1609 Het 50, "
                                "m1603 Hom 6, m306 Hom 25): the smallest P of paired t and Wilcoxon (Wilcoxon cannot go "
                                "below 0.125 with four mice). Dotted line: the WT mice's DS."),
        ("Caution", "Four mice, one of them WT, so this is BTs against DS rather than mutant against WT; two of the four have "
                    "fewer than ten BTs. IED-class events (3 in all) are too few to test."),
    ])
    save(fig, "09_q7_continuum")


def q8():
    rows = []
    for what, w_ in (("sink", "sink, BT over own DS"), ("gain", "fast-power gain, BT minus own DS")):
        for kk in ("uMML", "uOML", "lMML", "lOML"):
            rows.append(("%s %s" % (LAYW[kk], w_), what, kk))
    import matplotlib
    cmap = matplotlib.colormaps["RdBu_r"]
    cells = {}
    for lab, what, kk in rows:
        for b in BANDS:
            if what == "gain" and b not in ("notch", "1-300", "5-300"):
                continue
            cells[(lab, b)] = q7_stats(b, kk, what)
    nsig = sum(1 for s in cells.values() if np.isfinite(s["p"]) and s["p"] < 0.05)
    ANSWERS[8] = ("No: on every band that reaches 300 Hz the BTs carry more fast power than their own DS in all four mice; "
                  "their extra MML current keeps its direction on every band but never reaches P < 0.05 (%d of %d cells "
                  "do, all of them fast power or the upper OML)." % (nsig, len(cells)))
    fig, y = kpage(8, ANSWERS[8])
    y += 0.6
    W, H = fig.get_size_inches()
    x0, label_w, cell_h = 0.5, 2.4, 0.2
    cw = (7.5 - label_w) / len(BANDS)
    a = F.axes_in(fig, x0 + label_w, y, cw * len(BANDS), cell_h * len(rows))
    a.set_xlim(0, len(BANDS))
    a.set_ylim(len(rows), 0)
    a.axis("off")
    for i, (lab, what, kk) in enumerate(rows):
        for j, b in enumerate(BANDS):
            s = cells.get((lab, b))
            if s is None or not np.isfinite(s["p"]):
                a.text(j + 0.5, i + 0.5, "—", ha="center", va="center", fontsize=5.6, color=F.FAINT)
                continue
            up = s.get("up", 0) - (s["n"] - s.get("up", 0))
            strength = min(1.0, -np.log10(max(s["p"], 1e-4)) / 2.5)
            a.add_patch(matplotlib.patches.Rectangle((j + 0.03, i + 0.06), 0.94, 0.88,
                                                     color=cmap(0.5 + 0.45 * strength * np.sign(up)), lw=0))
            a.text(j + 0.5, i + 0.5, "%d/%d  %s" % (s.get("up", 0), s["n"], pw(s["p"])), ha="center", va="center",
                   fontsize=5.0, weight="bold" if s["p"] < 0.05 else "normal")
        fig.text((x0 + label_w - 0.06) / W, 1 - (y + (i + 0.5) * cell_h) / H, lab, fontsize=5.8, ha="right", va="center")
    for j, b in enumerate(BANDS):
        fig.text((x0 + label_w + (j + 0.5) * cw) / W, 1 - (y - 0.04) / H, BAND_WORD[b], fontsize=5.4, ha="center", va="bottom")
    y += cell_h * len(rows) + 0.4
    textcol(fig, y, [
        ("How to read it", "Each cell: in how many of the four mice the BTs carry more than the same mouse's DS, and the paired P "
                           "(smallest of paired t and Wilcoxon). Red: BT higher; blue: lower; bold: P < 0.05. Fast power "
                           "needs a band that reaches 300 Hz."),
    ])
    save(fig, "10_q8_q7_open_filters")


def every():
    fig, y = kpage(0, "every mouse's dentate spike down the probe, with the layers each rule picks; the table holds the "
                      "numbers the pages use.", kicker="KCNT1 MENU · EVERY MOUSE")
    y += 0.2
    W, H = fig.get_size_inches()
    for j, l in enumerate(LABS):
        a = F.axes_in(fig, 0.75 + j * 1.25, y + 0.35, 0.95, 3.2)
        p = PROF.get(("v6", l))
        if p is None:
            continue
        prof = np.asarray(p["peak"], float)
        ref = p["ref"] if np.isfinite(p["ref"]) else np.nanmax(-prof)
        rows = np.arange(prof.size)
        a.fill_betweenx(rows, 0, -prof / ref, where=prof < 0, color="#c2571a", alpha=0.55, lw=0)
        a.fill_betweenx(rows, 0, -prof / ref, where=prof >= 0, color="#2f6db5", alpha=0.45, lw=0)
        a.plot(-prof / ref, rows, color=F.INK, lw=0.6)
        tl = TL["mice"].get(l, {})
        for blade in ("upper", "lower"):
            rr = (tl.get("rows") or {}).get(blade, {})
            for lay, col in (("MML", "#7a2a8a"), ("OML", "#2a7a4a")):
                for r in rr.get(lay, []):
                    a.axhspan(r - 0.5, r + 0.5, xmin=0.0, xmax=0.08, color=col, lw=0)
        a.set_ylim(63.5, 20)
        a.set_xlim(-1.3, 1.3)
        a.axvline(0, color=F.FAINT, lw=0.5)
        a.set_title("%s %s" % (l, GENO[l]), fontsize=6.4, color=GCOL[GENO[l]], loc="left")
        a.set_xlabel("Sink →", fontsize=5.6)
        if j == 0:
            a.set_ylabel("Contact (row, down the probe; 20 µm apart)", fontsize=5.8)
        else:
            a.set_yticklabels([])
    y += 3.95
    F.put(fig, 0.75, y, "Orange: sink (minus the CSD at the DS peak, each mouse over its own deepest sink); blue: source. "
          "Ticks at the left edge: the tight rule's MML (purple) and OML (green) contacts in each blade.", 7.2, size=5.8,
          color=F.SOFT)
    y += 0.45
    cols = ["Mouse", "Geno", "Sex", "DS (Halo)", "BT/min", "Sink", "Fast power*", "Sep. index", "DS1/DS2", "Up MML", "Low MML",
            "Dom. freq."]
    xs = [0.5, 1.05, 1.5, 1.85, 2.5, 3.1, 3.65, 4.35, 5.0, 5.75, 6.4, 7.05]
    for c, x in zip(cols, xs):
        fig.text(x / W, 1 - y / H, c, fontsize=6.0, weight="bold", va="top")
    y += 0.17
    for l in LABS:
        t = R["types"][l]
        row = [l, GENO[l], SEX[l], "%d" % R["counts"][("halo", l)]["DS"], "%.2f" % bt[l], "%.2f" % V(K["sink"])[l],
               "%.1f" % V(K["out"])[l], "%.2f" % t["si"], "%d/%d" % (t["n1"], t["n2"]), "%.2f" % V(q3keys[0])[l],
               "%.2f" % V(q3keys[2])[l], "%.1f" % V(q4dom[0])[l]]
        for v, x in zip(row, xs):
            fig.text(x / W, 1 - y / H, v, fontsize=6.0, va="top")
        y += 0.15
    y += 0.1
    textcol(fig, y, [
        ("", "Sink: DS sink at its peak, WT average = 1. *Fast power for a standard sink (dB). Up / Low MML: tight-rule MML sink "
             "(WT = 1). Dom. freq.: upper MML dominant frequency (Hz). Every number per mouse and every test is in "
             "tables/per_mouse_values_and_tests.csv."),
        ("What differs from PTEN, and what comes next", "Six mice, one recording each, two a genotype; sex confounded with "
                                                         "genotype; the PTEN IED border reused; every recording from 2026 on "
                                                         "the H3 wheel configuration (PTEN: 2023-2025), so KCNT1 and PTEN mice "
                                                         "are never in one test. Not done yet: the duplicate-stamp check "
                                                         "(PTEN's 10 ms rule, as a dry run), depth bands set by hand in the "
                                                         "Extraction Room (the default band was used), CSC 43 marked bad (see "
                                                         "the narrow pair at rows 40 to 43 above), an IED grouping from the "
                                                         "sheet, and the machine-learning runs, which need more mice. Next mice to "
                                                         "add: WT 531 (only 10 Lock events now), Het 530, Hom 1604 s2 and 310 s2 "
                                                         "once their Lock sets are committed."),
    ])
    save(fig, "11_every_mouse_and_table")


ANSWERS = {
    1: "No: neither the current a dentate spike carries nor the fast power it produces for the same current follows gene "
       "dose; Hom and WT means are the same (×%.2f and ×%.2f)." % (hr(K["sink"]), hr(K["out"])),
    2: "Every mouse makes both types by count, but none separates them well, and their shares and rates do not follow "
       "dose. DS1's sink rises faster in Hom than WT mice (P %s, 2 against 2)." % pw(hp("q2|rise_ds1")),
    3: "Mostly no: 1 of 8 layer sinks follows gene dose (the upper OML under the tight rule, P %s), and the old rule finds "
       "none." % pw(dp(q3keys[1])),
    4: "Not clearly: the DS's dominant frequency (12-18 Hz) is lower in the Hom mice's upper MML (P %s, dose P %s); fast "
       "power's center and gain do not follow dose in any layer." % (pw(hp(q4dom[0])), pw(dp(q4dom[0]))),
    5: "",
    6: "Partly: borderline transients are rarer in WT mice and gene dose ranks the mice that make more of them first (AUC "
       "%.2f), but over six mice the dose trend is not reliable (P %s)." % (AUC_DOSE, pw(dp("bt_rate"))),
    7: "Yes for fast power: in the four mice with five or more borderline transients (one WT, one Het, two Hom), BTs carry "
       "more fast power than the same mouse's DS in every layer and every mouse; more MML current in most, short of P "
       "0.05. Too few mutant mice with BTs to set them against WT DS.",
    8: "",
}

if __name__ == "__main__":
    q5()
    q8()
    _PAGE[0] = 0          # the two calls above only worked out the answers to 5 and 8; every page is drawn again below
    order = [cover, pipeline, q1, q2, q3, q4, q5, q6, q7, q8, every]
    for fn in order:
        fn()
    try:
        import fitz  # PyMuPDF
        doc = fitz.open()
        for f in sorted(os.listdir(PAGES)):
            if f.endswith(".pdf"):
                doc.insert_pdf(fitz.open(os.path.join(PAGES, f)))
        doc.save(os.path.join(OUT, "KCNT1_DS_Prelim_Menu_112726.pdf"))
        print("merged", doc.page_count)
    except ImportError:
        from matplotlib.backends.backend_pdf import PdfPages  # noqa: F401
        print("PyMuPDF not here: merge the page PDFs with j_merge.py's miniconda step")
