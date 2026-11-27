"""deep_qc5.py -> deep_qc11.py: round 11 of the quality check (2026-11-17)."""
import io
import re

SRC = r"C:\Users\Z390\AppData\Local\Temp\claude\4f94f33fe0a28c30\7a6601ed-d746-46d4-b1b0-3073ab9de62e\scratchpad\deep_qc5.py"
DST = SRC.replace("deep_qc5.py", "deep_qc11.py")
s = io.open(SRC, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:80], s.count(a))
    s = s.replace(a, b)


rep('round10\\quality_check"', 'round11\\quality_check"')
rep('''SEP = [r_ for r_ in RECS.values() if r_.ok and r_.separable()]
''', '')
rep('''H = 386.0''', '''H = 380.0''')
# no verdict words
rep('''def word(si):
    return "separable" if si >= 0.45 else ("partial" if si >= 0.2 else "not separable")''', '''def word(si):
    return ""''')
rep('''"Separation index %.2f, %s.   DS1 %d events (%.0f%%), DS2 %d." % (e["si"], word(e["si"]), e["n1"], 100.0 * e["n1"] / d["n"], e["n2"]),''',
    '''"Separation index %.2f.   DS1 %d events (%.0f%%), DS2 %d.%s" % (e["si"], e["n1"], 100.0 * e["n1"] / d["n"], e["n2"], renamed),''')
rep('''"Separation index %.2f, %s.   DS1 %d (%.0f%%), DS2 %d.%s%s   %d events (%.0f%%) differ from row 1." % (
            e2["si"], word(e2["si"]), int((t2 == 1).sum()),''', '''"Separation index %.2f.   DS1 %d (%.0f%%), DS2 %d.%s%s   %d events (%.0f%%) differ from row 1." % (
            e2["si"], int((t2 == 1).sum()),''')
rep('''"Separation index %.2f (%s on held-out events), %s.   DS1 %d (%.0f%%), DS2 %d.   %d events (%.0f%%) differ from row 1 (ringed)." % (
                oc["si"], "%.2f" % oc["heldout"] if oc.get("heldout") is not None else "not measured", word(oc["si"]),''',
    '''"Separation index %.2f (%s on held-out events).   DS1 %d (%.0f%%), DS2 %d.   %d events (%.0f%%) differ from row 1 (ringed)." % (
                oc["si"], "%.2f" % oc["heldout"] if oc.get("heldout") is not None else "not measured",''')
rep('''    for lo, hi, c in ((0, 0.2, "#F3F3F3"), (0.2, 0.45, "#E9E9E9"), (0.45, 1.0, "#DEDEDE")):
        ax.axvspan(lo, hi, color=c, lw=0, zorder=0)
''', '''    ax.axvspan(0, 1, color="#F3F3F3", lw=0, zorder=0)
''')
# names by anatomy (m13), counts from the names used
rep('''    ty = e["types"]
    Q, O =''', '''    ty = np.asarray(e["types"], int)
    R_ = RECS[d["lab"]]
    renamed = ""
    if R_.naming.get(m, {}).get("verdict") == "swapped":
        ty = 3 - ty
        renamed = "   Names swapped from Jarvis's (sanity check)."
    e = dict(e, n1=int((ty == 1).sum()), n2=int((ty == 2).sum()))
    Q, O =''')
# DS3 from the battery dataset: layers looked for past the analyzed band
rep('''    src = (DS3.get(d["gid"]) or {}).get(key)
    if src is None:
        e_ = d["splits"].get(key) or {}
        src = e_ if ("score" in e_ or e_.get("why")) and e_.get("why") != "not scored for DS3" else None
    n = ty.size
    if src is None or src.get("why") or "score" not in src:''', '''    src = RECS[d["lab"]].ds3w.get(key)
    n = ty.size
    if src is None or src.get("why") or "score" not in src:''')
rep('''"gap": abs(src["oml"] - src["mml"]) * 50,''', '''"gap": src["gap_um"],''')
# row 4: one figure
i0 = s.index("def row4(fig, y0, d):")
i1 = s.index("order = [d for d in recs")
s = s[:i0] + '''def row4(fig, y0, d):
    """DS1 and DS2 without DS3, depth normalized, against the group (one figure)."""
    r = RECS[d["lab"]]
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    k = r.landmarks
    grp = GROUPS[r.group]
    fig.add_artist(Rectangle((4 / W, 1 - (y0 + 5.4) / H), 1.2 / W, 5.4 / H, color=G.col_of(d), lw=0, transform=fig.transFigure))
    fig.text(7 / W, 1 - (y0 + 1.6) / H, "4   DS1 and DS2 without DS3, depth normalized, against %s" % ("the other controls" if r.group == "CTL" else "the other PTEN recordings"),
             fontsize=7.5, fontweight="bold", ha="left", va="center", color=INK)
    me = NC.typed_u(r)
    top, hh = y0 + 9.0, 39.0
    ax = ax_mm(18, top, 44, hh)
    for c_, col in ((2, C_DS2), (1, C_DS1)):
        Y = np.array([NC.typed_u(x)[c_] for x in grp if x.lab != r.lab and NC.typed_u(x)[c_] is not None])
        if Y.size:
            mu = np.nanmean(Y, axis=0)
            kk = np.isfinite(Y).sum(axis=0)
            mu[kk < max(2, 0.6 * Y.shape[0])] = np.nan
            ax.plot(mu, NC.GRID_U, color=col, lw=0.8, ls=(0, (3, 2)), alpha=0.85)
        if me[c_] is not None:
            ax.plot(me[c_], NC.GRID_U, color=col, lw=1.4)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    for yv in (0, 1):
        ax.axhline(yv, color=HAIR, lw=0.5, zorder=0)
    for su in me["src_u"]:
        ax.plot([1.0], [su], marker="<", color=RED, ms=3.2, transform=ax.get_yaxis_transform(), clip_on=False)
    ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper blade's sink", "lower blade's sink"], fontsize=FS_S)
    ax.set_xlabel("CSD at the DS peak (left = sink)" + chr(10) + "1 = this recording's average sink", fontsize=FS_S)
    ax.set_title("Solid: this recording.  Dashed: mean of the others in its group", fontsize=FS_S, loc="left", pad=3)
    lines = ["How it is normalized.  Depth: 0 is where this recording's average dentate spike (all %d events) has its deepest sink in the upper blade, 1 the same in" % r.n,
             "the lower blade (%.0f µm apart here). Every recording is stretched to that ruler, so the two blades line up whatever the probe's track." % k["blade_um"],
             "Size: CSD divided by the depth of that average sink (mean of the two blades), the same number for DS1 and DS2, so their sizes still compare.",
             "Red ticks: the source on the cell-layer side of each blade.",
             "",
             "DS1 and DS2 from row 1's classifier, the DS3 events taken out: DS1 %d events, DS2 %d.%s" % (
                 me["n"][1], me["n"][2], "" if (me[1] is not None and me[2] is not None) else "  A type with fewer than 5 events is not drawn.")]
    import textwrap as _tw
    yy_ = top + 3
    for t_ in _tw.wrap(" ".join(x for x in lines[:4]), 104) + [""] + _tw.wrap(lines[5], 104):
        fig.text(76 / W, 1 - yy_ / H, t_, fontsize=FS_S, ha="left", va="center", color=INK)
        yy_ += 3.5


''' + s[i1:]
rep('''        if only and d["lab"] not in only:
            continue''', '''        if only and d["lab"] not in only:
            continue
        if d["lab"] in dsdata.EXCLUDED:
            continue''')
rep('''    row4(fig, 76.0 + 3 * 68.0, d)''', '''    row4(fig, 76.0 + 3 * 68.0, d)''')
rep('''        "Row 4.  Depth normalized by this recording's own landmarks (blue ticks: the two main sinks; red ticks: the source next to each). Gray band: mean ± s.e.m. of the recording's group; "
        "dashed: mean of the six separable recordings.",''', '''        "Names.  DS1 is the type whose sink sits farther from the cell layer, checked in both blades (Jarvis's rule had m13 the other way round). m6 is left out (confounding factors during the experiment).",''')
rep('''        "molecular layer contacts are where DS1's and DS2's mean sinks peak in this row's classification.",''', '''        "molecular layer contacts are where DS1's and DS2's mean sinks peak in this row's classification, looked for past",
        "    the analyzed band too (5 contacts), on the cell layer's far side.",''')
rep('''        fig.text(4 / W, 1 - (352.0 + 3.3 * i_) / H''', '''        fig.text(4 / W, 1 - (343.0 + 3.3 * i_) / H''')
io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print("written", DST)

s = io.open(DST, encoding="utf-8").read()
rep('''def align(to, ty):''', '''def named(lab, key, to, ty):
    """A row's types named by the anatomy where the check decides it
    (DS1 = sink farther from the cell layer), else as in row 1; and which
    events are grouped differently from row 1 (whatever the names)."""
    to = np.asarray(to, int)
    a_, diff = align(to, ty)
    R0 = RECS[lab]
    if R0.naming.get(key, {}).get("verdict") in ("ok", "swapped") and R0.has(key) and R0.types(key).size == to.size:
        t_ = R0.types(key)
        if np.mean((t_ == to) | (t_ == 3 - to)) > 0.999:
            return t_, diff
    return a_, diff


def align(to, ty):''')
rep('''ds3_info(d, k2_, align(e2_["types"], ty)[0],''', '''ds3_info(d, k2_, named(d["lab"], k2_, e2_["types"], ty)[0],''')
rep('''ds3_info(d, "opt_curve", align(oc_["types"], ty)[0],''', '''ds3_info(d, "opt_curve", named(d["lab"], "opt_curve", oc_["types"], ty)[0],''')
rep('''    t2, diff2 = align(e2["types"], ty)''', '''    t2, diff2 = named(d["lab"], k2, e2["types"], ty)''')
rep('''        t3, diff3 = align(oc["types"], ty)''', '''        t3, diff3 = named(d["lab"], "opt_curve", oc["types"], ty)''')
rep('''        "molecular layer contacts are where DS1's''', '''        "layer contacts are where DS1's''')
rep('''"Each row is one way of classifying the same events, drawn the same way. Colors: DS1 blue, DS2 orange, named as in row 1.",''',
    '''"Each row is one way of classifying the same events, drawn the same way. Colors: DS1 blue, DS2 orange, named in every row by where the sink sits (as in row 1 where that cannot be decided).",''')
io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print("second pass ok")
