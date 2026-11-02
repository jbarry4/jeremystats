"""
plot_strategy_trend.py - per-trial strategy measures for one or more mice, as in Figure 9 (bottom):

  E  shocks per trial
  F  strategy score per trial  = OPP / (OPP + CW)
  G  mean direction per trial  = circular mean of the angle from the shock-sector centre

Mouse and trial numbers are read from the file names (e.g. 933_13_RoomTrack_Room_*.dat).
Writes a CSV of all per-trial measures and a PNG.

Usage
  python plot_strategy_trend.py data/964_*.dat data/933_*.dat -o trend.png --csv trend.csv \
      --labels 964="964 Sham learner" 933="933 TBI non-learner" --highlight 964=1,15 933=7,13
"""
import argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from metrics import trial_metrics, unwrap_for_plot
from tracker_io import parse_name

PALETTE = ['#1baf7a', '#eb6834', '#2a78d6', '#4a3aa7', '#eda100', '#e87ba4']
MARKERS = ['D', 's', 'o', '^', 'v', 'P']
N_TRIALS, DAY_SPLIT = 16, 8.5          # 2 days x 8 trials


def collect(files, halves=False):
    rows = [trial_metrics(f, halves=halves) for f in files]
    return pd.DataFrame(rows).sort_values(['mouse', 'trial']).reset_index(drop=True)


def plot_trend(df, out, labels=None, highlight=None, order=None, width=23.2, height=6.2):
    """order: mouse numbers in legend/colour order (default: order of --labels, else first appearance)."""
    labels, highlight = labels or {}, highlight or {}
    mice = list(order) if order else (list(labels) if labels else list(dict.fromkeys(df.mouse)))
    fig, axs = plt.subplots(1, 3, figsize=(width, height))

    def draw(ax, ycol, f=lambda y: y):
        for k, m in enumerate(mice):
            g = df[df.mouse == m].sort_values('trial'); x = g.trial.values; y = f(g[ycol].values)
            c, mk = PALETTE[k % len(PALETTE)], MARKERS[k % len(MARKERS)]
            labelled = False
            for seg in (x <= 8, x >= 9):                                  # break the line between days
                if seg.any():
                    ax.plot(x[seg], y[seg], color=c, lw=2.4, marker=mk, ms=7, mec='white',
                            label=None if labelled else labels.get(m, str(m)))
                    labelled = True
            if m in highlight:
                sel = np.isin(x, highlight[m])
                ax.scatter(x[sel], y[sel], s=260, facecolor='none', edgecolor=c, lw=2, zorder=5)

    draw(axs[0], 'shocks'); axs[0].set_ylabel('Shocks per trial', fontsize=12)
    axs[0].set_title('E  Shocks per trial', loc='left', fontsize=13)
    draw(axs[1], 'strategy_score', lambda y: 100 * y)
    axs[1].axhline(50, color='#6b6b6b', lw=.9, ls=':'); axs[1].set_ylim(10, 100)
    axs[1].set_ylabel('Opposite / (Opposite + CW) (%)', fontsize=12)
    axs[1].set_title('F  Strategy score per trial', loc='left', fontsize=13)
    draw(axs[2], 'mean_direction', unwrap_for_plot)
    ax = axs[2]; ax.set_ylim(-280, -70)
    for lo, hi, lab, c in [(-120, -60, 'CW', '#b37700'), (-210, -150, 'Opposite', '#1baf7a'), (-300, -240, 'CCW', '#2a78d6')]:
        ax.axhspan(lo, hi, color=c, alpha=.1)
        ax.text(N_TRIALS + .7, (lo + hi) / 2 if lab != 'CW' else -95, lab, fontsize=11, color=c, va='center')
    ax.set_yticks([-270, -225, -180, -135, -90])
    ax.set_yticklabels(['+90° (CCW)', '+135°', '±180° (Opp)', '−135°', '−90° (CW)'])
    ax.set_ylabel('Mean direction from shock-sector centre (°)', fontsize=12)
    ax.set_title('G  Mean direction per trial', loc='left', fontsize=13)
    for ax in axs:
        ax.axvline(DAY_SPLIT, color='#6b6b6b', ls='--', lw=.9)
        ax.set_xticks(range(1, N_TRIALS + 1)); ax.set_xticklabels([f'T{i}' for i in range(1, N_TRIALS + 1)], fontsize=9.5)
        ax.set_xlim(.5, N_TRIALS + 2.3 if ax is axs[2] else N_TRIALS + .5)
        for s in ['top', 'right']: ax.spines[s].set_visible(False)
        ax.grid(color='#eeeeee', lw=.6)
    axs[0].legend(frameon=False, fontsize=11, loc='upper right')
    note = 'Dashed line = Day 1 / Day 2. Rotation carries CCW → Opposite → CW → shock sector.'
    if highlight: note = 'Open circles = highlighted trials. ' + note
    fig.text(0.008, 0.015, note, fontsize=10.5, color='#6b6b6b')
    fig.tight_layout(rect=(0, .04, 1, 1)); fig.savefig(out, dpi=170); plt.close(fig)
    return out


def _kv(items, conv):
    out = {}
    for it in items or []:
        k, v = it.split('=', 1); out[int(k)] = conv(v)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+', help='Tracker .dat files (any number of mice and trials)')
    ap.add_argument('-o', '--out', default='strategy_trend.png')
    ap.add_argument('--csv', default='strategy_trend.csv', help='per-trial measures')
    ap.add_argument('--labels', nargs='*', help='MOUSE="legend label" pairs')
    ap.add_argument('--highlight', nargs='*', help='MOUSE=trial,trial pairs to circle')
    ap.add_argument('--halves', action='store_true', help='also compute measures for each 5-min half')
    a = ap.parse_args()
    df = collect(a.files, halves=a.halves)
    df.to_csv(a.csv, index=False); print('wrote', a.csv)
    labels = _kv(a.labels, str)
    order = list(labels) or list(dict.fromkeys(parse_name(f)[0] for f in a.files))
    print('wrote', plot_trend(df, a.out, labels, _kv(a.highlight, lambda v: [int(t) for t in v.split(',')]), order))
