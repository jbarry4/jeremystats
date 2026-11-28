"""Extraction Room 2.0, preliminary write-up (2026-11-18): methods and results
PDFs from the VACC run r006 (2026-11-20, amber v3: the Halo set with m21 in; r005 left m21 out, r003 and r004 were run 4 data).

  python make_room2.py   ->  ../room2_preliminary/Room2_methods.pdf, Room2_results.pdf (+ PNGs)
"""
import json
import os
import sys
import textwrap

import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

import house as Hs
import measures as MS
from house import plt, ax_mm, text_mm, INK, MUTE, HAIR, RED, FS, FS_S

sys.path.insert(0, os.environ.get("JAPP", "/gpfs2/scratch/sakhava1/kcnt1_prelim/app"))
from backend import er2run as R          # noqa: E402
from backend.er2 import engine as E      # noqa: E402

OUT = os.path.join(os.path.dirname(Hs.__file__), "..", "room2_preliminary")
OUT = os.path.abspath(OUT)
os.makedirs(OUT, exist_ok=True)
RUNS = ["r006"]
TARGET_WORD = {"pten_vs_ctl": "PTEN against control", "ko_pct": "Knockout % (a number)", "low_vs_high": "Low (under 10%) against high (15%+) knockout",
               "ied3": "Control / IED− / IED+ (three classes)", "iedpos_vs_iedneg": "IED+ against IED− (PTEN only)"}
VIEW_WORD = {"core": "Waveform + depth + DS type", "context": "+ event context", "filters": "+ six other filters", "before_after": "+ before/after power",
             "events_all": "Every per-event feature", "mouse": "Per-mouse tables", "everything": "Everything (+ nuisance)", "nuisance": "Nuisance only"}
MODEL_WORD = {"linear": "Linear", "lasso": "Lasso", "forest": "Forest", "boosting": "Boosting", "mlp": "Small net", "deepsets": "Deep sets",
              "attention": "Attention"}
SCORE_WORD = {"binary": "AUC", "multiclass": "macro AUC", "regression": "rank correlation"}
FILT = {"none": "no filter", "1_100": "1–100 Hz", "1_300": "1–300 Hz", "5_300": "5–300 Hz", "5_50": "5–50 Hz", "10_40": "10–40 Hz"}
STATW = {"median": "median", "iqr": "spread (IQR)", "mean": "mean", "sd": "SD", "p10": "10th percentile", "p90": "90th percentile"}
WINW = {"pre_far": "−500 to −200 ms", "pre_near": "−150 to −50 ms", "post_near": "+50 to +150 ms", "post_far": "+200 to +500 ms"}


def human(name):
    """A feature's name in words."""
    if name == "(everything else)":
        return name
    base, _, stat = name.partition("|")
    if base == "share":
        return "share of events that are " + {"ds1": "DS1", "ds2": "DS2", "ds3": "DS3", "unscored": "too small to score DS3"}.get(stat, stat)
    if base in ("battery", "waveform", "laminar", "timing", "structure") or name.startswith(("waveform|", "laminar|", "timing|", "structure|")):
        bits = name.split("|")
        return "per mouse: %s (%s)" % (bits[1].replace("_", " "), bits[2] if len(bits) > 2 else "")
    if name.startswith("around|"):
        bits = name.split("|")
        return "per mouse, before/after: %s (%s)" % (bits[1].replace("_", " "), bits[2] if len(bits) > 2 else "")
    if name.startswith("nuisance|"):
        return "nuisance: " + name.split("|")[1].replace("_", " ")
    pre = ""
    if base.startswith("f_"):
        fb, _, base = base[2:].partition("__")
        pre = FILT.get(fb, fb) + ": "
    if base.startswith("type_"):
        w = "event is " + {"ds1": "DS1", "ds2": "DS2", "ds3": "DS3", "unscored": "too small to score DS3"}.get(base[5:], base[5:])
    elif base.startswith("ba_pow_") or base.startswith("ba_pp_"):
        pp = base.startswith("ba_pp_")
        rest = base[6:] if pp else base[7:]
        band, _, rest = rest.partition("_")
        if pp:
            win, _, depth = rest.partition("_")
            w = "%s %s power, after over before (%s)" % ("spiking" if band == "MUA" else band + " Hz", "", "50–150 ms" if win == "near" else "200–500 ms")
        else:
            for wk in WINW:
                if rest.startswith(wk):
                    win, depth = wk, rest[len(wk) + 1:]
                    break
            else:
                win, depth = rest, ""
            w = "%s power over random moments, %s" % ("spiking" if band == "MUA" else band + " Hz", WINW.get(win, win))
        w += ", " + ("whole shank" if depth == "shank" else "depth u " + depth.replace("u", "").replace("_", " to "))
    else:
        w = (MS.EVENT_FEATURES.get(base, (None, base))[1]).split(";")[0]
        if len(w) > 95:
            w = base.replace("_", " ")
    if stat:
        if stat.endswith("_median"):
            w += " (%s median)" % stat[:-7].upper()
        else:
            w += " (%s over events)" % STATW.get(stat, stat)
    return pre + w


def load():
    by = {}
    for rid in RUNS:
        try:
            for r in R.results(rid):
                if "score" in r:
                    by.setdefault((r["target"], r["view"], r["model"]), r)
        except Exception:                                   # noqa: BLE001
            continue
    return list(by.values())


def wrap(fig, H, x, y, s, width=170, **kw):
    for i, ln in enumerate(textwrap.wrap(s, width)):
        text_mm(fig, H, x, y + 3.4 * i, ln, **kw)
    return y + 3.4 * len(textwrap.wrap(s, width))


# ------------------------------------------------------------------ methods
METHODS = [
    ("What was asked", "Can anything in the dentate spikes alone tell PTEN mice from controls, low from high knockout, IED+ from IED− mice, "
     "control / IED− / IED+ apart, or guess the % knockout; and if a model can, which inputs carry it."),
    ("The frozen inputs (amber bundle v3)", "Every event of the Halo set (4,525 events in 16 recordings, one per mouse; m6 and m51 not included). m21 has no winning classifier once its duplicate stamps are gone (none keeps 5 events of each type), so its events carry no DS type. Every other "
     "recording has its winning classifier's DS1 / DS2 / DS3 call held fixed ('set in amber': the classifier marked FINAL OPTIMIZED SEPARATION in the round 11 "
     "quality check; no model re-classifies). Per event, 644 numbers: the waveform and depth-profile measures at the DS (sink and source sizes and "
     "durations, timing between source and sink and between blades, where the sink sits, the source between the blades, the LFP at the source); "
     "event context (interval before and after, time in the recording, detector peak, theta percentile); the winner's call (DS1, DS2, DS3, or too "
     "small to score DS3); the same waveform measures under six other filters (no filter, 1–100, 1–300, 5–300, 5–50, 10–40 Hz); and the power before "
     "and after the DS (±500 ms, 7 bands from 1–4 Hz to multi-unit spiking, 4 windows, 11 depths, each over random moments of the same recording). "
     "Per mouse, 1,593 numbers: the battery's per-mouse measures, the before/after battery's locking and burst measures, and nuisance values."),
    ("Nuisance values", "Things that are not about the dentate spikes and could still differ between groups: where the dentate sat on the probe "
     "(which contacts hold each blade's main sink and the source between them, the distance between the blades, the source-to-sink distances, all read "
     "off each recording's own average CSD), the number of bad contacts, the width of the analyzed band, the year recorded (from the session date), "
     "the number of events, the recording length, and which classifier won with its separation index. A 'nuisance only' model is on every "
     "leaderboard as a baseline: a spike-based model has to beat it to mean anything."),
    ("Targets", "PTEN against control (16 mice); % knockout as a number, controls at 0 (16); low (under 10%) against high (15% or more) knockout "
     "(PTEN only, 9 mice); control / IED− / IED+ (16); IED+ against IED− (PTEN only, 9). Each target is its own model."),
    ("Input views", "Waveform + depth + DS type; + event context; + the six other filters; + before/after power; every per-event feature; the "
     "per-mouse tables only; everything including nuisance; nuisance only."),
    ("Models", "A label belongs to a mouse, so every model makes one call per mouse from that mouse's whole cloud of events, never a call per event. "
     "Pooled models summarize each mouse's events as distributions (median, spread, mean, SD, 10th and 90th percentile, and the DS1 / DS2 / DS3 "
     "medians and shares of every feature), then fit a linear model (L2), a lasso (L1), a random forest, gradient boosting, or a small neural net "
     "(16 units), after choosing the 100 (trees: 400) columns most rank-correlated with the target among the training mice. Two set networks read the "
     "events themselves: each event passes through the same two layers, the mouse's events are pooled (a plain mean: 'deep sets'; or learned "
     "weights: 'attention'), and a small head makes the call."),
    ("Testing (held-out mice only)", "PTEN against control leaves one control and one PTEN mouse out at a time (all 63 pairs); every other target "
     "leaves one mouse out. Nothing about a held-out mouse (its events, its pooled numbers) is used to train, choose columns, scale, or fill in "
     "missing values. Scores: AUC (for pairs: the share of held-out control/PTEN pairs ordered right) and the share of calls right; for % knockout "
     "the rank correlation between predicted and true and the mean absolute error; for three classes, macro AUC and the share right. The bar: AUC "
     "0.80, rank correlation 0.70."),
    ("Opening a model", "On held-out mice only: permutation (scramble one family, or one feature, with other mice's or events' values and see how "
     "much the held-out score falls; 5 repeats); Shapley values (how much each family, and each of the 20 strongest features, pushed each held-out "
     "mouse's call); retraining without each family; and, for attention, which event features go with the weight an event gets. The MOST "
     "IMPORTANT list adds up rank points over the four methods and over the models that reached the bar (or the three best when none did)."),
    ("Where it ran", "Jarvis's Extraction Room tab 'Room 2.0 · models', on the VACC (one slurm array, 260 tasks, run r006, all answered; "
     "the same settings as run r003 on the earlier data and r005 without m21). The same code gives the same numbers on this "
     "computer and on the cluster (checked on run r002). Figures: battery/make_room2_figs.py."),
    ("Significance signs", "On the figures, uncorrected: held-out scores against the truth (one-sided Mann-Whitney on held-out scores; Spearman for the "
     "knockout guess; binomial against 1 in 3 for three groups) and, per parameter, between groups (two-sided Mann-Whitney; Kruskal-Wallis for "
     "three; Spearman with knockout). * P < 0.05, ** P < 0.01, *** P < 0.001. None is corrected for the 260 models, the choice of the best three, "
     "or the five parameters shown, so none is a finding."),
    ("What this is not", "A test of a hypothesis. 260 models were fitted; the best of many models looks good by chance, and with 9 to 16 mice a held-out "
     "score is 9 to 16 calls. Testing on held-out mice stops a model seeing the mouse it calls; it does not stop the best of 260 being lucky. The next "
     "step is a chance check (labels shuffled) on the models that reached the bar, then new mice. Also: with one mouse left out, a model that "
     "learned nothing scores below 0.5 (leaving a mouse out tilts the training set against its own class), which is why some squares read 0.00; "
     "0.5 is not the chance line, the shuffled-label check is."),
]


def methods_pdf(out=None, word="PRELIMINARY", name="Room2_methods.pdf"):
    H = 262.0
    pages, cur, y = [], None, 0
    OUT_ = out or OUT
    with PdfPages(os.path.join(OUT_, name)) as pdf:
        fig = Hs.page(H)
        Hs.stamp(fig, word)
        text_mm(fig, H, 4, 6, "Extraction Room 2.0 · methods", fontsize=10, fontweight="bold")
        y = 13
        for head, body in METHODS:
            need = 6 + 3.4 * len(textwrap.wrap(body, 168))
            if y + need > H - 10:
                pdf.savefig(fig)
                fig.savefig(os.path.join(OUT_, name.replace(".pdf", "_%d.png" % (len(pages) + 1))), dpi=150)
                pages.append(1)
                plt.close(fig)
                fig = Hs.page(H)
                Hs.stamp(fig, word)
                y = 8
            text_mm(fig, H, 4, y, head, fontsize=FS + 0.5, fontweight="bold")
            y = wrap(fig, H, 4, y + 4, body, 168, fontsize=FS_S + 0.3, color=INK) + 3
        # the testing scheme, drawn
        if y + 40 > H - 10:
            pdf.savefig(fig)
            plt.close(fig)
            fig = Hs.page(H)
            Hs.stamp(fig, word)
            y = 8
        text_mm(fig, H, 4, y, "How a mouse is called (one test of the 63 for PTEN against control)", fontsize=FS + 0.5, fontweight="bold")
        ax = ax_mm(fig, H, 8, y + 5, 165, 30)
        mice = ["m2", "m21", "m22", "m26", "m59", "m60", "m61", "m8", "m33", "m1", "m7", "m13", "m28", "m3", "m5", "m34"]
        for i, m in enumerate(mice):
            held = m in ("m22", "m3")
            col = Hs.C_CTL if i < 7 else "#C8591A"
            ax.add_patch(plt.Rectangle((i, 0.55), 0.85, 0.8, color=col, alpha=1.0 if not held else 0.25, lw=0))
            ax.text(i + 0.42, 0.95, m, ha="center", va="center", fontsize=5, color="white" if not held else INK)
            if held:
                ax.add_patch(plt.Rectangle((i, 0.55), 0.85, 0.8, fill=False, ec=RED, lw=1.2))
        ax.set_xlim(-0.2, 16)
        ax.set_ylim(0.4, 1.5)
        wrap(fig, H, 8, y + 37, "Train on the other 14 mice's events (columns chosen, scaled and filled in on them only), then call the two held-out mice "
             "(red boxes) from their own events; repeat for every control/PTEN pair. The score is how often the PTEN mouse gets the higher score.",
             160, fontsize=FS_S, color=INK)
        ax.axis("off")
        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT_, name.replace(".pdf", "_%d.png" % (len(pages) + 1))), dpi=150)
        plt.close(fig)


# ------------------------------------------------------------------ results
def overview(pdf, Rs):
    H = 262.0
    fig = Hs.page(H)
    Hs.stamp(fig, "PRELIMINARY")
    text_mm(fig, H, 4, 6, "Extraction Room 2.0 · every model's held-out score", fontsize=10, fontweight="bold")
    wrap(fig, H, 4, 11, "Each square is one model on one set of inputs, scored only on mice it never saw (AUC for two classes, macro AUC for three, rank "
         "correlation for % knockout). Boxed = reached the bar (0.80, or 0.70 for % knockout). The bottom row is the nuisance-only baseline: placement on "
         "the probe, year, event count. A square is worth something only where it is clearly above both its baseline and 0.5 (0 for % knockout).",
         172, fontsize=FS_S, color=MUTE)
    views = list(E.VIEWS)
    models = list(E.MODELS)
    for k, t in enumerate(E.TARGETS):
        col, row = k % 2, k // 2
        x0, y0 = 32 + col * 90, 30 + row * 76
        ax = ax_mm(fig, H, x0, y0, 58, 52)
        M = np.full((len(views), len(models)), np.nan)
        P = np.zeros_like(M, bool)
        task = None
        for r in Rs:
            if r["target"] != t:
                continue
            task = r["task"]
            M[views.index(r["view"]), models.index(r["model"])] = r["score"]["main"]
            P[views.index(r["view"]), models.index(r["model"])] = bool(r.get("passes"))
        lo = 0.0 if task == "regression" else 0.5
        im = ax.imshow(M, cmap="RdBu_r", vmin=lo - 0.5 if task == "regression" else 0.0, vmax=1.0, aspect="auto")
        for i in range(len(views)):
            for j in range(len(models)):
                if np.isfinite(M[i, j]):
                    ax.text(j, i, "%.2f" % M[i, j], ha="center", va="center", fontsize=4.4, color="white" if abs(M[i, j] - lo) > 0.35 else INK)
                    if P[i, j]:
                        ax.add_patch(plt.Rectangle((j - 0.48, i - 0.48), 0.96, 0.96, fill=False, ec=INK, lw=1.2))
                else:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=4.6, color=MUTE)
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels([MODEL_WORD[m] for m in models], fontsize=4.6, rotation=35, ha="right")
        ax.set_yticks(range(len(views)))
        ax.set_yticklabels([VIEW_WORD[v] for v in views], fontsize=4.6)
        ax.set_title("%s (%s)" % (TARGET_WORD[t], SCORE_WORD.get(task, "")), fontsize=FS_S, loc="left", pad=3)
        ax.tick_params(length=0)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Room2_results_1_overview.png"), dpi=150)
    plt.close(fig)


def target_page(pdf, Rs, lb, t, k):
    H = 262.0
    mine = sorted([r for r in Rs if r["target"] == t], key=lambda r: -(r["score"]["main"] if np.isfinite(r["score"]["main"]) else -9))
    if not mine:
        return
    task = mine[0]["task"]
    base = max([r["score"]["main"] for r in mine if r["view"] == "nuisance"] or [np.nan])
    best = next((r for r in mine if r["view"] != "nuisance"), mine[0])
    fig = Hs.page(H)
    Hs.stamp(fig, "PRELIMINARY")
    text_mm(fig, H, 4, 6, "%s" % TARGET_WORD[t], fontsize=10, fontweight="bold")
    n_pass = sum(1 for r in mine if r.get("passes") and r["view"] != "nuisance")
    y = wrap(fig, H, 4, 11, "%d models. %d spike-based model%s reached the bar (%.2f). Nuisance-only baseline: best %.2f. Best spike-based model: %s on %s, "
             "%s %.2f." % (len(mine), n_pass, "" if n_pass == 1 else "s", E.BAR[task], base, MODEL_WORD[best["model"]], VIEW_WORD[best["view"]].lower(),
                           SCORE_WORD[task], best["score"]["main"]), 172, fontsize=FS_S + 0.3, color=INK)
    # a: the 20 best models
    text_mm(fig, H, 2, y + 3, "a  The 20 best models (held-out score)", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 52, y + 7, 60, 64)
    top = mine[:20]
    vals = [r["score"]["main"] for r in top]
    cols = ["#7A7A7A" if r["view"] == "nuisance" else ("#1B7F4B" if r.get("passes") else "#C8591A") for r in top]
    ax.barh(range(len(top)), vals, color=cols, height=0.7)
    ax.axvline(E.BAR[task], color=INK, lw=0.8, ls=(0, (3, 2)))
    if np.isfinite(base):
        ax.axvline(base, color="#7A7A7A", lw=0.8)
    ax.axvline(0.0 if task == "regression" else 0.5, color=HAIR, lw=0.6)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(["%s · %s" % (VIEW_WORD[r["view"]], MODEL_WORD[r["model"]]) for r in top], fontsize=4.4)
    ax.invert_yaxis()
    ax.set_xlim(min(-0.2, min(vals) - 0.05) if task == "regression" else 0.3, 1.0)
    ax.set_xlabel(SCORE_WORD[task] + " on held-out mice", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    ax.text(E.BAR[task], len(top) - 0.3, " bar", fontsize=4.4, va="bottom")
    if np.isfinite(base):
        ax.text(base, -0.9, "nuisance only", fontsize=4.2, va="bottom", ha="center", color="#7A7A7A")
    # b: the best spike-based model's calls, mouse by mouse
    text_mm(fig, H, 118, y + 3, "b  The best spike-based model's held-out calls", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 128, y + 9, 50, 58)
    per = {}
    for c in best["calls"]:
        v = np.atleast_1d(np.array(c["call"], float))
        p = per.setdefault(c["lab"], {"truth": c["truth"], "sum": np.zeros(v.size), "n": 0})
        p["sum"] += v
        p["n"] += 1
    labs = list(per)
    meta = {m["lab"]: m for m in json.load(open(os.path.join(R.AMB.AMBER, "v1", "manifest.json")))["mice"]}
    colr = lambda lab: Hs.GROUP_COL[meta[lab]["subgroup"]] if lab in meta else MUTE
    if task == "regression":
        tr = np.array([per[l]["truth"] for l in labs])
        pr = np.array([per[l]["sum"][0] / per[l]["n"] for l in labs])
        ax.scatter(tr, pr, c=[colr(l) for l in labs], s=16, edgecolors="white", lw=0.4)
        for l, a_, b_ in zip(labs, tr, pr):
            ax.text(a_ + 0.4, b_, l, fontsize=4.0, va="center", color=MUTE)
        lim = [min(tr.min(), pr.min()) - 2, max(tr.max(), pr.max()) + 2]
        ax.plot(lim, lim, color=HAIR, lw=0.6)
        ax.set_xlabel("True % knockout", fontsize=FS_S)
        ax.set_ylabel("Held-out guess (%)", fontsize=FS_S)
    elif task == "binary":
        cls = best["classes"]
        order = sorted(labs, key=lambda l: (per[l]["truth"], per[l]["sum"][0] / per[l]["n"]))
        pr = [per[l]["sum"][0] / per[l]["n"] for l in order]
        ax.barh(range(len(order)), pr, color=[colr(l) for l in order], height=0.7)
        ax.axvline(0.5, color=INK, lw=0.6, ls=(0, (3, 2)))
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(["%s (%s)" % (l, cls[int(per[l]["truth"])]) for l in order], fontsize=4.4)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Held-out score for '%s'\n(mean over the tests that held it out)" % cls[1], fontsize=FS_S)
    else:
        cls = best["classes"]
        order = sorted(labs, key=lambda l: per[l]["truth"])
        P = np.array([per[l]["sum"] / per[l]["n"] for l in order])
        left = np.zeros(len(order))
        for c_, (nm, col) in enumerate(zip(cls, [Hs.C_CTL, Hs.GROUP_COL["IED-"], Hs.GROUP_COL["IED+"]])):
            ax.barh(range(len(order)), P[:, c_], left=left, color=col, height=0.7, label=nm)
            left += P[:, c_]
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(["%s (%s)" % (l, cls[int(per[l]["truth"])]) for l in order], fontsize=4.4)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Held-out share given to each class", fontsize=FS_S)
        ax.legend(frameon=False, fontsize=4.2, loc="lower right")
    ax.tick_params(labelsize=4.6)
    ax.set_title("%s · %s: %s %.2f" % (VIEW_WORD[best["view"]], MODEL_WORD[best["model"]], SCORE_WORD[task], best["score"]["main"]), fontsize=4.8, loc="left", pad=2)
    # c, d: MOST IMPORTANT
    y2 = y + 82
    mi = (lb.get("most_important") or {}).get(t)
    if mi:
        text_mm(fig, H, 2, y2, "c  MOST IMPORTANT families  (%s)" % mi["basis"], fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 52, y2 + 4, 50, 36)
        fam = mi["families"][:8]
        ax.barh(range(len(fam)), [d["points"] for d in fam], color="#4C78A8", height=0.7)
        ax.set_yticks(range(len(fam)))
        ax.set_yticklabels([d["item"] for d in fam], fontsize=4.6)
        ax.invert_yaxis()
        ax.set_xlabel("points (rank points over methods and models, per model)", fontsize=FS_S - 0.4)
        ax.tick_params(labelsize=4.6)
        text_mm(fig, H, 2, y2 + 48, "d  MOST IMPORTANT features (each held-out method ranks them; points added over methods and models)", fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 96, y2 + 52, 80, 64)
        feat = mi["features"][:15]
        ax.barh(range(len(feat)), [d["points"] for d in feat], color="#B279A2", height=0.7)
        ax.set_yticks(range(len(feat)))
        ax.set_yticklabels(["%s  [%d methods, %d models]" % (human(d["item"]), d["n_methods"], d["n_models"]) for d in feat], fontsize=4.2)
        ax.invert_yaxis()
        ax.set_xlabel("points", fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
    note = {"pten_vs_ctl": "The nuisance-only baseline (above all the year recorded) gets 0.82, as high as the best spike-based model (0.83): controls and "
                           "PTEN mice were mostly recorded in different years, so this target cannot be told apart from when the mice were recorded.",
            "iedpos_vs_iedneg": "Nine mice (4 IED−, 5 IED+): AUC 0.95 is 19 of 20 IED−/IED+ pairs ordered right, and the best of 52 models can land there "
                                "by luck. Not yet checked against shuffled labels.",
            "ko_pct": "Rank correlation over 16 mice, 7 of them controls at 0 %: much of a high correlation can come from telling controls (0) from PTEN.",
            "ied3": "Macro AUC averages the three one-against-the-rest AUCs; three classes over 16 mice.",
            "low_vs_high": "Nine PTEN mice (3 low, 6 high): two models reached the bar (event context, set networks, 0.83 = 15 of 18 pairs); none did in run r003, on the data before the duplicate stamps came out."}.get(t, "")
    wrap(fig, H, 4, H - 19, "Read with care: " + note + " With one mouse left out, a model that learned nothing scores BELOW 0.5 (leaving a mouse "
         "out tilts the training set against its own class), so 0.5 is not the chance line here: the shuffled-label check is.", 172, fontsize=FS_S, color=RED)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Room2_results_%d_%s.png" % (k, t)), dpi=150)
    plt.close(fig)


def glossary(pdf, lb):
    H = 262.0
    fig = Hs.page(H)
    Hs.stamp(fig, "PRELIMINARY")
    text_mm(fig, H, 4, 6, "The measures named on these pages, in words", fontsize=10, fontweight="bold")
    seen = []
    for t, mi in (lb.get("most_important") or {}).items():
        for d in mi["features"][:15]:
            b = d["item"].split("|")[0]
            if b.startswith("f_"):
                b = b.split("__", 1)[1]
            if b in MS.EVENT_FEATURES and b not in seen:
                seen.append(b)
    y = 14
    for b in seen:
        y = wrap(fig, H, 4, y, "%s — %s" % (b.replace("_", " "), MS.EVENT_FEATURES[b][1]), 170, fontsize=FS_S + 0.2, color=INK) + 1.2
    y += 3
    for s in ("u: the blade-to-blade depth scale (0 = the upper blade's main sink, 1 = the lower blade's; negative = toward CA1).",
              "v: within one blade, 0 = the source on the cell-layer side, 1 = that blade's main sink, above 1 = farther out.",
              "Power over random moments: an event's band power divided by the mean over random moments of the same recording at the same contacts "
              "and time (log2; 0 = no different).",
              "Statistics over events: for each mouse, the median (or spread, mean, SD, 10th / 90th percentile) of the measure over its events; "
              "'DS1 median' = over its DS1 events only."):
        y = wrap(fig, H, 4, y, s, 170, fontsize=FS_S + 0.2, color=MUTE) + 1.2
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Room2_results_glossary.png"), dpi=150)
    plt.close(fig)


def results_pdf():
    Rs = load()
    lb = R.leaderboard(RUNS[0])
    # MOST IMPORTANT over the merged runs
    most = {}
    from backend.er2 import explain as EX
    for t in E.TARGETS:
        mine = [r for r in Rs if r["target"] == t and r["view"] != "nuisance"]
        good = [r for r in mine if r.get("passes")]
        why = "models that reached the bar"
        if not good:
            good = sorted(mine, key=lambda r: -(r["score"]["main"] if np.isfinite(r["score"]["main"]) else -9))[:3]
            why = "no model reached the bar: the three best"
        if good:
            most[t] = dict(EX.consolidate(good), basis=why)
    lb = {"most_important": most}
    with PdfPages(os.path.join(OUT, "Room2_results.pdf")) as pdf:
        overview(pdf, Rs)
        for k, t in enumerate(E.TARGETS, 2):
            target_page(pdf, Rs, lb, t, k)
        glossary(pdf, lb)
    print("tasks used", len(Rs))


if __name__ == "__main__":
    methods_pdf()
    results_pdf()
    print("saved", OUT)
