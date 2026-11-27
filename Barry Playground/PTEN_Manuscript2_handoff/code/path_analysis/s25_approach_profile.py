"""Step 25. The shape of the approach: speed against distance from the goal.

This is the Whishaw test drawn rather than counted.  Whishaw, Cassel and Jarrard (1995) take
deceleration on approach as the sign that an animal expects the goal at a place.  Every directed
run into the current goal is expressed as speed against distance from the goal centre, with each
run scaled to its own approach maximum, so what is compared is the SHAPE of the approach and not
how fast the mouse runs in general.  Runs are averaged within a mouse and mice within a group, so
every line is a mean over mice and the band is the SE over mice.

The curve hooks: the mouse accelerates away from the wall, peaks 12 to 16 cm out, then decelerates
into the zone.  The dashed line at 70% of the run's approach maximum is the same braking criterion
the event-based measures use (s21), so this figure and those counts refer to one definition.

Runs are found exactly as in s21: the final approach before each entry into the current goal,
walked back while the mouse is moving towards the goal, kept when it launched at least 20 cm out.
Each run is cut at the frame it entered the zone, because after that it is no longer an approach.
A bin is drawn where at least half of the group's mice contribute a run reaching that far out.

Two figures:
  fig_approach_profile.png        phase 10, cue removed and cue present  (the pair in the summary)
  fig_approach_profile_phases.png the same, every phase 7 to 10, cue removed above, present below

Statistics, printed: the profiles are compared with a max-statistic permutation test over the
whole profile, which corrects for testing many bins - Hi against WT in each condition, and the
within-animal hidden-minus-cued profile.  Both are nulls, and that is the point: the approach is
normal, and what differs is whether a run brakes at all and what happens on arrival.

Reads the raw tracking files (as s21 does).
Outputs: WORK/approach/approach_profiles.csv and the two figures.
"""
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
from config import DATA_ROOT, WORK, FIGS
import warnings
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg')
warnings.filterwarnings('ignore', category=RuntimeWarning)
import matplotlib.pyplot as plt
from traj_lib import read_dat, target_xy

CM = 75 / 255; SF = 30
LAUNCH_MIN = 20.0        # cm, a directed run, as everywhere in this package
BRAKE = 70.0             # % of the run's approach maximum; the s21 braking criterion
EDGES = np.arange(5, 57, 2); CEN = EDGES[:-1] + 1.0
COL = {'CTL': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}
LAB = {'CTL': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}
INK = '#0b0b0b'; MUT = '#52514e'; GRID = '#e4e3de'
CACHE = os.path.join(WORK, 'approach', 'approach_profiles.csv')

sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values


def compute():
    S = pd.read_pickle(WORK + '/approach/sessions.pkl')
    P = json.load(open(WORK + '/approach/paths.json'))
    out = []
    for _, r in S.iterrows():
        if r.File not in P: continue
        h, d = read_dat(os.path.join(DATA_ROOT, P[r.File])); st = d['state']
        Xs = sm(np.where(d['X'] == 0, np.nan, d['X'])); Ys = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
        gx, gy, gr = target_xy(h); n = len(Xs)
        k = 7; sp = np.full(n, np.nan)
        sp[k:-k] = np.hypot(Xs[2 * k:] - Xs[:-2 * k], Ys[2 * k:] - Ys[:-2 * k]) * CM / (2 * k / SF)
        dist = np.hypot(Xs - gx, Ys - gy) * CM
        vx = np.gradient(Xs) * SF * CM; vy = np.gradient(Ys) * SF * CM; spg = np.hypot(vx, vy)
        ux, uy = gx - Xs, gy - Ys
        err = np.degrees(np.arccos(np.clip((vx * ux + vy * uy) / (spg * np.hypot(ux, uy) + 1e-9), -1, 1)))
        inz = np.isin(st, [1, 2, 3]); mov = spg > 5
        E = np.where((st[:-1] == 0) & (st[1:] == 1))[0] + 1
        E = E[(E > 3 * SF) & (E < n - 3 * SF)]
        for e in E:
            bad = 0; j2 = e - 1; lo = max(0, e - 20 * SF)
            while j2 > lo and not inz[j2]:
                if mov[j2] and err[j2] < 45: bad = 0
                else: bad += 1
                if bad > 15: break
                j2 -= 1
            s0 = min(j2 + bad, e - 1)
            if dist[s0] < LAUNCH_MIN: continue
            seg = sp[s0:e + 1]; dd = dist[s0:e + 1]
            if len(seg) < 5 or np.all(~np.isfinite(seg)): continue
            vmax = np.nanmax(seg)
            if not vmax > 0: continue
            s = seg / vmax * 100.0
            kb = np.digitize(dd, EDGES) - 1
            row = dict(Mouse=r.Mouse, Phase=int(r.Phase), Cond=r.Condition)
            for i in range(len(CEN)):
                sel = (kb == i) & np.isfinite(s)
                row['b%02d' % i] = s[sel].mean() if sel.any() else np.nan
            out.append(row)
    T = pd.DataFrame(out)
    T.to_csv(CACHE, index=False)
    print('runs profiled:', len(T))
    return T


T = pd.read_csv(CACHE) if os.path.exists(CACHE) else compute()
BC = ['b%02d' % i for i in range(len(CEN))]
p = pd.read_pickle(WORK + '/probe.pkl'); G = p.drop_duplicates('MouseID').set_index('MouseID').G3
T['G3'] = T.Mouse.map(G); T = T[T.G3.isin(COL)]


def mice_array(cond, g, phases):
    """One row per mouse: its mean profile over the runs of those phases."""
    d = T[(T.Cond == cond) & (T.G3 == g) & (T.Phase.isin(phases))]
    rows, ids = [], []
    for m, dm in d.groupby('Mouse'):
        with np.errstate(invalid='ignore'):
            rows.append(np.nanmean(dm[BC].values.astype(float), 0))
        ids.append(m)
    return np.array(rows) if rows else np.zeros((0, len(CEN))), ids


def band(A):
    n = np.sum(np.isfinite(A), 0)
    keep = n >= max(2, int(np.ceil(len(A) / 2)))
    with np.errstate(invalid='ignore'):
        mu = np.nanmean(A, 0); sd = np.nanstd(A, 0, ddof=1)
    se = sd / np.sqrt(np.maximum(n, 1))
    mu = np.where(keep, mu, np.nan); se = np.where(keep, se, np.nan)
    return mu, se


def draw(ax, cond, phases, legend=False, ylab=True, xlab=True):
    gr = 5.625
    ax.axvspan(gr, 0, color='#efeee8', lw=0)
    for g in ['CTL', 'Lo', 'Hi']:
        mu, se = band(mice_array(cond, g, phases)[0])
        ok = np.isfinite(mu)
        ax.fill_between(CEN[ok], (mu - se)[ok], (mu + se)[ok], color=COL[g], alpha=0.16, lw=0)
        ax.plot(CEN[ok], mu[ok], color=COL[g], lw=1.8, label=LAB[g])
    ax.axhline(BRAKE, color=MUT, lw=0.8, ls=(0, (4, 3)))
    ax.text(gr / 2, 21.5, 'goal', fontsize=6.6, color=MUT, ha='center')
    ax.set_xlim(60, 3); ax.set_ylim(20, 100); ax.set_xticks([60, 40, 20])
    if xlab: ax.set_xlabel('distance from the goal (cm)', fontsize=8.4, labelpad=2)
    if ylab: ax.set_ylabel("speed (% of that run's maximum)", fontsize=8.4)
    else: ax.set_yticklabels([])
    for s in ['top', 'right']: ax.spines[s].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.6); ax.set_axisbelow(True)
    ax.tick_params(labelsize=8)
    if legend: ax.legend(frameon=False, fontsize=7.6, loc='lower right')


def maxstat(A, B, nperm=10000, seed=0):
    """Largest absolute difference in bin means, with mouse labels shuffled between the groups."""
    if len(A) < 2 or len(B) < 2: return np.nan, np.nan
    rng = np.random.default_rng(seed); both = np.vstack([A, B]); na = len(A)
    ok = np.sum(np.isfinite(both), 0) >= 4
    with np.errstate(invalid='ignore'):
        obs = np.nanmax(np.abs(np.nanmean(A, 0) - np.nanmean(B, 0))[ok])
        cnt = 0
        for _ in range(nperm):
            idx = rng.permutation(len(both))
            dd = np.abs(np.nanmean(both[idx[:na]], 0) - np.nanmean(both[idx[na:]], 0))[ok]
            if np.nanmax(dd) >= obs: cnt += 1
    return obs, (cnt + 1) / (nperm + 1)


os.makedirs(FIGS, exist_ok=True)
# ---------------------------------------------------------------- phase 10, the pair
fig = plt.figure(figsize=(7.0, 2.9))
for i, (cond, ttl) in enumerate([('H', 'a   Cue removed, phase 10'),
                                 ('V', 'b   Cue present, phase 10')]):
    ax = fig.add_axes([0.085 + i * 0.500, 0.195, 0.380, 0.655])
    draw(ax, cond, [10], legend=(i == 0))
    ax.set_xticks([60, 50, 40, 30, 20, 10])
    ax.text(58, BRAKE + 1.5, 'braking threshold', fontsize=7, color=MUT, va='bottom')
    ax.set_title(ttl, fontsize=9, loc='left', pad=5)
out1 = os.path.join(FIGS, 'fig_approach_profile.png')
fig.savefig(out1, dpi=200); print('wrote', out1)

# ---------------------------------------------------------------- every phase
fig = plt.figure(figsize=(7.4, 4.3))
gs = fig.add_gridspec(2, 4, hspace=0.33, wspace=0.10, left=0.085, right=0.985,
                      top=0.885, bottom=0.115)
for i, (cond, rlab) in enumerate([('H', 'cue removed'), ('V', 'cue present')]):
    for j, ph in enumerate([7, 8, 9, 10]):
        ax = fig.add_subplot(gs[i, j])
        draw(ax, cond, [ph], legend=(i == 0 and j == 3), ylab=(j == 0), xlab=(i == 1))
        if i == 0:
            ax.set_title('Phase %d%s' % (ph, ' (trained)' if ph == 7 else ''),
                         fontsize=9, color=INK, fontweight='semibold', pad=4)
        if j == 0:
            ax.text(-0.33, 0.5, rlab, transform=ax.transAxes, rotation=90, ha='center',
                    va='center', fontsize=9.2, color=INK, fontweight='semibold')
fig.suptitle('The shape of the approach, every phase', x=0.010, ha='left',
             fontsize=11.5, fontweight='semibold', color=INK, y=0.985)
out2 = os.path.join(FIGS, 'fig_approach_profile_phases.png')
fig.savefig(out2, dpi=200); print('wrote', out2)

# ---------------------------------------------------------------- statistics
print('\nmax-statistic permutation over the whole profile (10,000 relabellings)')
for cond, nm in [('H', 'cue removed'), ('V', 'cue present')]:
    for ph in [[10], [7, 8, 9, 10]]:
        o, pv = maxstat(mice_array(cond, 'Hi', ph)[0], mice_array(cond, 'CTL', ph)[0])
        print('  %-11s phase %-10s Hi vs WT: max difference %4.1f points, p = %.3f'
              % (nm, ph[0] if len(ph) == 1 else '7-10', o, pv))
dif = {}
for g in COL:
    AH, ih = mice_array('H', g, [10]); AV, iv = mice_array('V', g, [10])
    both = [m for m in ih if m in iv]
    dif[g] = np.array([AH[ih.index(m)] - AV[iv.index(m)] for m in both])
o, pv = maxstat(dif['Hi'], dif['CTL'])
print('  within animal, hidden minus cued at phase 10, Hi vs WT: %4.1f points, p = %.3f' % (o, pv))
print('\npeaks, phase 10')
for cond, nm in [('H', 'cue removed'), ('V', 'cue present')]:
    for g in ['CTL', 'Lo', 'Hi']:
        mu, _ = band(mice_array(cond, g, [10])[0])
        print('  %-11s %-11s peak %.0f%% at %.0f cm, %.0f%% at the zone edge, %d mice'
              % (nm, LAB[g], np.nanmax(mu), CEN[np.nanargmax(mu)], mu[0],
                 len(mice_array(cond, g, [10])[0])))
