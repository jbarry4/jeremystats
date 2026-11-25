"""Step 15. Heading toward the goal as a function of distance from it, visible vs hidden (report Figure 32).

## NOT IN MATLAB: designed here. It refines Figures 21-22 (s04, s05), which summarise each approach by one launch
## distance per entry; this step uses every running frame instead, so it shows where along the way the mouse starts
## to orient to the goal.

Same smoothing, speed and arena fit as s04. For each of the 256 probe sessions (phases 7-10, visible and hidden):
  frames kept   running (> 5 cm/s), outside the goal zone (tracker state 0), and not in the 2 s after leaving the goal
                zone (so mice moving away from the goal after a visit do not count). Frames at the wall
                (radius > 0.8 x fitted arena radius) are kept separately; along the wall the heading is set by the wall.
  heading error angle between the velocity vector and the vector to the goal centre (0 = straight at the goal).
  goal-directedness = mean cos(heading error): 1 = straight at the goal, 0 = unrelated to it (random heading).
Per mouse and condition (phases 7-10 pooled, frames off the wall), in 2.5 cm bins of distance from the goal centre
(bins with < 30 frames dropped):
  reach  distance at which goal-directedness first falls below 0.1, going outward from the goal (linear interpolation).
  gd     mean goal-directedness from 10 to 40 cm (frame-weighted), a measure with no threshold.
Launch distances (s04, WORK/approach/entF.pkl): per mouse, % of goal entries launched from at least 20, 30, 40 cm.
Tests: visible vs hidden, paired t within group (and per distance bin, per phase for WT); groups, Mann-Whitney.
Outputs: WORK/heading/heading_bins.pkl, heading_mouse.csv, heading_profile.csv, heading_stats.txt; FIGS/fig32_heading_profile.png.
"""
import os, sys, json, warnings
_HERE = os.path.dirname(os.path.abspath(__file__)); sys.path[:0] = [_HERE, os.path.dirname(_HERE)]
import config
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import ttest_rel, mannwhitneyu, sem
from traj_lib import read_dat, target_xy
from arena_fit import fit_arena
warnings.filterwarnings('ignore')
DATA_ROOT, WORK, FIGS = config.DATA_ROOT, config.WORK, config.FIGS
OUT = os.path.join(WORK, 'heading'); os.makedirs(OUT, exist_ok=True)
CM = 75 / 255; SF = 30; EDGES = np.arange(0, 77.5, 2.5); THR = 0.1; GR = ['WT', 'Lo', 'Hi']
fp = lambda p: 'p < 0.001' if p < 0.001 else f'p = {p:.3f}'
mw = lambda a, b: mannwhitneyu(a, b, alternative='two-sided').pvalue
LOG = []
def log(s=''): print(s); LOG.append(s)

# ---------------------------------------------------------------- frames -> per-session distance bins
binf = os.path.join(OUT, 'heading_bins.pkl')
if not os.path.exists(binf) or '--recompute' in sys.argv:
    S = pd.read_pickle(os.path.join(WORK, 'approach', 'sessions.pkl')); P = json.load(open(os.path.join(WORK, 'approach', 'paths.json')))
    sm = lambda a: pd.Series(a).interpolate(limit=15).rolling(5, center=True, min_periods=3).mean().values
    rows = []
    for _, r in S.iterrows():
        if r.File not in P or int(r.Phase) not in (7, 8, 9, 10): continue
        h, d = read_dat(os.path.join(DATA_ROOT, P[r.File])); st = d['state']
        cx, cy, Rf = fit_arena(d['X'], d['Y'])
        X = sm(np.where(d['X'] == 0, np.nan, d['X'])); Y = sm(np.where(d['Y'] == 0, np.nan, d['Y']))
        gx, gy, gr = target_xy(h)
        wall = np.hypot(X - cx, Y - cy) / Rf > 0.8; dist = np.hypot(X - gx, Y - gy) * CM
        vx = np.gradient(X) * SF * CM; vy = np.gradient(Y) * SF * CM; spd = np.hypot(vx, vy)
        ux, uy = gx - X, gy - Y; err = np.degrees(np.arccos(np.clip((vx * ux + vy * uy) / (spd * np.hypot(ux, uy) + 1e-9), -1, 1)))
        inz = np.isin(st, [1, 2, 3]); post = np.zeros(len(st), bool)
        for x in np.where(inz[:-1] & ~inz[1:])[0] + 1: post[x:x + 2 * SF] = True
        ok = (spd > 5) & ~inz & ~post & ~np.isnan(err) & ~np.isnan(dist); b = np.digitize(dist, EDGES) - 1
        for wl in (False, True):
            m = ok & (wall == wl)
            for k in np.unique(b[m]):
                e = err[m & (b == k)]
                rows.append(dict(Mouse=r.Mouse, Phase=int(r.Phase), Cond=r.Condition, bin=k, wall=wl, n=len(e), sum_err=e.sum(),
                                 n_aim=(e < 45).sum(), sum_cos=np.cos(np.radians(e)).sum(), zone_r_cm=gr * CM))
    pd.DataFrame(rows).to_pickle(binf)

p = pd.read_pickle(os.path.join(WORK, 'probe.pkl')); m0 = p.drop_duplicates('MouseID').set_index('MouseID')
G = m0.G3.replace({'CTL': 'WT'}); IED = m0.IED == '+'
B = pd.read_pickle(binf); B['g'] = B.Mouse.map(G); B = B[B.g.isin(GR)]

def profile(x):
    a = x.groupby(['g', 'Mouse', 'Cond', 'bin'])[['n', 'sum_cos', 'sum_err', 'n_aim']].sum().reset_index()
    a['gd'] = a.sum_cos / a.n; a['err'] = a.sum_err / a.n; a['aimed'] = a.n_aim / a.n * 100; a['d'] = a.bin * 2.5 + 1.25
    return a[a.n >= 30]
def reach(c):
    c = c.sort_values('d'); d = c.d.values; y = c.gd.values
    for i in range(1, len(d)):
        if y[i] < THR <= y[i - 1]: return d[i - 1] + (y[i - 1] - THR) / (y[i - 1] - y[i]) * (d[i] - d[i - 1])
    return np.nan if y[0] < THR else d[-1]
def per_mouse(a):
    out = []
    for (g, m, c), x in a.groupby(['g', 'Mouse', 'Cond']):
        band = x[(x.d >= 10) & (x.d <= 40)]
        out.append(dict(g=g, Mouse=m, Cond=c, reach=reach(x), gd=np.average(band.gd, weights=band.n)))
    o = pd.DataFrame(out).pivot_table(index=['Mouse'], columns='Cond', values=['reach', 'gd']); o.columns = [f'{a}_{b}' for a, b in o.columns]
    o['g'] = o.index.map(G); return o

off = B[~B.wall]; A = profile(off); M = per_mouse(A); Aall = profile(B); Mall = per_mouse(Aall)
for ph in [7, 8, 9, 10]:
    mp = per_mouse(profile(off[off.Phase == ph])); M[f'reach_V_p{ph}'] = mp.reach_V; M[f'reach_H_p{ph}'] = mp.reach_H
E = pd.read_pickle(os.path.join(WORK, 'approach', 'entF.pkl')); E['g'] = E.Mouse.map(G); E = E[E.g.isin(GR)]
for t in [20, 30, 40]:
    s = E.groupby(['Mouse', 'Cond']).launch.apply(lambda l: (l >= t).mean() * 100).unstack(); M[f'launch_ge{t}_V'] = s.V; M[f'launch_ge{t}_H'] = s.H
M['reach_all_frames_V'] = Mall.reach_V; M['reach_all_frames_H'] = Mall.reach_H; M['gd_all_frames_V'] = Mall.gd_V; M['gd_all_frames_H'] = Mall.gd_H
M['IED'] = M.index.map(IED); M.index.name = 'Mouse'
M.round(4).to_csv(os.path.join(OUT, 'heading_mouse.csv'))
A[['g', 'Mouse', 'Cond', 'd', 'n', 'gd', 'err', 'aimed']].round(4).to_csv(os.path.join(OUT, 'heading_profile.csv'), index=False)

def paired(lab, v, D=M):
    for g in GR:
        x = D[D.g == g]; V, H = x[f'{v}_V'], x[f'{v}_H']; ok = V.notna() & H.notna()
        log(f'  {lab} {g} (n {ok.sum()}): visible {V.mean():.3f}  hidden {H.mean():.3f}  paired {fp(ttest_rel(V[ok], H[ok]).pvalue)}  visible higher in {int((V[ok] > H[ok]).sum())}/{ok.sum()}')
    for c in ['V', 'H']:
        w = D[D.g == 'WT'][f'{v}_{c}'].dropna()
        log(f'     {"visible" if c == "V" else "hidden"}: Lo vs WT {fp(mw(D[D.g == "Lo"][f"{v}_{c}"].dropna(), w))}  Hi vs WT {fp(mw(D[D.g == "Hi"][f"{v}_{c}"].dropna(), w))}  Lo vs Hi {fp(mw(D[D.g == "Lo"][f"{v}_{c}"].dropna(), D[D.g == "Hi"][f"{v}_{c}"].dropna()))}')
log('Frames off the wall, phases 7-10 pooled. reach = distance (cm) where goal-directedness falls below 0.1; gd = mean goal-directedness 10-40 cm.')
paired('reach', 'reach'); paired('gd', 'gd')
log('\nAll frames (wall included)'); paired('reach', 'reach_all_frames'); paired('gd', 'gd_all_frames')
log('\nWT reach by phase (frames off the wall)')
for ph in [7, 8, 9, 10]:
    x = M[M.g == 'WT']; V, H = x[f'reach_V_p{ph}'], x[f'reach_H_p{ph}']; ok = V.notna() & H.notna()
    log(f'  phase {ph}: visible {V.mean():.1f}  hidden {H.mean():.1f}  paired {fp(ttest_rel(V[ok], H[ok]).pvalue)}  {int((V[ok] > H[ok]).sum())}/{ok.sum()}')
log('\nWT goal-directedness by distance bin (frames off the wall): visible, hidden, paired t')
for d in sorted(A.d.unique()):
    s = A[(A.g == 'WT') & (A.d == d)].pivot(index='Mouse', columns='Cond', values='gd').dropna()
    if len(s) > 3: log(f'  {d:5.2f} cm: {s.V.mean():.3f}  {s.H.mean():.3f}  {fp(ttest_rel(s.V, s.H).pvalue)}  (n {len(s)})')
log('\nLaunch distances: % of goal entries launched from at least x cm')
for t in [20, 30, 40]: paired(f'>= {t} cm', f'launch_ge{t}')
open(os.path.join(OUT, 'heading_stats.txt'), 'w').write('\n'.join(LOG) + '\n')

# ---------------------------------------------------------------- Figure 32
plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8.5, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.grid': True,
                     'grid.color': '#e9e8e3', 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'; GRY = '#9a9993'; RED = '#b3261e'
COL = {'WT': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}; MK = {'WT': 'o', 'Lo': 's', 'Hi': '^'}
star = lambda p: '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else 'ns'
def title(ax, t, sub=None):
    ax.set_title(t, fontsize=9, color=INK, fontweight='bold', loc='left', pad=(25 if '\n' in sub else 16) if sub else 6)
    if sub: ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=7.2, color=MUT, va='bottom')
zr = B.zone_r_cm.median()
fig, axs = plt.subplots(2, 2, figsize=(7.6, 6.3), gridspec_kw={'width_ratios': [1.35, 1]})
ax = axs[0, 0]; w = A[(A.g == 'WT') & (A.d <= 48)]
for c, ls, lab in [('V', '-', 'cue visible'), ('H', (0, (4, 2)), 'cue hidden')]:
    t = w[w.Cond == c].groupby('d').gd.agg(['mean', sem]); ax.plot(t.index, t['mean'], color=COL['WT'], ls=ls, lw=1.8, label=lab)
    ax.fill_between(t.index, t['mean'] - t['sem'], t['mean'] + t['sem'], color=COL['WT'], alpha=0.15 if c == 'V' else 0.08, lw=0)
for d in sorted(w.d.unique()):
    s = w[w.d == d].pivot(index='Mouse', columns='Cond', values='gd').dropna()
    if len(s) > 3 and ttest_rel(s.V, s.H).pvalue < 0.05: ax.text(d, 0.66, '*', ha='center', va='bottom', fontsize=8, color=RED)
ax.axhline(0, color=GRY, lw=0.9, ls=(0, (4, 3))); ax.axhline(THR, color=GRY, lw=0.6, ls=':')
ax.axvspan(0, zr, color='#e9e8e3', alpha=0.8, lw=0); ax.text(zr / 2, 0.5, 'goal\nzone', ha='center', fontsize=6.5, color=MUT)
rv, rh = M[M.g == 'WT'].reach_V.mean(), M[M.g == 'WT'].reach_H.mean()
for r, ls in [(rv, '-'), (rh, (0, (4, 2)))]: ax.plot([r, r], [-0.03, THR], color=INK, lw=0.9, ls=ls)
ax.annotate('', xy=(rv, 0.13), xytext=(rh, 0.13), arrowprops=dict(arrowstyle='<->', color=INK, lw=0.8))
ax.text((rv + rh) / 2, 0.145, f'reach {rh:.0f} → {rv:.0f} cm', ha='center', fontsize=7, color=INK)
ax.set_xlim(0, 48); ax.set_ylim(-0.05, 0.72); ax.set_xlabel('distance from goal centre (cm)'); ax.set_ylabel('goal-directedness\n(mean cos of heading error; 0 = random)')
ax.legend(loc='center right', fontsize=7.4)
title(ax, 'A  WT: heading toward the goal by distance', 'running, off the wall, phases 7–10; 19 mice ± SE; *: paired t p < 0.05')
ax = axs[0, 1]
for i, g in enumerate(GR):
    x = M[M.g == g]; xv, xh = i - 0.2, i + 0.2
    for m, r in x.iterrows():
        ied = bool(IED.get(m, False))
        ax.plot([xv, xh], [r.reach_V, r.reach_H], color=COL[g], lw=0.6, alpha=0.45)
        ax.scatter(xv, r.reach_V, s=18, marker='D' if ied else 'o', color=COL[g], edgecolor='#fcfcfb', lw=0.8, zorder=4)
        ax.scatter(xh, r.reach_H, s=18, marker='D' if ied else 'o', facecolor='#fcfcfb', edgecolor=COL[g], lw=0.8, zorder=4)
    ok = x.reach_V.notna() & x.reach_H.notna()
    ax.plot([xv - .13, xv + .13], [x.reach_V.mean()] * 2, color=COL[g], lw=2.2, zorder=3); ax.plot([xh - .13, xh + .13], [x.reach_H.mean()] * 2, color=GRY, lw=2.2, zorder=3)
    pv = ttest_rel(x.reach_V[ok], x.reach_H[ok]).pvalue
    ax.text(i, 52, f'{star(pv)}\n{int((x.reach_V[ok] > x.reach_H[ok]).sum())}/{ok.sum()} mice', ha='center', va='bottom', fontsize=6.8, color=RED if pv < 0.05 else MUT)
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(GR); ax.set_xlim(-0.55, 2.55); ax.set_ylim(8, 62); ax.set_ylabel('reach (cm)')
title(ax, 'B  Every group, nearly every mouse', 'reach = distance where A falls below 0.1;\nfilled: visible; open: hidden; paired t')
ax = axs[1, 0]; xs = np.arange(0, 56, 1)
for g in GR:
    for c, ls in [('V', '-'), ('H', (0, (4, 2)))]:
        cur = np.array([[(l >= t).mean() * 100 for t in xs] for _, l in E[(E.g == g) & (E.Cond == c)].groupby('Mouse').launch])
        ax.plot(xs, cur.mean(0), color=COL[g], ls=ls, lw=1.6 if g == 'WT' else 1.0, alpha=1 if g == 'WT' else 0.8)
for t in [20, 30, 40]:
    x = M[M.g == 'WT']; ax.text(t, x[f'launch_ge{t}_V'].mean() + 4, f'{x[f"launch_ge{t}_V"].mean():.0f} vs {x[f"launch_ge{t}_H"].mean():.0f}%', fontsize=6.6, color=COL['WT'])
ax.set_xlabel('launch distance (cm)'); ax.set_ylabel('% of goal entries launched\nfrom at least this far'); ax.set_xlim(0, 55); ax.set_ylim(0, 102)
ax.legend(handles=[Line2D([], [], color=COL[g], lw=1.6, label={'WT': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}[g]) for g in GR] +
          [Line2D([], [], color=GRY, lw=1.4, label='visible'), Line2D([], [], color=GRY, lw=1.4, ls=(0, (4, 2)), label='hidden')], fontsize=7, loc='upper right')
title(ax, 'C  Launch distances: the whole distribution shifts', 'mean of per-mouse curves; text: WT at 20, 30, 40 cm, visible vs hidden')
ax = axs[1, 1]; x = M[M.g == 'WT']
for c, ls, mf in [('V', '-', COL['WT']), ('H', (0, (4, 2)), '#fcfcfb')]:
    mu = [x[f'reach_{c}_p{ph}'].mean() for ph in [7, 8, 9, 10]]; se = [x[f'reach_{c}_p{ph}'].sem() for ph in [7, 8, 9, 10]]
    ax.errorbar([7, 8, 9, 10], mu, yerr=se, color=COL['WT'], ls=ls, marker='o', mfc=mf, ms=5, lw=1.5, capsize=2, label='visible' if c == 'V' else 'hidden')
for ph in [7, 8, 9, 10]:
    ok = x[[f'reach_V_p{ph}', f'reach_H_p{ph}']].dropna(); ax.text(ph, 40.5, star(ttest_rel(ok.iloc[:, 0], ok.iloc[:, 1]).pvalue), ha='center', fontsize=7, color=RED)
ax.set_xticks([7, 8, 9, 10]); ax.set_xlabel('probe phase'); ax.set_ylabel('reach (cm)'); ax.set_ylim(14, 44); ax.set_xlim(6.6, 10.4); ax.legend(fontsize=7, loc='lower right')
title(ax, 'D  WT: the gap holds at every phase', 'mean ± SE; paired t per phase')
fig.suptitle('With the cue, mice head for the goal from much further away', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.subplots_adjust(left=0.1, right=0.985, bottom=0.08, top=0.86, wspace=0.32, hspace=0.62)
fig.savefig(os.path.join(FIGS, 'fig32_heading_profile.png'), dpi=200); plt.close()
