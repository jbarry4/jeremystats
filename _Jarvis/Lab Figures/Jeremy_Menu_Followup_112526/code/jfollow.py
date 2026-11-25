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


if __name__ == "__main__":
    os.makedirs(os.path.join(DEST, "tables"), exist_ok=True)
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
