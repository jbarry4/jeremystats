import io
P = r"C:\Users\Z390\Desktop\DS_PTEN_figures_2026-11-16\battery\make_sanity.py"
s = io.open(P, encoding="utf-8").read()


def rep(a, b, cnt=1):
    global s
    assert s.count(a) == cnt, (a[:70], s.count(a))
    s = s.replace(a, b)


rep('''    yA = y0 + 9
    hA = 44
    # a  mean CSD down the probe
    letter(fig, H, 2, yA - 3, "a")
    ax = ax_mm(fig, H, 14, yA, 34, hA)''', '''    yA = y0 + 11
    hA = 44
    for x, ttl in ((2, "a  Each type's mean CSD down the probe"), (58, "b  Events of each type"), (100, "c  Each event at the two DS3 contacts"),
                   (142, "d  DS3 score of each event")):
        text_mm(fig, H, x, yA - 4.5, ttl, fontsize=FS_S + 0.3, fontweight="bold")
    # a  mean CSD down the probe
    ax = ax_mm(fig, H, 14, yA, 30, hA)''')
rep('''    for g in sorted({kl["rowGU"], kl["rowGL"]}):
        ax.plot([span * 0.98], [(g - lo) * 50], marker="<", color=Hs.RED, ms=3.2, clip_on=False)
    w = f["w"]
    if "score" in w:
        for row, nm in ((w["outer"], "outer"), (w["middle"], "middle")):
            ax.plot([-span], [(row - lo) * 50], marker=">", color=C_DS3, ms=3.4, clip_on=False)
            ax.text(-span * 1.08, (row - lo) * 50, nm, fontsize=4.6, color=C_DS3, ha="right", va="center")''', '''    for g in sorted({kl["rowGU"], kl["rowGL"]}):
        ax.plot([span], [(g - lo) * 50], marker="<", color=Hs.RED, ms=3.2, clip_on=False)
        ax.text(span * 1.12, (g - lo) * 50, "cell layer\\nsource", fontsize=4.2, color=Hs.RED, ha="left", va="center", linespacing=0.9)
    w = f["w"]
    if "score" in w:
        o_y, m_y = (w["outer"] - lo) * 50, (w["middle"] - lo) * 50
        dy = 0 if abs(o_y - m_y) > 90 else 45
        for yv, nm, sg in ((o_y, "outer", -1 if o_y < m_y else 1), (m_y, "middle", 1 if o_y < m_y else -1)):
            ax.plot([span], [yv], marker="<", color=C_DS3, ms=3.4, clip_on=False)
            ax.text(span * 1.12, yv + sg * dy, nm, fontsize=4.6, color=C_DS3, ha="left", va="center")''')
rep('''    ax.set_xlabel("CSD at the DS peak\\n(left = sink, right = source)", fontsize=FS_S)''', '''    ax.set_xlabel("CSD at the DS peak (±3 ms)\\nleft = sink, right = source", fontsize=FS_S - 0.3)''')
rep('''    letter(fig, H, 52, yA - 3, "b")
    ax = ax_mm(fig, H, 56, yA + 4, 32, hA - 14)''', '''    ax = ax_mm(fig, H, 60, yA + 3, 30, hA - 16)''')
rep('''    if f["x_counts"] is None:
        ax.text(0, len(bars) - 0.2, "DS3 cannot be scored", fontsize=4.8, color=MUTE, va="top")''', '''    if f["x_counts"] is None:
        ax.text(0, 0.62, "DS3 cannot be scored", fontsize=4.8, color=MUTE, va="center")
    ax.text(0, -1.25, "DS1", fontsize=5, color=C_DS1, fontweight="bold", va="center")
    ax.text(r.n * 0.2, -1.25, "DS3", fontsize=5, color=C_DS3, fontweight="bold", va="center")
    ax.text(r.n * 0.4, -1.25, "DS2", fontsize=5, color=C_DS2, fontweight="bold", va="center")''')
rep('''    ax.set_ylim(len(bars) - 0.4, -0.75)''', '''    ax.set_ylim(max(len(bars), 2) - 0.4, -0.75)''')
rep('''    letter(fig, H, 96, yA - 3, "c")
    ax = ax_mm(fig, H, 104, yA, 32, 32)''', '''    ax = ax_mm(fig, H, 106, yA, 30, 30)''')
rep('''    letter(fig, H, 142, yA - 3, "d")
    ax = ax_mm(fig, H, 148, yA, 31, 28)''', '''    ax = ax_mm(fig, H, 150, yA, 29, 28)''')
rep('''    yy = yA + hA + 6''', '''    yy = yA + hA + 11''')
rep('''                H = 262.0''', '''                H = 276.0''')
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("ok")
