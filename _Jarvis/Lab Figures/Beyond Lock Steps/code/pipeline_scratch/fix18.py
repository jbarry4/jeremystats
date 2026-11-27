"""Round 10 of the quality check: DS3 wording, the paper's own procedure
for DS3, and a fourth row with the recording on the normalized axes."""
import io
import os

p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deep_qc5.py")
s = io.open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('OUT = r"c:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16\\quality_check_round9"',
    'OUT = r"c:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16\\round10\\quality_check"\n'
    'sys.path.insert(0, r"C:\\Users\\Z390\\Desktop\\DS_PTEN_figures_2026-11-16\\battery")\n'
    'import dsdata  # noqa: E402\nimport normcurves as NC  # noqa: E402\n'
    'RECS = {r_.lab: r_ for r_ in dsdata.load("v6")}\n'
    'GROUPS = {"CTL": [r_ for r_ in RECS.values() if r_.ok and r_.group == "CTL"], "PTEN": [r_ for r_ in RECS.values() if r_.ok and r_.group == "PTEN"]}\n'
    'SEP = [r_ for r_ in RECS.values() if r_.ok and r_.separable()]')
rep("H = 318.0", "H = 386.0")
rep('''        w3 = "DS3.  Not measurable under this classification: DS1's and DS2's mean sinks do not give separate outer and middle layer contacts."''',
    '''        w3 = ("DS3.  Cannot be scored under this classification: DS1's and DS2's mean sinks peak at the same contact, so outer and middle "
              "cannot be told apart. That is not 'no DS3': the events are one type here.")''')
rep('(137, I3, "DS3", "no DS3 events" if D3["ok"] else "DS3 not measurable")', '(137, I3, "DS3", "no event scores as DS3" if D3["ok"] else "DS3 cannot be scored")')
rep('(160, In, "DS1, DS2 without DS3", "same as the first" if D3["ok"] else "DS3 not measurable")',
    '(160, In, "DS1, DS2 without DS3", "same as the first" if D3["ok"] else "DS3 cannot be scored")')
rep('            ax.text(0.5, 0.5, none.replace(" ", chr(10), 1), transform=ax.transAxes,', '            ax.text(0.5, 0.5, chr(10).join(none.rsplit(" ", 2)[0:1] + [" ".join(none.rsplit(" ", 2)[1:])]), transform=ax.transAxes,')
rep("    notes = [\n", '''    row4(fig, 76.0 + 3 * 68.0, d)
    notes = [
        "Row 4.  Depth normalized by this recording's own landmarks (blue ticks: the two main sinks; red ticks: the source next to each). Gray band: mean ± s.e.m. of the recording's group; "
        "dashed: mean of the six separable recordings.",
''')
rep("(287.0 + 3.3 * i_)", "(352.0 + 3.3 * i_)")
rep("order = [d for d in recs", '''def row4(fig, y0, d):
    """This recording on the normalized axes, against its group."""
    r = RECS[d["lab"]]
    ax_mm = lambda x, y, w, h: G.ax_mm(fig, H, x, y, w, h)
    k = r.landmarks
    c = NC.curves(r)
    grp = GROUPS[r.group]
    fig.add_artist(Rectangle((4 / W, 1 - (y0 + 5.4) / H), 1.2 / W, 5.4 / H, color=G.col_of(d), lw=0, transform=fig.transFigure))
    fig.text(7 / W, 1 - (y0 + 1.6) / H, "4   Depth normalized: this recording against %s" % ("the controls" if r.group == "CTL" else "the PTEN recordings"),
             fontsize=7.5, fontweight="bold", ha="left", va="center", color=INK)
    fig.text(7 / W, 1 - (y0 + 4.6) / H, "Landmarks.  Main sinks %.0f µm apart; source to main sink %.0f µm (upper blade), %.0f µm (lower); %s." % (
        k["blade_um"], k["gcl_to_sink_upper_um"], k["gcl_to_sink_lower_um"],
        "one source between the blades" if k["source_gap_um"] < 60 else "two sources %.0f µm apart" % k["source_gap_um"]), fontsize=FS_S, ha="left", va="center")
    ty = c["typed"]
    if ty is not None and "ratio" in ty:
        fig.text(7 / W, 1 - (y0 + 7.4) / H, "DS1 against DS2 (%s).  DS1's sink sits at %.2f× (upper) and %.2f× (lower) DS2's distance from the source; its size is %.2f× and %.2f× DS2's." % (
            "separable" if r.separable() else "not separable, names arbitrary", ty["ratio"][0], ty["ratio"][1], ty["amp"][0], ty["amp"][1]),
            fontsize=FS_S, ha="left", va="center", color=MUTE)
    bits = []
    for blade in ("upper", "lower"):
        L = NC.literature_ds3(r, blade)
        bits.append("%s blade: the two quarters' sinks peak at the same contact, so the layers cannot be placed" % blade if L is None else
                    "%s blade: outer and middle contacts %d µm apart; DS1 %.0f%%, DS2 %.0f%%, DS3 %.0f%%, unscored %.0f%%" % (
                        blade, L["gap_um"], 100 * L["share"][1], 100 * L["share"][2], 100 * L["share"][3], 100 * L["share"][0]))
    fig.text(7 / W, 1 - (y0 + 10.2) / H, "DS3 by the paper's own procedure (Tarcsay et al. 2025: layers from the two extreme quarters of PC1).  " + ";   ".join(bits) + ".",
             fontsize=FS_S, ha="left", va="center", color=C_DS3)
    top, hh = y0 + 23.5, 34.0
    # 1 the landmarks on the raw depth axis
    ax = ax_mm(12, top, 26, hh)
    rows = np.arange(64)
    dep = r.depth_um(rows)
    ax.plot(r.mean_csd_peak, dep, color=INK, lw=0.9)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    for key, col in (("U", C_DS1), ("L", C_DS1), ("GU", RED), ("GL", RED)):
        ax.plot([0.9, 1.0], [r.depth_um(k[key])] * 2, color=col, lw=1.6, transform=ax.get_yaxis_transform(), clip_on=False, solid_capstyle="butt")
    a_, b_ = r.band
    for y in (r.depth_um(a_) - 25, r.depth_um(b_) + 25):
        ax.axhline(y, color=INK, lw=0.5, ls=(0, (4, 2)), alpha=0.7)
    lo, hi = r.depth_um(max(0, a_ - 6)), r.depth_um(min(63, b_ + 6))
    ax.set_ylim(hi, lo)
    ax.set_xticks([0])
    ax.set_ylabel("Depth from band center (µm)", fontsize=FS)
    ax.set_xlabel("Mean CSD at the peak", fontsize=FS_S)
    # 2 blade to blade
    ax = ax_mm(50, top, 24, hh)
    Y = np.array([NC.curves(x)["prof_u"] for x in grp])
    mu, se = np.nanmean(Y, axis=0), np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
    ax.fill_betweenx(NC.GRID_U, mu - se, mu + se, color="#BDBDBD", lw=0, alpha=0.8)
    ax.plot(c["prof_u"], NC.GRID_U, color=G.col_of(d), lw=1.1)
    ax.axvline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper" + chr(10) + "sink", "lower" + chr(10) + "sink"], fontsize=FS_S - 0.5)
    ax.set_xticks([-1, 0, 1])
    ax.set_xlabel("CSD (1 = main sinks)", fontsize=FS_S)
    # 3 folded, all events
    ax = ax_mm(93, top, 38, hh)
    Y = np.array([NC.curves(x)["fold"] for x in grp])
    mu, se = np.nanmean(Y, axis=0), np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
    ax.fill_between(NC.GRID_V, mu - se, mu + se, color="#BDBDBD", lw=0, alpha=0.8)
    ax.plot(NC.GRID_V, c["fold"], color=G.col_of(d), lw=1.1)
    for x_ in (0, 1):
        ax.axvline(x_, color=HAIR, lw=0.5, zorder=0)
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-0.5, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["source", "main sink", "2x out"], fontsize=FS_S)
    ax.set_ylabel("CSD (−1 = main sink)", fontsize=FS_S)
    ax.set_xlabel("All events, blades folded", fontsize=FS_S)
    # 4 folded, DS1 and DS2
    ax = ax_mm(143, top, 36, hh)
    for c_, col in ((2, C_DS2), (1, C_DS1)):
        Y = np.array([NC.curves(x)["typed"]["fold"][c_] for x in SEP])
        ax.plot(NC.GRID_V, np.nanmean(Y, axis=0), color=col, lw=0.7, ls=(0, (3, 2)), alpha=0.8)
        if ty is not None and c_ in ty["fold"]:
            ax.plot(NC.GRID_V, ty["fold"][c_], color=col, lw=1.1)
    for x_ in (0, 1):
        ax.axvline(x_, color=HAIR, lw=0.5, zorder=0)
    ax.axhline(0, color=HAIR, lw=0.5, zorder=0)
    ax.set_xlim(-0.5, 2.6)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["source", "main sink", "2x out"], fontsize=FS_S)
    ax.set_ylabel("CSD (−1 = DS2's sink)", fontsize=FS_S)
    ax.set_xlabel("DS1 and DS2, blades folded", fontsize=FS_S)
    for x, s_ in ((12, "Landmarks"), (50, "Blade to blade"), (93, "Within a blade"), (143, "Within a blade, by type")):
        fig.text(x / W, 1 - (top - 3.5) / H, s_, fontsize=FS, ha="left", va="center", color=INK)


order = [d for d in recs''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
