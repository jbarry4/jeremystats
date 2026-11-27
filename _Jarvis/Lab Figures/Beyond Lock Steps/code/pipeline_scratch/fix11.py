import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
p = os.path.join(HERE, "deep_qc.py")
s = io.open(p, encoding="utf-8").read()


def cut(a, b, new):
    global s
    i0 = s.index(a)
    i1 = s.index(b, i0)
    s = s[:i0] + new + s[i1:]


def rep(a, b):
    global s
    assert s.count(a) == 1, (a[:70], s.count(a))
    s = s.replace(a, b)


rep("H = 176.0", "H = 186.0")
# the notes: one block at the foot of the page
cut("    fig.text(4 / W, 1 - 171.5 / H,", "    # e  the classifier's axis", "")
cut('    fig.text(58 / W, 1 - 166.0 / H, "f: ', "    # g  the PCA plane", "")
cut("    fig.text(131 / W, 1 - 166.0 / H,", "    return fig\n\n\norder", '''    notes = [
        "d: mean sink ± s.e.m. of each type on one scale, at the depths of c. Dashed lines: the noise floor of each mean (99th percentile of the "
        "mean's |CSD| more than 30 ms from the DS peak).",
        "    Ticks at the right: sink centroid above the floor, where the sink clears it.",
        "f: ●  both sinks   ▲  upper sink   ▼  lower sink. Red ring: the best classifier. Open marker: one type holds under 5% of events, so the "
        "classifier is not eligible.",
        "g: PC1 and PC2 of the events, coloured by the best classifier. Grey dashed: k-means cut on PC1. Solid: two-Gaussian mixture, straight "
        "boundary. Dotted: mixture, curved boundary."
        + ("  Events keeping their type on 40 bootstrap refits: " + ", ".join(st_) + "." if st_ else "")]
    for i_, t_ in enumerate(notes):
        fig.text(4 / W, 1 - (169.5 + 3.6 * i_) / H, t_, fontsize=FS_S - 0.5, ha="left", va="center", color=MUTE)
''')
rep('lines.append(("%s: DS1 sink %.1f× floor," % (nm, I["clear"][b]) + chr(10) + "centroid %+d µm distal to DS2" % I["out"][b]).replace("-", "−"))',
    'lines.append("%s: DS1 sink %.1f× floor," % (nm, I["clear"][b]) + chr(10) + "centroid %d µm %s to DS2" % (abs(I["out"][b]), "distal" if I["out"][b] >= 0 else "proximal"))')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
