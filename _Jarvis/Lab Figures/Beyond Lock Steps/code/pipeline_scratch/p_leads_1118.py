P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:90]
    s = s.replace(a, b, 1)


# the rows between the sinks: without the sink lobes
rep('''        rows = [(x, "", "#7A5195") for x in r.good(np.arange(k["rowU"] + 1, k["rowL"]))]''',
    '''        rows = [(x, "", "#7A5195") for x in r.good(np.array(k["src_rows"], int))]''')
# the winner's name
rep('''    return "%s under the %s classifier" % (v, {"used": "best eligible", "best_nocut": "best (no minimum)"}.get(P["clf"], P["clf"].replace("_", " ")))''',
    '''    if P["clf"] == "winner":
        return "%s under each recording's winning classifier" % v
    return "%s under the %s classifier" % (v, {"used": "best eligible", "best_nocut": "best (no minimum)"}.get(P["clf"], P["clf"].replace("_", " ")))''')
# DS3 build-up: the noise floor in words, and every recording's DS1 / DS2 / DS3 / too-small shares
rep('''    text_mm(fig, H, 2, y0 - 2.5, "a–b  How DS3 is scored: every event's sink at the outer against the middle contact (green wedge = DS3, gray corner = under the noise floor)",
            fontsize=FS_S, fontweight="bold")''',
    '''    text_mm(fig, H, 2, y0 - 2.5, "a–b  How DS3 is scored: every event's sink at the outer against the middle contact (green wedge = DS3, gray corner = too small to tell)",
            fontsize=FS_S, fontweight="bold")''')
rep('''    ax.set_ylabel("DS3 score\\n(outer − middle) / sum", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    return y0 + 50''', '''    ax.set_ylabel("DS3 score\\n(outer − middle) / sum", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    note = ("Too small to tell (gray corner, the 'noise floor'): for each recording, the same two contacts are read 40 ms before and 40 ms after every "
            "dentate spike, when there is no spike, and the sum of the two sinks there is taken; the floor is the 99th percentile of those sums. An event "
            "whose two sinks together are not bigger than that floor cannot be told apart from the background, so it gets no DS3 score. "
            "Score −1 = all of the sink at the middle contact, +1 = all at the outer contact, within ±0.5 = shared (DS3).")
    yy = y0 + 39
    for i_, ln in enumerate(textwrap.wrap(note, 120)):
        text_mm(fig, H, 16, yy + 2.6 * i_, ln, fontsize=4.4, color=MUTE)
    yy += 2.6 * len(textwrap.wrap(note, 120)) + 4
    text_mm(fig, H, 2, yy, "d  What every recording's events are: DS1, DS2 and DS3 (DS3 taken out of DS1 and DS2), and too small to tell", fontsize=FS_S, fontweight="bold")
    ax = ax_mm(fig, H, 16, yy + 3, 120, 26)
    for j, r in enumerate(order):
        c_ = clf_of(r)
        w = r.ds3w.get(c_) or {}
        if not (c_ and r.has(c_)) or "score" not in w:
            continue
        t = r.types(c_)
        sc = np.asarray(w["score"], float)
        fin = np.isfinite(sc)
        d3 = fin & (np.abs(sc) <= 0.5)
        parts = [((t == 1) & ~d3 & fin, C_DS1, "DS1"), ((t == 2) & ~d3 & fin, C_DS2, "DS2"), (d3, C_DS3_, "DS3"), (~fin, "#C9C9C9", "too small to tell")]
        b0 = 0.0
        for m_, col, nm in parts:
            ax.bar([j], [m_.mean()], bottom=[b0], color=col, lw=0, width=0.75, label=nm if j == 0 else None)
            b0 += m_.mean()
        ax.text(j, 1.01, "%.0f%%" % (100 * d3.mean()), fontsize=3.9, ha="center", va="bottom", color=C_DS3_)
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(["%s\\n%s" % (r.lab, {"CTL": "CTL", "IED-": "IED−", "IED+": "IED+"}[r.subgroup]) for r in order], fontsize=3.9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("Share of events", fontsize=FS_S)
    ax.tick_params(labelsize=4.6)
    ax.legend(frameon=False, fontsize=4.2, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    text_mm(fig, H, 16, yy + 32, "Number above a bar = the recording's DS3 share. Gray = events too small to tell (no DS3 score).", fontsize=4.4, color=MUTE)
    return yy + 40''')
# the old border-filter build-up is not used any more; the filter sets' result title
rep('''    elif P["fam"] == "filter":
        y2 = build_filter(fig, H, y, L, P, recs, sides)''', '''    elif P["fam"] == "filter" and not P["es"].startswith("b_"):
        y2 = build_filter(fig, H, y, L, P, recs, sides)''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
