"""
v3: Vertical anatomical depth-profile plots comparing Base vs CNO, for each
metric category (Voltage/CSD x Raw/Normalized), reading from
'SPSS Plotting Values Output.xlsx'.

This is the "other axis" of v2 (SPSS_to_Plots_v2.py): v2 held Group fixed per
panel and compared TimeFrame (GZ vs AS) within it; v3 holds TimeFrame fixed
per panel (Initiation Phase / Propagation Phase) and compares Group (Base vs
CNO) within it -- i.e. Base-Initiation vs CNO-Initiation, and
Base-Propagation vs CNO-Propagation, each as their own panel.

Significance stars use the same two-tailed Wald z-test approach as v2 (see
that file's docstring for the independent-samples caveat), just applied
across Group instead of across TimeFrame.

Colors are deliberately a blue/orange pair (not the red family v2 uses) so
the two chart variants -- "phase comparison" vs "drug comparison" -- are
distinguishable at a glance.
"""

import os
import math
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ================= CONFIGURATION =================
INPUT_FILE = 'SPSS Plotting Values Output.xlsx'
OUTPUT_DIR = 'SPSS_Graphs_v3'

REGION_ORDER = [
    'CA1 SLM', 'DG OML1', 'DG MML1', 'DG GCL1', 'HIL', 'DG GCL2', 'DG MML2', 'DG OML2'
]
TIMEFRAME_ORDER = ['GZ', 'AS']

PALETTE = {'Base': '#2a78d6', 'CNO': '#eb6834'}
TF_LABELS = {'GZ': 'Initiation Phase', 'AS': 'Propagation Phase'}

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


def compute_significance(df, timeframe):
    """Two-tailed Wald z-test of Base vs CNO mean, per region, within one TimeFrame."""
    sig = {}
    tdf = df[df['TimeFrame'] == timeframe]
    for region in REGION_ORDER:
        reg = tdf[tdf['Region'] == region]
        base = reg[reg['Group'] == 'Base']
        cno = reg[reg['Group'] == 'CNO']
        if base.empty or cno.empty:
            continue
        m1, se1 = base.iloc[0]['Mean'], base.iloc[0]['SE']
        m2, se2 = cno.iloc[0]['Mean'], cno.iloc[0]['SE']
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
    tf_present = [tf for tf in TIMEFRAME_ORDER if tf in df['TimeFrame'].unique()]
    if not tf_present:
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

    fig, axes = plt.subplots(1, len(tf_present), figsize=(6.5 * len(tf_present), 9),
                              sharey=True)
    if len(tf_present) == 1:
        axes = [axes]

    for ax, tf in zip(axes, tf_present):
        tdf = df[df['TimeFrame'] == tf]
        sig = compute_significance(df, tf)

        for group in ['Base', 'CNO']:
            gdf = tdf[tdf['Group'] == group]
            if gdf.empty:
                continue
            y_vals = [region_index[r] for r in gdf['Region']]
            ax.errorbar(gdf['Mean'], y_vals, xerr=gdf['SE'], fmt='-o',
                        color=PALETTE[group], label=group,
                        linewidth=2.5, markersize=8, capsize=5)

        for region, (p, stars) in sig.items():
            if not stars:
                continue
            reg = tdf[tdf['Region'] == region]
            base_row = reg[reg['Group'] == 'Base']
            cno_row = reg[reg['Group'] == 'CNO']
            if base_row.empty or cno_row.empty:
                continue
            draw_significance_bracket(ax, region_index[region],
                                       base_row.iloc[0]['Mean'], cno_row.iloc[0]['Mean'], stars)

        ax.set_xlim(x_min, x_max)
        ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=6))
        ax.grid(axis='x', linestyle='--', alpha=0.3)
        ax.set_title(TF_LABELS.get(tf, tf), fontsize=14)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(axis='both', direction='in', length=6, width=1)
        ax.set_xlabel(x_label, fontsize=11)

    axes[0].invert_yaxis()
    axes[0].set_yticks(range(len(REGION_ORDER)))
    axes[0].set_yticklabels(REGION_ORDER, fontsize=11)
    axes[0].set_ylabel('Anatomical Region', fontsize=12)
    axes[-1].legend(title='Group', frameon=False, loc='best')

    metric_title = f'{metric} Depth Profile: Base vs CNO' + (' [Normalized]' if is_normalized else '')
    fig.suptitle(metric_title, fontsize=16)
    fig.tight_layout(rect=[0, 0, 1, 0.95])

    fname = f'{metric}{"_Normalized" if is_normalized else ""}_BaseVsCNO'
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
        print(f'\nPlotting {metric}{" [Normalized]" if is_normalized else ""} (Base vs CNO) ...')
        plot_category(metric, is_normalized, df)

        for tf in TIMEFRAME_ORDER:
            if tf not in df['TimeFrame'].unique():
                continue
            sig = compute_significance(df, tf)
            for region in REGION_ORDER:
                if region in sig and sig[region][1]:
                    p, stars = sig[region]
                    print(f'    {TF_LABELS.get(tf, tf)} / {region}: p={p:.4f} {stars}')

    print('\nAll categories processed.')


if __name__ == '__main__':
    main()
