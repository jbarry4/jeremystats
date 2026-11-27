import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''    if feat in ("lfp_fwhm", "lfp_asym", "lfp_pre", "lfp_post", "lat_sink_minus_lfp"):
        return O, None, "lfp_time"''', '''    if feat in ("lfp_fwhm", "lfp_asym", "lfp_pre", "lfp_post", "lat_sink_minus_lfp"):
        return O, ((-30, -10) if feat == "lfp_pre" else ((10, 30) if feat == "lfp_post" else None)), "lfp_time"
    if feat == "lfp_pos_u":
        return S, peak, "lfp_depth"''')
# panel a: LFP image for LFP features
rep('''    M = dsdata.fill_bad(r.csd.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
    v = np.nanpercentile(np.abs(M), 99)
    ax.imshow(M, aspect="auto", cmap=CSD_CMAP.reversed(), vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25], interpolation="bilinear")''',
    '''    if kind in ("lfp_time", "lfp_depth"):
        M = dsdata.fill_bad(r.lfp.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
        v = np.nanpercentile(np.abs(M), 99)
        ax.imshow(M, aspect="auto", cmap="PuOr_r", vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25], interpolation="bilinear")
        ax.text(-39, -15, "mean LFP (purple +, brown −)", fontsize=4.4, color=INK, va="top")
    else:
        M = dsdata.fill_bad(r.csd.mean(axis=0).T, r.bad_rows).T[lo:hi + 1]
        v = np.nanpercentile(np.abs(M), 99)
        ax.imshow(M, aspect="auto", cmap=CSD_CMAP.reversed(), vmin=-v, vmax=v, extent=[r.t_ms[0], r.t_ms[-1], (hi - lo + 0.5) * 50, -25], interpolation="bilinear")
        ax.text(-39, -15, "mean CSD (blue sink, red source)", fontsize=4.4, color=INK, va="top")''')
rep('''    if kind == "between":
        ax.text(41.5, ((k["rowU"] + k["rowL"]) / 2 - lo) * 50, "every row\\nbetween", fontsize=4.6, color="#7A5195", va="center")''',
    '''    if kind == "between":
        ax.text(41.5, ((k["rowU"] + k["rowL"]) / 2 - lo) * 50, "every row\\nbetween", fontsize=4.6, color="#7A5195", va="center")
    if kind == "lfp_depth":
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
        ax.plot([3.5, 3.5], [(a_ - lo) * 50, (b_ - lo) * 50], color="#7A5195", lw=2.0)
        ax.text(41.5, ((a_ + b_) / 2 - lo) * 50, "searched\\nfor the\\nlargest\\nLFP", fontsize=4.6, color="#7A5195", va="center")''')
# panel b: LFP depth profile of one event
rep('''    else:
        lf = r.lfp[i, src].mean(axis=0)''', '''    elif kind == "lfp_depth":
        ax.remove()
        ax = ax_mm(fig, H, x + 8, y, 30, 40)
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)
        rows_ = np.arange(a_, b_ + 1)
        pr = dsdata.fill_bad(r.lfp_peak[i], r.bad_rows)[rows_]
        uu = r.u(rows_)
        ax.plot(pr, uu, color=INK, lw=1.0)
        j = int(np.argmax(pr))
        ax.plot([pr[j]], [uu[j]], "o", color="#7A5195", ms=3.5)
        ax.text(pr[j], uu[j] - 0.06, " largest: %.2f" % uu[j], fontsize=4.6, color="#7A5195", va="bottom")
        for yv, wd in ((0, "upper sink row"), (1, "lower sink row")):
            ax.axhline(yv, color=HAIR, lw=0.5)
            ax.text(ax.get_xlim()[0], yv, wd, fontsize=4.2, color=MUTE, va="bottom")
        ax.set_ylim(uu[-1] + 0.05, uu[0] - 0.05)
        ax.set_xlabel("LFP at the DS peak (µV)", fontsize=FS_S)
        ax.set_ylabel("Blade-to-blade position", fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
        return event_note(r, feat, i)
    else:
        lf = r.lfp[i, src].mean(axis=0)''')
rep('''        if feat == "lfp_fwhm":
            draw_fwhm(ax, t, lf, INK)''', '''        if feat == "lfp_fwhm":
            draw_fwhm(ax, t, lf, INK)
        if feat in ("lfp_pre", "lfp_post"):
            c0 = int(np.argmin(np.abs(t)))
            p = c0 - 6 + int(np.argmax(lf[c0 - 6:c0 + 7]))
            w_ = (t >= -30) & (t <= -10) if feat == "lfp_pre" else (t >= 10) & (t <= 30)
            ax.plot([t[p]], [lf[p]], "o", color=INK, ms=3)
            ax.plot([t[w_][0], t[w_][-1]], [lf[w_].mean()] * 2, color="#7A5195", lw=2.2)
            ax.text(t[w_][0], lf[w_].mean(), "mean here\\n", fontsize=4.4, color="#7A5195", va="bottom")
            ax.text(t[p] + 1.5, lf[p], "peak", fontsize=4.4, color=INK, va="center")''')
# landmark leads: their own build-up
rep('''    else:
        y2 = y + 6
        for i, s in enumerate(L.get("steps", [])):''', '''    elif P["name"].startswith("gcl_to_sink"):
        y0 = y + 5
        text_mm(fig, H, 2, y0 - 2.5, "a–d  Where the distance is read: the average dentate spike (CSD at the peak) down the probe, one typical recording per side", fontsize=FS_S, fontweight="bold")
        for j, side in enumerate(sides):
            cand = [r for r in recs if in_side(r, side)]
            vals = np.array([Mdf.loc[L["id"]][r.lab] for r in cand])
            r = cand[int(np.argmin(np.abs(vals - np.median(vals))))]
            panel_landmarks(fig, H, 22 + j * 88, y0 + 1, r)
        y2 = y0 + 66
    else:
        y2 = y + 6
        for i, s in enumerate(L.get("steps", [])):''')
rep('''def pick_event(vals):''', '''def panel_landmarks(fig, H, x, y, r):
    k = r.landmarks
    ax = ax_mm(fig, H, x, y, 40, 56)
    lo, hi = max(0, k["rowU"] - 7), min(63, k["rowL"] + 7)
    rows = np.arange(lo, hi + 1)
    p = r.mean_csd_peak[rows]
    dep = (rows - lo) * 50.0
    ax.plot(p, dep, color=INK, lw=1.0)
    ax.axvline(0, color=HAIR, lw=0.5)
    span = np.abs(p).max() * 1.1
    ax.set_xlim(-span, span * 1.9)
    for a_, b_, nm in ((k["U"], k["GU"], k["gcl_to_sink_upper_um"]), (k["GL"], k["L"], k["gcl_to_sink_lower_um"])):
        ya, yb = (a_ - lo) * 50, (b_ - lo) * 50
        ax.annotate("", xy=(span * 1.25, ya), xytext=(span * 1.25, yb), arrowprops=dict(arrowstyle="<->", lw=0.8, color="#7A5195", shrinkA=0, shrinkB=0))
        ax.text(span * 1.32, (ya + yb) / 2, "%.0f µm" % nm, fontsize=5, color="#7A5195", va="center")
    for key, col, wd in (("U", C_DS1, "sink"), ("L", C_DS1, "sink"), ("GU", RED, "source"), ("GL", RED, "source")):
        yy = (k[key] - lo) * 50
        ax.plot([span * 1.0, span * 1.18], [yy, yy], color=col, lw=1.2)
    ax.text(span * 1.0, (k["U"] - lo) * 50 - 30, "deepest sink", fontsize=4.4, color=C_DS1, va="bottom")
    ax.set_ylim(dep[-1] + 25, -25)
    ax.set_title("%s (%s): mean of the blades %.0f µm" % (r.lab, Hs.GROUP_NAME[r.subgroup], 0.5 * (k["gcl_to_sink_upper_um"] + k["gcl_to_sink_lower_um"])),
                 fontsize=FS_S, loc="left", pad=3, color=Hs.col_of(r))
    ax.set_xlabel("CSD at the DS peak (left = sink)", fontsize=FS_S)
    ax.set_ylabel("Depth below contact %d (µm)" % (lo + 1), fontsize=FS_S)
    ax.tick_params(labelsize=4.8)


def pick_event(vals):''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
