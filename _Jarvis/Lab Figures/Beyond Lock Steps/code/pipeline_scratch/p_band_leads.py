P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


rep('''T = pd.read_pickle(os.path.join(HERE, "merged", "tests.pkl"))
Mdf = pd.read_pickle(os.path.join(HERE, "merged", "measures.pkl")).set_index("id")''',
    '''MERGED = os.environ.get("BATTERY_MERGED", "merged")     # the filter battery's leads: merged_filters
T = pd.read_pickle(os.path.join(HERE, MERGED, "tests.pkl"))
Mdf = pd.read_pickle(os.path.join(HERE, MERGED, "measures.pkl")).set_index("id")''')
rep('''RECS = {es: [r for r in dsdata.load(es) if r.ok] for es in ("v6", "v8")}''',
    '''class _Recs(dict):
    """Event sets, loaded when first asked for (the filter sets are seven)."""
    def __missing__(self, es):
        self[es] = [r for r in dsdata.load(es) if r.ok]
        return self[es]


RECS = _Recs()
BAND_ORDER = ["b_none", "b_1_300", "b_1_100", "b_5_300", "b_ds", "b_5_50", "b_10_40"]
BAND_SHORT = {"b_none": "none", "b_1_300": "1–300", "b_1_100": "1–100", "b_5_300": "5–300", "b_ds": "5–100 (DS)", "b_5_50": "5–50", "b_10_40": "10–40"}
SET_NAME = {"v6": "Halo set", "v7": "10% grace set", "v8": "No P-spikes set"}
SET_NAME.update({k: "Halo events, %s" % v for k, v in dsdata.BANDS.items()})''')
rep('''    lines.append("Other event set (%s): " % ("No P-spikes" if P["es"] == "v6" else "Halo") + ("not available" if not np.isfinite(r["p_other_set"]) else "P = %.3f, %s sign" % (
        r["p_other_set"], "same" if r["same_sign_other_set"] == 1 else "opposite")))''',
    '''    other_word = ("Same measure under the DS filter (5–100 Hz)" if P["es"].startswith("b_") else
                  "Other event set (%s)" % ("No P-spikes" if P["es"] == "v6" else "Halo"))
    lines.append(other_word + ": " + ("not available" if not np.isfinite(r["p_other_set"]) else "P = %.3f, %s sign" % (
        r["p_other_set"], "same" if r["same_sign_other_set"] == 1 else "opposite")))''')
rep('''{"v6": "Halo set", "v7": "10% grace set", "v8": "No P-spikes set"}[P["es"]]''', '''SET_NAME[P["es"]]''')
# the across-filters panel, after e
rep('''    y3 = max(y2 + 61, yN + 4)
    for head, key in''', '''    y3 = max(y2 + 61, yN + 4)
    if P["es"].startswith("b_"):
        y3 = build_bands(fig, H, y3, L, P)
    for head, key in''')
rep('''    H = 262.0
    fig = Hs.page(H)''', '''    H = 262.0 if not parse(L["id"])["es"].startswith("b_") else 318.0
    fig = Hs.page(H)''')
rep('''def lead_page(k, L, prefix="Lead"):''', '''def band_id(mid, es):
    f, n, _e, c, v = mid.split("|")
    return "|".join([f, n, es, c, v])


def build_bands(fig, H, y, L, P):
    """f: the same number under every filter, every recording; g: the average
    dentate spike of one typical recording under the DS filter and this one."""
    y0 = y + 2
    text_mm(fig, H, 2, y0, "f  The same number under every filter (same events, same types; only the filter changes). Lines join a recording's values; "
            "bold = group median", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, y0 + 4, 104, 36)
    recs6 = RECS["v6"]
    ids = [band_id(L["id"], es) for es in BAND_ORDER]
    V = np.array([[Mdf.loc[i].get(r.lab, np.nan) if i in Mdf.index else np.nan for i in ids] for r in recs6], float)
    lims = outlier_limits(V.ravel())
    Vc = np.clip(V, lims[0], lims[1])
    xs = np.arange(len(BAND_ORDER))
    for j, r in enumerate(recs6):
        ax.plot(xs, Vc[j], color=Hs.col_of(r), lw=0.5, alpha=0.55)
    for g in ("CTL", "IED-", "IED+"):
        idx = [j for j, r in enumerate(recs6) if r.subgroup == g]
        ax.plot(xs, np.nanmedian(Vc[idx], axis=0), color=Hs.GROUP_COL[g], lw=1.8, label=Hs.GROUP_NAME[g])
    k_this = BAND_ORDER.index(P["es"])
    ax.axvspan(k_this - 0.35, k_this + 0.35, color="#F2E6A0", alpha=0.5, lw=0, zorder=0)
    ax.set_xticks(xs)
    ax.set_xticklabels([BAND_SHORT[b].replace(" (", chr(10) + "(") for b in BAND_ORDER], fontsize=4.8)
    ax.set_xlabel("Filter (Hz)", fontsize=FS_S)
    ax.set_ylabel(L["ylabel"], fontsize=FS_S - 0.3)
    ax.set_ylim(lims[0], lims[1])
    ax.tick_params(labelsize=4.8)
    ax.legend(frameon=False, fontsize=4.4, loc="best")
    rows = T[T["contrast"] == L["contrast"]].set_index("id")
    ps = ["%s P = %s" % (BAND_SHORT[b], ("%.3f" % rows.loc[i]["p"]) if i in rows.index else "–") for b, i in zip(BAND_ORDER, ids)]
    text_mm(fig, H, 16, y0 + 44.5, CNAME[L["contrast"]] + ", raw P under each filter:  " + ";  ".join(ps), fontsize=4.5, color=INK)
    # g: the average dentate spike under the DS filter and under this one
    ex = typical(RECS[P["es"]], SIDE[L["contrast"]][1], L["id"])
    if ex is not None and P["feat"] is not None:
        rows_, win, kind = place(ex, P["feat"])
        rr = [q for q, _w, _c in rows_][:2]
        text_mm(fig, H, 128, y0 + 0, "g  %s's average event at %s" % (ex.lab, "the read rows"), fontsize=FS_S, fontweight="bold")
        ax = ax_mm(fig, H, 136, y0 + 4, 42, 36)
        ds = {r_.lab: r_ for r_ in RECS["b_ds"]}[ex.lab]
        for rec_, nm, ls in ((ds, "5–100 Hz (DS filter)", (0, (3, 2))), (ex, dsdata.BANDS[P["es"]], "-")):
            X = rec_.lfp if kind in ("lfp_time", "lfp_depth") else rec_.csd
            for q, col in zip(rr, (C_DS1, RED)):
                ax.plot(rec_.t_ms, X[:, q, :].mean(axis=0) * (1 if kind in ("lfp_time", "lfp_depth") else -1), color=col, lw=0.9, ls=ls,
                        label="%s, contact %d" % (nm, rec_.contacts[q]))
        ax.axvline(0, color=HAIR, lw=0.5)
        ax.set_xlim(-50, 50)
        ax.set_xlabel("ms from the DS peak", fontsize=FS_S)
        ax.set_ylabel("LFP (µV)" if kind in ("lfp_time", "lfp_depth") else "Sink up (−CSD)", fontsize=FS_S)
        ax.tick_params(labelsize=4.6)
        ax.legend(frameon=False, fontsize=3.9, loc="upper right")
    return y0 + 53


def lead_page(k, L, prefix="Lead"):''')
rep('''            ("leads_filter.json", "Leads_filter_UNCORRECTED.pdf", "Filter_lead", "Filter lead"),''',
    '''            ("leads_band.json", "Leads_filter_UNCORRECTED.pdf", "Filter_lead", "Filter lead"),''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
