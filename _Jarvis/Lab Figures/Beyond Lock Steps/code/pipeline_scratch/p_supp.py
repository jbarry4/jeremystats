import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_supplement.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('round10/Supplemental_figures.pdf', 'round11/Supplemental_figures.pdf')
rep('OUT = os.path.join(os.path.dirname(dsdata.HERE), "round10")', 'OUT = os.path.join(os.path.dirname(dsdata.HERE), "round11")')
i0 = s.index("# a  the minimum type size")
i1 = s.index("# b  the optimized boundary")
s = s[:i0] + '''# a  the best eligible index under each minimum type size, every recording
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
ax.set_xlabel("Smallest share of events a type must hold (%)\\n(0 = 5 events)", fontsize=FS)
ax.set_ylabel("Best eligible separation index", fontsize=FS)
ax.set_ylim(-0.03, 1.03)
ax.set_title("The minimum type size", fontsize=FS, loc="left", pad=3)

''' + s[i1:]
rep('''ax.set_xlabel("Distance between the outer and middle\\nlayer contacts (µm)", fontsize=FS)''',
    '''ax.set_xlabel("How far apart the two contacts used as\\nouter and middle layer are (µm)", fontsize=FS)''')
rep('''ax.set_title("DS3 follows contact spacing", fontsize=FS, loc="left", pad=3)''', '''ax.set_title("DS3 share against that distance", fontsize=FS, loc="left", pad=3)''')
rep('''    ax.axhline(dsdata.SEPARABLE, color=HAIR, lw=0.6, zorder=0)
''', '')
i0 = s.index("# h  where DS1 sits relative to DS2")
i1 = s.index("# i  the paper's procedure")
s = s[:i0] + '''# h  how far apart DS1's and DS2's sinks sit, against the index
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
ax.set_ylabel("DS1's sink farther from the cell layer\\nthan DS2's (µm, mean of blades)", fontsize=FS)
ax.set_title("How far apart the two types' sinks sit", fontsize=FS, loc="left", pad=3)

''' + s[i1:]
rep('''notes = ["a: a recording counts as separable when a conventional classifier reaches an index of 0.45 with each type holding at least the share on the x axis.",''',
    '''notes = ["m6 is left out (confounding factors during the experiment). a: each recording's best separation index among the conventional classifiers whose smaller type holds at least the share on the x axis.",''')
rep('''"c: every recording under every eligible classifier (green) and under the paper's procedure, one blade at a time (black rings). d-f: the best eligible index against event count, recording length and date.",''',
    '''"c: DS3 share against how far apart (µm) the two contacts the score compares are; every recording under every eligible classifier (green), and the paper's procedure one blade at a time (black rings).",
         "    d-f: the best eligible index against event count, recording length and date.",''')
rep('''"g: mean over recordings of the adjusted Rand index between each pair of conventional classifiers (where both are eligible). h: DS1's sink centroid over DS2's, both as distances from the source between the blades.",''',
    '''"g: mean over recordings of the adjusted Rand index between each pair of conventional classifiers (where both are eligible). h: under the best eligible classifier, names checked (sanity check).",''')
rep('''H = 202.0''', '''H = 206.0''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
