"""Step 17. What arrival looks like: speed along the path, and how much the mice slow.

Two sheets, because the five rows do not fit one page:

fig16a_arrival_runs
a  Every directed run into the hidden goal at phase 10 for one mouse per group, drawn in
   goal-centred coordinates and rotated so that the approach comes from the left, with the path
   coloured by speed.  The dot on each run marks where the mouse was 1.2 s after it entered:
   inside the zone (green) is a reward, outside (red) is a miss.  This is the reward rule drawn
   directly.
b  One run per mouse, the run whose slowing ratio is closest to that mouse's median, so it is
   typical rather than chosen.  A dot every 0.1 s: where the mouse is slow the dots bunch up,
   where it is fast they spread out.  All three panels share one axis range, so the goal circle
   is the same size in each and the runs are drawn to the same scale.
c  Mean speed around every entry into the current goal - directed runs and chance crossings alike
   - at the trained location, the last rotation, and the cued last rotation.  This is the only
   panel that includes entries the mouse did not aim at.

fig16b_arrival_phase
a  Slowing ratio: the mean speed over the 1.2 s after entry divided by the mean speed over the
   1.5 s to 0.5 s before it, on directed runs.  1 means the mouse did not slow at all.  This
   controls for approach speed within each run, so it separates a failure to settle from running
   fast in general.  Beside it, total pause time per session, hidden and cued.
b  Pause time split by where the pause happened, with the cued open interior as the control.

Arenas are not drawn here: panels a and b of the first sheet are goal-centred and rotated, with y
negated so that the handedness of the approach matches the room.

Reads WORK/approach/runs_ex.pkl, arrival_dir.pkl and pauses_d.pkl (s11, s16).
Output: figures/fig16a_arrival_runs.png, figures/fig16b_arrival_phase.png
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import WORK, FIGS
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D
from scipy.stats import mannwhitneyu as mw, linregress

plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 9,
                     'figure.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb'})
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
MK = {'CTL': 'o', 'Lo': '^', 'Hi': 's'}          # shape as well as colour, so the lines separate
DX = {'CTL': -0.085, 'Lo': 0.0, 'Hi': 0.085}     # small x offset, so overlapping means stay visible
SF = 30; VMAX = 35.0
IN_C = '#1a7f37'; OUT_C = '#d1242f'
norm = Normalize(0, VMAX); cmap = plt.get_cmap('viridis')

p = pd.read_pickle(WORK + '/probe.pkl'); G = p.drop_duplicates('MouseID').set_index('MouseID').G3
R = pd.read_pickle(WORK + '/approach/runs_ex.pkl'); R['G3'] = R.Mouse.map(G)
R = R[(R.Cond == 'H') & R.G3.isin(COL)].copy()


def run_slow(r):
    e = r.ent_i; v = np.asarray(r.v, float)
    pre = v[max(0, e - int(1.5 * SF)):max(0, e - int(0.5 * SF))]
    post = v[e:e + int(1.2 * SF)]
    if len(pre) < 5 or len(post) < 5: return np.nan
    a = np.nanmean(pre)
    return np.nan if not a > 0 else np.nanmean(post) / a


R['slow'] = R.apply(run_slow, axis=1)

EX = [('CTL', 22.0), ('Lo', 10.0), ('Hi', 34.0)]


def align(r):
    """Goal-centred, rotated so the approach comes from the left.  y is negated first: the tracker
    stores y running down the image, so without this the curvature of every run is mirrored."""
    x = np.asarray(r.x, float); y = -np.asarray(r.y, float)
    th = np.pi - np.arctan2(y[0], x[0]); c, s = np.cos(th), np.sin(th)
    return c * x - s * y, s * x + c * y


# ================================================================ sheet 1: what the runs look like
figA = plt.figure(figsize=(7.0, 7.1))
gs = figA.add_gridspec(3, 3, height_ratios=[1.00, 0.44, 0.95], hspace=0.55, wspace=0.14,
                       left=0.095, right=0.900, top=0.880, bottom=0.075)

# ---------------------------------------------------------------- a: all directed runs
for j, (g, m) in enumerate(EX):
    ax = figA.add_subplot(gs[0, j])
    d = R[(R.G3 == g) & (R.Mouse == m)]; gr = d.iloc[0].gr
    for _, r in d.iterrows():
        x, y = align(r); v = np.nan_to_num(np.asarray(r.v, float))
        pts = np.array([x, y]).T.reshape(-1, 1, 2)
        lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=cmap, norm=norm,
                            lw=1.0, alpha=0.85); lc.set_array(v[:-1]); ax.add_collection(lc)
        e = r.ent_i; k = e + int(1.2 * SF)
        if k < len(x):
            ins = np.hypot(x[k], y[k]) <= gr
            ax.plot(x[k], y[k], 'o', ms=4.2, mfc=(IN_C if ins else OUT_C), mec='white', mew=0.6, zorder=5)
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(gr * np.cos(th), gr * np.sin(th), color='#333333', lw=1.1, zorder=3)
    ax.set_aspect('equal'); ax.set_xlim(-42, 42); ax.set_ylim(-30, 30); ax.axis('off')
    ax.set_title(f'{LAB[g]} (M{m:.0f})\n{len(d)} runs · {100*d.rewarded.mean():.0f}% rewarded',
                 fontsize=8.4, color=COL[g], pad=3)
    if j == 0:
        ax.plot([-40, -30], [-27, -27], color=MUT, lw=1.4)
        ax.text(-35, -25.5, '10 cm', fontsize=6.6, ha='center', color=MUT)

# ---------------------------------------------------------------- b: one typical run each
pick = []
for g, m in EX:
    d = R[(R.G3 == g) & (R.Mouse == m)].dropna(subset=['slow'])
    pick.append((g, m, d.iloc[(d.slow - d.slow.median()).abs().values.argmin()]))
XY = []
for g, m, r in pick:
    x, y = align(r)
    cut = min(len(x), r.ent_i + int(2.0 * SF))
    XY.append((x[:cut], y[:cut], np.nan_to_num(np.asarray(r.v, float))[:cut]))
gr0 = pick[0][2].gr
PAD = 2.5
xs = np.concatenate([x for x, _, _ in XY] + [[-gr0, gr0]])
ys = np.concatenate([y for _, y, _ in XY] + [[-gr0, gr0]])
cx0, cy0 = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
axB = [figA.add_subplot(gs[1, j]) for j in range(3)]
bb = axB[0].get_position()
asp = (bb.width * figA.get_figwidth()) / (bb.height * figA.get_figheight())
wx = max(xs.max() - xs.min() + 2 * PAD, (ys.max() - ys.min() + 2 * PAD) * asp)
wy = wx / asp                                    # one window for all three, so the goals match
for j, ((g, m, r), (x, y, v)) in enumerate(zip(pick, XY)):
    ax = axB[j]
    pts = np.array([x, y]).T.reshape(-1, 1, 2)
    lc = LineCollection(np.concatenate([pts[:-1], pts[1:]], axis=1), cmap=cmap, norm=norm, lw=2.0)
    lc.set_array(v[:-1]); ax.add_collection(lc)
    sidx = np.arange(0, len(x), 3)
    ax.scatter(x[sidx], y[sidx], s=7, c=v[sidx], cmap=cmap, norm=norm,
               edgecolor='white', linewidth=0.3, zorder=4)
    k = r.ent_i + int(1.2 * SF)
    if k < len(x):
        ins = np.hypot(x[k], y[k]) <= r.gr
        ax.plot(x[k], y[k], 'o', ms=5.6, mfc=(IN_C if ins else OUT_C), mec='white', mew=0.7, zorder=6)
    th = np.linspace(0, 2 * np.pi, 200)
    ax.plot(r.gr * np.cos(th), r.gr * np.sin(th), color='#333333', lw=1.1, zorder=3)
    ax.axis('off'); ax.set_aspect('equal')
    ax.set_xlim(cx0 - wx / 2, cx0 + wx / 2); ax.set_ylim(cy0 - wy / 2, cy0 + wy / 2)
    ax.set_title(f'slowing ratio {r.slow:.2f}', fontsize=7.8, color=MUT, pad=1)

# ---------------------------------------------------------------- c: every entry, directed or not
A = pd.read_pickle(WORK + '/approach/arrival_dir.pkl'); A['G3'] = A.Mouse.map(G)
A = A[A.G3.isin(COL)].copy()
t = (np.arange(181) - 3 * SF) / SF


def all_entries(g, ph, cond):
    """Per-mouse profile over every entry (directed and chance), weighted by the number of
    entries, then the mean and SE across mice."""
    out = []
    for mm, q in A[(A.G3 == g) & (A.Phase == ph) & (A.Cond == cond)].groupby('Mouse'):
        w = q.n.values.astype(float)
        if w.sum() <= 0: continue
        P = np.vstack([np.asarray(v, float) for v in q.prof.values])
        out.append(np.nansum(P * w[:, None], axis=0) / w.sum())
    Aa = np.vstack(out)
    return np.nanmean(Aa, 0), np.nanstd(Aa, 0, ddof=1) / np.sqrt(len(Aa)), Aa


CPAN = [(7.0, 'H', 'Hidden, trained location\n(phase 7)'),
        (10.0, 'H', 'Hidden, last rotation\n(phase 10)'),
        (10.0, 'V', 'Cued, last rotation\n(visible phase 10)')]
gsc = gs[2, :].subgridspec(1, 3, wspace=0.30)
for j, (ph, cond, ttl) in enumerate(CPAN):
    ax = figA.add_subplot(gsc[0, j])
    ax.axvspan(0, 1.2, color='#efeee8', zorder=0)
    ax.axvline(0, color='#9a9993', lw=0.8, ls=':', zorder=1)
    win = {}
    for g in ['CTL', 'Lo', 'Hi']:
        mu, se, Aa = all_entries(g, ph, cond)
        ax.fill_between(t, mu - se, mu + se, color=COL[g], alpha=0.15, lw=0)
        ax.plot(t, mu, color=COL[g], lw=1.6, label=LAB[g])
        k0, k1 = 3 * SF, 3 * SF + int(1.2 * SF)
        win[g] = np.nanmean(Aa[:, k0:k1], axis=1)
    pv = mw(win['Hi'], win['CTL'], alternative='two-sided')[1]
    ax.set_xlim(-2.0, 2.5); ax.set_ylim(0, 26)
    ax.set_xlabel('time from entry (s)', fontsize=7.8, color=MUT)
    if j == 0: ax.set_ylabel('speed (cm/s)', fontsize=7.8, color=MUT)
    ax.set_title(ttl, fontsize=8.2, color=INK, fontweight='semibold', pad=3)
    ax.text(0.03, 0.055, 'reward window, Hi vs WT\n%s' %
            ('p < .001' if pv < 0.001 else 'p = ' + ('%.3f' % pv).lstrip('0')),
            transform=ax.transAxes, ha='left', fontsize=6.6, va='bottom',
            color=(INK if pv < 0.05 else MUT))
    ax.text(0.6, 24.6, '1.2 s to earn it', fontsize=6.4, color=MUT, ha='center')
    for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
    for sp in ['left', 'bottom']: ax.spines[sp].set_color('#9a9993')
    ax.tick_params(colors=MUT, labelsize=7.4); ax.grid(axis='y', color=GRID, lw=0.6)
    ax.set_axisbelow(True)

sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap); sm.set_array([])
cax = figA.add_axes([0.915, 0.560, 0.015, 0.300])
cb = figA.colorbar(sm, cax=cax); cb.set_label('Speed (cm/s)', fontsize=7.6, color=MUT)
cb.ax.tick_params(labelsize=7, colors=MUT); cb.outline.set_visible(False)
figA.legend(handles=[Line2D([], [], marker='o', ls='', ms=5, mfc=IN_C, mec='white', label='in the zone 1.2 s after entry (reward)'),
                     Line2D([], [], marker='o', ls='', ms=5, mfc=OUT_C, mec='white', label='outside it (no reward)')],
            loc='upper center', bbox_to_anchor=(0.5, 0.947), ncol=2, frameon=False, fontsize=7.6)
figA.legend(handles=[Line2D([], [], color=COL[g], lw=1.8, label=LAB[g]) for g in ['CTL', 'Lo', 'Hi']],
            loc='upper center', bbox_to_anchor=(0.5, 0.400), ncol=3, frameon=False, fontsize=7.6)
figA.suptitle('Arriving at the goal: what the runs look like', fontsize=11.5, y=0.982,
              color=INK, fontweight='semibold')
for lab, x, y in [('a', 0.012, 0.892), ('b', 0.012, 0.590), ('c', 0.012, 0.312)]:
    figA.text(x, y, lab, fontsize=11, weight='bold', va='top', color=INK)
os.makedirs(FIGS, exist_ok=True)
outA = os.path.join(FIGS, 'fig16a_arrival_runs.png')
figA.savefig(outA, dpi=200); print('wrote', outA)

# ================================================================ sheet 2: slowing and pausing
A2 = A[A.directed]
b = lambda q, lo, hi: np.nanmean(q[int((lo + 3) * SF):int((hi + 3) * SF) + 1])
A2 = A2.assign(sl=A2.prof.apply(lambda q: b(q, 0, 1.2)) / A2.prof.apply(lambda q: b(q, -1.5, -0.5)))
Pp = pd.read_pickle(WORK + '/approach/pauses_d.pkl'); Pp['G3'] = Pp.Mouse.map(G)
Pp = Pp[Pp.G3.isin(COL)]
# pause time, split by where the pause happened.  Wall pauses (radius > 0.8 of the arena) are
# already excluded by the pause definition in s11, so 'far' is the open interior, not the wall.
PT = Pp.groupby(['G3', 'Mouse', 'Phase', 'Cond']).apply(
        lambda x: pd.Series({'t': x.dur.sum(), 'n': len(x), 'mdur': x.dur.mean(),
                             't_in': x.loc[x.dcur < 1, 'dur'].sum(),
                             't_near': x.loc[(x.dcur >= 1) & (x.dcur < 2.5), 'dur'].sum(),
                             't_far': x.loc[x.dcur >= 2.5, 'dur'].sum()})).reset_index()
PH = [7.0, 8.0, 9.0, 10.0]
rng = np.random.default_rng(3)


def slope_p(df, val, cond):
    sl = {}
    for g in ['CTL', 'Hi']:
        sl[g] = [linregress(x.index.values.astype(float), x.values).slope
                 for m, gg in df[(df.G3 == g) & (df.Cond == cond)].groupby('Mouse')
                 for x in [gg.groupby('Phase')[val].mean()] if len(x) >= 3]
    return mw(sl['Hi'], sl['CTL'], alternative='two-sided')[1]


figB = plt.figure(figsize=(7.0, 5.0))
gsB = figB.add_gridspec(2, 4, hspace=0.95, wspace=0.60, left=0.088, right=0.985,
                        top=0.800, bottom=0.085)
PANELS = [(A2, 'sl', 'H', 'Slowing ratio\n(in goal / before)', 'Hidden goal', (0.25, 1.40)),
          (A2, 'sl', 'V', None, 'Cued goal', (0.25, 1.40)),
          (PT, 't', 'H', 'Pause time per\nsession (s)', 'Hidden goal', (0, 300)),
          (PT, 't', 'V', None, 'Cued goal', (0, 300)),
          (PT, 't_in', 'H', 'Pause time (s)', 'Hidden: in the goal\nzone (<1 r)', (0, 40)),
          (PT, 't_near', 'H', None, 'Hidden: around it\n(1–2.5 r)', (0, 90)),
          (PT, 't_far', 'H', None, 'Hidden: open interior\n(>2.5 r)', (0, 260)),
          (PT, 't_far', 'V', None, 'Cued: open interior\n(>2.5 r)', (0, 260))]
for jj, (df, val, cond, ylab, ttl, ylim) in enumerate(PANELS):
    ax = figB.add_subplot(gsB[jj // 4, jj % 4])
    d = df[df.Cond == cond]
    rr = ylim[1] - ylim[0]
    for g in ['CTL', 'Lo', 'Hi']:
        mu = []; se = []
        for ph in PH:
            v = d[(d.Phase == ph) & (d.G3 == g)].groupby('Mouse')[val].mean().values
            mu.append(np.mean(v)); se.append(np.std(v, ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0)
            ax.scatter(PH.index(ph) + DX[g] + rng.uniform(-0.05, 0.05, len(v)), v, s=6, color=COL[g],
                       alpha=0.33, edgecolor='none', zorder=2)
        ax.errorbar(np.arange(len(PH)) + DX[g], mu, yerr=se, color=COL[g], lw=1.7, marker=MK[g],
                    ms=3.8, mec='#fcfcfb', mew=0.6, capsize=2, elinewidth=0.9, zorder=4, label=LAB[g])
    if val == 'sl': ax.axhline(1.0, color='#9a9993', lw=0.8, ls=':', zorder=1)
    ax.set_xticks(range(len(PH))); ax.set_xticklabels([f'{q:.0f}' for q in PH], fontsize=7.6)
    ax.set_xlim(-0.45, len(PH) - 0.55)
    ax.set_ylim(ylim[0] - rr * 0.30, ylim[1])          # the band below the data holds the slope text
    ax.set_xlabel('Phase', fontsize=7.8, color=MUT, labelpad=1)
    ax.set_title(ttl, fontsize=8.2, color=INK, fontweight='semibold', pad=10)
    for sp in ['top', 'right']: ax.spines[sp].set_visible(False)
    for sp in ['left', 'bottom']: ax.spines[sp].set_color('#9a9993')
    ax.spines['left'].set_bounds(ylim[0], ylim[1])
    ax.tick_params(colors=MUT, labelsize=7.4)
    ax.set_yticks([q for q in ax.get_yticks() if ylim[0] - 1e-9 <= q <= ylim[1]])
    ax.grid(axis='y', color=GRID, lw=0.6); ax.set_axisbelow(True)
    if ylab: ax.set_ylabel(ylab, fontsize=7.8, color=MUT)
    pv = slope_p(df, val, cond)
    sl = {}
    for g in ['CTL', 'Hi']:
        sl[g] = np.mean([linregress(x.index.values.astype(float), x.values).slope
                         for m, gg in d[d.G3 == g].groupby('Mouse')
                         for x in [gg.groupby('Phase')[val].mean()] if len(x) >= 3])
    fm = '{:+.2f}' if val in ('sl', 'mdur') else '{:+.1f}'
    ax.text(0.5, 0.075, 'slope WT ' + fm.format(sl['CTL']) + ', Hi ' + fm.format(sl['Hi']),
            transform=ax.transAxes, ha='center', va='bottom', fontsize=6.3, color=MUT)
    ax.text(0.5, -0.005, 'group $\\times$ phase p = %.3f' % pv, transform=ax.transAxes,
            ha='center', va='bottom', fontsize=6.8, color=(INK if pv < 0.05 else MUT))
    for ph in PH:                                       # per-phase Hi vs WT, printed above the axes
        x1 = d[(d.Phase == ph) & (d.G3 == 'Hi')].groupby('Mouse')[val].mean()
        x2 = d[(d.Phase == ph) & (d.G3 == 'CTL')].groupby('Mouse')[val].mean()
        q = mw(x1, x2, alternative='two-sided')[1]
        if q < 0.05:
            i = PH.index(ph)
            ax.annotate('%s' % ('%.3f' % q).lstrip('0'), xy=(i, 1.005), xycoords=('data', 'axes fraction'),
                        ha='center', va='bottom', fontsize=6.5, color=INK, annotation_clip=False)
figB.legend(handles=[Line2D([], [], color=COL[g], lw=1.8, marker=MK[g], ms=4, label=LAB[g])
                     for g in ['CTL', 'Lo', 'Hi']],
            loc='upper center', bbox_to_anchor=(0.5, 0.945), ncol=3, frameon=False, fontsize=7.8)
figB.suptitle('Slowing and pausing across the rotations', fontsize=11.5, y=0.982, color=INK,
              fontweight='semibold')
figB.text(0.012, 0.862, 'a', fontsize=11, weight='bold', va='top', color=INK)
figB.text(0.012, 0.445, 'b', fontsize=11, weight='bold', va='top', color=INK)
outB = os.path.join(FIGS, 'fig16b_arrival_phase.png')
figB.savefig(outB, dpi=200); print('wrote', outB)
