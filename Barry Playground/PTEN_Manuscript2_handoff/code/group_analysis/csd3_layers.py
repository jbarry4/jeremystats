"""Layer profile of theta CSD (Figures 28 and 29). Uses the same inputs and exclusions as csd3_data.py.

Per mouse and session, each layer's CSD = mean of the channels with that layer label.
Groups: WT / Pten KO Lo / Pten KO Hi (Figure 28) and WT / KO without IEDs / KO with IEDs (Figure 29).
Statistics (following the lab's earlier analysis): GEE, Gaussian, exchangeable working correlation, clustered by mouse,
one coefficient per group x layer cell with the WT hilus as the reference cell. Run separately for baseline, after CNO,
and the change (CNO - baseline). Holm correction across the cells of each panel.
Also: paired t-test baseline vs CNO within group, Mann-Whitney vs WT within a layer, and the share of the baseline excess
over WT that CNO removes. Writes work/csd3/layers_gee.csv and layers_means.csv; figures to FIGS.
Figures are drawn with the layers running top to bottom (CA1 SP at the top, as along the probe) and CSD on the x-axis.
"""
import os, sys, warnings
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, _ROOT)
from config import *
import numpy as np, pandas as pd, pyreadstat, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
import statsmodels.api as sm, statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests
from scipy import stats
warnings.filterwarnings('ignore'); pd.set_option('display.width', 250)
plt.rcParams.update({'font.family': ['Inter', 'Helvetica', 'Arial', 'DejaVu Sans'], 'font.size': 8.5, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': '#9a9993', 'axes.labelcolor': '#52514e', 'xtick.color': '#52514e', 'ytick.color': '#52514e',
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb', 'axes.grid': True,
                     'grid.color': '#e9e8e3', 'grid.linewidth': 0.6, 'axes.axisbelow': True, 'legend.frameon': False})
INK = '#0b0b0b'; MUT = '#52514e'
LAY = ['CA1 SP', 'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2']
LAB = {L: L.replace('DG ', '').replace('HIL', 'Hilus') for L in LAY}

c, _ = pyreadstat.read_sav(CSD_SAV)
c['mouse'] = c.SESSID.str.extract(r'M(\d+)s')[0].astype(int); c['Estimate'] = c.Estimate.str.strip()
c = c[(c.Group != 'DKO') & ~c.mouse.isin(EPHYS_EXCLUDE)]
c = c[~((c.mouse == 59) & (c.Condition != 'CNO') & (c.SESSID != M59_BASELINE))]
c['cond'] = np.where(c.Condition == 'CNO', 'cno', 'base')
m = c[c.Estimate.isin(LAY)].groupby(['mouse', 'cond', 'Estimate']).CSD.mean().unstack('cond').reset_index()
m = m.merge(c.groupby('mouse').agg(grp=('Group', 'first'), ied=('IEDBIN', 'max')), left_on='mouse', right_index=True)
x4 = pd.read_excel(CNO_XLSX); x4['mouse'] = x4['UVM #'].astype(str).str.replace('M', '').astype(int)
pct = x4.set_index('mouse')['JB % hits'].dropna().to_dict(); pct.update(PCT_EXTRA)
m['pct'] = [0.0 if g == 'ZCTL' else pct[i] for i, g in zip(m.mouse, m.grp)]
m['LH'] = np.where(m.grp == 'ZCTL', 'WT', np.where(m.pct < 15, 'Lo', 'Hi'))
m['IED'] = np.where(m.grp == 'ZCTL', 'WT', np.where(m.ied == 1, 'IED+', 'IED-'))
m['chg'] = m.cno - m.base

SPLITS = {'LH': dict(groups=['WT', 'Lo', 'Hi'], col={'WT': '#2a78d6', 'Lo': '#008300', 'Hi': '#e34948'}, mk={'WT': 'o', 'Lo': 'o', 'Hi': 'o'},
                     lab={'WT': 'WT', 'Lo': 'Pten KO Lo', 'Hi': 'Pten KO Hi'}, fn='fig28_layer_profile_lohi',
                     title='Theta CSD by layer: WT, Pten KO Lo and Pten KO Hi'),
          'IED': dict(groups=['WT', 'IED-', 'IED+'], col={'WT': '#2a78d6', 'IED-': '#008300', 'IED+': '#e34948'}, mk={'WT': 'o', 'IED-': 'o', 'IED+': 'D'},
                      lab={'WT': 'WT', 'IED-': 'KO, no IEDs', 'IED+': 'KO, IEDs'}, fn='fig29_layer_profile_ied',
                      title='Theta CSD by layer: WT, KO without IEDs and KO with IEDs')}


def gee(col, v):
    x = m.dropna(subset=[v]).copy(); x['cell'] = x[col] + '|' + x.Estimate; ref = 'WT|HIL'
    x['cell'] = pd.Categorical(x.cell, [ref] + sorted(q for q in x.cell.unique() if q != ref))
    f = smf.gee(f'{v} ~ C(cell)', groups='mouse', data=x, cov_struct=sm.cov_struct.Exchangeable(), family=sm.families.Gaussian()).fit()
    p = {k.split('[T.')[1][:-1]: f.pvalues[k] for k in f.params.index if k.startswith('C(cell)')}
    ks = list(p); ph = multipletests([p[k] for k in ks], method='holm')[1]
    return p, dict(zip(ks, ph))


rows_gee, rows_mean = [], []
RES = {}
for key, S in SPLITS.items():
    R = {v: gee(key, v) for v in ['base', 'cno', 'chg']}; RES[key] = R
    for v in R:
        for cell, p in R[v][0].items():
            g, L = cell.split('|'); rows_gee.append(dict(split=key, panel=v, group=g, layer=L, p=p, p_holm=R[v][1][cell]))
    for g in S['groups']:
        for L in LAY:
            q = m[(m[key] == g) & (m.Estimate == L)]
            rows_mean.append(dict(split=key, group=g, layer=L, n_base=q.base.notna().sum(), base=q.base.mean(), base_se=q.base.sem(),
                                  n_cno=q.cno.notna().sum(), cno=q.cno.mean(), cno_se=q.cno.sem(), chg=q.chg.mean(), chg_se=q.chg.sem()))
G = pd.DataFrame(rows_gee); M = pd.DataFrame(rows_mean)
G.to_csv(os.path.join(WORK, 'csd3', 'layers_gee.csv'), index=False); M.to_csv(os.path.join(WORK, 'csd3', 'layers_means.csv'), index=False)

if __name__ == '__main__':
    for key, S in SPLITS.items():
        print(f'\n######## {S["title"]}')
        print('mice:', {g: sorted(int(i) for i in m[m[key] == g].mouse.unique()) for g in S['groups']})
        print(M[M.split == key].pivot(index='layer', columns='group', values=['base', 'cno', 'chg']).reindex(LAY).round(4).to_string())
        for v in ['base', 'cno', 'chg']:
            t = G[(G.split == key) & (G.panel == v)]
            print(f'  GEE p vs WT hilus [{v}]')
            for g in S['groups']:
                tt = t[t.group == g].set_index('layer')
                print('    ', g, ' '.join(f"{LAB[L]}:{tt.p[L]:.3f}{'†' if tt.p_holm[L] < 0.05 else ''}" for L in LAY if L in tt.index))
        for L in ['DG GCL2', 'DG MML2']:
            w = m[(m.Estimate == L) & (m[key] == 'WT')]
            for g in S['groups'][1:]:
                q = m[(m.Estimate == L) & (m[key] == g)]; qb = q.dropna(subset=['base', 'cno'])
                ex0 = q.base.mean() - w.base.mean(); ex1 = q.cno.mean() - w.cno.mean()
                print(f'  {g:4s} {LAB[L]}: {q.base.mean():.4f} -> {q.cno.mean():.4f}  paired p={stats.ttest_rel(qb.cno, qb.base).pvalue:.3f} | '
                      f'MW vs WT baseline p={stats.mannwhitneyu(q.base.dropna(), w.base.dropna()).pvalue:.3f}, after CNO p={stats.mannwhitneyu(q.cno.dropna(), w.cno.dropna()).pvalue:.3f} | '
                      f'excess over WT {ex0:+.4f} -> {ex1:+.4f} ({100 * (1 - ex1 / ex0):.0f}% removed)')
            a = m[(m.Estimate == L) & (m[key] == S['groups'][1])]; b = m[(m.Estimate == L) & (m[key] == S['groups'][2])]
            print(f'  {LAB[L]} {S["groups"][2]} vs {S["groups"][1]}: baseline p={stats.mannwhitneyu(b.base, a.base).pvalue:.3f}, CNO p={stats.mannwhitneyu(b.cno, a.cno).pvalue:.3f}, change p={stats.mannwhitneyu(b.chg.dropna(), a.chg.dropna()).pvalue:.3f}')

    # ---------- figures: layers top to bottom, CSD on x
    for key, S in SPLITS.items():
        R = RES[key]
        fig, axs = plt.subplots(1, 3, figsize=(8.2, 4.8), sharey=True)
        ypos = {L: i for i, L in enumerate(LAY)}
        for ax, (v, t) in zip(axs, [('base', 'Baseline'), ('cno', 'After CNO'), ('chg', 'CNO − baseline')]):
            x = m.dropna(subset=[v]); refv = x[(x[key] == 'WT') & (x.Estimate == 'HIL')][v].mean()
            for gi, g in enumerate(S['groups']):
                q = x[x[key] == g].groupby('Estimate')[v]; mu = q.mean().reindex(LAY); se = q.sem().reindex(LAY)
                ys = np.arange(len(LAY)) + (gi - 1) * 0.14
                ax.errorbar(mu, ys, xerr=se, color=S['col'][g], marker=S['mk'][g], ms=5.2, lw=2, capsize=2.3, mec='#fcfcfb', mew=0.7,
                            label=f"{S['lab'][g]} (n={x[x[key] == g].mouse.nunique()})", zorder=3)
                for i, L in enumerate(LAY):
                    k = f'{g}|{L}'
                    if k in R[v][0] and R[v][0][k] < 0.05:
                        right = mu[L] >= refv; xx = mu[L] + se[L] if right else mu[L] - se[L]
                        ax.text(xx + (0.0007 if right else -0.0007), ys[i], '**' if R[v][1][k] < 0.05 else '*', ha='left' if right else 'right',
                                va='center', fontsize=9.5, color=S['col'][g], fontweight='bold', zorder=6,
                                bbox=dict(facecolor='#fcfcfb', edgecolor='none', pad=0.2, alpha=0.9))
            hi = LAY.index('HIL'); ax.axhspan(hi - 0.42, hi + 0.42, color='#e9e8e3', alpha=0.75, zorder=0, lw=0)
            if v == 'chg': ax.axvline(0, color='#9a9993', lw=0.9)
            ax.set_ylim(len(LAY) - 0.5, -0.5)
            ax.set_title(t, fontsize=10, color=INK, fontweight='bold', loc='left', pad=8)
            ax.set_xlabel('Theta CSD' if v != 'chg' else 'CNO − baseline', fontsize=8)
        axs[0].set_yticks(range(len(LAY))); axs[0].set_yticklabels([LAB[L] for L in LAY], fontsize=8.5)
        axs[0].set_xlim(0, 0.08); axs[1].set_xlim(0, 0.08); axs[2].set_xlim(-0.03, 0.025)
        h, l = axs[0].get_legend_handles_labels()
        fig.legend(h, l, loc='upper left', bbox_to_anchor=(0.01, 0.945), ncol=3, fontsize=7.8, handletextpad=0.3, columnspacing=1.2)
        fig.suptitle(S['title'], x=.01, ha='left', fontsize=12, fontweight='bold', color=INK, y=.99)
        fig.text(0.5, 0.012, 'Mean ± SE across mice (each mouse = mean of its channels in that layer). Shaded row: WT hilus, the reference.\n'
                 '* p < 0.05 vs WT hilus (GEE, clustered by mouse); ** also after Holm correction within the panel. M26 excluded.',
                 ha='center', fontsize=7.2, color=MUT)
        fig.tight_layout(rect=(0, 0.07, 1, 0.94)); fig.savefig(os.path.join(FIGS, S['fn'] + '.png'), dpi=200); plt.close()
    print('figures written')
