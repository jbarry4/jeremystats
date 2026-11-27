"""Supplemental figures (round11/Supplemental_figures.pdf): how the
classification choices behave.
  python make_supplement.py
"""
import os

import numpy as np
from sklearn.metrics import adjusted_rand_score

import dsdata
import house as Hs
import normcurves as N
from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, RED, C_DS3, FS, FS_S

OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")
recs = [r for r in dsdata.load("v6") if r.ok]
GC = {"CTL": Hs.C_CTL, "IED-": Hs.C_IEDN, "IED+": Hs.C_IEDP}
H = 206.0
fig = Hs.page(H)
text_mm(fig, H, 4, 5, "Supplemental: how the classification choices behave", fontsize=9, fontweight="bold")

# a  the best eligible index under each minimum type size, every recording
letter(fig, H, 2, 11, "a")
ax = ax_mm(fig, H, 14, 19, 46, 38)
ths = [0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15]
for r in recs:
    y = []
    for th in ths:
        v = [r.si(c) for c in dsdata.CONVENTIONAL if r.has(c) and min(r.labels[c]["n1"], r.labels[c]["n2"]) >= max(5, th * r.n)]
        y.append(max(v) if v else np.nan)
    ax.plot([100 * t for t in ths], y, color=Hs.col_of(r), lw=0.8, marker="o", ms=1.8, alpha=0.9)
    ax.text(15.4, y[-1], r.lab, fontsize=3.8, color=Hs.col_of(r), va="center")
ax.axvline(5, color=HAIR, lw=0.6, zorder=0)
ax.text(5.3, 1.0, "rule used", fontsize=FS_S - 0.5, color=MUTE, va="top")
ax.set_xlim(0, 17.5)
ax.set_xlabel("Smallest share of events a type must hold (%)\n(0 = 5 events)", fontsize=FS)
ax.set_ylabel("Best eligible separation index", fontsize=FS)
ax.set_ylim(-0.03, 1.03)
ax.set_title("The minimum type size", fontsize=FS, loc="left", pad=3)

# b  the optimized boundary: fitted against held out
letter(fig, H, 66, 11, "b")
ax = ax_mm(fig, H, 78, 19, 40, 38)
for r in recs:
    if r.has("opt_curve") and r.labels["opt_curve"].get("heldout_si") is not None:
        ax.scatter([r.si("opt_curve")], [r.labels["opt_curve"]["heldout_si"]], s=14, color=Hs.col_of(r), edgecolor="white", linewidth=0.4, zorder=3)
ax.plot([0, 1], [0, 1], color=HAIR, lw=0.6, zorder=0)
ax.set_xlim(-0.02, 1)
ax.set_ylim(-0.05, 1)
ax.set_xlabel("Index on the events it was fitted to", fontsize=FS)
ax.set_ylabel("Index on held-out events", fontsize=FS)
ax.set_title("The optimized boundary overfits little", fontsize=FS, loc="left", pad=3)

# c  DS3 share against the spacing of the two layer contacts
letter(fig, H, 124, 11, "c")
ax = ax_mm(fig, H, 136, 19, 43, 38)
rng = np.random.default_rng(2)
gx, gy = [], []
for r in recs:
    for c in dsdata.CLASSIFIERS:
        if r.has(c) and r.eligible(c) and r.ds3(c) is not None:
            gx.append(r.ds3_gap_um[c])
            gy.append(100 * r.ds3(c).mean())
gx, gy = np.array(gx), np.array(gy)
ax.scatter(gx + rng.uniform(-12, 12, gx.size), gy, s=4, color=C_DS3, alpha=0.4, linewidth=0, label="this work: layers from DS1 and DS2 means")
lx, ly = [], []
for r in recs:
    for b in ("upper", "lower"):
        L = N.literature_ds3(r, b)
        if L is not None:
            lx.append(L["gap_um"])
            ly.append(100 * L["share"][3])
lx, ly = np.array(lx), np.array(ly)
ax.scatter(lx + rng.uniform(-12, 12, lx.size), ly, s=13, facecolor="none", edgecolor=INK, linewidth=0.6, label="the paper's procedure (PC1 quarters)")
ax.axhline(27, color=MUTE, lw=0.5, ls=(0, (3, 2)))
ax.text(398, 29, "reported: 16-28%", fontsize=FS_S - 0.5, color=MUTE, ha="right", va="bottom")
ax.set_xlim(0, 400)
ax.set_ylim(-3, 103)
ax.set_xlabel("How far apart the two contacts used as\nouter and middle layer are (µm)", fontsize=FS)
ax.set_ylabel("Events scored DS3 (%)", fontsize=FS)
ax.legend(frameon=False, fontsize=FS_S - 0.5, loc="center right", handletextpad=0.3, borderaxespad=0.1, bbox_to_anchor=(1.0, 0.47))
ax.set_title("DS3 share against that distance", fontsize=FS, loc="left", pad=3)

# d  separability against things that should not matter
for j, (key, xl, fn, logx) in enumerate((("n", "Events in the recording", lambda r: r.n, True), ("dur", "Recording length (min)", lambda r: r.dur_min, False),
                                          ("year", "Year recorded", lambda r: r.year + (int(r.date[5:7]) - 1) / 12.0, False))):
    letter(fig, H, 2 + j * 44, 72, "def"[j])
    ax = ax_mm(fig, H, 14 + j * 44, 80, 32, 32)
    for r in recs:
        ax.scatter([fn(r)], [r.si(r.used)], s=14, color=Hs.col_of(r), edgecolor="white", linewidth=0.4, zorder=3)
    if logx:
        ax.set_xscale("log")
        ax.set_xticks([100, 200, 400, 700])
        ax.set_xticklabels(["100", "200", "400", "700"])
        ax.minorticks_off()
    if key == "year":
        ax.set_xticks([2023, 2024, 2025, 2026])
        ax.set_xticklabels(["2023", "2024", "2025", ""])
    ax.set_ylim(-0.03, 1)
    ax.set_xlabel(xl, fontsize=FS)
    if j == 0:
        ax.set_ylabel("Best eligible index", fontsize=FS)
    ax.set_title(("Best index against event count", "against recording length", "against date")[j], fontsize=FS, loc="left", pad=3)

# g  agreement between classifiers
letter(fig, H, 136, 72, "g")
conv = dsdata.CONVENTIONAL
A = np.full((len(conv), len(conv)), np.nan)
for i, a in enumerate(conv):
    for j, b in enumerate(conv):
        v = [adjusted_rand_score(r.types(a), r.types(b)) for r in recs if r.has(a) and r.has(b) and r.eligible(a) and r.eligible(b)]
        if len(v) >= 3:
            A[i, j] = np.mean(v)
ax = ax_mm(fig, H, 152, 80, 27, 27)
im = ax.imshow(A, cmap=Hs.SI_CMAP, vmin=0, vmax=1)
ax.set_xticks([])
ax.set_yticks(range(len(conv)))
ax.set_yticklabels([c.replace("pca_gmm", "mixture").replace("_", " ") for c in conv], fontsize=3.8)
ax.tick_params(axis="y", length=0, pad=1)
ax.set_title("Classifier agreement", fontsize=FS, loc="left", pad=3)
cax = ax_mm(fig, H, 152, 110, 27, 1.5)
cax.imshow(np.linspace(0, 1, 100)[None, :], aspect="auto", cmap=Hs.SI_CMAP, extent=[0, 1, 0, 1])
cax.set_yticks([])
cax.set_xticks([0, 0.5, 1])
cax.tick_params(labelsize=FS_S - 0.5)
cax.set_xlabel("mean adjusted Rand index", fontsize=FS_S - 0.5)

# h  how far apart DS1's and DS2's sinks sit, against the index
letter(fig, H, 2, 124, "h")
ax = ax_mm(fig, H, 14, 132, 46, 36)
for r in recs:
    dd = r.naming.get(r.used, {}).get("diff", [np.nan, np.nan])
    if np.isfinite(dd).any():
        ax.scatter([r.si(r.used)], [np.nanmean(dd)], s=14, color=Hs.col_of(r), edgecolor="white", linewidth=0.4, zorder=3)
        ax.annotate(r.lab, (r.si(r.used), np.nanmean(dd)), xytext=(2.5, 0), textcoords="offset points", fontsize=3.8, color=MUTE, va="center")
ax.axhline(0, color=HAIR, lw=0.6, zorder=0)
ax.set_xlim(-0.02, 1)
ax.set_xlabel("Best eligible separation index", fontsize=FS)
ax.set_ylabel("DS1's sink farther from the cell layer\nthan DS2's (µm, mean of blades)", fontsize=FS)
ax.set_title("How far apart the two types' sinks sit", fontsize=FS, loc="left", pad=3)

# i  the paper's procedure: can it place the layers?
letter(fig, H, 66, 124, "i")
ax = ax_mm(fig, H, 78, 132, 100, 36)
x = 0
ticks, labs = [], []
for sg in ("CTL", "IED-", "IED+"):
    for r in sorted([r for r in recs if r.subgroup == sg], key=lambda r: r.ko):
        for k, b in enumerate(("upper", "lower")):
            L = N.literature_ds3(r, b)
            xx = x + (k - 0.5) * 0.36
            if L is None:
                ax.text(xx, 2, "×", fontsize=FS, ha="center", va="bottom", color=MUTE)
                continue
            bot = 0
            for c, col in ((1, Hs.C_DS1), (3, C_DS3), (2, Hs.C_DS2), (0, "#D0D0D0")):
                ax.bar([xx], [100 * L["share"][c]], bottom=bot, width=0.32, color=col, lw=0)
                bot += 100 * L["share"][c]
        ticks.append(x)
        labs.append(r.lab)
        x += 1
    x += 0.5
ax.set_xticks(ticks)
ax.set_xticklabels(labs, fontsize=FS_S - 0.5)
ax.set_ylim(0, 100)
ax.set_ylabel("Events (%)", fontsize=FS)
ax.set_title("The paper's procedure on each recording (left bar: upper blade; right bar: lower blade)", fontsize=FS, loc="left", pad=3)
notes = ["m6 is left out (confounding factors during the experiment). a: each recording's best separation index among the conventional classifiers whose smaller type holds at least the share on the x axis.",
         "b: the boundary fitted to maximize the index, scored on the half of the events it did not see.",
         "c: DS3 share against how far apart (µm) the two contacts the score compares are; every recording under every eligible classifier (green), and the paper's procedure one blade at a time (black rings).",
         "    d-f: the best eligible index against event count, recording length and date.",
         "g: mean over recordings of the adjusted Rand index between each pair of conventional classifiers (where both are eligible). h: under the best eligible classifier, names checked (sanity check).",
         "i: Tarcsay et al. 2025: outer and middle layers from the two extreme quarters of PC1, relative sink within ±0.5 = DS3. DS1 blue, DS3 green, DS2 orange, unscored gray; × the layers cannot be placed.",
         "    Our probe has 50 µm between contacts; theirs 20-25 µm."]
for i, s in enumerate(notes):
    text_mm(fig, H, 4, 180 + 3.2 * i, s, fontsize=FS_S - 0.6, color=MUTE)
fig.savefig(os.path.join(OUT, "Supplemental_figures.pdf"))
fig.savefig(os.path.join(OUT, "Supplemental_figures.png"), dpi=200)
print("saved")
