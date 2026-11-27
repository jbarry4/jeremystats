P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


rep('''    elif P["fam"] == "timing":
        y2 = build_timing(fig, H, y, L, P, recs, sides)''', '''    elif P["fam"] == "around":
        y2 = build_around(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "timing":
        y2 = build_timing(fig, H, y, L, P, recs, sides)''')
rep('''def band_id(mid, es):''', '''AROUND = {}


def around_maps(r, band, var):
    """(rows' u, median log2 power over random moments [rows x 101 bins]) for one recording."""
    import around_measures as AM
    key = (r.lab, band, var)
    if key not in AROUND:
        D = AM.load(r)
        if D is None:
            AROUND[key] = None
            return None
        bi = AM.BANDS.index(band)
        m = D["evok"].copy()
        if var in ("ds1x", "ds2x") and r.winner:
            t = r.types("winner")
            m3 = r.ds3("winner")
            m3 = np.zeros(r.n, bool) if m3 is None else m3
            m &= (t == (1 if var == "ds1x" else 2)) & ~m3
        mrd = D["rdE"][:, bi].mean(axis=0)
        mrd[mrd <= 0] = np.nan
        lr = np.log2(np.maximum(D["evE"][m][:, bi], 1e-12) / mrd[None])
        rows = np.array(r.good(np.arange(1, 63)), int)
        AROUND[key] = (r.u(rows), np.nanmedian(lr[:, rows, :], axis=0), int(m.sum()))
    return AROUND[key]


def build_around(fig, H, y, L, P, recs, sides):
    """Before/after measures: where and when the band's power differs from random moments."""
    import around_measures as AM
    A_ = L["around"]
    band, var = A_["band"], P["var"] or "all"
    w = A_.get("window")
    lo_u, hi_u = A_.get("u", (None, None))
    y0 = y + 5
    text_mm(fig, H, 2, y0 - 2.5, "a–b  %s around the DS, depth by time, two typical recordings: each event's power over the mean of random moments of the same recording "
            "(log2; red = more than at random moments, blue = less), median over %s" % (AM.BAND_WORD[band], events_word(P)), fontsize=FS_S, fontweight="bold")
    TB = AM.TB
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        got = around_maps(r, band, var)
        if got is None:
            continue
        u, M, n = got
        ax = ax_mm(fig, H, 16 + j * 58, y0 + 5, 46, 46)
        o = np.argsort(u)
        ax.pcolormesh(TB, u[o], M[o], cmap="RdBu_r", vmin=-1, vmax=1, shading="nearest", rasterized=True)
        for yy in (0, 1):
            ax.axhline(yy, color=INK, lw=0.5, ls=(0, (2, 2)))
        ax.axvline(0, color=INK, lw=0.5)
        if w:
            for x_ in w:
                ax.axvline(x_, color="#7A5195", lw=0.8)
        if lo_u is not None:
            ax.axhspan(lo_u, hi_u, xmin=0, xmax=1, fill=False, ec="#7A5195", lw=0.9)
        ax.set_ylim(min(u.max(), 3.0), max(u.min(), -2.0))
        ax.set_yticks([-2, -1, 0, 1, 2, 3])
        ax.set_yticklabels(["−2", "−1", "0 upper\\nblade", "1 lower\\nblade", "2", "3"], fontsize=4.4)
        ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
        ax.set_ylabel("Depth (u; toward CA1 is up)", fontsize=FS_S)
        ax.set_title("%s (%s), %d events: %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], n, fmt(Mdf.loc[L["id"]].get(r.lab, np.nan))), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.6)
    # c: the time course at the depth read, every recording
    text_mm(fig, H, 130, y0 - 2.5 + 4.5, "c  At the depth read, every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 136, y0 + 5, 42, 46)
    groups = {}
    for r in recs:
        got = around_maps(r, band, var)
        if got is None:
            continue
        u, M, n = got
        sel = (u >= lo_u) & (u < hi_u) if lo_u is not None else np.ones(u.size, bool)
        if not sel.any():
            continue
        tr = np.nanmean(M[sel], axis=0)
        ax.plot(TB, tr, color=Hs.col_of(r), lw=0.4, alpha=0.6)
        groups.setdefault(r.subgroup, []).append(tr)
    for g, trs in groups.items():
        ax.plot(TB, np.nanmedian(np.array(trs), axis=0), color=Hs.GROUP_COL[g], lw=1.6, label=Hs.GROUP_NAME[g])
    ax.axhline(0, color=HAIR, lw=0.5)
    ax.axvline(0, color=INK, lw=0.5)
    if w:
        ax.axvspan(w[0], w[1], color="#7A5195", alpha=0.12, lw=0)
    ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
    ax.set_ylabel("Power over random moments (log2)", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    ax.legend(frameon=False, fontsize=4.2, loc="upper left")
    note = A_.get("note", "")
    if note:
        for i_, ln in enumerate(textwrap.wrap(note, 125)):
            text_mm(fig, H, 16, y0 + 59 + 2.6 * i_, ln, fontsize=4.4, color=MUTE)
    return y0 + 72


def band_id(mid, es):''')
rep('''SET_NAME = {"v6": "Halo set", "v7": "10% grace set", "v8": "No P-spikes set"}''',
    '''SET_NAME = {"v6": "Halo set", "v7": "10% grace set", "v8": "No P-spikes set"}''')
rep('''            ("leads_general.json", "Leads_not_DS_type_UNCORRECTED.pdf", "General_lead", "Lead (no DS type)")]''',
    '''            ("leads_general.json", "Leads_not_DS_type_UNCORRECTED.pdf", "General_lead", "Lead (no DS type)"),
            ("leads_around.json", "Leads_before_after_UNCORRECTED.pdf", "Before_after_lead", "Before/after lead")]''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
