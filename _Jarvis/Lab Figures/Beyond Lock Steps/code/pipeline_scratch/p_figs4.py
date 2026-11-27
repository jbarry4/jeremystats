P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_room2_figs.py"
s = open(P, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


a0 = s.index("def overview(pdf, ctx):")
a1 = s.index("def main(only=None):")
s = s[:a0] + '''def overview(pdf, ctx):
    H = 150.0
    fig = Hs.page(H)
    Hs.stamp(fig, "UNCORRECTED")
    text_mm(fig, H, 3, 4, "Fig. 1 | Every model's held-out score, by target, input and model", fontsize=T7, fontweight="bold")
    views, models = list(E.VIEWS), list(E.MODELS)
    VS = {"core": "Waveform + depth", "context": "+ event context", "filters": "+ seven filters", "before_after": "+ before/after power",
          "events_all": "Every event feature", "mouse": "Per-mouse tables", "everything": "Everything", "nuisance": "Nuisance only"}
    MS_ = {"linear": "Linear", "lasso": "Lasso", "forest": "Forest", "boosting": "Boosting", "mlp": "Small net", "deepsets": "Deep sets",
           "attention": "Attention"}
    pos = [(30, 14), (88, 14), (146, 14), (30, 80), (88, 80)]
    for k, (t, title) in enumerate(TARGETS):
        x0, y0 = pos[k]
        M = np.full((len(views), len(models)), np.nan)
        Pm = np.zeros_like(M, bool)
        task = None
        for (tt, v, m), r in ctx.res.items():
            if tt != t:
                continue
            task = r["task"]
            M[views.index(v), models.index(m)] = r["score"]["main"]
            Pm[views.index(v), models.index(m)] = bool(r.get("passes"))
        letter(fig, H, x0 - (27 if x0 == 30 else 4), y0 - 1, "abcde"[k])
        text_mm(fig, H, x0, y0 + 0.5, "%s (%s)" % (title, SCORE[task]), fontsize=T5 + 0.3, fontweight="bold")
        ax = ax_mm(fig, H, x0, y0 + 4, 32, 38)
        lo, hi = (-0.5, 1.0) if task == "regression" else (0.0, 1.0)
        im = ax.imshow(M, cmap="RdBu_r", vmin=lo, vmax=hi, aspect="auto")
        mid = 0.25 if task == "regression" else 0.5
        for i in range(len(views)):
            for j in range(len(models)):
                if np.isfinite(M[i, j]):
                    ax.text(j, i, ("%.2f" % M[i, j]).replace("-", "−"), ha="center", va="center", fontsize=3.4,
                            color="white" if abs(M[i, j] - mid) > 0.33 else INK)
                    if Pm[i, j]:
                        ax.add_patch(Rectangle((j - 0.47, i - 0.47), 0.94, 0.94, fill=False, ec=INK, lw=0.9))
                else:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=3.6, color=MUTE)
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels([MS_[m] for m in models], fontsize=4.0, rotation=55, ha="right", rotation_mode="anchor")
        ax.set_yticks(range(len(views)))
        ax.set_yticklabels([VS[v] for v in views] if x0 == 30 else [""] * len(views), fontsize=4.2)
        ax.tick_params(length=0, pad=1.2)
        for s_ in ax.spines.values():
            s_.set_visible(False)
        cax = ax_mm(fig, H, x0 + 33.5, y0 + 4, 1.3, 38)
        cb = fig.colorbar(im, cax=cax)
        cb.ax.tick_params(labelsize=3.8, length=1.5, width=0.4, pad=1)
        cb.outline.set_linewidth(0.4)
        cb.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: ("%.1f" % v).replace("-", "−")))
    notes = ["Every square is one model (column) on one input view (row),", "scored only on mice it never saw.",
             "Boxed: reached the bar (AUC 0.80; Spearman ρ 0.70 for", "knockout percentage).", "Bottom row: nuisance-only inputs (where the dentate sat",
             "on the probe, year, event count, recording length).", "—: the set networks need events; these views have none.",
             "With one mouse held out, a model that learned nothing", "scores below 0.5, so 0.5 is not the chance line."]
    for i, ln in enumerate(notes):
        text_mm(fig, H, 132, 86 + i * 3.4, ln, fontsize=4.6, color=MUTE)
    pdf.savefig(fig)
    fig.savefig(os.path.join(OUT, "Fig1_overview.png"), dpi=300)
    plt.close(fig)


''' + s[a1:]
rep('''            what, unit = ("Each event's band power, %s; log2 (0 = no change). Spiking (MUA) is the raw 30 kHz signal band-passed 300–3000 Hz and "
                          "rectified" % ("after over before" if base.startswith("ba_pp_") else "over the mean of random moments of the same recording"),
                          "log2")''', '''            what, unit = ("Each event's %s, log2 (0 = no change); spiking = 300–3000 Hz, rectified" % (
                "power after over before" if base.startswith("ba_pp_") else "power over random moments"), "log2")''')
rep('''                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s): log2 over random moments" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])''',
    '''                    text_mm(fig, H, 24, y0 + 11.2, "%s (%s), log2 over random" % (rec.lab, ex[-1][2]), fontsize=4.4, color=ex[-1][1])''')
rep('''    o = np.argsort(u)
    ax.pcolormesh(np.arange(-50, 51) * 10.0, u[o], M[o], cmap="RdBu_r", vmin=-1, vmax=1, shading="nearest", rasterized=True)''',
    '''    o = np.argsort(u)
    show = (u >= -2.0) & (u <= 2.5)
    v = float(np.nanpercentile(np.abs(M[show]), 98)) or 1.0
    ax.pcolormesh(np.arange(-50, 51) * 10.0, u[o], M[o], cmap="RdBu_r", vmin=-v, vmax=v, shading="nearest", rasterized=True)
    ax.text(1.02, 1.0, "±%.1f" % v, transform=ax.transAxes, fontsize=3.8, va="top", color=MUTE)''')
open(P, "w", encoding="utf-8").write(s)
print("ok")
