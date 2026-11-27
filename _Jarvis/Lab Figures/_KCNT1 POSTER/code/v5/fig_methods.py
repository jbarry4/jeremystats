"""Methods figures (poster v5), each at its print size.
  M_headfixed  the NBH'25 poster's head-fixed mouse illustration (its own image, with its transparency) and a probe drawn here
  M_laminar    the NBH'25 poster's H3 laminar recording (a control mouse; its 64 traces as drawn, data/nbh_laminar.npz) with its
               printed layer labels, 1 s and 500 uV bars
  M_events     the curated dentate spike and IED of KCNT1 m1609 (VACC raw, methods_fig_v4.py's processing) in the v5 style
  M_histology  Dylan Marchand's 2024 SST/NeuN hilus image (the PDF's own tiles)
  M_arena      the NBH'25 poster's arena photo (its own image) with the rotation and shock zone drawn here"""
import os, sys, json
import numpy as np
import fitz
from PIL import Image
from matplotlib.patches import FancyArrowPatch, Polygon, FancyBboxPatch, Wedge, Rectangle, ConnectionPatch
import style as S
import hpc

HERE = os.path.dirname(os.path.abspath(__file__))
RES = r"C:\Users\info\Desktop\JeremyStats\_Jarvis\Lab Figures\KCNT1 POSTER\Poster Resources"
NBH = fitz.open(os.path.join(RES, "FinalNBH'25 1.pdf"))
DYL = fitz.open(os.path.join(RES, "FinalKcnt1_Dylan 1.pdf"))
LIGHT = "#2F86D6"
R = S.REGION


def pix_rgba(doc, xref):
    p = fitz.Pixmap(doc, xref)
    smask = doc.xref_get_key(xref, "SMask")
    if p.colorspace is None or p.colorspace.n != 3:
        p = fitz.Pixmap(fitz.csRGB, p)
    rgb = np.frombuffer(p.samples, np.uint8).reshape(p.height, p.width, p.n)[:, :, :3]
    if smask[0] == "xref":
        m = fitz.Pixmap(doc, int(smask[1].split()[0]))
        a = np.frombuffer(m.samples, np.uint8).reshape(m.height, m.width)
        return np.dstack([rgb, a])
    return np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])


# ===================================================================== head-fixed
fig = S.figure(5.0, 3.65)
S.title(fig, 0.0, 0.0, "Head-fixed recording", size=S.LABEL)
mouse = pix_rgba(NBH, 1042)
ma = S.ax_at(fig, 0.0, 1.5, 3.2, 3.2 * mouse.shape[0] / mouse.shape[1])
ma.imshow(mouse, interpolation="bilinear"); ma.axis("off")
# head bar and the probe going in (in the mouse image's pixels)
H, W = mouse.shape[:2]
hx, hy = 0.452 * W, 0.255 * H                 # the head window
ma.add_patch(FancyBboxPatch((0.08 * W, -0.42 * H), 0.86 * W, 0.09 * H, boxstyle="round,pad=0,rounding_size=20", fc="#4A5260", ec="none",
                            clip_on=False, zorder=3))
ma.add_patch(FancyBboxPatch((0.37 * W, -0.33 * H), 0.12 * W, 0.14 * H, boxstyle="round,pad=0,rounding_size=12", fc="#4A5260", ec="none",
                            clip_on=False, zorder=3))
ma.plot([hx - 6, hx - 6], [-0.19 * H, hy], c=S.INK, lw=1.4, clip_on=False, zorder=4)
ma.plot([hx + 7, hx + 7], [-0.19 * H, hy], c=LIGHT, lw=1.4, clip_on=False, zorder=4)
ma.text(0.5 * W, -0.46 * H, "head bar", ha="center", va="bottom", fontsize=S.NOTE, color=S.SOFT)
# the probe, drawn
pa = S.ax_at(fig, 3.3, 0.42, 1.65, 3.15)
pa.set_xlim(-0.05, 1); pa.set_ylim(1.08, -0.06); pa.axis("off")
shank = Polygon([[0.14, -0.02], [0.32, -0.02], [0.32, 0.92], [0.23, 1.0], [0.14, 0.92]], closed=True, fc="#D5DAE0", ec="#8A94A0", lw=0.8)
pa.add_patch(shank)
for i in range(64):
    yy = 0.06 + i * (0.86 / 63)
    pa.add_patch(Rectangle((0.2, yy - 0.004), 0.06, 0.008, fc=S.INK, ec="none"))
pa.plot([0.07, 0.07], [-0.02, 0.84], c=LIGHT, lw=2.6, solid_capstyle="butt")
pa.add_patch(Polygon([[0.07, 0.84], [-0.03, 1.03], [0.17, 1.03]], closed=True, fc=LIGHT, alpha=0.28, ec="none"))
pa.plot([0.39, 0.39], [0.06, 0.92], c=S.INK, lw=1.0)
pa.plot([0.36, 0.42], [0.06, 0.06], c=S.INK, lw=1.0); pa.plot([0.36, 0.42], [0.92, 0.92], c=S.INK, lw=1.0)
pa.text(0.45, 0.49, "64 contacts\n20 µm apart\n1.28 mm", ha="left", va="center", fontsize=S.SMALL, color=S.INK, linespacing=1.05)
pa.text(0.07, -0.04, "fiber", ha="center", va="bottom", fontsize=S.SMALL, color=LIGHT, fontweight="bold")
pa.text(0.23, -0.04, "probe", ha="left", va="bottom", fontsize=S.SMALL, color=S.INK, fontweight="bold")
for ya in (0.0, 1.0):
    fig.add_artist(ConnectionPatch(xyA=(hx + 12, hy - 0.05 * H if ya == 0 else hy + 0.02 * H), coordsA=ma.transData,
                                   xyB=(0.0, -0.02 if ya == 0 else 1.03), coordsB=pa.transData, color=S.FAINT, lw=0.9, ls=(0, (3, 2))))
S.save(fig, os.path.join(HERE, "out", "M_headfixed.png"))
print("M_headfixed")

# ===================================================================== laminar recording
L = np.load(os.path.join(HERE, "data", "nbh_laminar.npz"), allow_pickle=True)
fig = S.figure(8.6, 3.65)
SEC, UV = float(L["sec_pt"]), float(L["uv_pt"])
lay = json.loads(str(L["layers"]))
ax = S.ax_at(fig, 1.55, 0.36, 6.55, 2.98)
SRCPDF = fitz.open(os.path.join(RES, "FinalNBH'25 1.pdf"))[0]
P = SRCPDF.rect.width / 2212.0
Rr = fitz.Rect(338 * P, 514 * P, 848 * P, 742 * P)
paths = [d for d in SRCPDF.get_drawings() if fitz.Rect(d["rect"]).intersects(Rr) and d["type"] == "s"]
xmin = min(fitz.Rect(d["rect"]).x0 for d in paths)
for d in paths:
    its = [it for it in d["items"] if it[0] == "l"]
    pts = np.array([(it[1].x, it[1].y) for it in its] + [(its[-1][2].x, its[-1][2].y)])
    ax.plot((pts[:, 0] - xmin) / SEC, pts[:, 1], c=S.INK, lw=0.32)
ytop, ybot = 852, 1140
ax.set_xlim(0, 7.15); ax.set_ylim(ybot, ytop); S.bare(ax)
labs = [("SP", "SP", R["CA1"]), ("SR", "SR", R["CA1"]), ("SLM", "SLM", R["CA1"]), ("OML", "OML", R["Supra blade"]),
        ("MML", "MML", R["Supra blade"]), ("GCL", "GCL", R["Supra blade"]), ("HILUS", "Hilus", R["Hilus"])]
for key, txt, colr in labs:
    ax.text(-0.12, lay[key], txt, ha="right", va="center", fontsize=S.NOTE + 0.5, color=colr, transform=ax.transData)
for nm, a0, a1, colr in (("CA1", ytop + 4, (lay["SLM"] + lay["OML"]) / 2 - 3, R["CA1"]), ("DG", (lay["SLM"] + lay["OML"]) / 2 + 3, ybot - 2, R["Supra blade"])):
    ax.plot([-0.95, -0.95], [a0, a1], c=colr, lw=2.2, clip_on=False, solid_capstyle="butt")
    ax.text(-1.08, (a0 + a1) / 2, nm, rotation=90, ha="right", va="center", fontsize=S.LABEL, fontweight="bold", color=colr)
ax.plot([6.15, 7.15], [ybot + 6, ybot + 6], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(6.65, ybot + 9, "1 s", ha="center", va="top", fontsize=S.NOTE, color=S.INK)
ax.plot([7.25, 7.25], [ybot - 2, ybot - 2 - UV], c=S.INK, lw=1.8, clip_on=False, solid_capstyle="butt")
ax.text(7.32, ybot - 2 - UV / 2, "500 µV", rotation=90, ha="left", va="center", fontsize=S.NOTE, color=S.INK)
S.title(fig, 0.0, 0.0, "Laminar recording, CA1 to dentate gyrus (64 contacts)", size=S.LABEL)
S.save(fig, os.path.join(HERE, "out", "M_laminar.png"))
print("M_laminar")

# ===================================================================== DS and IED
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "vacc"))
import methods_fig_v4 as MF  # noqa: E402
from scipy.signal import butter, sosfiltfilt  # noqa: E402
VACC = os.path.join(os.path.dirname(HERE), "vacc")
EV = [("Dentate spike", os.path.join(VACC, "windows_m1609.npz"), 1716.611, True),
      ("IED", os.path.join(VACC, "ied_m1609_s1.npz"), 882.748327, False)]
ev = []
for label, npz, tv, is_ds in EV:
    X, half, z = MF.load(npz, tv)
    Xn = MF.notch(X)
    tt = np.arange(X.shape[-1]) / MF.FS - half
    w = (tt >= -MF.HALF) & (tt <= MF.HALF)
    V = Xn[[c - 1 for c in MF.EVEN]]
    if is_ds:
        V = MF.band(V, 5.0, 100.0)
    else:
        V = sosfiltfilt(butter(3, 1.0, btype="high", fs=MF.FS, output="sos"), V, axis=-1)
        V = V - np.median(V[:, (tt >= -0.15) & (tt < -0.06)], axis=1, keepdims=True)
    V = V[:, w]
    sw = (tt >= -0.5) & (tt <= 0.5)
    SP = []
    for c in MF.SPEC_CH:
        s_, f_, ts_ = MF.xf_spec(Xn[c - 1][sw])
        SP.append((s_ - MF.baseline(z, c)[:, None], f_, ts_ - 0.5))
    ev.append(dict(label=label, V=V, C=MF.csd(V), S=SP, tm=tt[w] * 1000, is_ds=is_ds))
gain = np.percentile(np.abs(ev[0]["V"]), 99.5)
clim = np.percentile(np.abs(ev[0]["C"]), 99.5)
allS = np.concatenate([s.ravel() for e in ev for s, _f, _t in e["S"]])
slo, shi = -6.0, max(12.0, float(np.percentile(allS, 99.9)))
fig = S.figure(13.8, 5.0)
Y0, HH = 0.62, 3.78
for k, e in enumerate(ev):
    x0 = 1.35 + k * 5.5
    tm = e["tm"]
    S.text_at(fig, x0, 0.0, e["label"], fontsize=S.TITLE + 1, fontweight="bold", color=S.INK)
    S.text_at(fig, x0 + (1.55 if e["is_ds"] else 0.48), 0.04, "5–100 Hz" if e["is_ds"] else "above 1 Hz · same voltage and CSD scales",
              fontsize=S.NOTE, color=S.SOFT)
    # voltage
    ax = S.ax_at(fig, x0, Y0, 1.3, HH)
    for r in range(32):
        ax.plot(tm, r - 1.4 * e["V"][r] / gain, color=S.INK, lw=0.6, clip_on=False)
    ax.set_xlim(tm[0], tm[-1]); ax.set_ylim(32.3, -1.5); S.bare(ax)
    if k == 0:
        for key, txt, colr in (("upper_sink", "supra blade sink", R["Supra blade"]), ("source", "hilar source", R["Hilus"]),
                               ("lower_sink", "infra blade sink", R["Infra blade"])):
            ch = MF.MARKS[key]
            ax.text(tm[0] - 22, MF.EVEN.index(ch), "%s\nch %d" % (txt, ch), ha="right", va="center", fontsize=S.SMALL + 0.5,
                    color=colr, fontweight="bold", linespacing=0.95)
        for c in (2, 64):
            ax.text(tm[0] - 22, MF.EVEN.index(c), "ch %d" % c, ha="right", va="center", fontsize=S.SMALL + 0.5, color=S.SOFT)
    sb = 1000.0
    ax.plot([tm[-1] + 10] * 2, [31, 31 - 1.4 * sb / gain], color=S.INK, lw=1.6, clip_on=False, solid_capstyle="butt")
    ax.text(tm[-1] + 20, 31 - 0.7 * sb / gain, "1 mV", rotation=90, va="center", ha="left", fontsize=S.NOTE)
    ax.plot([tm[-1] - 50, tm[-1]], [32.9, 32.9], color=S.INK, lw=1.6, clip_on=False, solid_capstyle="butt")
    ax.text(tm[-1] - 25, 33.3, "50 ms", ha="center", va="top", fontsize=S.NOTE)
    ax.set_title("Voltage", fontsize=S.LABEL, pad=4, fontweight="normal")
    # CSD
    ax = S.ax_at(fig, x0 + 1.75, Y0, 1.4, HH)
    im = ax.imshow(e["C"], aspect="auto", cmap=S.CSD_CMAP, vmin=-clim, vmax=clim, interpolation="bilinear", extent=[tm[0], tm[-1], 31.5, -0.5])
    ax.set_yticks([]); ax.spines["left"].set_visible(False)
    ax.set_xticks([-100, 0, 100]); ax.set_xlabel("ms", labelpad=1)
    ax.set_title("CSD", fontsize=S.LABEL, pad=4, fontweight="normal")
    # spectrograms, 8 contacts
    sh = (HH - 7 * 0.05) / 8
    for j, (c, (s_, f_, ts_)) in enumerate(zip(MF.SPEC_CH, e["S"])):
        ax2 = S.ax_at(fig, x0 + 3.62 + (0.76 if k == 1 else 0), Y0 + j * (sh + 0.05), 1.42, sh)
        im2 = ax2.pcolormesh(ts_ * 1000, f_, s_, cmap=S.SPEC_CMAP, vmin=slo, vmax=shi, shading="gouraud", rasterized=True)
        ax2.set_ylim(0, 600); ax2.set_xlim(-500, 500); ax2.set_yticks([])
        ax2.axvline(0, color="w", lw=0.6, ls=(0, (2, 2)), alpha=0.7)
        ax2.text(-0.05, 0.5, "ch %d" % c, transform=ax2.transAxes, ha="right", va="center", fontsize=S.SMALL, color=S.SOFT)
        if j < 7:
            ax2.set_xticks([]); ax2.spines["bottom"].set_visible(False)
        else:
            ax2.set_xticks([-400, 0, 400]); ax2.set_xlabel("ms", labelpad=1)
        if j == 0:
            ax2.set_title("0–600 Hz", fontsize=S.LABEL, pad=4, fontweight="normal")
    if k == 1:
        cax = S.ax_at(fig, x0 + 3.24, Y0 + 0.9, 0.11, HH - 1.8)
        cb = fig.colorbar(im, cax=cax, ticks=[-clim * 0.85, clim * 0.85])
        cb.ax.set_yticklabels(["sink", "source"], fontsize=S.NOTE); cb.ax.tick_params(length=0, pad=2); cb.outline.set_visible(False)
        cax = S.ax_at(fig, x0 + 5.93, Y0 + 0.9, 0.11, HH - 1.8)
        cb = fig.colorbar(im2, cax=cax, ticks=[slo, 0, shi])
        cb.ax.set_yticklabels(["−6", "0", "+%d" % round(shi)], fontsize=S.SMALL); cb.ax.tick_params(length=2, pad=2)
        cb.outline.set_visible(False)
        S.text_at(fig, x0 + 5.985, Y0 + 0.62, "dB", fontsize=S.NOTE, ha="center")
S.save(fig, os.path.join(HERE, "out", "M_events.png"))
print("M_events: gain %.0f uV, CSD clim %.0f, spectrogram %.0f..%.0f dB, IED peak %.0f uV" % (gain, clim, slo, shi, np.abs(ev[1]["V"]).max()))

# ===================================================================== histology
page = DYL[0]
P = 3456 / 2212.0
Rh = fitz.Rect(1878 * P, 112 * P, 2188 * P, 419 * P)
tiles = [(fitz.Rect(i["bbox"]), i) for i in page.get_image_info(xrefs=True) if fitz.Rect(i["bbox"]).intersects(Rh)]
s = 4.0                                                  # px per pt (half the tiles' own 8.33)
x0 = min(t[0].x0 for t in tiles); y0 = min(t[0].y0 for t in tiles)
x1 = max(t[0].x1 for t in tiles); y1 = max(t[0].y1 for t in tiles)
can = Image.new("RGB", (int((x1 - x0) * s), int((y1 - y0) * s)), "black")
for r, i in tiles:
    p = fitz.Pixmap(DYL, i["xref"])
    if p.colorspace is None or p.colorspace.n != 3:
        p = fitz.Pixmap(fitz.csRGB, p)
    im = Image.frombytes("RGB", (p.width, p.height), p.samples[:p.width * p.height * 3] if p.n == 3 else p.samples)
    can.paste(im.resize((max(1, int(round(r.width * s))), max(1, int(round(r.height * s)))), Image.LANCZOS),
              (int(round((r.x0 - x0) * s)), int(round((r.y0 - y0) * s))))
fig = S.figure(2.6, 2.6)
ax = S.ax_at(fig, 0, 0, 2.6, 2.6)
ax.imshow(np.asarray(can)); ax.axis("off")
ax.text(0.04, 0.96, "SST", transform=ax.transAxes, ha="left", va="top", fontsize=S.NOTE + 1, fontweight="bold", color="#7CFC6A")
ax.text(0.04, 0.85, "NeuN", transform=ax.transAxes, ha="left", va="top", fontsize=S.NOTE + 1, fontweight="bold", color="#FF6B4A")
S.save(fig, os.path.join(HERE, "out", "M_histology.png"))
print("M_histology", can.size)

# ===================================================================== arena
ar = pix_rgba(NBH, 1468)[:, :, :3]
Hh, Ww = ar.shape[:2]
crop = ar[int(0.04 * Hh):int(0.93 * Hh), int(0.08 * Ww):int(0.93 * Ww)]
fig = S.figure(2.6, 2.6 * crop.shape[0] / crop.shape[1])
ax = S.ax_at(fig, 0, 0, 2.6, 2.6 * crop.shape[0] / crop.shape[1])
ax.imshow(crop); ax.axis("off")
h2, w2 = crop.shape[:2]
ax.add_patch(FancyArrowPatch((0.47 * w2, 0.05 * h2), (0.08 * w2, 0.55 * h2), connectionstyle="arc3,rad=0.42", arrowstyle="-|>",
                             mutation_scale=14, lw=2.2, color="white"))
ax.text(0.05 * w2, 0.05 * h2, "turns", ha="left", va="top", fontsize=S.NOTE, color="white", fontweight="bold")
ax.text(0.97 * w2, 0.05 * h2, "shock\nzone", ha="right", va="top", fontsize=S.NOTE, color="#FFC27A", fontweight="bold", linespacing=0.95)
S.save(fig, os.path.join(HERE, "out", "M_arena.png"))
print("M_arena", crop.shape)
