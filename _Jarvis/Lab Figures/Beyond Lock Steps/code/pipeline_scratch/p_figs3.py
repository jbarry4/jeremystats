P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2_figs.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


# IED− with a true minus everywhere it is drawn
rep('''    if cls:
        cls = [c[0].upper() + c[1:] for c in cls]
    return mice, y, task, cls''', '''    if cls:
        cls = [(c[0].upper() + c[1:]).replace("IED-", "IED−") for c in cls]
    return mice, y, task, cls''')
rep('''    cls = [c[0].upper() + c[1:] for c in r["classes"]] if r["classes"] else None''',
    '''    cls = [(c[0].upper() + c[1:]).replace("IED-", "IED−") for c in r["classes"]] if r["classes"] else None''')
# words for the before/after parameters
rep('''def label_of(item):
    es, band, base, stat = parse(item)''', '''BA_WIN = {"pre_far": "−500 to −200 ms", "pre_near": "−150 to −50 ms", "post_near": "+50 to +150 ms", "post_far": "+200 to +500 ms"}


def ba_parts(base):
    """(after-over-before?, band, window, depth bin) of a before/after parameter."""
    pp = base.startswith("ba_pp_")
    rest = base[6:] if pp else base[7:]
    band, _, rest = rest.partition("_")
    if pp:
        win, _, depth = rest.partition("_")
    else:
        win = next(w for w in BA_WIN if rest.startswith(w))
        depth = rest[len(win) + 1:]
    return pp, band, win, depth


def ba_words(base):
    pp, band, win, depth = ba_parts(base)
    what = "spiking (MUA)" if band == "MUA" else band + " Hz power"
    where = "whole shank" if depth == "shank" else "u %s to %s" % tuple(x.replace("-", "−") for x in depth.replace("u", "").split("_"))
    if pp:
        return "%s after over before (%s), %s" % (what[0].upper() + what[1:], "+200 to +500 against −500 to −200 ms" if win == "far"
                                                   else "+50 to +150 against −150 to −50 ms", where)
    return "%s over random moments, %s, %s" % (what[0].upper() + what[1:], BA_WIN[win], where)


def label_of(item):
    es, band, base, stat = parse(item)
    if base.startswith("ba_"):
        return ba_words(base) + (" (%s over events)" % STATW.get(stat, stat) if stat else "")''')
# per-event values from the frozen bundle: exactly what the models read
rep('''    def ev(self, es, lab, base):
        key = (es, lab)''', '''    def ev_amber(self, item, lab):
        col = item.split("|")[0]
        if col == "share":
            col = "type_" + item.split("|")[1]
        if col not in self.data.efeat:
            return None
        mi = self.labs.index(lab)
        return self.data.X[self.data.bag == mi, self.data.efeat.index(col)]

    def ev(self, es, lab, base):
        key = (es, lab)''')
rep('''    for lab, col, word in examples:
        v = ctx.ev(es, lab, base)
        allv.append(v[np.isfinite(v)])''', '''    for lab, col, word in examples:
        v = ctx.ev_amber(item, lab)
        if v is None:
            v = ctx.ev(es, lab, base)
        allv.append(v[np.isfinite(v)])''')


# before/after where panel
rep('''def type_panel(''', '''def ba_panel(fig, H, x, y, w, h, r, base):
    """The parameter's band around the DS, depth by time, in one recording:
    each event's power over random moments (log2), median over events."""
    import make_leads as ML
    pp, band, win, depth = ba_parts(base)
    got = ML.around_maps(r, band, "all")
    ax = ax_mm(fig, H, x, y, w, h)
    if got is None:
        return ax
    u, M, n = got
    o = np.argsort(u)
    ax.pcolormesh(np.arange(-50, 51) * 10.0, u[o], M[o], cmap="RdBu_r", vmin=-1, vmax=1, shading="nearest", rasterized=True)
    for yy in (0, 1):
        ax.axhline(yy, color=INK, lw=0.4, ls=(0, (2, 2)))
    ax.axvline(0, color=INK, lw=0.4)
    wins = {"near": [(-150, -50), (50, 150)], "far": [(-500, -200), (200, 500)]}[win] if pp else [{"pre_far": (-500, -200), "pre_near": (-150, -50),
                                                                                                     "post_near": (50, 150), "post_far": (200, 500)}[win]]
    if depth != "shank":
        a_, b_ = (float(x_) for x_ in depth.replace("u", "").split("_"))
        for w0, w1 in wins:
            ax.add_patch(Rectangle((w0, a_), w1 - w0, b_ - a_, fill=False, ec="#6A3D9A", lw=0.8))
    else:
        for w0, w1 in wins:
            ax.axvspan(w0, w1, color="#6A3D9A", alpha=0.12, lw=0)
    ax.set_ylim(min(u.max(), 2.5), max(u.min(), -2.0))
    ax.set_xlim(-500, 500)
    ax.set_xticks([-500, 0, 500])
    ax.set_xlabel("Time from DS peak (ms)", fontsize=T5)
    ax.set_ylabel("Depth (u)", fontsize=T5)
    tidy(ax, 4.6)
    return ax


def type_panel(''')
rep('''            rec = ctx.recs(es).get(ex[-1][0]) if ex else None
            if rec is not None and rec.landmarks is not None:
                where_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                text_mm(fig, H, 24, y0 + 11.2, "%s (%s)" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])''', '''            rec = ctx.recs(es if not base.startswith("ba_") else "v6").get(ex[-1][0]) if ex else None
            if rec is not None and rec.landmarks is not None:
                if base.startswith("ba_"):
                    ba_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s): log2 over random moments" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])
                else:
                    where_panel(fig, H, 24, y0 + 13, 24, 24, rec, base)
                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s)" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])''')
rep('''        what, unit = WHAT.get(base, (base.replace("_", " "), ""))''', '''        what, unit = WHAT.get(base, (base.replace("_", " "), ""))
        if base.startswith("ba_"):
            what, unit = ("Each event's band power, %s; log2 (0 = no change). Spiking (MUA) is the raw 30 kHz signal band-passed 300–3000 Hz and "
                          "rectified" % ("after over before" if base.startswith("ba_pp_") else "over the mean of random moments of the same recording"),
                          "log2")''')
# minus signs in rho; a group key on the knockout panels
rep('''        ax.text(0.98, 0.98, "ρ %+.2f %s" % (st.spearmanr(ko[ok], vals[ok]).correlation, stars(p)), transform=ax.transAxes, ha="right", va="top", fontsize=4.8)''',
    '''        ax.text(0.98, 0.98, ("ρ %+.2f %s" % (st.spearmanr(ko[ok], vals[ok]).correlation, stars(p))).replace("-", "−"), transform=ax.transAxes,
                ha="right", va="top", fontsize=4.8)''')
rep('''    heads = ["Where it is read (typical mouse, mean CSD)", "Every event, a typical mouse per group", "Every mouse"]
    for x, s in ((44, heads[0]), (96, heads[1]), (146, heads[2])):
        text_mm(fig, H, x, 11, s, fontsize=T5, color=MUTE, ha="center")''', '''    heads = ["Where it is read (typical mouse)", "Every event, a typical mouse per group", "Every mouse"]
    for x, s in ((44, heads[0]), (96, heads[1]), (153, heads[2])):
        text_mm(fig, H, x, 11, s, fontsize=T5, color=MUTE, ha="center")
    if task == "regression":
        for j, (g, nm) in enumerate((("CTL", "Control"), ("IED-", "IED−"), ("IED+", "IED+"))):
            fig.add_artist(plt.Circle(((140 + j * 12) / Hs.W, 1 - 14.2 / H), 0.0045, color=Hs.GROUP_COL[g], transform=fig.transFigure))
            text_mm(fig, H, 141.5 + j * 12, 14.2, nm, fontsize=4.4)''')
# type rows: legend under the title, not floating
rep('''                fig.add_artist(Rectangle(((9 + j * 14) / Hs.W, 1 - (y0 + 16) / H), 1.6 / Hs.W, 1.6 / H, color=col, transform=fig.transFigure))
                text_mm(fig, H, 11.5 + j * 14, y0 + 15.2, nm.replace(" to score DS3", ""), fontsize=4.2)''', '''                fig.add_artist(Rectangle(((9 + (j % 2) * 26) / Hs.W, 1 - (y0 + 9.2 + (j // 2) * 4) / H), 1.8 / Hs.W, 1.8 / H, color=col,
                                         transform=fig.transFigure))
                text_mm(fig, H, 11.6 + (j % 2) * 26, y0 + 8.3 + (j // 2) * 4, nm, fontsize=4.4)
            text_mm(fig, H, 9, y0 + 18, "Each mouse's events by the winning", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 20.6, "classifier's call (DS3: relative sink", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 23.2, "within ±0.5 between the two layers).", fontsize=4.4, color=MUTE)''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
