"""The battery's two reports and their tables.
  battery_reports/uncorrected/Battery_UNCORRECTED.pdf, all_tests_UNCORRECTED.csv
  battery_reports/corrected/Battery_corrected.pdf, all_tests_corrected.csv
  battery_reports/measures.csv   (every measure: what it is and its 16 numbers)
  python make_reports.py
"""
import json
import os

import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

import house as Hs
from house import plt, ax_mm, text_mm, INK, MUTE, HAIR, RED, FS, FS_S, W

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "battery_reports")
T = pd.read_pickle(os.path.join(HERE, "merged", "tests.pkl"))
Mdf = pd.read_pickle(os.path.join(HERE, "merged", "measures.pkl"))
OMNI = json.load(open(os.path.join(HERE, "merged", "omnibus.json")))
CNAME = {
    "PTEN_vs_CTL": "PTEN against control", "KO_dose_PTEN": "Against % knockout, PTEN only", "KO_dose_all": "Against % knockout, all mice (controls at 0)",
    "highKO_vs_CTL": "PTEN with 15%+ knockout against control", "lowKO_vs_CTL": "PTEN under 10% knockout against control",
    "trend_CTL_lowKO_highKO": "Ordered trend: control, low knockout, high knockout", "IEDpos_vs_IEDneg": "PTEN IED+ against PTEN IED−",
    "IEDpos_vs_CTL": "PTEN IED+ against control", "IEDneg_vs_CTL": "PTEN IED− against control",
    "trend_CTL_IEDneg_IEDpos": "Ordered trend: control, IED−, IED+", "variance_PTEN_vs_CTL": "Spread, PTEN against control (Brown-Forsythe)"}
ORDER = list(CNAME)


def label(r):
    bits = [r["name"]]
    if r["variant"] and r["variant"] != "all":
        bits.append(r["variant"])
    if r["classifier"]:
        bits.append(r["classifier"])
    bits.append("Halo set" if r["event_set"] == "v6" else "Strict set")
    return "  ·  ".join(bits)


def concepts(df, k):
    """The k strongest tests, one per measure idea (the same measure under
    another classifier, type or event set is folded into its strongest)."""
    df = df.sort_values("p")
    seen, out = set(), []
    for _, r in df.iterrows():
        key = (r["family"], r["name"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
        if len(out) >= k:
            break
    return out


def table_page(title, sub, rows, corrected, stamp):
    H = 20 + 7.2 * len(rows) + 16
    fig = Hs.page(H)
    if stamp:
        Hs.stamp(fig)
    text_mm(fig, H, 4, 5, title, fontsize=9, fontweight="bold")
    text_mm(fig, H, 4, 10, sub, fontsize=FS_S, color=MUTE)
    cols = [(4, "Measure  ·  type  ·  classifier  ·  event set", "left"), (116, "n", "right"), (127, "effect", "right"), (139, "raw P", "right")]
    cols += ([(151, "q (family)", "right"), (164, "family-wise P", "right"), (179, "other set P", "right")] if corrected else
             [(152, "other set P", "right"), (165, "same sign,\nclassifiers", "right"), (179, "P < 0.05,\nclassifiers", "right")])
    for x, s, ha in cols:
        text_mm(fig, H, x, 15.5, s, fontsize=FS_S - 0.5, ha=ha, color=MUTE, linespacing=1.1)
    fig.add_artist(plt.Line2D([4 / W, 179 / W], [1 - 18 / H] * 2, color=INK, lw=0.5))
    for i, r in enumerate(rows):
        y = 21.5 + 7.2 * i
        fig.add_artist(plt.Rectangle((2 / W, 1 - (y + 1.6) / H), 1.0 / W, 3.2 / H, color={"timing": "#4C78A8", "waveform": "#F58518", "laminar": "#54A24B", "structure": "#B279A2", "filter": "#9D755D"}[r["family"]], lw=0))
        text_mm(fig, H, 4, y, label(r), fontsize=FS_S, fontweight="bold")
        text_mm(fig, H, 4, y + 3.0, r["desc"], fontsize=4.4, color=MUTE)
        text_mm(fig, H, 116, y, ("%d / %d" % (r["n_a"], r["n_b"])) if r["n_b"] else "%d" % r["n_a"], fontsize=FS_S, ha="right")
        text_mm(fig, H, 127, y, ("%+.2f" % r["effect"]).replace("-", "−"), fontsize=FS_S, ha="right")
        text_mm(fig, H, 139, y, "%.4f" % r["p"], fontsize=FS_S, ha="right", fontweight="bold")
        po = "–" if not np.isfinite(r["p_other_set"]) else ("%.3f%s" % (r["p_other_set"], "" if r["same_sign_other_set"] == 1 else " (opposite)"))
        if corrected:
            text_mm(fig, H, 151, y, "%.2f" % r["q_family"], fontsize=FS_S, ha="right", color=INK if r["q_family"] < 0.1 else MUTE)
            text_mm(fig, H, 164, y, "%.3f" % r["p_maxT"] if np.isfinite(r["p_maxT"]) else "–", fontsize=FS_S, ha="right", color=INK if r["p_maxT"] < 0.1 else MUTE)
            text_mm(fig, H, 179, y, po, fontsize=FS_S, ha="right")
        else:
            text_mm(fig, H, 152, y, po, fontsize=FS_S, ha="right")
            text_mm(fig, H, 165, y, "%.0f%% of %d" % (100 * r["share_same_sign"], r["n_variants"]) if r["n_variants"] > 1 else "–", fontsize=FS_S, ha="right")
            text_mm(fig, H, 179, y, "%.0f%%" % (100 * r["share_p05"]) if r["n_variants"] > 1 else "–", fontsize=FS_S, ha="right")
    yb = 21.5 + 7.2 * len(rows) + 2
    text_mm(fig, H, 4, yb, "Bar color: family (blue timing, orange waveform, green laminar, purple structure). Effect: rank-biserial for two groups (+ = the first-named group higher), rho or tau for dose and trends. "
            "n: first-named group / the other.", fontsize=FS_S - 0.6, color=MUTE)
    text_mm(fig, H, 4, yb + 3.2, ("q (family): Benjamini-Hochberg within this family and contrast. Family-wise P: against the strongest of all measures in this contrast when the mouse labels are shuffled." if corrected else
                                  "Other set P: the same measure on the other event set. Classifiers columns: over this measure's versions under other classifiers, the share with the same sign, and with the same sign and raw P < 0.05."),
            fontsize=FS_S - 0.6, color=MUTE)
    text_mm(fig, H, 4, yb + 6.4, "One row per measure idea: where a measure exists under several classifiers, types or event sets, its strongest version is the one listed.", fontsize=FS_S - 0.6, color=MUTE)
    return fig


def overview(corrected):
    H = 150.0
    fig = Hs.page(H)
    if not corrected:
        Hs.stamp(fig)
    text_mm(fig, H, 4, 5, "The test battery: %s" % ("corrected for the number of tests" if corrected else "raw P values, no correction"), fontsize=9, fontweight="bold")
    text_mm(fig, H, 4, 10.5, "%s measures (one number per mouse each), %s tests, on 16 recordings (control 7, PTEN 9: IED− 4, IED+ 5; m6 left out). A lead-finding pass on pilot data." % (
        format(len(Mdf), ","), format(len(T), ",")), fontsize=FS_S, color=MUTE)
    text_mm(fig, H, 4, 13.6, "Run 5 (2026-11-19): as run 4 (one classifier per recording, the winner), on the data with duplicate stamps removed and m1 on "
            "its Lock alignment; Halo and Strict sets.", fontsize=FS_S, color=MUTE)
    # a  how the P values are spread
    Hs.letter(fig, H, 2, 16, "a")
    ax = ax_mm(fig, H, 13, 24, 50, 36)
    ax.hist(T["p"], bins=np.linspace(0, 1, 41), color="#BFC5CC", lw=0)
    ax.axhline(len(T) / 40.0, color=RED, lw=0.7, ls=(0, (3, 2)))
    ax.set_xlabel("Raw P", fontsize=FS)
    ax.set_ylabel("Tests", fontsize=FS)
    ax.set_title("All tests (dashed: what chance alone gives)", fontsize=FS, loc="left", pad=3)
    # b  per contrast: hits against shuffled labels
    Hs.letter(fig, H, 70, 16, "b")
    ax = ax_mm(fig, H, 116, 24, 46, 36)
    cs = [c for c in ORDER if c in OMNI]
    for i, c in enumerate(cs):
        o = OMNI[c]
        ax.plot([0, 100.0 * o["null_95th"] / o["n_measures"]], [i, i], color="#BFC5CC", lw=4, solid_capstyle="butt")
        ax.plot([100.0 * o["null_median"] / o["n_measures"]] * 2, [i - 0.3, i + 0.3], color=MUTE, lw=0.8)
        ax.scatter([100.0 * o["observed_over_1.96"] / o["n_measures"]], [i], s=14, color=RED if o["p_more_hits_than_chance"] < 0.05 else INK, zorder=3)
        ax.text(1.02, i, "P = %.3f" % o["p_more_hits_than_chance"], transform=ax.get_yaxis_transform(), fontsize=FS_S - 0.5, va="center", ha="left", clip_on=False,
                color=RED if o["p_more_hits_than_chance"] < 0.05 else MUTE)
    ax.set_yticks(range(len(cs)))
    ax.set_yticklabels([CNAME[c] for c in cs], fontsize=FS_S - 0.5)
    ax.set_ylim(len(cs) - 0.5, -0.5)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Measures beyond |z| = 1.96 (%)", fontsize=FS)
    ax.set_title("Is there more than chance gives? dot: this data; bar: shuffled labels, up to the 95th percentile", fontsize=FS_S, loc="right", pad=3)
    # c  counts
    Hs.letter(fig, H, 2, 70, "c")
    text_mm(fig, H, 8, 73, "Tests by family and contrast: number run, and the share with raw P under 0.05 (5% is chance)", fontsize=FS)
    fams = [f for f in ["timing", "waveform", "laminar", "structure", "filter"] if (T["family"] == f).any()]
    for j, f in enumerate(fams):
        text_mm(fig, H, 82 + j * 21, 79, f, fontsize=FS_S, fontweight="bold", ha="center")
    for i, c in enumerate(ORDER):
        y = 84 + 4.3 * i
        text_mm(fig, H, 8, y, CNAME[c], fontsize=FS_S)
        for j, f in enumerate(fams):
            s = T[(T["contrast"] == c) & (T["family"] == f)]
            if len(s):
                sh = (s["p"] < 0.05).mean()
                text_mm(fig, H, 82 + j * 21, y, "%s   %.1f%%" % (format(len(s), ","), 100 * sh), fontsize=FS_S, ha="center", color=RED if sh > 0.10 else INK)
    y = 84 + 4.3 * len(ORDER) + 4
    if corrected:
        lines = ["After correction: tests with q under 0.10: %d over all tests, %d within their contrast, %d within their family and contrast. Family-wise P under 0.10: %d (under 0.05: %d)." % (
            (T.q_all < 0.10).sum(), (T.q_contrast < 0.10).sum(), (T.q_family < 0.10).sum(), (T.p_maxT < 0.10).sum(), (T.p_maxT < 0.05).sum()),
            "Under q 0.10 within family or contrast, or family-wise P under 0.10: " + ("; ".join(
                "%s (%s, %s; P %.2g, other set P %.2g)" % (r["name"], r["event_set"].replace("v6", "Halo").replace("v8", "Strict"), CNAME.get(r["contrast"], r["contrast"]),
                                                           r["p"], r["p_other_set"])
                for _, r in T[(T.q_contrast < 0.10) | (T.q_family < 0.10) | (T.p_maxT < 0.10)].head(4).iterrows()) or "none") + ".",
            "None is under q 0.10 over all tests unless the count above says so.",
            "b is the honest overall reading: for each contrast, how many measures look strong in this data against how many look strong when the mouse labels are shuffled (2,000 times).",
            "q: Benjamini-Hochberg false discovery rate. Family-wise P: the chance that the strongest of all measures in a contrast is this strong under shuffled labels; it allows for the measures being correlated."]
    else:
        lines = ["Raw P under 0.05: %s of %s tests (%.1f%%); under 0.01: %s; under 0.001: %s. Many measures are versions of one another (type, event set), so these counts are not independent." % (
            format((T.p < 0.05).sum(), ","), format(len(T), ","), 100 * (T.p < 0.05).mean(), format((T.p < 0.01).sum(), ","), format((T.p < 0.001).sum(), ",")),
            "Nothing on these pages is corrected for the number of tests. The corrected report is in the folder beside this one.",
            "b: for each contrast, the share of measures that look strong in this data (dot) against the same when the mouse labels are shuffled (bar)."]
    for i, s in enumerate(lines):
        text_mm(fig, H, 4, y + 3.3 * i, s, fontsize=FS_S - 0.3, color=INK if i == 0 else MUTE)
    return fig


def report(corrected):
    sub = os.path.join(OUT, "corrected" if corrected else "uncorrected")
    os.makedirs(sub, exist_ok=True)
    name = "Battery_corrected.pdf" if corrected else "Battery_UNCORRECTED.pdf"
    with PdfPages(os.path.join(sub, name)) as pdf:
        fig = overview(corrected)
        pdf.savefig(fig)
        fig.savefig(os.path.join(sub, name.replace(".pdf", "_overview.png")), dpi=200)
        plt.close(fig)
        if corrected:
            surv = T[(T.q_family < 0.10) | (T.p_maxT < 0.10)]
            rows = concepts(surv, 30)
            if rows:
                fig = table_page("What stands after correction (q within family and contrast under 0.10, or family-wise P under 0.10)",
                                 "%d tests in all; one row per measure idea" % len(surv), rows, True, False)
                pdf.savefig(fig)
                plt.close(fig)
        for c in ORDER:
            s = T[T["contrast"] == c]
            if s.empty:
                continue
            rows = concepts(s, 22)
            fig = table_page(CNAME[c], "%s tests; the 22 strongest measure ideas by raw P" % format(len(s), ","), rows, corrected, not corrected)
            pdf.savefig(fig)
            plt.close(fig)
    keep = ["family", "name", "variant", "classifier", "event_set", "contrast", "test", "n_a", "n_b", "est_a", "est_b", "effect", "effect_kind", "p", "p_alt", "alt_kind",
            "p_alt2", "alt2_kind", "p_other_set", "same_sign_other_set", "n_variants", "share_same_sign", "share_p05",
            "rho_log_events", "rho_minutes", "rho_year", "rho_bad_contacts", "rho_band_contacts", "rho_blade_um", "id"]
    if corrected:
        keep = keep[:14] + ["q_all", "q_contrast", "q_family", "p_maxT"] + keep[14:]
    T.sort_values("p")[keep].to_csv(os.path.join(sub, "all_tests_corrected.csv" if corrected else "all_tests_UNCORRECTED.csv"), index=False, float_format="%.5g")
    return sub


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    Mdf.to_csv(os.path.join(OUT, "measures.csv"), index=False, float_format="%.6g")
    for cor in (False, True):
        print("saved", report(cor))
