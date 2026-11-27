import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


EXTRA = '''
# ------------------------------------------------------- other build-ups
def typical(recs, side, mid):
    cand = [r for r in recs if in_side(r, side) and np.isfinite(Mdf.loc[mid].get(r.lab, np.nan))]
    if not cand:
        return None
    vals = np.array([Mdf.loc[mid][r.lab] for r in cand])
    return cand[int(np.argmin(np.abs(vals - np.median(vals))))]


def build_timing(fig, H, y, L, P, recs, sides):
    """Event trains: when the events happen, their intervals, every recording."""
    y0 = y + 5
    ex = [typical(recs, sd, L["id"]) for sd in sides]
    ex = [e for e in ex if e is not None]
    text_mm(fig, H, 2, y0 - 2.5, "a  When the events happen (%s; one row per recording, first 10 minutes)" % events_word(P), fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 1, 100, 18)
    for i, r in enumerate(ex):
        m = mask_of(r, P)
        t = r.times_s[m] if m is not None else r.times_s
        t = t[t <= 600]
        ax.vlines(t / 60.0, i - 0.35, i + 0.35, color=Hs.col_of(r), lw=0.5)
        ax.text(-0.15, i, "%s (%s)" % (r.lab, Hs.GROUP_NAME[r.subgroup]), fontsize=4.6, ha="right", va="center", color=Hs.col_of(r))
    ax.set_ylim(len(ex) - 0.5, -0.5)
    ax.set_yticks([])
    ax.set_xlim(0, 10)
    ax.set_xlabel("Minutes into the recording", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    text_mm(fig, H, 124, y0 - 2.5, "b  Intervals between events", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 132, y0 + 1, 44, 30)
    bins = np.logspace(-1.5, 2.5, 40)
    for r in ex:
        m = mask_of(r, P)
        t = np.sort(r.times_s[m] if m is not None else r.times_s)
        d = np.diff(t)
        ax.hist(d, bins=bins, color=Hs.col_of(r), alpha=0.55, density=True, lw=0, label="%s, %d intervals" % (r.lab, d.size))
    if P["name"].startswith("short_"):
        thr = float(P["name"].split("_")[1].rstrip("s"))
        ax.axvline(thr, color=INK, lw=0.8, ls=(0, (3, 2)))
        ax.text(thr * 1.1, ax.get_ylim()[1] * 0.95, "%g s" % thr, fontsize=4.6, va="top")
    ax.set_xscale("log")
    ax.set_xlabel("Interval (s, log scale)", fontsize=FS_S)
    ax.set_ylabel("Density", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="upper left")
    y1 = y0 + 44
    text_mm(fig, H, 2, y1 - 3, "d  Every recording's intervals (%s): line = median, bar = middle half; number above = the recording's value" % events_word(P), fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y1 + 1, 163, 30)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.subgroup == "IED-"], key=lambda r: r.ko) + \\
        sorted([r for r in recs if r.subgroup == "IED+"], key=lambda r: r.ko)
    for j, r in enumerate(order):
        m = mask_of(r, P)
        if m is None or m.sum() < 3:
            continue
        d = np.diff(np.sort(r.times_s[m]))
        jit = np.random.default_rng(1).uniform(-0.28, 0.28, d.size)
        ax.scatter(j + jit, d, s=0.8, color=Hs.col_of(r), alpha=0.35, lw=0, rasterized=True)
        q1, q2, q3 = np.percentile(d, [25, 50, 75])
        ax.plot([j - 0.32, j + 0.32], [q2, q2], color=INK, lw=1.0)
        ax.plot([j, j], [q1, q3], color=INK, lw=0.6)
        ax.text(j, 300, fmt(Mdf.loc[L["id"]].get(r.lab, np.nan)), fontsize=4.2, ha="center", va="bottom")
    ax.set_yscale("log")
    ax.set_ylim(0.02, 600)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=4.8)
    for i_, r in enumerate(order):
        ax.get_xticklabels()[i_].set_color(Hs.GROUP_COL[r.subgroup])
    ax.set_ylabel("Interval (s, log)", fontsize=FS_S)
    ax.tick_params(labelsize=4.8)
    return y1 + 44


def build_profile(fig, H, y, L, P, recs, sides):
    """Measures read off the average dentate spike's depth profile."""
    import normcurves as NC
    y0 = y + 5
    text_mm(fig, H, 2, y0 - 2.5, "a–d  Where it is read: the average dentate spike (all events, CSD at the peak) on the normalized depth, typical recordings and group means",
            fontsize=FS_S, fontweight="bold")
    band = L.get("band_u")
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        ax = ax_mm(fig, H, 22 + j * 52, y0 + 4, 34, 56)
        c = NC.curves(r)
        ax.plot(c["prof_u"], NC.GRID_U, color=Hs.col_of(r), lw=1.2)
        ax.axvline(0, color=HAIR, lw=0.5)
        for yy in (0, 1):
            ax.axhline(yy, color=HAIR, lw=0.5)
        if band:
            ax.axhspan(band[0], band[1], color="#7A5195", alpha=0.15, lw=0)
        ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["upper blade's\\nsink", "lower blade's\\nsink"], fontsize=4.6)
        ax.set_xlabel("CSD at the peak\\n(1 = average sink)", fontsize=FS_S)
        ax.set_title("%s (%s): %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], fmt(Mdf.loc[L["id"]][r.lab])), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.8)
    ax = ax_mm(fig, H, 130, y0 + 4, 40, 56)
    for g in ("CTL", "IED-", "IED+"):
        Y = np.array([NC.curves(r)["prof_u"] for r in recs if r.subgroup == g])
        mu = np.nanmean(Y, axis=0)
        se = np.nanstd(Y, axis=0) / np.sqrt(np.isfinite(Y).sum(axis=0).clip(1))
        ax.fill_betweenx(NC.GRID_U, mu - se, mu + se, color=Hs.GROUP_COL[g], alpha=0.2, lw=0)
        ax.plot(mu, NC.GRID_U, color=Hs.GROUP_COL[g], lw=1.1, label=Hs.GROUP_NAME[g])
    if band:
        ax.axhspan(band[0], band[1], color="#7A5195", alpha=0.15, lw=0)
    ax.axvline(0, color=HAIR, lw=0.5)
    ax.set_ylim(NC.GRID_U[-1], NC.GRID_U[0])
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["upper", "lower"], fontsize=4.6)
    ax.set_title("Group means ± s.e.m.", fontsize=FS_S, loc="left", pad=3)
    ax.legend(frameon=False, fontsize=4.4, loc="lower left")
    ax.tick_params(labelsize=4.8)
    return y0 + 76


def build_ds3(fig, H, y, L, P, recs, sides):
    """DS3 measures: every event at the two layer contacts, and the score."""
    y0 = y + 5
    clf_of = lambda r: r.used if P["clf"] in ("", "used") else P["clf"]
    text_mm(fig, H, 2, y0 - 2.5, "a–b  How DS3 is scored: every event's sink at the outer against the middle contact (green wedge = DS3, gray corner = under the noise floor)",
            fontsize=FS_S, fontweight="bold")
    for j, sd in enumerate(sides):
        r = typical(recs, sd, L["id"])
        if r is None:
            continue
        w = r.ds3w.get(clf_of(r)) or {}
        if "score" not in w:
            continue
        ax = ax_mm(fig, H, 18 + j * 50, y0 + 4, 32, 32)
        so, sm = np.maximum(-r.csd_peak[:, w["outer"]], 0), np.maximum(-r.csd_peak[:, w["middle"]], 0)
        top = float(np.percentile(np.concatenate([so, sm]), 99)) * 1.08 or 1.0
        xx = np.linspace(0, top, 50)
        ax.fill_between(xx, xx / 3.0, np.minimum(3.0 * xx, top), color=C_DS3_, alpha=0.13, lw=0)
        ax.fill_between([0, min(w["floor"], top)], [min(w["floor"], top), 0], 0, color="#DADADA", lw=0)
        t = r.types(clf_of(r))
        for k_, col in ((2, C_DS2), (1, C_DS1)):
            ax.scatter(so[t == k_], sm[t == k_], s=2, color=col, lw=0, alpha=0.75)
        ax.set_xlim(0, top)
        ax.set_ylim(0, top)
        ax.set_xlabel("Sink at outer contact", fontsize=FS_S)
        ax.set_ylabel("Sink at middle contact", fontsize=FS_S)
        ax.set_title("%s (%s): %s" % (r.lab, Hs.GROUP_NAME[r.subgroup], fmt(Mdf.loc[L["id"]][r.lab])), fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
        ax.tick_params(labelsize=4.6)
    text_mm(fig, H, 120, y0 - 2.5 + 4.5, "c  The score of every event, every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 126, y0 + 6, 52, 30)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.group == "PTEN"], key=lambda r: (r.subgroup != "IED-", r.ko))
    for j, r in enumerate(order):
        w = r.ds3w.get(clf_of(r)) or {}
        if "score" not in w:
            continue
        sc = w["score"][np.isfinite(w["score"])]
        jit = np.random.default_rng(1).uniform(-0.3, 0.3, sc.size)
        ax.scatter(j + jit, sc, s=0.6, color=Hs.col_of(r), alpha=0.4, lw=0, rasterized=True)
    ax.axhspan(-0.5, 0.5, color=C_DS3_, alpha=0.12, lw=0)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=3.8, rotation=90)
    ax.set_ylabel("DS3 score\\n(outer − middle) / sum", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    return y0 + 50


def build_filter(fig, H, y, L, P, recs, sides):
    """What the stricter event border drops."""
    import measures as MS_
    y0 = y + 5
    R7 = {r.lab: r for r in dsdata.load("v7") if r.ok}
    text_mm(fig, H, 2, y0 - 2.5, "a  Halo events the 10% grace border keeps (dark) and drops (light), every recording", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 2, 90, 34)
    order = [r for r in recs if r.group == "CTL"] + sorted([r for r in recs if r.group == "PTEN"], key=lambda r: (r.subgroup != "IED-", r.ko))
    parts = {}
    for j, r in enumerate(order):
        b = R7.get(r.lab)
        if b is None:
            continue
        ink = MS_.match(r.times_s, b.times_s)
        parts[r.lab] = ink
        ax.bar([j], [ink.sum()], color=Hs.col_of(r), lw=0)
        ax.bar([j], [(~ink).sum()], bottom=[ink.sum()], color=Hs.col_of(r), alpha=0.35, lw=0)
        ax.text(j, r.n + 8, "%.0f%%" % (100 * (~ink).mean()), fontsize=4.0, ha="center", va="bottom")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([r.lab for r in order], fontsize=4.4)
    ax.set_ylabel("Halo events", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    feat = next((f for f in MS_.FILTER_FEATS if P["name"].startswith(f + "_")), None)
    if feat is not None:
        text_mm(fig, H, 114, y0 - 2.5, "b  %s: dropped against kept, two typical recordings" % short_name(feat), fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 124, y0 + 2, 52, 34)
        for j, sd in enumerate(sides):
            r = typical(recs, sd, L["id"])
            if r is None or r.lab not in parts:
                continue
            x = feats(r)[feat]
            ink = parts[r.lab]
            for k_, (mk, nm) in enumerate(((ink, "kept"), (~ink, "dropped"))):
                v = x[mk & np.isfinite(x)]
                xx = j * 2.4 + k_
                jit = np.random.default_rng(2).uniform(-0.3, 0.3, v.size)
                ax.scatter(xx + jit, v, s=1.2, color=Hs.col_of(r), alpha=0.5 if nm == "kept" else 0.9, lw=0)
                if v.size:
                    ax.plot([xx - 0.35, xx + 0.35], [np.median(v)] * 2, color=INK, lw=1.0)
                ax.text(xx, ax.get_ylim()[0], "%s\\n%s" % (r.lab, nm), fontsize=4.2, ha="center", va="top")
        ax.set_xticks([])
        ax.set_ylabel(short_name(feat), fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
    return y0 + 50

'''
rep('''def lead_page(k, L):''', EXTRA + '''
def lead_page(k, L):''')
rep('''from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, RED, C_DS1, C_DS2, CSD_CMAP, FS, FS_S, W''',
    '''from house import plt, ax_mm, text_mm, letter, INK, MUTE, HAIR, RED, C_DS1, C_DS2, CSD_CMAP, FS, FS_S, W
from house import C_DS3 as C_DS3_''')
rep('''    elif P["name"].startswith("gcl_to_sink"):''', '''    elif P["fam"] == "timing":
        y2 = build_timing(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "filter":
        y2 = build_filter(fig, H, y, L, P, recs, sides)
    elif P["fam"] == "structure" and ("ds3" in P["name"] or "relsink" in P["name"] or "unscorable" in P["name"]):
        y2 = build_ds3(fig, H, y, L, P, recs, sides)
    elif P["name"].startswith(("profile_u", "net_u", "mean_sink_asym", "mean_source_over", "main_sink_fwhm")):
        y2 = build_profile(fig, H, y, L, P, recs, sides)
    elif P["name"].startswith("gcl_to_sink"):''')
rep('''    text_mm(fig, H, 2, y2 - 3, "e  The result: one number per recording (%s)" % ("Halo set" if P["es"] == "v6" else "No P-spikes set"), fontsize=FS_S, fontweight="bold")''',
    '''    text_mm(fig, H, 2, y2 - 3, "e  The result: one number per recording (%s)" % {"v6": "Halo set", "v7": "10% grace set", "v8": "No P-spikes set"}[P["es"]], fontsize=FS_S, fontweight="bold")''')
rep('''if __name__ == "__main__":
    with PdfPages(os.path.join(OUT, "Leads_explained_UNCORRECTED.pdf")) as pdf:
        for k, L in enumerate(LEADS, 1):
            fig = lead_page(k, L)
            pdf.savefig(fig)
            fig.savefig(os.path.join(OUT, ("Lead_%02d.png" % k) if not L["title"].startswith("NOT A LEAD") else "Appendix_LFP_artifact.png"), dpi=170)
            plt.close(fig)
            print("lead", k, flush=True)
    print("saved", len(LEADS))''', '''SETS_OUT = [("leads.json", "Leads_explained_UNCORRECTED.pdf", "Lead"), ("leads_ds3.json", "Leads_DS3_UNCORRECTED.pdf", "DS3_lead"),
            ("leads_filter.json", "Leads_filter_UNCORRECTED.pdf", "Filter_lead"), ("leads_general.json", "Leads_not_DS_type_UNCORRECTED.pdf", "General_lead")]

if __name__ == "__main__":
    import sys as _sys
    only = _sys.argv[1:]
    for js, pdfname, stem in SETS_OUT:
        if only and js not in only:
            continue
        path = os.path.join(HERE, js)
        if not os.path.isfile(path):
            continue
        LL = json.load(open(path, encoding="utf-8"))
        with PdfPages(os.path.join(OUT, pdfname)) as pdf:
            for k, L in enumerate(LL, 1):
                fig = lead_page(k, L)
                pdf.savefig(fig)
                fig.savefig(os.path.join(OUT, ("%s_%02d.png" % (stem, k)) if not L["title"].startswith("NOT A LEAD") else "Appendix_LFP_artifact.png"), dpi=170)
                plt.close(fig)
                print(js, k, flush=True)
        print("saved", pdfname, len(LL))''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
