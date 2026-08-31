"""
Same stage-by-stage treatment as H3_channel_journey_diagrams, but for H10
-- specifically for the session in
Config files/H10_D_open_Cheetah2026-07-21_16-59-03.cfg.

Key difference from H3: H10 is a real 2-shank probe (confirmed against
the probeinterface cambridgeneurotech 'ASSY-77-H10' vendor entry), AND
the -SetChannelNumber table itself is NOT stable across H10 sessions
(this session's table is a 4th distinct variant, different from the
three found in AD_channel_mapping_figures.py). So stage G here cannot
carry a "VERIFIED" badge the way H3's did -- it shows what the geometry
STRUCTURALLY must be, and flags exactly what remains unverified.

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
H10_OLD_CFG = CONFIG_DIR / "Cheetah2023-10-27_14-28-44_chronicH10.cfg"
H10_CORNERS_CFG = CONFIG_DIR / "Cheetah2026-04-20_14-14-12_H10_Corners_Display.cfg"
H10_NEWMAP_CFG = CONFIG_DIR / "H10 Chronic new map_wheel_06-12-26.cfg"

N_CH = 64

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

# real vendor geometry, cambridgeneurotech ASSY-77-H10 (2 shanks x 32 sites, staggered)
SHANK0 = [
    (18.5, 330.0), (37.0, 255.0), (18.5, 270.0), (37.0, 285.0), (18.5, 240.0), (37.0, 315.0),
    (18.5, 210.0), (37.0, 225.0), (18.5, 180.0), (37.0, 195.0), (18.5, 150.0), (37.0, 165.0),
    (37.0, 45.0), (37.0, 135.0), (37.0, 75.0), (0.0, 165.0), (18.5, 0.0), (0.0, 135.0),
    (0.0, 45.0), (0.0, 105.0), (0.0, 255.0), (18.5, 300.0), (0.0, 285.0), (0.0, 315.0),
    (18.5, 30.0), (18.5, 60.0), (0.0, 75.0), (18.5, 120.0), (0.0, 195.0), (0.0, 225.0),
    (37.0, 105.0), (18.5, 90.0),
]
SHANK1 = [
    (187.0, 315.0), (150.0, 75.0), (168.5, 210.0), (168.5, 180.0), (187.0, 285.0), (187.0, 105.0),
    (187.0, 225.0), (187.0, 195.0), (168.5, 240.0), (168.5, 270.0), (187.0, 255.0), (168.5, 330.0),
    (187.0, 75.0), (187.0, 135.0), (187.0, 45.0), (187.0, 165.0), (168.5, 150.0), (150.0, 105.0),
    (150.0, 45.0), (150.0, 135.0), (168.5, 0.0), (150.0, 165.0), (168.5, 30.0), (150.0, 195.0),
    (168.5, 60.0), (150.0, 225.0), (168.5, 90.0), (150.0, 315.0), (168.5, 120.0), (150.0, 285.0),
    (168.5, 300.0), (150.0, 255.0),
]


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


SHANK0_XC = 18.5
SHANK1_XC = 168.5


def draw_h10_shanks(ax, x0=0.30, x1=0.62, y_top=0.90, y_bot=0.10, x_scale_boost=2.6,
                     rect_hw_mult=1.6, color_by_index=False):
    """Draws the real 2-shank staggered ASSY-77-H10 geometry (x exaggerated for legibility)."""
    y_min, y_max = 0.0, 330.0
    hw = 0.05

    def to_axes(shank_pts, x_center, shank_xc):
        pts = []
        for x, y in shank_pts:
            xn = x_center + (x - shank_xc) / 37.0 * hw * x_scale_boost
            yn = y_top - (y - y_min) / (y_max - y_min) * (y_top - y_bot)
            pts.append((xn, yn))
        return pts

    draw_shank(ax, x0, y_top, y_bot, hw * rect_hw_mult)
    draw_shank(ax, x1, y_top, y_bot, hw * rect_hw_mult)

    pts0 = to_axes(SHANK0, x0, SHANK0_XC)
    pts1 = to_axes(SHANK1, x1, SHANK1_XC)
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)] if color_by_index else None
    for i, (x, y) in enumerate(pts0):
        c = colors[i] if colors else "#7a8bb8"
        ax.add_patch(Circle((x, y), 0.009, facecolor=c, edgecolor="black", linewidth=0.3, zorder=2))
    for i, (x, y) in enumerate(pts1):
        c = colors[32 + i] if colors else "#b87a9e"
        ax.add_patch(Circle((x, y), 0.009, facecolor=c, edgecolor="black", linewidth=0.3, zorder=2))
    return pts0, pts1


# ---------------------------------------------------------------- stage 1
def stage1(out: Path):
    fig, ax = new_fig(title="Stage A -- Physical electrode sites on the H10 probe (2 shanks)")
    draw_h10_shanks(ax, x0=0.20, x1=0.42)

    ax.text(0.20, 0.94, "shank 0\n(32 sites)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.42, 0.94, "shank 1\n(32 sites)", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.31, 0.05, "tip (enters tissue first)", ha="center", fontsize=9)
    ax.text(0.31, 0.965, "top / insertion point", ha="center", fontsize=9)

    note_box(
        ax, 0.55, 0.30, 0.42, 0.55,
        "Confirmed against the probeinterface cambridgeneurotech\n"
        "'ASSY-77-H10' vendor entry (Probe_H10_mismatch_figure.py,\n"
        "earlier in this session): H10 is a genuinely 2-shank probe,\n"
        "32 staggered sites per shank, 150 um shank separation,\n"
        "11x15 um rect contacts. x-offsets here are exaggerated for\n"
        "legibility -- true shank width is only ~37 um.\n\n"
        "This is structurally different from H3 in a way that matters:\n"
        "a single straight line (H3's probe_config.prb shape) CANNOT\n"
        "represent this geometry, no matter how correct the channel\n"
        "order turns out to be.\n\n"
        "As with H3, nothing here has a channel NUMBER yet --\n"
        "that's applied downstream, starting at stage C.",
        title="What this stage is",
        fontsize=8.6,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 2
def stage2(out: Path):
    fig, ax = new_fig(title="Stage B -- H10 headstage / EIB wiring (fixed, physical, not a file)")
    draw_h10_shanks(ax, x0=0.08, x1=0.24, y_top=0.90, y_bot=0.22, x_scale_boost=1.4, rect_hw_mult=1.0)

    hs_x0, hs_x1 = 0.38, 0.55
    hs_y0, hs_y1 = 0.20, 0.80
    ax.add_patch(FancyBboxPatch((hs_x0, hs_y0), hs_x1 - hs_x0, hs_y1 - hs_y0,
                 boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor="#e4e9f7", edgecolor="#4a5fa5", linewidth=1.8))
    ax.text((hs_x0 + hs_x1) / 2, (hs_y0 + hs_y1) / 2,
            "H10 headstage / EIB\nadapter board\n\nfixed copper-trace\nrouting per board\n(same idea as H3 --\nbut see stage C)",
            ha="center", va="center", fontsize=9)

    pin_x = 0.78
    pin_ys = [0.78 - i * (0.6 / 15) for i in range(16)]
    for py in pin_ys:
        ax.add_patch(Circle((pin_x, py), 0.008, facecolor="#cccccc", edgecolor="#555555", linewidth=0.6, zorder=2))
    ax.text(pin_x, 0.83, "raw ADC hardware\nchannels (DigitalLynxSX)", fontsize=8.5, ha="center")
    for py in pin_ys[::3]:
        ax.add_patch(FancyArrowPatch((hs_x1, 0.5), (pin_x - 0.02, py), connectionstyle="arc3,rad=-0.1",
                     arrowstyle="-", color="#888888", linewidth=0.7, alpha=0.5, linestyle="dashed"))
    for xf in (0.08, 0.24):
        ax.add_patch(FancyArrowPatch((xf + 0.02, 0.5), (hs_x0, 0.5), connectionstyle="arc3,rad=0.1",
                     arrowstyle="-", color="#888888", linewidth=0.9, alpha=0.6))

    note_box(
        ax, 0.06, 0.02, 0.90, 0.15,
        "Unlike H3, this routing does NOT appear to be a single fixed constant across sessions -- see stage C:\n"
        "the -SetChannelNumber table for H10 has changed at least 4 times across sessions sampled in this repo.\n"
        "That could mean different physical H10 headstage units were used, different probes, or genuine\n"
        "reconfiguration -- this diagram cannot tell which, only that the fixed-board assumption from H3 does not\n"
        "carry over cleanly here.",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=8.6,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 3
def stage3(out: Path):
    mapping = parse_channel_map(H10_CFG)
    others = {
        "chronicH10 (2023-10-27) / jan16 (2024-01-16)": parse_channel_map(H10_OLD_CFG),
        "H10_Corners_Display (2026-04-20)": parse_channel_map(H10_CORNERS_CFG),
        "H10 Chronic new map (2026-06-12)": parse_channel_map(H10_NEWMAP_CFG),
    }
    n_matches = {name: sum(1 for c in mapping if tbl.get(c) == mapping[c]) for name, tbl in others.items()}

    fig, ax = new_fig(title="Stage C -- Cheetah .cfg  -SetChannelNumber  (THIS session's table)")

    hw_vals = sorted(set(mapping.values()))
    hw_y = {v: 0.85 - 0.75 * i / (len(hw_vals) - 1) for i, v in enumerate(hw_vals)}
    csc_y = {c: 0.85 - 0.75 * (c - 1) / (N_CH - 1) for c in mapping}
    left_x, right_x = 0.14, 0.52
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]

    for v, y in hw_y.items():
        ax.add_patch(Circle((left_x, y), 0.006, facecolor="#999999", edgecolor="none", zorder=2))
    ax.text(left_x, 0.94, "raw hardware\nADC channel", fontsize=9.5, ha="center", fontweight="bold")

    for c, y in csc_y.items():
        ax.add_patch(Circle((right_x, y), 0.007, facecolor=colors[c - 1], edgecolor="black", linewidth=0.3, zorder=2))
    ax.text(right_x, 0.94, "logical CSC channel\n(CSC1..CSC64)", fontsize=9.5, ha="center", fontweight="bold")

    for c, hw in mapping.items():
        ax.plot([left_x + 0.006, right_x - 0.007], [hw_y[hw], csc_y[c]], color=colors[c - 1], linewidth=0.6, alpha=0.55, zorder=1)
    for c in [1, 16, 32, 48, 64]:
        ax.text(right_x + 0.015, csc_y[c], f"CSC{c}", fontsize=7.5, va="center")

    code_box(ax, 0.62, 0.90, raw_snippet(H10_CFG, 6), fontsize=7.8, title="Actual .cfg syntax (this session)")

    compare_lines = "\n".join(f"- {name}: {n}/64 channels match" for name, n in n_matches.items())
    note_box(
        ax, 0.60, 0.06, 0.37, 0.46,
        "This is a REAL, scrambled remap (see crossing lines) -- but\n"
        "unlike H3, it is not the same table used before.\n\n"
        "Compared against the 3 other H10 tables found earlier in\n"
        "this session:\n\n"
        f"{compare_lines}\n\n"
        "This session's table is a 4th DISTINCT variant. H10's\n"
        "channel mapping has now been observed to change at least\n"
        "4 times -- reinforcing that a single static probe_config.prb\n"
        "cannot be correct for every H10 session.",
        title="How this compares to other H10 sessions",
        facecolor=ACCENT_BG, edgecolor=ACCENT, fontsize=8.2,
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
        "Identical mechanism to H3: the logical CSC number from stage C becomes the literal filename.\n"
        "Nothing probe-specific happens here -- Neuralynx doesn't know or care whether the session is\n"
        "H3 or H10, it just writes whatever CSC numbers stage C assigned. The probe-specific risk is\n"
        "entirely upstream (stage C) and downstream (stage G), not in this step.",
        title="Why this stage matters",
        fontsize=9.2,
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
             fontsize=8.6, title="perpl_NLX2Binary.m (real loop, same script as H3)")

    bar_x, bar_y, bar_w, bar_h = 0.06, 0.36, 0.88, 0.14
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]
    seg_w = bar_w / N_CH
    for i, c in enumerate(colors):
        ax.add_patch(mpatches.Rectangle((bar_x + i * seg_w, bar_y), seg_w, bar_h, facecolor=c, edgecolor="none"))
    ax.add_patch(mpatches.Rectangle((bar_x, bar_y), bar_w, bar_h, facecolor="none", edgecolor="#333333", linewidth=1.4))
    ax.text(bar_x, bar_y + bar_h + 0.015, "CSC1", fontsize=9, ha="left")
    ax.text(bar_x + bar_w, bar_y + bar_h + 0.015, "CSC64", fontsize=9, ha="right")
    ax.text(bar_x + bar_w / 2, bar_y - 0.03, "CSC_Raw.dat  --  channel order in the binary file", fontsize=9.5, ha="center", fontweight="bold")

    note_box(
        ax, 0.06, 0.04, 0.88, 0.26,
        "Same script, same passthrough logic as H3 -- this stage carries no probe-specific behavior at all.\n"
        "Kilosort channel index (0-based) = CSC number - 1. CSC1.ncs -> binary channel 0, CSC64.ncs -> binary\n"
        "channel 63, for shank 0 AND shank 1 alike -- the binary has no concept of 'shank', that only exists\n"
        "once probe_config.prb (stage G) is applied.",
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
    box(0.06, 0.16, 0.30, 0.22, "probe_config_H10.prb  ?\n(geometry -- stage G)\nchannel index -> (x, y, shank)", "#f9dede", "#b33a3a")
    box(0.44, 0.36, 0.30, 0.28, "run_kilosort(\n  settings=settings_main,\n  probe_name=???,\n  filename=f'{data_path}\\\\CSC_Raw.dat',\n  ...)", "#fdeecb", "#c98a1e", fs=8.6)
    box(0.80, 0.36, 0.17, 0.28, "Kilosort\nspatial ops:\nwhitening,\ntemplates,\ndrift, unit\ndepth+shank", "#f9dede", "#b33a3a", fs=8.5)

    ax.add_patch(FancyArrowPatch((0.36, 0.73), (0.44, 0.58), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.36, 0.27), (0.44, 0.42), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.74, 0.50), (0.80, 0.50), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))

    note_box(
        ax, 0.06, 0.02, 0.91, 0.10,
        "kilosort_automation.py defaults probe_name to the single 'probe_config.prb' for every call. For H10 that\n"
        "default is structurally wrong (single shank) regardless of channel order -- a separate, correct H10 probe\n"
        "file is required, and per stage C, may need to be session-specific.",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=8.8,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 7 (final)
def stage7(out: Path):
    fig, ax = new_fig(w=13, h=12, title="Stage G -- what the final probe_config.prb SHOULD be for H10")

    pts0, pts1 = draw_h10_shanks(ax, x0=0.16, x1=0.34, y_top=0.90, y_bot=0.44, x_scale_boost=2.6, color_by_index=False)
    ax.text(0.16, 0.94, "shank 0", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.34, 0.94, "shank 1", ha="center", fontsize=9.5, fontweight="bold")
    ax.text(0.25, 0.395, "positions illustrative, NOT verified\n(see note below)",
            ha="center", va="top", fontsize=7.8, style="italic")

    ax.add_patch(FancyBboxPatch((0.55, 0.86), 0.16, 0.075, boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor=WARN_BG, edgecolor=WARN_EDGE, linewidth=1.8))
    ax.text(0.63, 0.898, "NOT VERIFIED\nchannel <-> shank order", ha="center", va="center", fontsize=8.3, fontweight="bold", color="#7a1f1f")

    code_box(
        ax, 0.53, 0.80,
        "channel_groups = {\n"
        "    0.0: {\n"
        "        'channels': [0, 1, ..., 63],\n"
        "        'geometry': {\n"
        "            # shank 0 (channels ?..?)\n"
        "            0:  (18.5, 330.0),\n"
        "            1:  (37.0, 255.0),\n"
        "            ...\n"
        "            # shank 1 (channels ?..?)\n"
        "            32: (187.0, 315.0),\n"
        "            33: (150.0,  75.0),\n"
        "            ...\n"
        "        },\n"
        "        'graph': [],\n"
        "    }\n"
        "}",
        fontsize=8.0, title="probe_config.prb  (STRUCTURE it needs)",
    )

    note_box(
        ax, 0.02, 0.02, 0.50, 0.31,
        "What we DO know (structural, vendor-confirmed):\n"
        "- 2 shanks, 32 sites each, 150 um apart\n"
        "- staggered zigzag within each shank, 11x15 um\n"
        "  contacts, ~37 um shank width\n"
        "- a single straight line (H3-style) is categorically\n"
        "  wrong here, independent of channel order\n\n"
        "What is NOT known / not yet checked:\n"
        "- which 32 of the 64 CSC channels in THIS session's\n"
        "  stage C table sit on shank 0 vs shank 1\n"
        "- whether channel order within each shank is\n"
        "  monotonic in depth (as confirmed for H3) or not\n"
        "- the probeinterface vendor 'contact_ids' order can't\n"
        "  answer this -- it's an Intan-system convention, not\n"
        "  this Neuralynx session's",
        title="What we know vs. don't (this session)",
        facecolor="#f2f2f2", edgecolor="#666666", fontsize=8.0,
    )

    note_box(
        ax, 0.53, 0.03, 0.44, 0.34,
        "How to actually finish this file:\n\n"
        "1. Run an equivalent ground-truth check to the H3 one --\n"
        "   e.g. a controlled reference/short applied to one known\n"
        "   shank, or lesion/histology tied to one shank, to learn\n"
        "   which CSC numbers land on shank 0 vs shank 1.\n\n"
        "2. Do this PER SESSION, not once -- stage C showed this\n"
        "   session's table differs from 3 other H10 sessions already\n"
        "   on file, so a mapping validated for one session cannot be\n"
        "   assumed for another.\n\n"
        "3. Until 1-2 are done, treat H10 unit-level Kilosort output\n"
        "   (depth, shank assignment, waveform shape) as unverified,\n"
        "   the same caution flagged in the earlier H10 mismatch figures.",
        title="What would make this VERIFIED",
        facecolor=WARN_BG, edgecolor=WARN_EDGE, fontsize=8.2,
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
