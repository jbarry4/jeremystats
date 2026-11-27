import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_leads.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''    if feat == "lfp_pos_u":
        return S, peak, "lfp_depth"''', '''    if feat == "lfp_pos_u":
        return S, peak, "lfp_depth"
    if feat in ("cen_um", "cen_v", "sink_width_um", "outer_share"):
        rows = [(x, "", "#7A5195") for b in ("upper", "lower") for x in r.good(r.blade_rows(b, 5))]
        return S + rows, peak, "csd_depth"''')
rep('''    if kind == "lfp_depth":
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)''', '''    if kind == "csd_depth":
        ax.text(41.5, ((k["rowU"] + k["rowL"]) / 2 - lo) * 50, "every row\\nof each\\nblade", fontsize=4.6, color="#7A5195", va="center")
    if kind == "lfp_depth":
        a_, b_ = max(0, k["rowU"] - 5), min(63, k["rowL"] + 5)''')
rep('''    elif kind == "lfp_depth":
        ax.remove()''', '''    elif kind == "csd_depth":
        ax.remove()
        ax = ax_mm(fig, H, x + 8, y, 30, 40)
        lo_, hi_ = max(0, k["rowU"] - 8), min(63, k["rowL"] + 8)
        rows_ = np.arange(lo_, hi_ + 1)
        pr = -dsdata.fill_bad(r.csd_peak[i], r.bad_rows)[rows_]
        dep = (rows_ - lo_) * 50.0
        ax.plot(pr, dep, color=INK, lw=1.0)
        ax.axvline(0, color=HAIR, lw=0.5)
        for blade, row in (("upper", k["rowU"]), ("lower", k["rowL"])):
            br = r.good(r.blade_rows(blade, 5))
            Sb = np.maximum(-r.csd_peak[i, br], 0)
            ax.axhline((row - lo_) * 50, color=C_DS1, lw=0.7, ls=(0, (3, 2)))
            if Sb.sum() > 0:
                c_ = (Sb * br).sum() / Sb.sum()
                ax.plot([pr.max() * 0.9], [(c_ - lo_) * 50], marker="<", color="#7A5195", ms=4)
                ax.annotate("", xy=(pr.max() * 0.82, (c_ - lo_) * 50), xytext=(pr.max() * 0.82, (row - lo_) * 50),
                            arrowprops=dict(arrowstyle="->", lw=0.7, color="#7A5195", shrinkA=0, shrinkB=0))
        ax.text(pr.max() * 0.95, -20, "dashed: usual sink row\\n◄ this event's sink center", fontsize=4.2, color="#7A5195", ha="right", va="bottom")
        ax.set_ylim(dep[-1] + 25, -25)
        ax.set_xlabel("Sink at the DS peak (−CSD)", fontsize=FS_S)
        ax.set_ylabel("Depth below contact %d (µm)" % (lo_ + 1), fontsize=FS_S)
        ax.tick_params(labelsize=4.8)
        return event_note(r, feat, i)
    elif kind == "lfp_depth":
        ax.remove()''')
rep('''        ax.text(pr[j], uu[j] - 0.06, " largest: %.2f" % uu[j], fontsize=4.6, color="#7A5195", va="bottom")''',
    '''        ax.text(pr[j], uu[j] - 0.06, " most positive: %.2f" % uu[j], fontsize=4.6, color="#7A5195", va="bottom")''')
rep('''        ax.text(-39, -15, "mean LFP (purple +, brown −)", fontsize=4.4, color=INK, va="top")''',
    '''        ax.text(-39, -15, "mean LFP (brown +, purple −)", fontsize=4.4, color=INK, va="top")''')
rep('''    text_mm(fig, H, 4, 5, "Lead %d.  %s" % (k, L["title"]), fontsize=9, fontweight="bold")''',
    '''    text_mm(fig, H, 4, 5, ("Lead %d.  %s" % (k, L["title"])) if not L["title"].startswith("NOT A LEAD") else ("Appendix.  " + L["title"]), fontsize=9, fontweight="bold")''')
rep('''            fig.savefig(os.path.join(OUT, "Lead_%02d.png" % k), dpi=170)''', '''            fig.savefig(os.path.join(OUT, ("Lead_%02d.png" % k) if not L["title"].startswith("NOT A LEAD") else "Appendix_LFP_artifact.png"), dpi=170)''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
