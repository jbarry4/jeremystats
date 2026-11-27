"""The ten most interesting leads from the UNCORRECTED battery, one page
each: battery_reports/uncorrected/Top10_leads_UNCORRECTED.pdf
The list and the words are in top10.json (chosen by hand from the
uncorrected table: effect size, the other event set, other classifiers,
confounds and biology, not only the smallest P).
  python make_top10.py
"""
import json
import os
import textwrap

import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

import house as Hs
from house import plt, ax_mm, text_mm, INK, MUTE, HAIR, RED, FS, FS_S, W
from make_reports import CNAME

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "battery_reports", "uncorrected")
T = pd.read_pickle(os.path.join(HERE, "merged", "tests.pkl"))
Mdf = pd.read_pickle(os.path.join(HERE, "merged", "measures.pkl")).set_index("id")
META = [m for m in json.load(open(os.path.join(HERE, "data", "meta.json"))) if m["n_v6"] >= 20 and m["lab"] not in ("m6",)]
LEADS = json.load(open(os.path.join(HERE, "top10.json"), encoding="utf-8"))


def wrap(fig, H, x, y, s, width=150, **kw):
    lines = textwrap.wrap(s, width)
    for i, ln in enumerate(lines):
        text_mm(fig, H, x, y + 3.3 * i, ln, **kw)
    return y + 3.3 * len(lines)


def lead_page(k, L):
    H = 150.0
    fig = Hs.page(H)
    Hs.stamp(fig)
    m = Mdf.loc[L["id"]]
    rows = T[T["id"] == L["id"]].set_index("contrast")
    r = rows.loc[L["contrast"]]
    text_mm(fig, H, 4, 5, "Lead %d.  %s" % (k, L["title"]), fontsize=9, fontweight="bold")
    y = wrap(fig, H, 4, 10.5, "Measure: %s%s.  Event set: %s." % (m["desc"], (" [%s]" % m["unit"]) if m["unit"] else "", "Halo" if m["event_set"] == "v6" else "No P-spikes"), 175,
             fontsize=FS_S, color=MUTE)
    vals = np.array([m[x["lab"]] for x in META], float)
    sg = np.array([x["subgroup"] for x in META])
    ko = np.array([x["ko"] for x in META], float)
    cols = [Hs.C_CTL if x["group"] == "CTL" else Hs.KO_CMAP(Hs.KO_NORM(x["ko"])) for x in META]
    # a  by group
    ax = ax_mm(fig, H, 16, 28, 52, 44)
    rng = np.random.default_rng(3)
    for i, g in enumerate(("CTL", "IED-", "IED+")):
        idx = np.where((sg == g) & np.isfinite(vals))[0]
        xs = i + rng.uniform(-0.17, 0.17, idx.size)
        ax.scatter(xs, vals[idx], s=18, c=[cols[j] for j in idx], edgecolor="white", linewidth=0.4, zorder=3)
        for xx, j in zip(xs, idx):
            ax.annotate(META[j]["lab"], (xx, vals[j]), xytext=(3, 0), textcoords="offset points", fontsize=4.2, va="center", color=MUTE)
        if idx.size:
            ax.plot([i - 0.3, i + 0.3], [np.median(vals[idx])] * 2, color=INK, lw=1.0, zorder=4)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["Control\n(n = %d)" % ((sg == "CTL") & np.isfinite(vals)).sum(), "PTEN IED−\n(n = %d)" % ((sg == "IED-") & np.isfinite(vals)).sum(),
                        "PTEN IED+\n(n = %d)" % ((sg == "IED+") & np.isfinite(vals)).sum()], fontsize=FS_S)
    ax.set_xlim(-0.6, 2.75)
    ax.set_ylabel(L.get("ylabel", m["name"]) + ((" (%s)" % m["unit"]) if m["unit"] else ""), fontsize=FS)
    # b  against knockout
    ax = ax_mm(fig, H, 84, 28, 46, 44)
    ok = np.isfinite(vals)
    xs = np.where(sg == "CTL", rng.uniform(-1.8, 1.8, ko.size), ko)
    ax.scatter(xs[ok], vals[ok], s=18, c=[c for c, o in zip(cols, ok) if o], edgecolor="white", linewidth=0.4, zorder=3)
    ax.set_xticks([0, 10, 20, 30])
    ax.set_xticklabels(["Control", "10", "20", "30"])
    ax.set_xlabel("PTEN knockout (% of granule cells)", fontsize=FS)
    # c  the numbers
    x0 = 138
    text_mm(fig, H, x0, 29, "This contrast", fontsize=FS, fontweight="bold")
    text_mm(fig, H, x0, 33, CNAME[L["contrast"]], fontsize=FS_S)
    lines = ["%s: effect %s, raw P = %.4f" % (r["test"], ("%+.2f" % r["effect"]).replace("-", "−"), r["p"])]
    if np.isfinite(r["p_alt"]):
        lines.append("%s: P %s" % (r["alt_kind"], "< 0.0001" if r["p_alt"] < 1e-4 else "= %.4f" % r["p_alt"]))
    if np.isfinite(r["p_alt2"]):
        lines.append("%s: P %s" % (r["alt2_kind"], "< 0.0001" if r["p_alt2"] < 1e-4 else "= %.4f" % r["p_alt2"]))
    lines.append("Other event set: " + ("not available" if not np.isfinite(r["p_other_set"]) else "P = %.3f, %s sign" % (r["p_other_set"], "same" if r["same_sign_other_set"] == 1 else "opposite")))
    if r["n_variants"] > 1:
        lines.append("Other classifiers: %.0f%% of %d same sign," % (100 * r["share_same_sign"], r["n_variants"]))
        lines.append("    %.0f%% also raw P < 0.05" % (100 * r["share_p05"]))
    lines.append("After correction: q (family) = %.2f," % r["q_family"])
    lines.append("    family-wise P = %.2f" % r["p_maxT"] if np.isfinite(r["p_maxT"]) else "    family-wise P not computed")
    for i, s in enumerate(lines):
        text_mm(fig, H, x0, 37.5 + 3.4 * i, s, fontsize=FS_S, color=RED if s.startswith("After") or s.startswith("    family") else INK)
    yy = 37.5 + 3.4 * len(lines) + 2.5
    text_mm(fig, H, x0, yy, "Tracks things it should not?", fontsize=FS, fontweight="bold")
    for i, (key, nm) in enumerate((("rho_log_events", "event count"), ("rho_minutes", "recording length"), ("rho_year", "year recorded"), ("rho_blade_um", "blade distance"))):
        v = m[key]
        text_mm(fig, H, x0, yy + 4 + 3.4 * i, "rho with %s: %s" % (nm, "–" if not np.isfinite(v) else ("%+.2f" % v).replace("-", "−")), fontsize=FS_S,
                color=RED if np.isfinite(v) and abs(v) >= 0.5 else INK)
    # d  every contrast of this measure
    text_mm(fig, H, 4, 84, "The same measure in every contrast (raw P)", fontsize=FS, fontweight="bold")
    cs = [c for c in CNAME if c in rows.index]
    for i, c in enumerate(cs):
        col_, row_ = i % 2, i // 2
        rr = rows.loc[c]
        text_mm(fig, H, 4 + col_ * 90, 88.5 + 3.4 * row_, "%s: effect %s, P = %.3f" % (CNAME[c], ("%+.2f" % rr["effect"]).replace("-", "−"), rr["p"]), fontsize=FS_S,
                color=INK if c == L["contrast"] else MUTE, fontweight="bold" if c == L["contrast"] else "normal")
    y = 88.5 + 3.4 * ((len(cs) + 1) // 2) + 4
    for head, key in (("Why it is interesting", "why"), ("What speaks against it", "against"), ("What would test it", "test")):
        text_mm(fig, H, 4, y, head, fontsize=FS, fontweight="bold")
        y = wrap(fig, H, 4, y + 3.6, L[key], 165, fontsize=FS_S) + 2.2
    return fig


if __name__ == "__main__":
    with PdfPages(os.path.join(OUT, "Top10_leads_UNCORRECTED.pdf")) as pdf:
        for k, L in enumerate(LEADS, 1):
            fig = lead_page(k, L)
            pdf.savefig(fig)
            if k <= 2:
                fig.savefig(os.path.join(OUT, "Top10_lead_%d.png" % k), dpi=200)
            plt.close(fig)
    print("saved", len(LEADS))
