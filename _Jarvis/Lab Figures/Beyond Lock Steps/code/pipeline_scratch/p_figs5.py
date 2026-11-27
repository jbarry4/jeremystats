P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2_figs.py"
s = open(P, encoding="utf-8").read()


def rep(a, b, n=1):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, n)


# the bars: four parts that add up to 1 (an unscored event is not also counted as DS1 or DS2)
rep('''        X = d.X[d.bag == mi]
        b0 = 0.0
        for f, col in (("ds1", C_DS1), ("ds2", C_DS2), ("ds3", C_DS3), ("unscored", "#CFCFCF")):
            s = float(np.nanmean(X[:, idx[f]]))''', '''        X = d.X[d.bag == mi]
        un = X[:, idx["unscored"]] > 0.5
        parts = {"ds1": (X[:, idx["ds1"]] > 0.5) & ~un, "ds2": (X[:, idx["ds2"]] > 0.5) & ~un, "ds3": X[:, idx["ds3"]] > 0.5, "unscored": un}
        b0 = 0.0
        for f, col in (("ds1", C_DS1), ("ds2", C_DS2), ("ds3", C_DS3), ("unscored", "#CFCFCF")):
            s = float(parts[f].mean())''')
rep('''            for j, (nm, col) in enumerate((("DS1", C_DS1), ("DS2", C_DS2), ("DS3", C_DS3), ("too small to score DS3", "#CFCFCF"))):''',
    '''            for j, (nm, col) in enumerate((("DS1", C_DS1), ("DS2", C_DS2), ("DS3", C_DS3), ("no DS3 score", "#CFCFCF"))):''')
rep('''            text_mm(fig, H, 9, y0 + 23.2, "within ±0.5 between the two layers).", fontsize=4.4, color=MUTE)''',
    '''            text_mm(fig, H, 9, y0 + 23.2, "within ±0.5 between the two layers;", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 25.8, "no score: too small, or no two layers to", fontsize=4.4, color=MUTE)
            text_mm(fig, H, 9, y0 + 28.4, "compare, as in m3).", fontsize=4.4, color=MUTE)''')
# minus signs in outlier labels
s = s.replace('"%s %s" % (d.labs[i], ML.fmt(vals[i]))', '("%s %s" % (d.labs[i], ML.fmt(vals[i]))).replace("-", "−")')
# no doubled brackets in names
rep('''"cen_um": "Sink centroid (µm)", "cen_v": "Sink centroid (v)",''', '''"cen_um": "Sink centroid in µm", "cen_v": "Sink centroid in v",''')
rep('''    m_txt = "; ".join("%s on %s (%s %.2f)" % (MODEL[r["model"]], VIEW[r["view"]], SCORE[task], r["score"]["main"]) for r in models)''',
    '''    m_txt = "; ".join("%s on %s, %s %.2f" % (MODEL[r["model"]], VIEW[r["view"]], SCORE[task], r["score"]["main"]) for r in models)''')
rep('''"values beyond the 1st and 99th percentiles are drawn at the edge. For the share of DS1, DS2 and DS3 events, the bars show every "
           "mouse's events by the winning classifier's call (DS3: relative sink within ±0.5; gray: too small to score).''',
    '''"values beyond the 1st and 99th percentiles are drawn at the edge. For the share of DS1, DS2 and DS3 events, the bars show every "
           "mouse's events by the winning classifier's call (DS3: relative sink within ±0.5; gray: no DS3 score, because the two layer sinks are "
           "under the noise floor or, as in m3, DS1's and DS2's sinks sit at the same contact so there are no two layers to compare).''')
open(P, "w", encoding="utf-8").write(s)
print("ok")

# Methods for this folder, from make_room2's text, stamped like the figures
M = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2.py"
m = open(M, encoding="utf-8").read()
m = m.replace('''def methods_pdf():
    H = 262.0''', '''def methods_pdf(out=None, word="PRELIMINARY", name="Room2_methods.pdf"):
    H = 262.0''')
m = m.replace('''    with PdfPages(os.path.join(OUT, "Room2_methods.pdf")) as pdf:
        fig = Hs.page(H)
        Hs.stamp(fig, "PRELIMINARY")''', '''    OUT_ = out or OUT
    with PdfPages(os.path.join(OUT_, name)) as pdf:
        fig = Hs.page(H)
        Hs.stamp(fig, word)''')
m = m.replace('''                fig.savefig(os.path.join(OUT, "Room2_methods_%d.png" % (len(pages) + 1)), dpi=150)
                pages.append(1)
                plt.close(fig)
                fig = Hs.page(H)
                Hs.stamp(fig, "PRELIMINARY")''', '''                fig.savefig(os.path.join(OUT_, name.replace(".pdf", "_%d.png" % (len(pages) + 1))), dpi=150)
                pages.append(1)
                plt.close(fig)
                fig = Hs.page(H)
                Hs.stamp(fig, word)''')
m = m.replace('''            pdf.savefig(fig)
            plt.close(fig)
            fig = Hs.page(H)
            Hs.stamp(fig, "PRELIMINARY")
            y = 8''', '''            pdf.savefig(fig)
            plt.close(fig)
            fig = Hs.page(H)
            Hs.stamp(fig, word)
            y = 8''')
m = m.replace('''        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT, "Room2_methods_%d.png" % (len(pages) + 1)), dpi=150)
        plt.close(fig)''', '''        pdf.savefig(fig)
        fig.savefig(os.path.join(OUT_, name.replace(".pdf", "_%d.png" % (len(pages) + 1))), dpi=150)
        plt.close(fig)''')
m = m.replace('''"slowest without the drop-one-family step). The same code gives the same numbers on this computer and on the cluster (checked on run r002)."),''',
              '''"slowest without the drop-one-family step; all 260 r003 tasks finished, so r004 is not used). The same code gives the same numbers on this "
     "computer and on the cluster (checked on run r002). Figures: battery/make_room2_figs.py."),
    ("Significance signs", "On the figures, uncorrected: held-out scores against the truth (one-sided Mann-Whitney on held-out scores; Spearman for the "
     "knockout guess; binomial against 1 in 3 for three groups) and, per parameter, between groups (two-sided Mann-Whitney; Kruskal-Wallis for "
     "three; Spearman with knockout). * P < 0.05, ** P < 0.01, *** P < 0.001. None is corrected for the 260 models, the choice of the best three, "
     "or the five parameters shown, so none is a finding."),''')
open(M, "w", encoding="utf-8").write(m)
print("ok methods")
