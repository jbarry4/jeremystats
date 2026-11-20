"""
plot_trial_summary.py - 2 x 2 behavioural summary for one trial (as in Figure 9):

  A  raw track (gray), shock sector (red lines), shocks (red circles),
     entries without shock (blue circles), arena-rotation arrow
  B  dwell-time map: 8 x 8 tracker-pixel bins (2.56 cm at 3.122 px/cm), unsmoothed, jet on black
  C  polar histogram (10 deg bins) in the room frame, with the preferred / least-preferred
     50% regions (TrackAnalysis definition), chance (1/36) and 0.1 circles, mean vector
  D  annular histogram (8 equal-area annuli)

Usage
  python plot_trial_summary.py FILE.dat [-o OUT.png] [--label "Mouse 933, T13"]
  python plot_trial_summary.py folder/*.dat --outdir summaries/       (one PNG per file)
"""
import argparse, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
from matplotlib.lines import Line2D
from tracker_io import load_trial
from metrics import zone_shares, circular_stats

INK, MUTED, RED, BLUE = '#1f1f1f', '#6b6b6b', '#e0201b', '#2a78d6'
BIN_PX = 8          # dwell-map bin size in tracker pixels (8 px = 2.56 cm here)
POLAR_BIN = 10      # degrees


def _frame(ax, T, pad=1.18):
    cx, cy, R = T['cx'], T['cy'], T['R_px']
    ax.set_xlim(cx - R * pad, cx + R * pad); ax.set_ylim(cy + R * pad, cy - R * pad)   # image y down
    ax.set_aspect('equal')


def panel_track(ax, T, ms=46):
    cx, cy, R = T['cx'], T['cy'], T['R_px']
    sc, sw = T['sector_centre'], T['sector_width']
    ax.add_patch(Circle((cx, cy), R, fill=False, ec=MUTED, lw=1.2))
    ax.plot(T['x_tracked'], T['y_tracked'], color='#8c8c8c', lw=.45)
    for a in (sc - sw / 2, sc + sw / 2):
        ax.plot([cx, cx + R * np.cos(np.radians(a))], [cy, cy - R * np.sin(np.radians(a))], color=RED, lw=1.8)
    s, q = T['shock_idx'], T['quick_entry_idx']
    ax.scatter(T['x_fill'][s], T['y_fill'][s], s=ms, facecolor='none', edgecolor=RED, lw=1.6, zorder=4)
    ax.scatter(T['x_fill'][q], T['y_fill'][q], s=ms, facecolor='none', edgecolor=BLUE, lw=1.6, zorder=4)
    # rotation arrow: on our arena a passive mouse drifts counter-clockwise on screen (CW zone -> shock sector)
    r = R * 1.1; t = np.radians(np.linspace(60, 120, 60))
    ax.plot(cx + r * np.cos(t), cy - r * np.sin(t), color=INK, lw=1.4)
    ax.annotate('', xy=(cx + r * np.cos(t[-1] + .05), cy - r * np.sin(t[-1] + .05)),
                xytext=(cx + r * np.cos(t[-3]), cy - r * np.sin(t[-3])),
                arrowprops=dict(arrowstyle='-|>', color=INK, lw=1.4, mutation_scale=14))
    ax.legend(handles=[Line2D([], [], marker='o', ls='', mfc='none', mec=RED, mew=1.6, ms=8, label=f'shock ({len(s)})'),
                       Line2D([], [], marker='o', ls='', mfc='none', mec=BLUE, mew=1.6, ms=8, label=f'entry without shock ({len(q)})')],
              loc='lower left', bbox_to_anchor=(-0.02, -0.04), frameon=False, fontsize=8.5)
    ax.set_title(f'A  Track (gray) and shock sector (red)\n    {len(T["entrance_idx"])} entrances with shock, '
                 f'{len(s)} shocks, {len(q)} entries without shock', loc='left', fontsize=10)
    _frame(ax, T); ax.axis('off')


def panel_dwell(ax, T, fig=None, vmax=None):
    d, lost = T['data'], T['lost']
    g = np.arange(0, 256 + BIN_PX, BIN_PX)                         # tracker image is 256 x 256 px
    H, _, _ = np.histogram2d(d.x[~lost], d.y[~lost], [g, g]); H = H * T['dt']   # seconds per bin
    cmap = plt.get_cmap('jet').copy(); cmap.set_bad('black')
    im = ax.imshow(np.ma.masked_equal(H.T, 0), cmap=cmap, origin='upper', extent=[0, 256, 256, 0],
                   interpolation='nearest', vmin=0 if vmax else None, vmax=vmax)
    ax.set_facecolor('black'); _frame(ax, T); ax.set_xticks([]); ax.set_yticks([])
    if fig is not None:
        cb = fig.colorbar(im, ax=ax, fraction=.046, pad=.03); cb.set_label('Time per bin (s)')
    ax.set_title(f'B  Dwell time ({BIN_PX / T["px_per_cm"]:.2f} cm bins, unsmoothed)', loc='left', fontsize=10)
    return im


def _preferred_regions(p, centres, sector_centre):
    """TrackAnalysis rule: start at the most (least) visited bin and add the larger (smaller)
    flanking bin until the region holds >= 50% of the time. Returns (lo, hi) bin indices."""
    nb = len(p)
    def grow(start, bigger):
        sel, lo, hi = [start], start, start
        while p[sel].sum() < 0.5:
            a, b = (lo - 1) % nb, (hi + 1) % nb
            if (p[a] >= p[b]) == bigger: sel.append(a); lo = a
            else: sel.append(b); hi = b
        return lo, hi
    imax = int(np.argmax(p))
    zmin = np.flatnonzero(p == p.min())                         # ties: least-visited bin nearest the sector
    imin = int(zmin[np.argmin(np.abs(((centres[zmin] - sector_centre + 180) % 360) - 180))])
    return grow(imax, True), grow(imin, False)


def panel_polar(ax, T, rmax=None):
    sc, sw = T['sector_centre'], T['sector_width']
    edges = np.arange(0, 361, POLAR_BIN); centres = (edges[:-1] + edges[1:]) / 2
    cnt, _ = np.histogram(T['theta'], edges); p = cnt / cnt.sum()
    pref, less = _preferred_regions(p, centres, sc)
    rmax = rmax or max(p.max() * 1.15, .12); ax.set_ylim(0, rmax * 1.3)
    ax.bar(np.radians(sc), rmax * 1.02, width=np.radians(sw), color='#d9d9d9', lw=0, zorder=0)
    for a in (sc - sw / 2, sc + sw / 2):
        ax.plot([np.radians(a)] * 2, [0, rmax * 1.02], color=RED, lw=1.5)
    for tc, pv in zip(np.radians(centres), p):
        ax.plot([tc, tc], [0, pv], color=INK, lw=2.4, solid_capstyle='butt')
    tt = np.linspace(0, 2 * np.pi, 400)
    ax.plot(tt, np.full_like(tt, 1 / len(p)), color='#9e9e9e', lw=1)     # chance
    ax.plot(tt, np.full_like(tt, .1), color=INK, lw=.6)                   # 0.1 reference
    def arc(lo, hi, rad, col):
        a0, a1 = np.radians(edges[lo]), np.radians(edges[hi + 1])
        if a1 <= a0: a1 += 2 * np.pi
        t = np.linspace(a0, a1, 200); ax.plot(t, np.full_like(t, rad), color=col, lw=4, solid_capstyle='butt')
    arc(*pref, rmax * 1.13, INK); arc(*less, rmax * 1.23, '#9e9e9e')
    a = np.radians(T['theta']); R = np.hypot(np.cos(a).mean(), np.sin(a).mean())
    mu = np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean()))
    ax.annotate('', xy=(np.radians(mu), R * rmax), xytext=(0, 0), arrowprops=dict(arrowstyle='-|>', color=RED, lw=1.8))
    labels = {'Shock': sc, 'CCW': sc + 90, 'Opposite': sc + 180, 'CW': sc - 90}
    ax.set_thetagrids([v % 360 for v in labels.values()], list(labels)); ax.tick_params(axis='x', pad=10)
    ax.set_yticks([]); ax.grid(False); ax.spines['polar'].set_visible(False)
    ax.set_title('C  Polar histogram (10° bins)\nblack arc = preferred 50%, gray arc = least preferred 50%,\n'
                 'gray circle = chance (1/36), thin circle = 0.1, red arrow = mean vector', loc='left', fontsize=8.5, pad=16)


def panel_annular(ax, T, ymax=None):
    Rcm = T['R_px'] / T['px_per_cm']
    bounds = Rcm * np.sqrt(np.arange(9) / 8)                             # 8 equal-area annuli
    ann = np.clip(np.digitize(T['r_cm'], bounds) - 1, 0, 7)
    pa = np.bincount(ann, minlength=8) / len(ann)
    ax.bar(np.arange(1, 9), pa, width=.9, color=INK)
    ax.axhline(1 / 8, color='#9e9e9e', ls='--', lw=1); ax.text(1, 1 / 8 + .008, 'chance (1/8)', color=MUTED, fontsize=8)
    if ymax: ax.set_ylim(0, ymax)
    ax.set_xticks(range(1, 9)); ax.set_xlabel('Equal-area annulus (1 = centre, 8 = rim)'); ax.set_ylabel('Proportion of time')
    for s in ['top', 'right']: ax.spines[s].set_visible(False)
    ax.set_title('D  Annular histogram (8 equal-area annuli)', loc='left', fontsize=10)


def trial_summary(path, out, label=None):
    T = load_trial(path)
    label = label or f'Mouse {T["mouse"]}, T{T["trial"]}'
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9})
    fig = plt.figure(figsize=(11.5, 11))
    panel_track(fig.add_subplot(2, 2, 1), T)
    panel_dwell(fig.add_subplot(2, 2, 2), T, fig)
    panel_polar(fig.add_subplot(2, 2, 3, projection='polar'), T)
    panel_annular(fig.add_subplot(2, 2, 4), T)
    z = zone_shares(T); mu, R = circular_stats(T)
    fig.suptitle(label, x=0.02, ha='left', fontsize=12, fontweight='bold')
    fig.text(0.02, 0.006,
             f'P quad time  T {z["T"]:.3f} · CCW {z["CCW"]:.3f} · OPP {z["OPP"]:.3f} · CW {z["CW"]:.3f}   |   '
             f'mean direction {mu:.0f}° from sector centre, R = {R:.2f}   |   frames missed {100 * T["lost"].mean():.1f}%\n'
             f'Arrow in A = arena rotation (carries the CW zone into the shock sector).', fontsize=8.3, color=MUTED)
    fig.tight_layout(rect=(0, .035, 1, .97)); fig.savefig(out, dpi=170); plt.close(fig)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+', help='Tracker .dat file(s)')
    ap.add_argument('-o', '--out', help='output PNG (single file only)')
    ap.add_argument('--outdir', default='.', help='output folder when several files are given')
    ap.add_argument('--label', help='figure title (single file only)')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    for f in a.files:
        out = a.out if (a.out and len(a.files) == 1) else os.path.join(a.outdir, os.path.basename(f).rsplit('.', 1)[0] + '_summary.png')
        print('wrote', trial_summary(f, out, a.label if len(a.files) == 1 else None))
