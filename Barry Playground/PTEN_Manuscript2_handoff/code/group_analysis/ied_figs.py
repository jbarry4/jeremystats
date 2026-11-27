"""IEDs: laminar structure, rate with and without CNO, and how they relate to theta CSD and behaviour (report Figures 33-35, S3, S4).

## NOT IN MATLAB: designed here from the outputs of the lab's IED pipeline (inputs/ied, see config.IED_DIR):
##   GrandAvg_SOLID_Base.csv, GrandAvg_SOLID_CNO.csv  spatially normalised grand-average voltage of the solid IEDs, 49 depth
##       bins x 1201 samples (-20 to +20 ms at 30 kHz, time 0 = IED peak), mean of the 5 sessions per condition (5 mice).
##   IED_session_summary.csv, IED_onsets_solid.csv     per-session recording length, number of solid IEDs and onset times.
##   stats_*.csv                                       the pipeline's per-depth IP vs PP and drug statistics (reported as given).
## Depth bins -> layers (fixed by the spatial normalisation; checked against the pipeline's raster):
##   CA1 SLM 5, OML1 4, MML1 5, GCL1 5, HIL 13, GCL2 7, MML2 5, OML2 5 bins, superficial to deep.
## Theta CSD and behaviour come from this package (work/csd3: csd3.pkl, layers_means.csv).

Measures
  Voltage: each bin baseline-corrected to its mean from -20 to -10 ms. Layer value = mean over the layer's bins and the window:
           initiation (IP) -1 to 0 ms, propagation (PP) 2 to 15 ms (the pipeline's windows).
  CSD (supplementary, approximate): -(second difference across depth bins) of the voltage after 3-point [1 2 1]/4 smoothing,
           a.u. per bin. The bins are not evenly spaced in tissue, so this is an approximation of the pipeline's channel CSD.
  Theta excess: baseline theta CSD of IED+ mice minus WT, per layer (layers_means.csv, IED split); SE = sqrt(SE1^2 + SE2^2).
  IED rate: solid IEDs / recording minutes; also the first 20 min of every session, so sessions of different length compare.
  Intervals: time between successive IEDs within a session.
Tests: paired t across mice for rates (n = 5); Spearman across layers for the profile match (descriptive, n = 8 layers).
The four mice with recordings and behaviour (M3, M5, M28, M34) are shown individually; n = 4 is descriptive.
Outputs: FIGS/fig33_ied_voltage.png, fig34_two_outputs.png, fig35_dissociation.png, figS3_ied_csd.png, figS4_ied_timing.png;
         WORK/ied/ied_stats.txt, ied_mouse.csv, ied_layers.csv, ied_sessions.csv.
"""
import os, sys, warnings
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, _ROOT)
import config
import numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from scipy.stats import ttest_rel, wilcoxon, spearmanr
warnings.filterwarnings('ignore')
IN, WORK, FIGS = config.IED_DIR, config.WORK, config.FIGS
OUT = os.path.join(WORK, 'ied'); os.makedirs(OUT, exist_ok=True); os.makedirs(FIGS, exist_ok=True)
plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8.5, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'; GRY = '#9a9993'; HI = '#e34948'; GRID = '#e9e8e3'
REG = ['CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2']; NB = [5, 4, 5, 5, 13, 7, 5, 5]
LAB = [r.replace('DG ', '') for r in REG]; EDGES = np.cumsum([0] + NB); ROWREG = np.repeat(np.arange(8), NB)
T = np.linspace(-20, 20, 1201); IP = (-1, 0); PP = (2, 15)
LOG = []
def log(s=''): print(s); LOG.append(s)
fp = lambda p: 'p < 0.001' if p < 0.001 else f'p = {p:.3f}'

# ---------------------------------------------------------------- data
def load(c):
    A = pd.read_csv(os.path.join(IN, f'GrandAvg_SOLID_{c}.csv')).values
    assert A.shape == (49, 1201)
    return A - A[:, (T >= -20) & (T <= -10)].mean(1, keepdims=True)
def csd(V):
    S = V.copy(); S[1:-1] = (V[:-2] + 2 * V[1:-1] + V[2:]) / 4
    C = np.full_like(S, np.nan); C[1:-1] = -(S[2:] - 2 * S[1:-1] + S[:-2]); return C
def prof(M, w):
    k = (T >= w[0]) & (T <= w[1]); return np.array([np.nanmean(M[ROWREG == i][:, k]) for i in range(8)])
V = {c: load(c) for c in ['Base', 'CNO']}; C = {c: csd(V[c]) for c in V}
S = pd.read_csv(os.path.join(IN, 'IED_session_summary.csv')); S['m'] = S.Mouse.str.extract(r'(\d+)')[0].astype(int)
O = pd.read_csv(os.path.join(IN, 'IED_onsets_solid.csv')); O['m'] = O.Mouse.str.extract(r'(\d+)')[0].astype(int)
O = O.sort_values(['Session_ID', 'Onset_s']); O['iei'] = O.groupby('Session_ID').Onset_s.diff()
NIED = S.groupby('Condition').N_solid_IEDs.sum().to_dict()
cs = pd.read_pickle(os.path.join(WORK, 'csd3', 'csd3.pkl'))
lm = pd.read_csv(os.path.join(WORK, 'csd3', 'layers_means.csv')); lm = lm[lm.split == 'IED']
MICE = sorted(S.m.unique()); BEH = [m for m in MICE if m in cs.index and pd.notna(cs.loc[m, 'Goal_base'])]

# ---------------------------------------------------------------- statistics
L = pd.DataFrame({'layer': REG})
for c in V:
    for w, nm in [(IP, 'IP'), (PP, 'PP')]:
        L[f'voltage_{nm}_{c}'] = prof(V[c], w); L[f'csd_{nm}_{c}'] = prof(C[c], w)
w_ = lm[lm.group == 'WT'].set_index('layer'); p_ = lm[lm.group == 'IED+'].set_index('layer')
L['theta_WT'] = w_.base.reindex(REG).values; L['theta_IEDpos'] = p_.base.reindex(REG).values
L['theta_excess'] = L.theta_IEDpos - L.theta_WT; L['theta_excess_se'] = np.sqrt(p_.base_se ** 2 + w_.base_se ** 2).reindex(REG).values
L.round(4).to_csv(os.path.join(OUT, 'ied_layers.csv'), index=False)
log(f'Grand averages: {NIED.get("Base")} baseline and {NIED.get("CNO")} CNO solid IEDs, 5 mice ({", ".join("M%d" % m for m in MICE)}).')
log('\nVoltage by layer (uV), grand average: initiation (-1 to 0 ms) and propagation (2 to 15 ms)')
log(L[['layer', 'voltage_IP_Base', 'voltage_IP_CNO', 'voltage_PP_Base', 'voltage_PP_CNO']].round(0).to_string(index=False))
log('\nApproximate CSD by layer (a.u.), grand average')
log(L[['layer', 'csd_IP_Base', 'csd_IP_CNO', 'csd_PP_Base', 'csd_PP_CNO']].round(1).to_string(index=False))
r, pv = spearmanr(L.theta_excess, L.csd_IP_Base.abs())
log(f'\nTheta excess (IED+ minus WT, baseline) vs |IED initiation CSD| across the 8 layers: Spearman rho {r:+.2f} ({fp(pv)}), descriptive')
log(L[['layer', 'theta_WT', 'theta_IEDpos', 'theta_excess', 'theta_excess_se']].round(4).to_string(index=False))

R = S.pivot(index='m', columns='Condition', values='IED_per_min')
LEN = S.set_index('Session_ID').Recording_length_s
r20 = {}
for (m, c), g in O.groupby(['m', 'Condition']):
    sid = S[(S.m == m) & (S.Condition == c)].Session_ID.iloc[0]; r20[(m, c)] = (g.Onset_s < 1200).sum() / min(LEN[sid], 1200) * 60
for m in MICE:
    for c in ['Base', 'CNO']: r20.setdefault((m, c), 0.0)
R20 = pd.Series(r20).unstack()
log('\nIED rate (per min), whole session and first 20 min')
for m in MICE: log(f'  M{m}: {R.loc[m, "Base"]:.2f} -> {R.loc[m, "CNO"]:.2f}  (first 20 min {R20.loc[m, "Base"]:.2f} -> {R20.loc[m, "CNO"]:.2f})')
log(f'  whole session: mean {R.Base.mean():.2f} -> {R.CNO.mean():.2f}, paired t {fp(ttest_rel(R.CNO, R.Base).pvalue)}, Wilcoxon {fp(wilcoxon(R.CNO, R.Base).pvalue)}, up in {int((R.CNO > R.Base).sum())}/{len(R)}')
pooled = S.groupby('Condition').apply(lambda g: g.N_solid_IEDs.sum() / g.Recording_length_min.sum())
log(f'  pooled: {pooled.Base:.2f} -> {pooled.CNO:.2f} per min (ratio {pooled.CNO / pooled.Base:.1f})')
log(f'  first 20 min: mean {R20.Base.mean():.2f} -> {R20.CNO.mean():.2f}, paired t {fp(ttest_rel(R20.CNO, R20.Base).pvalue)}')
b = O[O.Condition == 'Base'].iei.dropna(); cc = O[O.Condition == 'CNO'].iei.dropna()
log(f'\nIntervals between IEDs (pooled): baseline median {b.median():.0f} s (n {len(b)}), CNO {cc.median():.0f} s (n {len(cc)}); under 30 s: {(b < 30).mean() * 100:.0f}% vs {(cc < 30).mean() * 100:.0f}%')
for m in MICE:
    x = O[O.m == m]; log(f'  M{m}: median interval baseline {x[x.Condition == "Base"].iei.median():.0f} s, CNO {x[x.Condition == "CNO"].iei.median():.0f} s')

D = pd.DataFrame(index=MICE); D.index.name = 'Mouse'
D['Group'] = [cs.loc[m, 'G'] if m in cs.index else '' for m in MICE]
D['IED_per_min_base'] = R.Base; D['IED_per_min_CNO'] = R.CNO; D['IED_per_min_first20_base'] = R20.Base; D['IED_per_min_first20_CNO'] = R20.CNO
for k, nm in [('AVG4', 'theta_4layer'), ('M2G2', 'theta_MML2_GCL2'), ('GCL2', 'theta_GCL2'), ('MML2', 'theta_MML2')]:
    D[f'{nm}_base'] = [cs.loc[m, f'{k}_base'] for m in MICE]; D[f'{nm}_CNO'] = [cs.loc[m, f'{k}_cno'] for m in MICE]
    D[f'{nm}_change_pct'] = (D[f'{nm}_CNO'] / D[f'{nm}_base'] - 1) * 100
D['hidden_goal_time_base'] = [cs.loc[m, 'Goal_base'] for m in MICE]; D['hidden_goal_time_CNO'] = [cs.loc[m, 'Goal_cno'] for m in MICE]
D['visible_goal_time_base'] = [cs.loc[m, 'Vis_base'] for m in MICE]; D['visible_goal_time_CNO'] = [cs.loc[m, 'Vis_cno'] for m in MICE]
D.round(4).to_csv(os.path.join(OUT, 'ied_mouse.csv'))
log('\nPer mouse: IED rate, theta CSD change with CNO, hidden goal-zone time (%)')
for m in MICE:
    d = D.loc[m]
    log(f'  M{m}: IED x{d.IED_per_min_CNO / d.IED_per_min_base:.1f}; theta 4-layer {d.theta_4layer_change_pct:+.0f}%, MML2+GCL2 {d.theta_MML2_GCL2_change_pct:+.0f}%, GCL2 {d.theta_GCL2_change_pct:+.0f}%; '
        + (f'hidden goal {d.hidden_goal_time_base:.1f} -> {d.hidden_goal_time_CNO:.1f}' if pd.notna(d.hidden_goal_time_base) else 'no behaviour'))
S.to_csv(os.path.join(OUT, 'ied_sessions.csv'), index=False)
log('\nPipeline statistics (as given, inputs/ied/stats_*.csv)')
for f in ['stats_IED_rate.csv', 'stats_IEDlevel_IPvsPP_Base.csv', 'stats_Voltage_laminar_4panel.csv', 'stats_CSD_laminar_4panel.csv']:
    log(f'  {f}'); log(pd.read_csv(os.path.join(IN, f)).round(4).to_string(index=False))
open(os.path.join(OUT, 'ied_stats.txt'), 'w').write('\n'.join(LOG) + '\n')

# ---------------------------------------------------------------- plotting helpers
def title(ax, s, sub=None, pad=16):
    ax.set_title(s, fontsize=9, color=INK, fontweight='bold', loc='left', pad=pad if sub else 6)
    if sub: ax.text(0, 1.015 + (pad - 16) / 330, sub, transform=ax.transAxes, fontsize=7.2, color=MUT, va='bottom')
def raster(fig, cells, M, lim, letters, unit, sub):
    tw = (T >= -8) & (T <= 15)
    for j, c in enumerate(['Base', 'CNO']):
        ax = fig.add_subplot(cells[j])
        im = ax.imshow(M[c][:, tw], aspect='auto', cmap='jet', vmin=-lim, vmax=lim, extent=[-8, 15, 49, 0], interpolation='bilinear')
        for e in EDGES[1:-1]: ax.axhline(e, color=INK, lw=0.6, alpha=0.8)
        ax.axvline(0, color=INK, lw=0.6, ls=':')
        for w, nm in [(IP, 'IP'), (PP, 'PP')]:
            ax.plot(w, [-0.9, -0.9], color=INK, lw=3, solid_capstyle='butt', clip_on=False)
            ax.text(np.mean(w) if nm == 'PP' else w[0] - 0.6, -1.9, nm, ha='center' if nm == 'PP' else 'right', va='bottom', fontsize=6.5, color=INK)
        ax.set_yticks((EDGES[:-1] + EDGES[1:]) / 2); ax.set_yticklabels(LAB if j == 0 else [], fontsize=7); ax.tick_params(length=0, axis='y')
        ax.set_xlabel('time from IED peak (ms)', fontsize=7.8)
        title(ax, f'{letters[j]}  {"Baseline" if c == "Base" else "CNO"}', sub.format(n=NIED[c]), pad=28)
    cax = fig.add_subplot(cells[2]); cb = fig.colorbar(im, cax=cax); cb.ax.tick_params(labelsize=6.5); cb.set_label(unit, fontsize=7)

# ---------------------------------------------------------------- Figure 33: IED voltage
fig = plt.figure(figsize=(7.6, 7.0))
gs = fig.add_gridspec(2, 3, width_ratios=[1, 1, 0.05], height_ratios=[1, 0.95], wspace=0.14, hspace=0.5, left=0.1, right=0.9, top=0.87, bottom=0.07)
lim = max(abs(V[c][:, (T >= -8) & (T <= 15)]).max() for c in V)
raster(fig, [gs[0, 0], gs[0, 1], gs[0, 2]], V, lim, 'AB', 'voltage (µV)', 'grand average, 5 mice, {n} IEDs')
y = np.arange(8); xl = [min(min(prof(V[c], w).min() for w in (IP, PP)) for c in V), max(max(prof(V[c], w).max() for w in (IP, PP)) for c in V)]
xl = [xl[0] - 0.08 * (xl[1] - xl[0]), xl[1] + 0.08 * (xl[1] - xl[0])]
for j, (c, lt) in enumerate([('Base', 'C'), ('CNO', 'D')]):
    ax = fig.add_subplot(gs[1, j])
    ax.plot(prof(V[c], IP), y, color=INK, marker='o', ms=5, lw=1.6, label='initiation (IP), −1 to 0 ms')
    ax.plot(prof(V[c], PP), y, color=GRY, marker='s', ms=5, mfc='#fcfcfb', lw=1.4, ls=(0, (4, 2)), label='propagation (PP), 2 to 15 ms')
    ax.axvline(0, color=GRY, lw=0.8, ls=':'); ax.set_yticks(y); ax.set_yticklabels(LAB if j == 0 else [], fontsize=7.5); ax.invert_yaxis()
    ax.set_xlim(xl); ax.grid(axis='x', color=GRID, lw=0.6); ax.set_xlabel('voltage (µV)', fontsize=7.8)
    title(ax, f'{lt}  Voltage by layer, {"baseline" if c == "Base" else "CNO"}', 'filled: initiation (−1 to 0 ms); open: propagation (2 to 15 ms)')
fig.suptitle('The IED keeps its laminar structure with CNO', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.savefig(os.path.join(FIGS, 'fig33_ied_voltage.png'), dpi=200); plt.close()

# ---------------------------------------------------------------- Figure 34: one circuit, two outputs
ip = L.csd_IP_Base.values; ex = L.theta_excess.values; se = L.theta_excess_se.values
fig, axs = plt.subplots(1, 3, figsize=(7.6, 3.6), sharey=True, gridspec_kw={'width_ratios': [1, 1, 1.05]}); y = np.arange(8)
ax = axs[0]; ax.barh(y, ex, xerr=se, color=HI, height=0.6, error_kw=dict(ecolor=MUT, lw=0.8, capsize=2)); ax.axvline(0, color=GRY, lw=0.8)
ax.set_yticks(y); ax.set_yticklabels(LAB); ax.invert_yaxis(); ax.set_xlabel('theta CSD, IED+ minus WT (a.u.)', fontsize=7.8); ax.grid(axis='x', color=GRID, lw=0.6)
n_ied = int(lm[lm.group == 'IED+'].n_base.max()); n_wt = int(lm[lm.group == 'WT'].n_base.max())
title(ax, 'A  Excess theta current', f'baseline; IED+ ({n_ied}) vs WT ({n_wt}); ± SE')
ax = axs[1]; ax.barh(y, ip, color=['#2a78d6' if v < 0 else '#c0392b' for v in ip], height=0.6); ax.axvline(0, color=GRY, lw=0.8)
ax.set_xlabel('IED CSD, initiation (a.u., approximate)', fontsize=7.8); ax.grid(axis='x', color=GRID, lw=0.6)
title(ax, 'B  IED initiation current', '−1 to 0 ms, baseline; blue sink, red source')
ax = axs[2]; a = ex / np.nanmax(np.abs(ex)); b = np.abs(ip) / np.nanmax(np.abs(ip))
ax.axhspan(4.5, 6.5, color='#f9eeda', zorder=0)
ax.plot(a, y, color=HI, marker='o', lw=1.6, label='theta excess'); ax.plot(b, y, color=INK, marker='s', lw=1.4, ls=(0, (4, 2)), label='|IED current|')
ax.set_xlim(-0.15, 1.1); ax.set_xlabel('scaled to each maximum', fontsize=7.8); ax.legend(fontsize=7, loc='upper right'); ax.grid(axis='x', color=GRID, lw=0.6)
r, pv = spearmanr(a, b); title(ax, 'C  Both peak at GCL2–MML2', f'across the 8 layers ρ = {r:+.2f} (descriptive)')
fig.suptitle('One circuit, two outputs: theta excess and IED initiation share the lower blade', x=.01, ha='left', fontsize=11.5, fontweight='bold', color=INK, y=.995)
fig.subplots_adjust(left=0.1, right=0.985, bottom=0.15, top=0.78, wspace=0.12); fig.savefig(os.path.join(FIGS, 'fig34_two_outputs.png'), dpi=200); plt.close()

# ---------------------------------------------------------------- Figure 35: dissociation
fig, axs = plt.subplots(1, 3, figsize=(7.6, 3.5))
def paired(ax, vals, lab, ttl, sub, ms, off={}):
    for mm in ms:
        b0, c1 = vals[mm]; hl = mm == 28; col = HI if mm in BEH else GRY
        ax.plot([0, 1], [b0, c1], color=col, lw=1.8 if hl else 1.0, alpha=1 if hl else 0.7, zorder=2)
        for x, v, filled in [(0, b0, False), (1, c1, mm in BEH)]:   # all these mice are IED+: diamonds; open = baseline, filled = CNO
            ax.scatter(x, v, marker='D', s=30, facecolor=col if filled else '#fcfcfb', edgecolor='#fcfcfb' if filled else col, lw=0.9, zorder=3)
        ax.text(1.07, c1 + off.get(mm, 0), f'M{mm}', fontsize=6.8, va='center', color=INK if hl else MUT, fontweight='bold' if hl else 'normal')
    ax.set_xticks([0, 1]); ax.set_xticklabels(['baseline', 'CNO']); ax.set_xlim(-0.25, 1.35); ax.set_ylabel(lab, fontsize=7.8); ax.grid(axis='y', color=GRID, lw=0.6)
    title(ax, ttl, sub)
paired(axs[0], {m: (D.loc[m, 'theta_4layer_base'], D.loc[m, 'theta_4layer_CNO']) for m in MICE}, 'theta CSD, 4-layer mean (a.u.)', 'A  Theta current', 'falls in M3, M5, M34; M28 least', MICE)
paired(axs[1], {m: (D.loc[m, 'IED_per_min_base'], D.loc[m, 'IED_per_min_CNO']) for m in MICE}, 'IEDs per minute', 'B  IED rate', f'rises in {int((R.CNO > R.Base).sum())} of {len(R)}', MICE)
paired(axs[2], {m: (D.loc[m, 'hidden_goal_time_base'], D.loc[m, 'hidden_goal_time_CNO']) for m in BEH}, 'hidden goal-zone time (%)', 'C  Hidden-goal behaviour',
       f'improves in {int((D.hidden_goal_time_CNO > D.hidden_goal_time_base).sum())} of {len(BEH)}', BEH, off={3: 0.22, 34: 0.0, 28: -0.22})
fig.suptitle('Silencing KO cells: behaviour follows theta, not IED rate', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.text(0.01, 0.015, 'IED+ Hi mice (diamonds) with recordings and behaviour: open = baseline, filled = CNO; M13 (grey) has recordings only.\nRecording and behaviour sessions were on different days.', fontsize=6.8, color=MUT)
fig.subplots_adjust(left=0.08, right=0.97, bottom=0.19, top=0.78, wspace=0.55); fig.savefig(os.path.join(FIGS, 'fig35_dissociation.png'), dpi=200); plt.close()

# ---------------------------------------------------------------- Supplementary Figure S3: approximate CSD
clim = np.nanpercentile(np.abs(np.concatenate([C[c][:, (T >= -8) & (T <= 15)].ravel() for c in C])), 99.5)
fig = plt.figure(figsize=(5.6, 4.0)); gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.05], wspace=0.12, left=0.13, right=0.88, top=0.76, bottom=0.14)
raster(fig, [gs[0], gs[1], gs[2]], C, clim, 'AB', 'CSD (a.u.; negative = sink)', 'approximate: from the averaged voltage')
fig.suptitle('CSD of the averaged IED', x=.01, ha='left', fontsize=11, fontweight='bold', color=INK, y=.995)
fig.savefig(os.path.join(FIGS, 'figS3_ied_csd.png'), dpi=200); plt.close()

# ---------------------------------------------------------------- Supplementary Figure S4: timing
fig, axs = plt.subplots(1, 3, figsize=(7.6, 3.3), gridspec_kw={'width_ratios': [1.3, 1, 1]})
ax = axs[0]
for i, m in enumerate(MICE):
    for c, yy, col in [('Base', i * 2 + 0.35, INK), ('CNO', i * 2 - 0.35, HI)]:
        g = O[(O.m == m) & (O.Condition == c)]; sid = S[(S.m == m) & (S.Condition == c)].Session_ID.iloc[0]
        ax.plot([0, LEN[sid] / 60], [yy, yy], color=GRID, lw=5, solid_capstyle='butt', zorder=1)
        ax.vlines(g.Onset_min, yy - 0.3, yy + 0.3, color=col, lw=0.9, zorder=2)
ax.set_yticks([i * 2 for i in range(len(MICE))]); ax.set_yticklabels([f'M{m}' for m in MICE]); ax.invert_yaxis(); ax.set_xlabel('time from recording start (min)', fontsize=7.8)
title(ax, 'A  Every IED', 'black: baseline; red: CNO; grey bar: recording')
ax = axs[1]
for m in MICE:
    ax.plot([0, 1], [R20.loc[m, 'Base'], R20.loc[m, 'CNO']], color=HI if m in BEH else GRY, lw=1, marker='D', ms=4.5, mfc='#fcfcfb', mec=HI if m in BEH else GRY)
ax.set_xticks([0, 1]); ax.set_xticklabels(['baseline', 'CNO']); ax.set_xlim(-0.3, 1.3); ax.set_ylabel('IEDs per minute, first 20 min', fontsize=7.8); ax.grid(axis='y', color=GRID, lw=0.6)
title(ax, 'B  First 20 min of each session', f'mean {R20.Base.mean():.2f} → {R20.CNO.mean():.2f}; paired p = {ttest_rel(R20.CNO, R20.Base).pvalue:.2f}')
ax = axs[2]
for c, col in [('Base', INK), ('CNO', HI)]:
    x = np.sort(O[O.Condition == c].iei.dropna().clip(lower=0.05))
    ax.step(x, np.arange(1, len(x) + 1) / len(x) * 100, where='post', color=col, lw=1.5, label=f'{"baseline" if c == "Base" else "CNO"} ({len(x)} intervals)')
ax.axvline(30, color=GRY, lw=0.7, ls=':'); ax.set_xscale('log'); ax.set_xlabel('interval between IEDs (s)', fontsize=7.8); ax.set_ylabel('% of intervals shorter', fontsize=7.8)
ax.legend(fontsize=6.6, loc='upper left'); ax.grid(color=GRID, lw=0.6)
title(ax, 'C  Closer together', f'< 30 s apart: {(b < 30).mean() * 100:.0f}% → {(cc < 30).mean() * 100:.0f}% (pooled)')
fig.suptitle('IED timing within sessions', x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.995)
fig.subplots_adjust(left=0.07, right=0.985, bottom=0.16, top=0.78, wspace=0.45); fig.savefig(os.path.join(FIGS, 'figS4_ied_timing.png'), dpi=200); plt.close()
