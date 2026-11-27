P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2_figs.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


rep('''    ax.text(0.98, 0.98, stars(p), transform=ax.transAxes, ha="right", va="top", fontsize=T7, fontweight="bold", color=INK)
''', '')
rep('''    text_mm(fig, H, x, y - 1.7, "%s %.2f (bar %.2f; nuisance only %.2f)" % (SCORE[task], sc, E.BAR[task], base), fontsize=T5)''',
    '''    text_mm(fig, H, x, y - 1.7, "%s %.2f %s  (bar %.2f; nuisance only %.2f)" % (SCORE[task], sc, stars(p), E.BAR[task], base), fontsize=T5)''')
rep('''        elif stat == "sd":
            m_, s_ = np.mean(v), np.std(v)
            ax.plot([max(lo, m_ - s_), min(hi, m_ + s_)], [top * (0.95 - 0.07 * k_)] * 2, color=col, lw=1.4)''',
    '''        elif stat == "sd":
            m_, s_ = np.mean(v), np.std(v)
            yy = top * (0.95 - 0.08 * k_)
            ax.plot([max(lo, m_ - s_), min(hi, m_ + s_)], [yy, yy], color=col, lw=0.8)
            ax.plot([m_], [yy], marker="o", ms=2.2, color=col)''')
rep('''            q1, q3 = np.percentile(v, [25, 75])
            ax.plot([q1, q3], [top * (0.95 - 0.07 * k_)] * 2, color=col, lw=1.4)''',
    '''            q1, q3 = np.percentile(v, [25, 75])
            yy = top * (0.95 - 0.08 * k_)
            ax.plot([q1, q3], [yy, yy], color=col, lw=0.8)
            ax.plot([np.median(v)], [yy], marker="o", ms=2.2, color=col)''')
# legends: the significance tests
rep('''"%s Dots are mice (n = %d), colored by group; black lines are group medians.''',
    '''"%s Dots are mice (n = %d), colored by group; black lines are group medians. Significance signs (raw P, uncorrected for the 260 models or "
           "the choice of these three): one-sided Mann-Whitney test of the held-out scores between the two groups; Spearman correlation of the held-out "
           "guess with the true knockout; binomial test of the share of held-out calls right against 1 in 3 for three groups; * P < 0.05, ** P < 0.01, "
           "*** P < 0.001, n.s. not significant.''')
rep('''"as the models read it (the statistic named in the row title; for a set network, which reads every event, the mouse's median), with "
           "group medians." % fig_no),''', '''"as the models read it (the statistic named in the row title; for a set network, which reads every event, the mouse's median), with "
           "group medians; a mouse beyond three interquartile ranges is drawn at the edge as a triangle with its value. In the middle panels, "
           "dashed lines mark the statistic the models read (median, mean or a percentile); a bar with a dot marks mean ± SD or the middle half "
           "around the median. Significance signs over the right panels (raw P, uncorrected): two-sided Mann-Whitney test between two groups, "
           "Kruskal-Wallis across three, Spearman correlation with knockout for the knockout target." % fig_no),''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
