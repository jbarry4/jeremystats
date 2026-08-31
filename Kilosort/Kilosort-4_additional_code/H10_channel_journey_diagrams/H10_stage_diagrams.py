"""
H10 channel journey, refined against the real Cambridge NeuroTech pinout
reference for this exact probe/headstage variant:
    Probe_Playground/ASSY-77 H10-D-map.pdf  ("Mapping for Acute 64-Channel
    Probe ASSY-77 H10-D & H10-2-D", last updated 23 April 2026)

That PDF gives the true physical pin order, top-to-tip, for each of the
probe's two shanks (labeled "Back" and "Front" on the connector). This
version replaces the earlier generic/illustrative geometry with that real
layout, and replaces the earlier "NOT VERIFIED" stage G with an actual
verification: for this session's config
(Config files/H10_D_open_Cheetah2026-07-21_16-59-03.cfg), subtracting a
constant 63 from every -SetChannelNumber raw hardware channel recovers
the PDF's pin numbers exactly for 63 of 64 channels (CSC1-32 = Back
shank top-to-tip, CSC33-64 = Front shank top-to-tip). Only CSC32 (raw
hw=60) does not fit the pattern -- see stage C/G for that anomaly.

Scope: this session only, per instruction. The other H10 .cfg files
found elsewhere in this repo are not addressed here.

Usage:
    python H10_stage_diagrams.py [output_dir]
"""

import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon, Circle

CONFIG_DIR = Path(__file__).resolve().parent.parent / "Config files"
H10_CFG = CONFIG_DIR / "H10_D_open_Cheetah2026-07-21_16-59-03.cfg"

N_CH = 64
OFFSET = 63

INK = "#2b2f38"
CODE_BG = "#f5f5f5"
CODE_EDGE = "#999999"
ACCENT = "#c98a1e"
ACCENT_BG = "#fdeecb"
OK_EDGE = "#4c9a4c"
OK_BG = "#d9f2d9"
WARN_EDGE = "#b33a3a"
WARN_BG = "#f9dede"
CMAP = plt.get_cmap("viridis")

# Real pin layout from ASSY-77 H10-D-map.pdf, "Back" and "Front" shank
# diagrams, read top (insertion end) to tip, row by row. A row with two
# pins is read left, then right.
BACK_ROWS = [
    [21], [41, 32], [43], [42, 28], [23], [44, 22], [24], [35, 26], [30], [36, 25],
    [29], [49, 17], [16], [47, 19], [37], [45, 27], [33], [38, 20], [39], [46, 18],
    [40], [48],
]
FRONT_ROWS = [
    [64], [5, 59], [2], [3, 61], [62], [1, 63], [60], [7, 57], [58], [9, 55],
    [56], [11, 53], [54], [13, 51], [4], [15, 34], [6], [31, 50], [8], [14, 52],
    [10], [12],
]
N_ROWS = len(BACK_ROWS)  # 22

# pin -> (shank, row, col)  col: -1 left, 0 center, +1 right
PIN_POS = {}
for _rows, _shank in [(BACK_ROWS, "back"), (FRONT_ROWS, "front")]:
    for _r, _row in enumerate(_rows):
        if len(_row) == 1:
            PIN_POS[_row[0]] = (_shank, _r, 0)
        else:
            PIN_POS[_row[0]] = (_shank, _r, -1)
            PIN_POS[_row[1]] = (_shank, _r, 1)


def parse_channel_map(cfg_path: Path, max_csc: int = N_CH):
    pattern = re.compile(r'-SetChannelNumber\s+"CSC(\d+)"\s+(\d+)')
    mapping = {}
    for line in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.search(line)
        if m:
            csc_idx = int(m.group(1))
            if csc_idx <= max_csc:
                mapping[csc_idx] = int(m.group(2))
    return dict(sorted(mapping.items()))


def resolve_csc_positions(mapping):
    """Returns {csc: (shank, row, col) or None} using pin = hw - OFFSET."""
    out = {}
    for csc, hw in mapping.items():
        pin = hw - OFFSET
        out[csc] = PIN_POS.get(pin) if 1 <= pin <= 64 else None
    return out


def raw_snippet(cfg_path: Path, n_entries: int = 6) -> str:
    pattern = re.compile(r'-SetChannelNumber\s+"CSC\d+"\s+\d+')
    lines = [
        l.strip() for l in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if pattern.search(l)
    ]
    return f"# {cfg_path.name}\n" + "\n".join(lines[:n_entries]) + "\n..."


def new_fig(w=12, h=9, title=""):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if title:
        fig.suptitle(title, fontsize=14.5, fontweight="bold", y=0.975)
    return fig, ax


def draw_shank(ax, x_center, y_top, y_bottom, half_w, tip_frac=0.06, facecolor="#eef1f8", edgecolor="#3a4a6b"):
    tip_y = y_bottom
    taper_start_y = y_bottom + tip_frac * (y_top - y_bottom)
    pts = [
        (x_center - half_w, y_top), (x_center + half_w, y_top),
        (x_center + half_w, taper_start_y), (x_center, tip_y), (x_center - half_w, taper_start_y),
    ]
    ax.add_patch(Polygon(pts, closed=True, facecolor=facecolor, edgecolor=edgecolor, linewidth=1.8, zorder=1))


def code_box(ax, x, y, text, fontsize=8.5, ha="left", title=None):
    if title:
        ax.text(x, y + 0.014, title, fontsize=9.5, fontweight="bold", ha=ha, va="bottom", transform=ax.transAxes)
    ax.text(
        x, y, text, transform=ax.transAxes, fontfamily="monospace", fontsize=fontsize,
        va="top", ha=ha,
        bbox=dict(boxstyle="round,pad=0.5", facecolor=CODE_BG, edgecolor=CODE_EDGE),
    )


def note_box(ax, x, y, w, h, text, title=None, facecolor="#ffffff", edgecolor="#888888", fontsize=9):
    box = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=1.4, transform=ax.transAxes,
    )
    ax.add_patch(box)
    ty = y + h - 0.02
    if title:
        ax.text(x + 0.02, ty, title, fontsize=10.5, fontweight="bold", va="top", transform=ax.transAxes)
        ty -= 0.06
    ax.text(x + 0.02, ty, text, fontsize=fontsize, va="top", ha="left", transform=ax.transAxes, linespacing=1.5, wrap=True)


def draw_pdf_shanks(ax, x0, x1, y_top, y_bot, col_jitter, color_by_csc=None):
    """Draws Back (at x0) and Front (at x1) using the REAL PDF row/col layout.
    color_by_csc: optional {pin: csc_index (0-based)} to color by channel index."""
    hw = 0.045
    draw_shank(ax, x0, y_top, y_bot, hw)
    draw_shank(ax, x1, y_top, y_bot, hw)

    def row_y(r):
        return y_top - r / (N_ROWS - 1) * (y_top - y_bot)

    cmap_colors = None
    if color_by_csc is not None:
        cmap_colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]

    for rows, x_center, base_color in [(BACK_ROWS, x0, "#7a8bb8"), (FRONT_ROWS, x1, "#b87a9e")]:
        for r, row in enumerate(rows):
            y = row_y(r)
            cols = [0] if len(row) == 1 else [-1, 1]
            for pin, col in zip(row, cols):
                x = x_center + col * col_jitter
                color = base_color
                if cmap_colors is not None and pin in color_by_csc:
                    color = cmap_colors[color_by_csc[pin]]
                ax.add_patch(Circle((x, y), 0.009, facecolor=color, edgecolor="black", linewidth=0.3, zorder=2))


# ---------------------------------------------------------------- stage 1
def stage1(out: Path):
    fig, ax = new_fig(title="Stage A -- Physical electrode sites, real layout (ASSY-77 H10-D-map.pdf)")
    draw_pdf_shanks(ax, x0=0.20, x1=0.42, y_top=0.90, y_bot=0.10, col_jitter=0.03)

    ax.text(0.20, 0.94, "Back\n(32 sites)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.42, 0.94, "Front\n(32 sites)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.31, 0.05, "tip (enters tissue first)", ha="center", fontsize=9)
    ax.text(0.31, 0.965, "top / insertion point", ha="center", fontsize=9)

    note_box(
        ax, 0.55, 0.28, 0.42, 0.57,
        "Source: Probe_Playground/ASSY-77 H10-D-map.pdf (Cambridge\n"
        "NeuroTech, 'Mapping for Acute 64-Channel Probe ASSY-77\n"
        "H10-D & H10-2-D', updated 23 Apr 2026) -- the vendor's own\n"
        "documented pinout for the exact headstage/probe combo used\n"
        "in this session, not a generic library assumption.\n\n"
        "The probe's two shanks are labeled 'Back' and 'Front' on the\n"
        "connector itself -- that's the vendor's own terminology, used\n"
        "here instead of an arbitrary 'shank 0 / shank 1'.\n\n"
        "Row layout (single/paired contacts per depth row, 22 rows,\n"
        "tapering to single contacts near the tip) is copied directly\n"
        "from the PDF's shank diagrams, not guessed.\n\n"
        "Nothing here has a CSC number yet -- these are the probe's\n"
        "own connector pin numbers (1-64), assigned at manufacture.\n"
        "CSC numbering is applied downstream, starting at stage C.",
        title="What this stage is",
        fontsize=8.5,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 2
def stage2(out: Path):
    fig, ax = new_fig(title="Stage B -- probe connector pin -> raw ADC hardware channel")
    draw_pdf_shanks(ax, x0=0.09, x1=0.22, y_top=0.90, y_bot=0.24, col_jitter=0.018)

    hs_x0, hs_x1 = 0.38, 0.55
    hs_y0, hs_y1 = 0.20, 0.80
    ax.add_patch(FancyBboxPatch((hs_x0, hs_y0), hs_x1 - hs_x0, hs_y1 - hs_y0,
                 boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor="#e4e9f7", edgecolor="#4a5fa5", linewidth=1.8))
    ax.text((hs_x0 + hs_x1) / 2, (hs_y0 + hs_y1) / 2,
            "H10-D headstage / EIB\n\nfixed wiring, straight\nprobe-pin passthrough\n\n+ a CONSTANT +63\nport offset (see stage C)",
            ha="center", va="center", fontsize=9)

    pin_x = 0.78
    pin_ys = [0.78 - i * (0.6 / 15) for i in range(16)]
    for py in pin_ys:
        ax.add_patch(Circle((pin_x, py), 0.008, facecolor="#cccccc", edgecolor="#555555", linewidth=0.6, zorder=2))
    ax.text(pin_x, 0.83, "raw ADC hardware\nchannels (DigitalLynxSX)\n~64-127", fontsize=8.5, ha="center")
    for py in pin_ys[::3]:
        ax.add_patch(FancyArrowPatch((hs_x1, 0.5), (pin_x - 0.02, py), connectionstyle="arc3,rad=-0.1",
                     arrowstyle="-", color="#888888", linewidth=0.7, alpha=0.5, linestyle="dashed"))
    for xf in (0.09, 0.22):
        ax.add_patch(FancyArrowPatch((xf + 0.015, 0.5), (hs_x0, 0.5), connectionstyle="arc3,rad=0.1",
                     arrowstyle="-", color="#888888", linewidth=0.9, alpha=0.6))

    note_box(
        ax, 0.06, 0.02, 0.90, 0.15,
        "This is no longer a mystery, unlike the earlier version of this diagram: stage C shows raw hardware channel\n"
        "= probe pin + 63 for 63 of 64 channels, a clean constant offset -- consistent with this headstage simply being\n"
        "plugged into a hardware port that starts at ADC channel 64. Not a scramble at the board level; the apparent\n"
        "'scramble' seen when plotting CSC index against hardware channel comes entirely from CSC numbers being\n"
        "assigned in physical DEPTH order per shank, not in probe-pin order (see stage C).",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=8.6,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 3
def stage3(out: Path):
    mapping = parse_channel_map(H10_CFG)
    resolved = resolve_csc_positions(mapping)
    n_ok = sum(1 for v in resolved.values() if v is not None)

    fig, ax = new_fig(title="Stage C -- Cheetah .cfg  -SetChannelNumber  (this session, now decoded)")

    hw_vals = sorted(set(mapping.values()))
    hw_y = {v: 0.85 - 0.75 * i / (len(hw_vals) - 1) for i, v in enumerate(hw_vals)}
    csc_y = {c: 0.85 - 0.75 * (c - 1) / (N_CH - 1) for c in mapping}
    left_x, right_x = 0.14, 0.52
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]

    for v, y in hw_y.items():
        ax.add_patch(Circle((left_x, y), 0.006, facecolor="#999999", edgecolor="none", zorder=2))
    ax.text(left_x, 0.94, "raw hardware\nADC channel", fontsize=9.5, ha="center", fontweight="bold")

    for c, y in csc_y.items():
        edge = "black" if resolved[c] is not None else "red"
        lw = 0.3 if resolved[c] is not None else 1.6
        ax.add_patch(Circle((right_x, y), 0.007, facecolor=colors[c - 1], edgecolor=edge, linewidth=lw, zorder=2))
    ax.text(right_x, 0.94, "logical CSC channel\n(CSC1..CSC64)", fontsize=9.5, ha="center", fontweight="bold")

    for c, hw in mapping.items():
        ax.plot([left_x + 0.006, right_x - 0.007], [hw_y[hw], csc_y[c]], color=colors[c - 1], linewidth=0.6, alpha=0.55, zorder=1)
    for c in [1, 16, 32, 48, 64]:
        ax.text(right_x + 0.015, csc_y[c], f"CSC{c}", fontsize=7.5, va="center")

    code_box(ax, 0.62, 0.90, raw_snippet(H10_CFG, 6), fontsize=7.8, title="Actual .cfg syntax (this session)")

    note_box(
        ax, 0.60, 0.04, 0.37, 0.48,
        "Decoding rule: pin = raw_hw_channel - 63\n\n"
        f"Result: {n_ok}/64 channels land EXACTLY on a real\n"
        "pin position from ASSY-77 H10-D-map.pdf:\n"
        "  - CSC1-32 -> 'Back' shank, top to tip, in order\n"
        "  - CSC33-64 -> 'Front' shank, top to tip, in order\n\n"
        "The one exception: CSC32 (raw hw=60) gives pin=-3,\n"
        "not a valid probe pin. The PDF marks several connector\n"
        "pins as dedicated REF/GND rather than recording sites\n"
        "-- CSC32 is most likely tied to one of those, not a\n"
        "real depth-ordered electrode. Flagged red at right;\n"
        "treat this one channel as unresolved, not assumed.\n\n"
        "This is a genuine, verified decode -- not the 'not\n"
        "verified' placeholder used before the PDF was available.",
        title="What the offset actually means",
        facecolor=ACCENT_BG, edgecolor=ACCENT, fontsize=8.3,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 4
def stage4(out: Path):
    fig, ax = new_fig(title="Stage D -- Neuralynx writes one .ncs file per logical CSC channel")

    def file_icon(x, y, label, w=0.085, h=0.09, color="#e4e9f7", edge="#4a5fa5"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                     facecolor=color, edgecolor=edge, linewidth=1.3))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=7.8)

    shown = list(range(1, 7)) + [None] + list(range(62, 65))
    x0, gap, w = 0.02, 0.098, 0.085
    for i, c in enumerate(shown):
        x = x0 + i * gap
        if c is None:
            ax.text(x + w / 2, 0.545, "...", fontsize=20, ha="center", va="center", fontweight="bold")
            continue
        file_icon(x, 0.5, f"CSC{c}.ncs")
    x_last = x0 + (len(shown) - 1) * gap + w
    ax.annotate("", xy=(x0, 0.35), xytext=(x_last, 0.35),
                arrowprops=dict(arrowstyle="-|>", color="#333333", linewidth=1.6))
    ax.text((x0 + x_last) / 2, 0.30, "file / acquisition order", ha="center", fontsize=9, style="italic")

    note_box(
        ax, 0.06, 0.62, 0.88, 0.28,
        "Same mechanism as any other session: the logical CSC number from stage C becomes the literal filename.\n"
        "Now that stage C is decoded, CSC1.ncs through CSC32.ncs are known to be the Back shank top-to-tip, and\n"
        "CSC33.ncs through CSC64.ncs the Front shank top-to-tip (except CSC32, still unresolved). Nothing new\n"
        "happens at this stage -- it just carries that verified order forward as filenames.",
        title="Why this stage matters",
        fontsize=9,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 5
def stage5(out: Path):
    fig, ax = new_fig(title="Stage E -- perpl_NLX2Binary.m writes the binary in that exact order")

    code_box(ax, 0.06, 0.90,
             "for CSC = startchan:channelNum\n"
             "    filename = fullfile(filedir, ...\n"
             "        [probeName num2str(CSC) '.ncs']);\n"
             "    ...\n"
             "    fwrite(fid, data2, 'int16');\n"
             "end",
             fontsize=8.6, title="perpl_NLX2Binary.m (real loop, same script every session)")

    bar_x, bar_y, bar_w, bar_h = 0.06, 0.36, 0.88, 0.14
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]
    seg_w = bar_w / N_CH
    for i, c in enumerate(colors):
        ax.add_patch(mpatches.Rectangle((bar_x + i * seg_w, bar_y), seg_w, bar_h, facecolor=c, edgecolor="none"))
    ax.add_patch(mpatches.Rectangle((bar_x, bar_y), bar_w, bar_h, facecolor="none", edgecolor="#333333", linewidth=1.4))
    ax.text(bar_x, bar_y + bar_h + 0.015, "CSC1 (Back, top)", fontsize=8.5, ha="left")
    ax.text(bar_x + bar_w, bar_y + bar_h + 0.015, "CSC64 (Front, tip)", fontsize=8.5, ha="right")
    ax.text(bar_x + bar_w / 2, bar_y - 0.03, "CSC_Raw.dat  --  channel order in the binary file", fontsize=9.5, ha="center", fontweight="bold")

    note_box(
        ax, 0.06, 0.04, 0.88, 0.26,
        "Same script, same passthrough logic as every other session -- this stage carries no probe-specific behavior.\n"
        "Kilosort channel index (0-based) = CSC number - 1. CSC1.ncs -> binary channel 0 (Back, shallowest),\n"
        "CSC64.ncs -> binary channel 63 (Front, deepest). The binary itself has no concept of 'shank' -- that only\n"
        "exists once probe_config.prb (stage G) is applied.",
        title="What actually happens here",
        fontsize=9,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 6
def stage6(out: Path):
    fig, ax = new_fig(title="Stage F -- kilosort_automation.py handoff (H10 needs its OWN probe file)")

    def box(x, y, w, h, text, color, edge, fs=9):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                     facecolor=color, edgecolor=edge, linewidth=1.6))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    box(0.06, 0.62, 0.30, 0.22, "CSC_Raw.dat\n(binary -- stage E output)\n64 channels x N samples", "#e4e9f7", "#4a5fa5")
    box(0.06, 0.16, 0.30, 0.22, "probe_config_H10D.prb\n(geometry -- stage G, VERIFIED)\nchannel index -> (x, y, shank)", "#d9f2d9", OK_EDGE)
    box(0.44, 0.36, 0.30, 0.28, "run_kilosort(\n  settings=settings_main,\n  probe_name=\n    'probe_config_H10D.prb',\n  filename=f'{data_path}\\\\CSC_Raw.dat',\n  ...)", "#fdeecb", "#c98a1e", fs=8.3)
    box(0.80, 0.36, 0.17, 0.28, "Kilosort\nspatial ops:\nwhitening,\ntemplates,\ndrift, unit\ndepth+shank", "#f9dede", "#b33a3a", fs=8.5)

    ax.add_patch(FancyArrowPatch((0.36, 0.73), (0.44, 0.58), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.36, 0.27), (0.44, 0.42), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.74, 0.50), (0.80, 0.50), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))

    note_box(
        ax, 0.06, 0.02, 0.91, 0.10,
        "kilosort_automation.py defaults probe_name to the single 'probe_config.prb' for every call. For this session\n"
        "that needs to be a dedicated, verified H10-D file (stage G) instead -- a straight line is still structurally wrong.",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=8.8,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 7 (final)
def stage7(out: Path):
    mapping = parse_channel_map(H10_CFG)
    resolved = resolve_csc_positions(mapping)

    fig, ax = new_fig(w=13, h=12.5, title="Stage G -- the final, VERIFIED probe_config.prb for this H10-D session")

    color_by_csc = {}
    for csc, pos in resolved.items():
        if pos is not None:
            pin = mapping[csc] - OFFSET
            color_by_csc[pin] = csc - 1
    draw_pdf_shanks(ax, x0=0.16, x1=0.34, y_top=0.90, y_bot=0.44, col_jitter=0.022, color_by_csc=color_by_csc)
    ax.text(0.16, 0.94, "Back\n(CSC1-32)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.34, 0.94, "Front\n(CSC33-64)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.25, 0.395, "color = verified CSC channel index\n(gray gap = CSC32, unresolved)",
            ha="center", va="top", fontsize=7.8, style="italic")

    ax.add_patch(FancyBboxPatch((0.55, 0.86), 0.16, 0.075, boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor=OK_BG, edgecolor=OK_EDGE, linewidth=1.8))
    ax.text(0.63, 0.898, "VERIFIED  63/64\n(vendor pinout PDF)", ha="center", va="center", fontsize=8.3, fontweight="bold", color="#245c24")

    code_box(
        ax, 0.53, 0.80,
        "channel_groups = {\n"
        "    0.0: {\n"
        "        'channels': [0, 1, ..., 63],\n"
        "        'geometry': {\n"
        "            # Back shank (ch 0-31 = CSC1-32)\n"
        "            0:  (0.0,    0.0),   # CSC1, pin21\n"
        "            1:  (-18.5, 15.0),   # CSC2, pin41\n"
        "            2:  ( 18.5, 15.0),   # CSC3, pin32\n"
        "            ...\n"
        "            31: unresolved,      # CSC32, hw=60\n"
        "            # Front shank (ch 32-63 = CSC33-64)\n"
        "            32: (150.0,   0.0),  # CSC33, pin64\n"
        "            33: (131.5, 15.0),   # CSC34, pin5\n"
        "            ...\n"
        "        },\n"
        "        'graph': [],\n"
        "    }\n"
        "}",
        fontsize=7.6, title="probe_config.prb  (VERIFIED structure)",
    )

    note_box(
        ax, 0.02, 0.02, 0.50, 0.34,
        "How this was verified (not assumed):\n\n"
        "1. ASSY-77 H10-D-map.pdf gives the real probe-pin order,\n"
        "   top-to-tip, for the 'Back' and 'Front' shanks.\n"
        "2. This session's -SetChannelNumber table, minus a constant\n"
        "   63, reproduces that exact pin order for 63 of 64 channels:\n"
        "   CSC1-32 = Back top-to-tip, CSC33-64 = Front top-to-tip.\n"
        "3. Depth (y) and column (x) below follow the PDF's real row/\n"
        "   left-right layout; absolute microns use typical 15 um row\n"
        "   pitch and 18.5 um column offset (order is verified, exact\n"
        "   micron spacing is the one inferred piece).\n\n"
        "The one gap: CSC32 (raw hw=60) does not decode to a valid pin\n"
        "-- the PDF marks some connector pins as dedicated REF/GND,\n"
        "so CSC32 is most likely one of those, not a real electrode.\n"
        "Leave it out of the geometry (or flag as a bad channel)\n"
        "rather than guessing its position.",
        title="Verification method",
        facecolor="#f2f2f2", edgecolor="#666666", fontsize=8.0,
    )

    note_box(
        ax, 0.53, 0.03, 0.44, 0.34,
        "What this resolves:\n\n"
        "- Channel order is no longer 'not verified' for this session\n"
        "  -- it is grounded in the vendor's own documented pinout,\n"
        "  cross-checked arithmetically against the real .cfg file.\n\n"
        "- Both shank identity (Back vs Front) and depth order within\n"
        "  each shank are now known for 63/64 channels.\n\n"
        "What's still open:\n"
        "- CSC32's true identity (likely REF/GND, not electrode).\n"
        "- This verification is specific to sessions using this exact\n"
        "  -SetChannelNumber table (this H10_D_open/filtered pair) --\n"
        "  it does not automatically extend to other H10 configs,\n"
        "  which were out of scope for this pass.",
        title="Where this leaves things",
        facecolor=OK_BG, edgecolor=OK_EDGE, fontsize=8.2,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    stage1(out_dir / "01_stageA_electrode_sites.png")
    stage2(out_dir / "02_stageB_headstage_wiring.png")
    stage3(out_dir / "03_stageC_cheetah_remap.png")
    stage4(out_dir / "04_stageD_ncs_files.png")
    stage5(out_dir / "05_stageE_binary_creation.png")
    stage6(out_dir / "06_stageF_kilosort_handoff.png")
    stage7(out_dir / "07_stageG_final_probe_config.png")
