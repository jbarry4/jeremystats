"""The summary table: one row per recording, every classifier's separation
index as a colored cell, and the averages.
  round11/Summary_table.pdf / .png / .csv
"""
import csv
import os

import numpy as np

import dsdata
import house as Hs
import normcurves as N
from house import plt, INK, MUTE, HAIR, RED, FS_S

OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")
recs = [r for r in dsdata.load("v6") if not r.excluded]
order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.subgroup == "IED-"], key=lambda r: r.ko) + \
    sorted([r for r in recs if r.subgroup == "IED+"], key=lambda r: r.ko)
BASES = [("bite", "Bite line"), ("pca", "PCA, k-means"), ("pca_gap", "PCA + gap"), ("delta", "Delta"), ("delta_mid", "Delta middle")]
COLS = [(b + s, nm, {"": "both", "_top": "upper", "_bottom": "lower"}[s]) for b, nm in BASES for s in ("", "_top", "_bottom")] + \
    [("pca_gmm_line", "PCA mixture", "line"), ("pca_gmm_curve", "PCA mixture", "curve"), ("opt_line", "Optimized", "line"), ("opt_curve", "Optimized", "curve")]


def si_without_ds3(r, clf):
    m3 = r.ds3(clf)
    if m3 is None:
        return None, None
    t3 = r.types3(clf)
    keep = (t3 == 1) | (t3 == 2)
    if min((t3 == 1).sum(), (t3 == 2).sum()) < 5:
        return float(m3.mean()), None
    w = np.array(r.W["both"], float)[np.ix_(keep, keep)]
    np.fill_diagonal(w, 0.0)
    m = t3[keep] == 1
    na, nb = m.sum(), (~m).sum()
    Wm = w @ m
    saa, sab = float(m @ Wm), float((~m) @ Wm)
    sbb = float(w.sum()) - saa - 2 * sab
    return float(m3.mean()), 1.0 - (sab / (na * nb)) / ((saa / (na * (na - 1)) + sbb / (nb * (nb - 1))) / 2.0)


rows = []
for r in order:
    d = {"lab": r.lab, "group": r.subgroup, "ko": r.ko, "n": r.n, "si": {}, "el": {}}
    for clf, _, _ in COLS:
        if r.ok and r.has(clf):
            d["si"][clf], d["el"][clf] = r.si(clf), r.eligible(clf)
    el = [d["si"][c] for c in dsdata.CONVENTIONAL if d["el"].get(c)]
    d["mean"] = float(np.mean(el)) if el else None
    d["n_el"] = len(el)
    d["used"] = r.used
    d["best"] = r.si(r.used) if r.used else None
    d["heldout"] = r.labels["opt_curve"].get("heldout_si") if r.ok and r.has("opt_curve") else None
    d["ds3"], d["final"] = si_without_ds3(r, r.used) if r.used else (None, None)
    d["ds1"] = (r.types(r.used) == 1).mean() if r.used else None
    lit = [N.literature_ds3(r, b) for b in ("upper", "lower")] if r.ok else [None, None]
    d["lit"] = [None if x is None else x["share"][3] for x in lit]
    d["renamed"] = bool(r.used and "types_jarvis" in r.labels[r.used])
    d["names"] = r.naming.get(r.used, {}).get("verdict") if r.used else None
    rows.append(d)

# ------------------------------------------------------------------ drawing
CW, RH = 8.2, 5.4                         # cell width, row height (mm)
X0 = 44.0                                 # where the classifier cells start
extra = [("mean", "Mean of\neligible", 11), ("best", "Best\neligible", 10), ("heldout", "Optimized,\nheld out", 12), ("final", "Best, without\nDS3", 13),
         ("ds1", "DS1 %", 9), ("ds3", "DS3 %", 9), ("lit0", "DS3 %, paper's\nprocedure, upper", 15), ("lit1", "DS3 %, paper's\nprocedure, lower", 15)]
Wp = X0 + len(COLS) * CW + 4 + sum(e[2] for e in extra) + 42
Hp = 34 + (len(rows) + 5) * RH + 30
fig = plt.figure(figsize=(Wp / 25.4, Hp / 25.4))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, Wp)
ax.set_ylim(Hp, 0)
ax.axis("off")
ax.text(4, 6, "Separation of DS1 and DS2 in every recording, by every classifier", fontsize=9, fontweight="bold", va="center")
ax.text(4, 11, "Halo set; m6 left out (confounding factors during the experiment). Cell: separation index (1 = no overlap between DS1 and DS2, 0 = as much overlap as within a type). "
        "Gray italic: the classifier is not eligible there (one type under 5% of events). Red box: the best eligible classifier.", fontsize=FS_S, va="center", color=MUTE)
ytop = 30.0
for i, (clf, nm, sub) in enumerate(COLS):
    x = X0 + i * CW
    ax.text(x + CW / 2, ytop - 2.2, sub, fontsize=FS_S - 0.5, ha="center", va="center", color=MUTE)
    if sub in ("both", "line"):
        span = 3 if sub == "both" else 2
        ax.text(x + span * CW / 2, ytop - 6.5, nm, fontsize=FS_S, ha="center", va="center", fontweight="bold")
        ax.plot([x + 0.6, x + span * CW - 0.6], [ytop - 4.3] * 2, color=INK, lw=0.5)
xe = X0 + len(COLS) * CW + 4
xpos = {}
for key, nm, w in extra:
    xpos[key] = (xe, w)
    ax.text(xe + w / 2, ytop - 5.0, nm, fontsize=FS_S - 0.5, ha="center", va="center", linespacing=1.15)
    xe += w
for x, s in ((4, "Mouse"), (15, "Group"), (29, "KO %"), (37, "Events")):
    ax.text(x, ytop - 5.0, s, fontsize=FS_S, va="center", fontweight="bold")


def cell(x, y, w, v, eligible=True, ring=False, pct=False, cmap=Hs.SI_CMAP):
    if v is None or not np.isfinite(v):
        ax.text(x + w / 2, y + RH / 2, "·", fontsize=FS_S, ha="center", va="center", color=HAIR)
        return
    if eligible:
        ax.add_patch(plt.Rectangle((x + 0.25, y + 0.25), w - 0.5, RH - 0.5, color=cmap(float(np.clip(v, 0, 1))), lw=0))
    ax.text(x + w / 2, y + RH / 2, ("%.0f" % (100 * v)) if pct else ("%.2f" % (v if abs(v) >= 0.005 else 0.0)), fontsize=FS_S - 0.3, ha="center", va="center",
            color=(INK if v < 0.62 else "white") if eligible else "#A0A0A0", fontstyle="normal" if eligible else "italic",
            fontweight="normal")
    if ring:
        ax.add_patch(plt.Rectangle((x + 0.25, y + 0.25), w - 0.5, RH - 0.5, fill=False, edgecolor=RED, lw=1.0))


y = ytop
last = None
for d in rows:
    if last is not None and d["group"] != last:
        y += 1.6
    last = d["group"]
    ax.add_patch(plt.Rectangle((2, y + 0.6), 1.2, RH - 1.2, color=Hs.GROUP_COL[d["group"]], lw=0))
    ax.text(4, y + RH / 2, d["lab"], fontsize=FS_S, va="center", fontweight="bold")
    ax.text(15, y + RH / 2, Hs.GROUP_NAME[d["group"]].replace("PTEN ", ""), fontsize=FS_S, va="center")
    ax.text(29, y + RH / 2, "" if d["group"] == "CTL" else "%.1f" % d["ko"], fontsize=FS_S, va="center")
    ax.text(37, y + RH / 2, "%d" % d["n"], fontsize=FS_S, va="center")
    if d["n"] < 20:
        ax.text(X0, y + RH / 2, "too few events to classify", fontsize=FS_S, va="center", color=MUTE)
    else:
        for i, (clf, _, _) in enumerate(COLS):
            cell(X0 + i * CW, y, CW, d["si"].get(clf), d["el"].get(clf, False), clf == d["used"])
        cell(*xpos["mean"][:1], y, xpos["mean"][1], d["mean"])
        cell(xpos["best"][0], y, xpos["best"][1], d["best"])
        cell(xpos["heldout"][0], y, xpos["heldout"][1], d["heldout"])
        cell(xpos["final"][0], y, xpos["final"][1], d["final"])
        cell(xpos["ds1"][0], y, xpos["ds1"][1], d["ds1"], pct=True, cmap=plt.cm.Blues)
        cell(xpos["ds3"][0], y, xpos["ds3"][1], d["ds3"], pct=True, cmap=plt.cm.Greens)
        cell(xpos["lit0"][0], y, xpos["lit0"][1], d["lit"][0], pct=True, cmap=plt.cm.Greens)
        cell(xpos["lit1"][0], y, xpos["lit1"][1], d["lit"][1], pct=True, cmap=plt.cm.Greens)
        if d["names"] in ("swapped", "same place", "blades disagree"):
            ax.text(xe + 1, y + RH / 2, {"swapped": "names swapped from Jarvis's", "same place": "DS1, DS2 names arbitrary", "blades disagree": "names uncertain"}[d["names"]],
                    fontsize=FS_S - 0.5, va="center", color=RED)
    d["y"] = y
    y += RH
y += 3.0
ax.plot([2, xe], [y - 1.4] * 2, color=INK, lw=0.5)
for gname, sel in (("Mean, control", lambda d: d["group"] == "CTL"), ("Mean, PTEN IED−", lambda d: d["group"] == "IED-"),
                   ("Mean, PTEN IED+", lambda d: d["group"] == "IED+"), ("Mean, all PTEN", lambda d: d["group"] != "CTL")):
    ax.text(4, y + RH / 2, gname, fontsize=FS_S, va="center", fontweight="bold")
    grp = [d for d in rows if sel(d) and d["n"] >= 20]
    for i, (clf, _, _) in enumerate(COLS):
        v = [d["si"][clf] for d in grp if d["el"].get(clf)]
        cell(X0 + i * CW, y, CW, float(np.mean(v)) if v else None)
        ax.text(X0 + i * CW + CW - 0.6, y + 0.9, "%d" % len(v), fontsize=3.6, ha="right", va="center", color=MUTE)
    for key in ("mean", "best", "heldout", "final"):
        v = [d[key] for d in grp if d[key] is not None]
        cell(xpos[key][0], y, xpos[key][1], float(np.mean(v)) if v else None)
    for key, cm in (("ds1", plt.cm.Blues), ("ds3", plt.cm.Greens)):
        v = [d[key] for d in grp if d[key] is not None]
        cell(xpos[key][0], y, xpos[key][1], float(np.mean(v)) if v else None, pct=True, cmap=cm)
    for j in (0, 1):
        v = [d["lit"][j] for d in grp if d["lit"][j] is not None]
        cell(xpos["lit%d" % j][0], y, xpos["lit%d" % j][1], float(np.mean(v)) if v else None, pct=True, cmap=plt.cm.Greens)
    y += RH
notes = ["Group means use only the recordings where that classifier is eligible (small number in the cell's corner: how many).  ·  no value.",
         "Mean of eligible: the recording's average separation over its eligible conventional classifiers (the two optimized boundaries are left out: they were fitted to maximize the index).",
         "Optimized, held out: the optimized curve fitted on half the events and scored on the other half.  Best, without DS3: the best eligible classifier's index after its DS3 events are taken out.",
         "DS1 % and DS3 %: under the best eligible classifier; names checked against the anatomy (DS1 = sink farther from the cell layer; see the sanity check); DS3 layers looked for past the band.  Paper's procedure: Tarcsay et al. 2025, outer and middle layers from the two extreme quarters of PC1, one blade at a time; "
         "· where the two quarters' sinks peak at the same contact."]
for i, s_ in enumerate(notes):
    ax.text(4, y + 5 + 3.3 * i, s_, fontsize=FS_S - 0.5, va="center", color=MUTE)
fig.savefig(os.path.join(OUT, "Summary_table.pdf"))
fig.savefig(os.path.join(OUT, "Summary_table.png"), dpi=220)
plt.close(fig)
with open(os.path.join(OUT, "Summary_table.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["mouse", "group", "knockout_pct", "events"] + ["%s (%s)" % (nm, sub) for _, nm, sub in COLS] + ["eligible: " + c for c, _, _ in COLS] +
               ["mean of eligible", "best eligible classifier", "best index", "optimized held out", "best without DS3", "DS1 share", "DS3 share",
                "DS3 share paper upper", "DS3 share paper lower", "names check"])
    for d in rows:
        w.writerow([d["lab"], d["group"], d["ko"], d["n"]] + [("" if d["si"].get(c) is None else round(d["si"][c], 4)) for c, _, _ in COLS] +
                   [d["el"].get(c, "") for c, _, _ in COLS] + [d["mean"], d["used"], d["best"], d["heldout"], d["final"], d["ds1"], d["ds3"], d["lit"][0], d["lit"][1], d["names"]])
print("saved", OUT)
