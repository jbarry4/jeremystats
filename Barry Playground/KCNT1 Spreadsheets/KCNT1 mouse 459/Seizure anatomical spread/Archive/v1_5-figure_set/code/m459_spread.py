import sys, os; sys.path.insert(0, "/private/tmp/claude-501/-Users-jeremybarry-Documents-GitHub-jeremystats-Barry-Playground/5a2ce6c5-deec-452d-af93-23976cb0ccf2/scratchpad")
from m459_common import *
from scipy.ndimage import gaussian_filter1d
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.colors import AsinhNorm
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.backends.backend_pdf import PdfPages
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": .6})
OUT = "/Users/jeremybarry/Documents/GitHub/jeremystats/Barry Playground/KCNT1 Spreadsheets/KCNT1 mouse 459/Seizure anatomical spread"
os.makedirs(OUT, exist_ok=True)
TAG = "KCNT1_m459_s1_2024-12-06"
RN = [r[0] for r in REGIONS]; RC = {r[0]: r[3] for r in REGIONS}
SCHEM = {"CA1": ["CA1 (or/pyr)", "CA1 rad/l-m"], "Upper blade": ["Upper blade ML", "Upper blade GCL"], "Hilus": ["Hilus"],
         "Lower blade": ["Lower blade GCL", "Lower blade ML"]}
PHASES = [
 dict(n=1, title="Seizure starts in the HILUS", w=(887.5, 890.0), hl=(888.7, 889.55), new=["Hilus"], active=["Hilus"],
      text="Hilar discharges dominate: hilus CSD reaches ~30-37x baseline while both blades and CA1 stay near their pre-ictal level."),
 dict(n=2, title="Spread to the UPPER blade", w=(889.5, 891.3), hl=(890.0, 890.8), new=["Upper blade GCL", "Upper blade ML"], active=["Hilus", "Upper blade GCL", "Upper blade ML"],
      text="The upper (suprapyramidal) blade granule layer is recruited next: its CSD jumps to ~20-70x baseline and its MUA leads the burst at ~890.5 s."),
 dict(n=3, title="Spread to the LOWER blade", w=(890.7, 892.3), hl=(891.2, 892.1), new=["Lower blade GCL", "Lower blade ML"], active=["Hilus", "Upper blade GCL", "Upper blade ML", "Lower blade GCL", "Lower blade ML"],
      text="The lower (infrapyramidal) blade follows ~1 s later: lower GCL CSD rises to ~45-65x, then the lower molecular layer and below-DG channels."),
 dict(n=4, title="Whole depth, incorporating CA1", w=(891.8, 897.0), hl=(892.2, 897.0), new=["CA1 (or/pyr)", "CA1 rad/l-m"], active=RN,
      text="From ~892.2 s CA1 units fire with the dentate (CA1 MUA 4x to >30x baseline) and the discharge occupies the full probe until termination at ~916 s."),
 dict(n=5, title="Post-ictal", w=(912.0, 942.0), hl=(916.0, 942.0), new=[], active=["Lower blade GCL", "Lower blade ML", "CA1 (or/pyr)"],
      text="Hilus and upper blade stop at ~916-918 s. CA1 keeps firing to ~925 s while a slow wave travels from the upper blade up into CA1 (~919-926 s). The lower-blade granule layer fires longest (~932-935 s), then a slow wave crosses the lower blade (~934-938 s) and all layers fall silent."),
]

zl, zm = features(win=0.05)
tz = T0 + np.arange(zm.shape[1]) / 100
Cz = np.load(SP + "m459_cache/csd_ratio_100hz.npy"); zm10 = features(win=0.1)[1]
def _on(x, thr, hold=0.3, ref=886.0):
    ok = (x > thr) & (tz >= ref); k = int(hold * 100)
    for i in np.flatnonzero(ok):
        if ok[i:i+k].mean() > .8: return tz[i]
    return np.nan
def _off(x, thr, hold=0.3, a=905.0, b=945.0):
    ok = (x > thr) & (tz >= a) & (tz <= b); k = int(hold * 100); last = np.nan
    for i in np.flatnonzero(ok):
        if ok[i:i+k].mean() > .8: last = tz[i + k]
    return last
ON_CSD = np.array([np.nan if i in (0, 58, 63) else _on(Cz[i], 25) for i in range(64)])
ON_MUA = np.array([np.nan if i == 58 else _on(zm10[i], 10) for i in range(64)])
OFF_MUA = np.array([np.nan if i == 58 else _off(zm10[i], 6) for i in range(64)])
LF = sg.sosfiltfilt(sg.butter(4, [0.5, 300], "band", fs=FS, output="sos"), L, axis=1)

def schematic(ax, active, new):
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")
    def col(region): return RC[SCHEM[region][-1] if region != "Hilus" else "Hilus"] if any(r in active for r in SCHEM[region]) else "#e0e0e0"
    lw = lambda region: 3.2 if any(r in new for r in SCHEM[region]) else 2
    # CA1 pyramidal layer (arc)
    th = np.linspace(np.pi*0.15, np.pi*0.85, 50); ax.plot(5 + 4.5*np.cos(th), 5.2 + 3.6*np.sin(th), c=col("CA1"), lw=6 if col("CA1") != "#e0e0e0" else 4, solid_capstyle="round")
    ax.text(9.4, 8.6, "CA1", fontsize=7, ha="right")
    # dentate: C-shape opening to the right
    up = col("Upper blade"); lo = col("Lower blade")
    ax.plot([2.2, 8.2], [5.6, 5.6], c=up, lw=7, solid_capstyle="round"); ax.plot([2.2, 8.2], [2.4, 2.4], c=lo, lw=7, solid_capstyle="round")
    th = np.linspace(np.pi/2, 3*np.pi/2, 40); ax.plot(2.2 + 1.6*np.cos(th), 4.0 + 1.6*np.sin(th), c="#bdbdbd", lw=7, solid_capstyle="round")
    ax.add_patch(FancyBboxPatch((2.6, 3.0), 5.4, 2.0, boxstyle="round,pad=0.1", fc=col("Hilus"), ec="none", alpha=.85))
    ax.text(5.3, 4.0, "hilus", fontsize=7, ha="center", va="center", color="w" if col("Hilus") != "#e0e0e0" else "#777")
    ax.text(8.6, 5.6, "upper", fontsize=6.5, va="center"); ax.text(8.6, 2.4, "lower", fontsize=6.5, va="center")
    ax.plot([6.3, 6.3], [9.7, 0.6], c="k", lw=1); ax.plot(6.3, 0.6, "v", c="k", ms=4); ax.text(6.45, 9.5, "probe", fontsize=6)
    for reg, y in (("CA1", 8.6), ("Upper blade", 5.6), ("Hilus", 4.0), ("Lower blade", 2.4)):
        if any(r in new for r in SCHEM[reg]): ax.plot(6.3, y, "*", ms=11, c="gold", mec="k", mew=.6, zorder=5)

def region_bar(ax, top=True):
    for n, a, b, c in REGIONS:
        ax.add_patch(Rectangle((0, a - .5), 1, b - a + 1, fc=c, ec="w", lw=.5, transform=ax.get_yaxis_transform(), clip_on=False))

def figure(P):
    w0, w1 = P["w"]; h0, h1 = P["hl"]
    fig = plt.figure(figsize=(12, 15.5))
    gs = fig.add_gridspec(5, 2, height_ratios=[0.55, 1.5, 1.05, 0.75, 0.85], width_ratios=[1, 0.012], hspace=0.38, wspace=0.01,
                          left=0.12, right=0.93, top=0.95, bottom=0.04)
    # header: schematic + text
    hdr = gs[0, 0].subgridspec(1, 2, width_ratios=[0.22, 0.78], wspace=0.05)
    sax = fig.add_subplot(hdr[0]); schematic(sax, P["active"], P["new"])
    tax = fig.add_subplot(hdr[1]); tax.axis("off")
    tax.text(0, 0.95, f"Phase {P['n']} of 5 — {P['title']}", fontsize=15, fontweight="bold", va="top")
    tax.text(0, 0.62, f"{TAG}   ·   window {w0:.1f}–{w1:.1f} s   ·   highlighted {h0:.1f}–{h1:.1f} s", fontsize=9, color="#555", va="top")
    tax.text(0, 0.42, P["text"], fontsize=10, va="top", wrap=True)
    tax.text(0, 0.0, "Gold star = region newly recruited in this phase. Coloured = involved.", fontsize=8, color="#777")
    axes = [fig.add_subplot(gs[i, 0]) for i in range(1, 5)]
    for a in axes[1:3]: a.sharex(axes[0])
    s0, s1 = idx(w0), idx(w1); tt = w0 + np.arange(s1 - s0) / FS
    # A traces
    a = axes[0]; X = LF[:, s0:s1]; show = [i for i in range(64) if i != 58][::1]
    gap = 3.0 * np.median(np.std(X, 1))
    dec = max(1, (s1 - s0) // 6000)
    for j, i in enumerate(show):
        a.plot(tt[::dec], np.clip(X[i, ::dec], -2.5*gap, 2.5*gap) - i * gap, c=CHCOL[i], lw=.35)
    a.set_ylim(-64.5 * gap, 1.5 * gap); a.set_yticks([-(i) * gap for i in (0, 9, 19, 29, 39, 49, 59)]); a.set_yticklabels([f"CSC{i+1}" for i in (0, 9, 19, 29, 39, 49, 59)], fontsize=7)
    a.set_title(f"Voltage traces by region (0.5–300 Hz, all channels, CSC59 removed; spacing {gap:.0f} µV, clipped ±2.5)", loc="left", fontsize=9)
    for n, aa, bb, c in REGIONS:
        a.add_patch(Rectangle((-0.035, -(bb - 0.5) * gap), 0.02, (bb - aa + 1) * gap, fc=c, ec="w", lw=.5, transform=a.get_yaxis_transform(), clip_on=False))
    # B CSD
    b = axes[1]
    Xc = sg.sosfiltfilt(sg.butter(4, 60, fs=FS, output="sos"), L[:, s0:s1], axis=1)
    C = -np.diff(gaussian_filter1d(Xc, 1, axis=0), 2, axis=0) / 0.05**2
    lim = np.percentile(np.abs(C), 99); lwid = np.percentile(np.abs(C), 50)
    im = b.imshow(C, aspect="auto", cmap="RdBu", norm=AsinhNorm(linear_width=lwid, vmin=-lim, vmax=lim), extent=[w0, w1, 63.5, 1.5], interpolation="bilinear")
    for n, aa, bb, c in REGIONS:
        b.axhline(bb + .5, c="k", lw=.4, alpha=.5)
        b.add_patch(Rectangle((-0.035, aa - .5), 0.02, bb - aa + 1, fc=c, ec="w", lw=.5, transform=b.get_yaxis_transform(), clip_on=False))
    b.set_ylabel("CSC"); b.set_title("Current source density (<60 Hz, 50 µm; sink = red, source = blue; asinh scale)", loc="left", fontsize=9)
    cax = fig.add_subplot(gs[2, 1]); cb = fig.colorbar(im, cax=cax); cb.ax.tick_params(labelsize=6); cb.set_label("µV/mm²", fontsize=7)
    # C per-region MUA
    c_ = axes[2]; wz = (tz >= w0) & (tz <= w1)
    for n, aa, bb, col in REGIONS:
        y = np.median(zm[aa-1:bb, wz], 0)
        c_.plot(tz[wz], np.clip(y, 0.3, None), c=col, lw=2.2 if n in P["new"] else 1.0, alpha=1 if (n in P["new"] or not P["new"]) else .75, label=n)
    c_.set_yscale("log"); c_.set_ylim(0.3, 300); c_.axhline(5, c="k", ls=":", lw=.7)
    c_.set_ylabel("MUA (z vs baseline)"); c_.legend(ncol=4, fontsize=7, frameon=False, loc="upper left")
    c_.set_title("Per-region activity: multi-unit envelope (300–3000 Hz), median of channels, z-scored to 400–840 s baseline", loc="left", fontsize=9)
    # D onset / offset latency (fixed reference, shared across figures)
    d = axes[3]
    if P["n"] < 5:
        d.set_xlim(886, 896)
        for i in range(64):
            for arr, mk, fc in ((ON_CSD, "o", None), (ON_MUA, "D", "none")):
                v = arr[i]
                if not np.isfinite(v) or v > 896: continue
                col = CHCOL[i] if v <= h1 else "#cfcfcf"
                d.plot(v, i + 1, mk, ms=4.6 if mk == "o" else 3.6, c=col, mfc=(col if fc is None else "none"), mec=("k" if fc is None else col), mew=.4 if fc is None else 1.0)
        for n, aa, bb, col in REGIONS:
            v = ON_CSD[aa-1:bb]; v = v[np.isfinite(v) & (v <= 896)]
            if len(v) >= 2:
                m = np.median(v); d.plot([m, m], [aa - .4, bb + .4], c=(col if m <= h1 else "#bbbbbb"), lw=3, alpha=.65)
        d.axvspan(h0, min(h1, 896), color="gold", alpha=.18, lw=0)
        d.set_title("Onset-latency depth map (fixed reference, same in every phase): ● CSD |x| > 25× baseline  ◇ MUA z > 10  (≥0.3 s); grey = not yet recruited", loc="left", fontsize=8.5)
        d.text(886.1, 2, "early dots at 886.7–887.1 s = pre-ictal dentate-spike-like discharges\n(sinks in both molecular layers), before the hilar onset", fontsize=6.5, color="#666", va="top")
        d.text(1.0, -0.36, "Order (CSD region medians):  Hilus 889.0 → Upper ML 889.2 → Upper GCL 890.3 → Lower GCL 891.4 → Lower ML 891.9 → CA1 893.9–894.6;   MUA: hilus/upper 890.5 → lower 891.7 → CA1 893.3",
               transform=d.transAxes, ha="right", fontsize=7, color="#333")
    else:
        d.set_xlim(905, 945)
        for i in range(64):
            v = OFF_MUA[i]
            if np.isfinite(v): d.plot(v, i + 1, "o", ms=4.6, c=CHCOL[i], mec="k", mew=.4)
        for n, aa, bb, col in REGIONS:
            v = OFF_MUA[aa-1:bb]; v = v[np.isfinite(v)]
            if len(v): m = np.median(v); d.plot([m, m], [aa - .4, bb + .4], c=col, lw=3, alpha=.65)
        d.set_title("Offset-latency depth map: last time each channel's MUA is > 6 z for ≥0.3 s (when each layer goes quiet)", loc="left", fontsize=8.5)
    d.set_ylim(64.5, .5); d.set_ylabel("CSC")
    d.set_xlabel("Time in session (s)")
    for ax_ in axes[:3]:
        ax_.axvspan(h0, h1, color="gold", alpha=.12, lw=0, zorder=0)
        ax_.set_xlim(w0, w1)
        ax_.set_xlabel("Time in session (s)", fontsize=7.5); ax_.tick_params(labelbottom=True, labelsize=7)
    return fig, []

def layer_page():
    from m459_common import L as LL
    dz = np.load(SP + "m459_cache/layerdiag.npz")
    fig, ax = plt.subplots(1, 4, figsize=(12, 9), sharey=True, gridspec_kw=dict(wspace=.15))
    y = np.arange(1, 65)
    ax[0].plot(dz["rip"], y, c="k"); ax[0].set_title("Ripple RMS\n150–250 Hz (µV)")
    ax[1].plot(dz["mua"], y, c="k"); ax[1].set_title("Multi-unit\nenvelope")
    ax[2].plot(dz["thcorr"], y, c="k"); ax[2].axvline(0, c="k", lw=.5); ax[2].set_title("Theta (5–10 Hz)\ncorrelation vs CSC7")
    csd = dz["csd"]; t = (np.arange(csd.shape[1]) - 200) / 2000 * 1000; lim = np.percentile(np.abs(csd), 99)
    ax[3].imshow(csd, aspect="auto", cmap="RdBu", vmin=-lim, vmax=lim, extent=[t[0], t[-1], 63.5, 1.5]); ax[3].set_title("Dentate-spike-triggered CSD\n(n=118, sink = red)")
    ax[3].set_xlabel("ms from DS peak")
    for a in ax:
        for n, aa, bb, c in REGIONS: a.axhspan(aa - .5, bb + .5, color=c, alpha=.13, lw=0)
    for n, aa, bb, c in REGIONS: ax[3].text(1.03, (aa + bb) / 2, f"{n}\nCSC{aa}–{bb}", transform=ax[3].get_yaxis_transform(), fontsize=7, va="center", color=c)
    ax[0].set_ylim(64.5, .5); ax[0].set_ylabel("Channel (CSC)")
    fig.suptitle(f"{TAG} — layer map used for all phase figures (baseline 400–840 s; CSC59 interpolated)", fontsize=12, y=.97)
    return fig

def overview(orders):
    fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw=dict(height_ratios=[1, 1.2], hspace=.22))
    w0, w1 = 870, 945; wz = (tz >= w0) & (tz <= w1)
    for n, aa, bb, c in REGIONS: ax[0].plot(tz[wz], np.clip(np.median(zm[aa-1:bb, wz], 0), .3, None), c=c, lw=.8, label=n)
    ax[0].set_yscale("log"); ax[0].set_ylim(.3, 600); ax[0].legend(ncol=8, fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(.5, -0.02)); ax[0].set_ylabel("MUA z")
    ax[1].imshow(np.log10(np.clip(zm[:, wz], 1, None)), aspect="auto", cmap="magma", extent=[w0, w1, 64.5, .5], vmax=2)
    for n, aa, bb, c in REGIONS:
        ax[1].add_patch(Rectangle((-0.025, aa - .5), 0.015, bb - aa + 1, fc=c, ec="w", lw=.5, transform=ax[1].get_yaxis_transform(), clip_on=False))
    ax[1].set_ylabel("CSC"); ax[1].set_xlabel("Time in session (s)")
    for P in PHASES:
        ax[0].axvspan(*P["hl"], color=plt.cm.Set2(P["n"] - 1), alpha=.3, lw=0)
        ax[0].text(np.mean(P["hl"]), 380, str(P["n"]), ha="center", fontsize=11, fontweight="bold")
        for x_ in P["hl"]: ax[1].axvline(x_, c="w", lw=.8, ls="--")
        ax[1].plot(P["hl"], [0.2, 0.2], c=plt.cm.Set2(P["n"] - 1), lw=6, clip_on=False, solid_capstyle="butt")
    ax[0].set_title("Overview: the five phases on the multi-unit activity of every region (bottom: per-channel MUA, log z)", loc="left")
    fig.suptitle(f"{TAG} — seizure anatomical spread, overview", fontsize=13)
    return fig

with PdfPages(f"{OUT}/{TAG}_seizure_anatomical_spread.pdf") as pdf:
    figs = []
    orders = []
    for P in PHASES:
        f, o = figure(P); orders.append(o); figs.append((f"{P['n']}_{P['title'].split(' ')[-1] if P['n']<5 else 'postictal'}", f))
    ov = overview(orders); pdf.savefig(ov); ov.savefig(f"{OUT}/{TAG}_0_overview.png", dpi=200, bbox_inches="tight"); plt.close(ov)
    names = ["1_hilus_start", "2_upper_blade", "3_lower_blade", "4_whole_depth_CA1", "5_postictal"]
    for nm, (_, f) in zip(names, figs):
        pdf.savefig(f); f.savefig(f"{OUT}/{TAG}_{nm}.png", dpi=200); plt.close(f)
    lp = layer_page(); pdf.savefig(lp); lp.savefig(f"{OUT}/{TAG}_S_layer_map.png", dpi=200, bbox_inches="tight"); plt.close(lp)
for P, o in zip(PHASES, orders): print(P["n"], [(n, round(t, 2)) for t, n in o])
print(sorted(os.listdir(OUT)))
