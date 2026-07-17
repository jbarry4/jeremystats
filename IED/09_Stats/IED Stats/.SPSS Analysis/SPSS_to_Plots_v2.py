"""
v2: Vertical anatomical depth-profile plots comparing GZ (Initiation Phase) vs
AS (Propagation Phase), for each metric category (Voltage/CSD x Raw/Normalized),
reading from 'SPSS Plotting Values Output.xlsx'.

Fixes vs v1 (SPSS_to_Plots.py):
  - Axis limits/ticks are derived from each category's actual data range
    instead of being forced to span +/-1000 with 500-unit ticks. That forcing
    is what crushed the Normalized CSD/Voltage plots (values ~0.3-0.7) into an
    unreadable sliver near zero.
  - Significance stars are computed automatically per region (two-tailed Wald
    z-test of GZ vs AS using the Mean/SE already in the workbook) instead of a
    hardcoded region list. NOTE: this treats GZ and AS as independent samples
    using the marginal SEs from the Excel export, so it's an approximation --
    it may disagree slightly with a true paired/contrast p-value computed
    inside SPSS from the full covariance matrix. Swap in real contrast
    p-values here if/when they're exported (see compute_significance).
  - Base and CNO are drawn as two panels of one shared-x-axis figure per
    metric category, so the two groups are directly comparable at a glance.
"""

import os
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ================= CONFIGURATION =================
INPUT_FILE = 'SPSS Plotting Values Output.xlsx'
OUTPUT_DIR = 'SPSS_Graphs_v2'

REGION_ORDER = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]
GROUP_ORDER = ['Base', 'CNO']

PALETTE = {'GZ': '#C00000', 'AS': '#E57373'}
LABELS = {'GZ': 'Initiation Phase', 'AS': 'Propagation Phase'}

SIG_ALPHA = 0.05
AXIS_PAD_FRAC = 0.12
# =================================================


def normal_two_tailed_p(z):
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2))))


def stars_for_p(p):
    if p < 0.001:
        return '***'
    if p < 0.01:
        return '**'
    if p < SIG_ALPHA:
        return '*'
    return ''


def sheet_category(sheet_name):
    upper = sheet_name.upper()
    metric = 'Voltage' if 'VOLTAGE' in upper else 'CSD'
    is_normalized = 'NORMALIZED' in upper
    return metric, is_normalized


def load_sheet(xls, sheet_name):
    df = pd.read_excel(xls, sheet_name=sheet_name, header=1)
    if df.shape[1] < 5:
        return None
    df = df.iloc[:, [0, 1, 2, 3, 4]].copy()
    df.columns = ['Group', 'TimeFrame', 'Region', 'Mean', 'SE']

    df = df[pd.to_numeric(df['Mean'], errors='coerce').notna()].copy()
    if df.empty:
        return None
    df['Group'] = df['Group'].ffill()
    df['TimeFrame'] = df['TimeFrame'].ffill()
    df['Mean'] = df['Mean'].astype(float)
    df['SE'] = df['SE'].astype(float)

    df = df[df['Region'].isin(REGION_ORDER)].copy()
    if df.empty:
        return None
    df['Region'] = pd.Categorical(df['Region'], categories=REGION_ORDER, ordered=True)
    return df.sort_values(['Group', 'TimeFrame', 'Region'])


def compute_significance(df, group):
    """Two-tailed Wald z-test of GZ vs AS mean, per region, within one Group."""
    sig = {}
    gdf = df[df['Group'] == group]
    for region in REGION_ORDER:
        reg = gdf[gdf['Region'] == region]
        gz = reg[reg['TimeFrame'] == 'GZ']
        as_ = reg[reg['TimeFrame'] == 'AS']
        if gz.empty or as_.empty:
            continue
        m1, se1 = gz.iloc[0]['Mean'], gz.iloc[0]['SE']
        m2, se2 = as_.iloc[0]['Mean'], as_.iloc[0]['SE']
        se_diff = math.sqrt(se1 ** 2 + se2 ** 2)
        if se_diff == 0:
            continue
        z = (m1 - m2) / se_diff
        p = normal_two_tailed_p(z)
        sig[region] = (p, stars_for_p(p))
    return sig


def nice_xlim(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        span = max(abs(hi), 1.0)
    pad = span * AXIS_PAD_FRAC
    return lo - pad, hi + pad


def draw_significance_bracket(ax, y_pos, x1, x2, stars):
    start, end = min(x1, x2), max(x1, x2)
    y_line = y_pos - 0.16
    y_tick = y_pos - 0.10
    ax.plot([start, end], [y_line, y_line], color='black', lw=1)
    ax.plot([start, start], [y_line, y_tick], color='black', lw=1)
    ax.plot([end, end], [y_line, y_tick], color='black', lw=1)
    ax.text((start + end) / 2, y_line - 0.06, stars, ha='center', va='bottom',
            fontsize=15, fontweight='bold', color='black')


def plot_category(metric, is_normalized, df):
    region_index = {r: i for i, r in enumerate(REGION_ORDER)}
    groups_present = [g for g in GROUP_ORDER if g in df['Group'].unique()]
    if not groups_present:
        return

    all_vals = []
    for _, row in df.iterrows():
        all_vals.append(row['Mean'] - row['SE'])
        all_vals.append(row['Mean'] + row['SE'])
    x_min, x_max = nice_xlim(all_vals)

    if metric == 'Voltage':
        x_label = 'Normalized Voltage' if is_normalized else r'Voltage ($\mu$V)'
    else:
        x_label = 'Normalized CSD' if is_normalized else 'CSD Units'

    fig, axes = plt.subplots(1, len(groups_present), figsize=(6.5 * len(groups_present), 9),
                              sharey=True)
    if len(groups_present) == 1:
        axes = [axes]

    for ax, group in zip(axes, groups_present):
        gdf = df[df['Group'] == group]
        sig = compute_significance(df, group)

        for tf in ['GZ', 'AS']:
            tdf = gdf[gdf['TimeFrame'] == tf]
            if tdf.empty:
                continue
            y_vals = [region_index[r] for r in tdf['Region']]
            ax.errorbar(tdf['Mean'], y_vals, xerr=tdf['SE'], fmt='-o',
                        color=PALETTE[tf], label=LABELS[tf],
                        linewidth=2.5, markersize=8, capsize=5)

        for region, (p, stars) in sig.items():
            if not stars:
                continue
            reg = gdf[gdf['Region'] == region]
            gz_row = reg[reg['TimeFrame'] == 'GZ']
            as_row = reg[reg['TimeFrame'] == 'AS']
            if gz_row.empty or as_row.empty:
                continue
            draw_significance_bracket(ax, region_index[region],
                                       gz_row.iloc[0]['Mean'], as_row.iloc[0]['Mean'], stars)

        ax.set_xlim(x_min, x_max)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6))
        ax.grid(axis='x', linestyle='--', alpha=0.3)
        ax.set_title(group, fontsize=14)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(axis='both', direction='in', length=6, width=1)
        ax.set_xlabel(x_label, fontsize=11)

    axes[0].invert_yaxis()
    axes[0].set_yticks(range(len(REGION_ORDER)))
    axes[0].set_yticklabels(REGION_ORDER, fontsize=11)
    axes[0].set_ylabel('Anatomical Region', fontsize=12)
    axes[-1].legend(title='Time Frame', frameon=False, loc='best')

    metric_title = f'{metric} Depth Profile' + (' [Normalized]' if is_normalized else '')
    fig.suptitle(metric_title, fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    fname = f'{metric}{"_Normalized" if is_normalized else ""}_DepthProfile'
    fig.savefig(os.path.join(OUTPUT_DIR, fname + '.png'), dpi=300)
    fig.savefig(os.path.join(OUTPUT_DIR, fname + '.pdf'))
    plt.close(fig)
    print(f'Saved {fname}')


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    xls = pd.ExcelFile(INPUT_FILE)
    print(f'Found sheets: {xls.sheet_names}')

    by_category = {}
    for sheet in xls.sheet_names:
        df = load_sheet(xls, sheet)
        if df is None:
            continue
        by_category[sheet_category(sheet)] = df

    for (metric, is_normalized), df in by_category.items():
        print(f'\nPlotting {metric}{" [Normalized]" if is_normalized else ""} ...')
        plot_category(metric, is_normalized, df)

        for group in GROUP_ORDER:
            if group not in df['Group'].unique():
                continue
            sig = compute_significance(df, group)
            for region in REGION_ORDER:
                if region in sig and sig[region][1]:
                    p, stars = sig[region]
                    print(f'    {group} / {region}: p={p:.4f} {stars}')

    print('\nAll categories processed.')


if __name__ == '__main__':
    main()
