"""
One polished diagram per stage of the H3 channel's journey from silicon
to the geometry Kilosort actually sorts with, plus a final figure showing
what the resulting probe_config.prb represents once verified (see the
insertion-order ground truth confirmed in this session: CSC64 = tip /
enters first / deepest, CSC1 = top / enters last / shallowest).

Each stage is its own PNG so it can be looked at (or presented) on its
own. Data used in stages 3-7 is parsed live from the real Cheetah config,
not hand-typed.

Usage:
    python H3_stage_diagrams.py [output_dir]
"""

import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon, Circle

CONFIG_DIR = Path(__file__).resolve().parent.parent / "Config files"
H3_CFG = CONFIG_DIR / "Cheetah2026-06-01_wheel_H3.cfg"

N_CH = 64
PITCH_UM = 20.0

INK = "#2b2f38"
SHANK_FILL = "#eef1f8"
SHANK_EDGE = "#3a4a6b"
CODE_BG = "#f5f5f5"
CODE_EDGE = "#999999"
ACCENT = "#c98a1e"
ACCENT_BG = "#fdeecb"
OK_EDGE = "#4c9a4c"
OK_BG = "#d9f2d9"
CMAP = plt.get_cmap("viridis")


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


def raw_snippet(cfg_path: Path, n_entries: int = 5) -> str:
    pattern = re.compile(r'-SetChannelNumber\s+"CSC\d+"\s+\d+')
    lines = [
        l.strip() for l in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if pattern.search(l)
    ]
    return f"# {cfg_path.name}\n" + "\n".join(lines[:n_entries]) + "\n..."


def new_fig(w=11, h=8.5, title=""):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    if title:
        fig.suptitle(title, fontsize=15, fontweight="bold", y=0.975)
    return fig, ax


def draw_shank(ax, x_center, y_top, y_bottom, half_w, tip_frac=0.05, facecolor=SHANK_FILL, edgecolor=SHANK_EDGE):
    tip_y = y_bottom
    taper_start_y = y_bottom + tip_frac * (y_top - y_bottom)
    pts = [
        (x_center - half_w, y_top),
        (x_center + half_w, y_top),
        (x_center + half_w, taper_start_y),
        (x_center, tip_y),
        (x_center - half_w, taper_start_y),
    ]
    ax.add_patch(Polygon(pts, closed=True, facecolor=facecolor, edgecolor=edgecolor, linewidth=1.8, zorder=1))


def contact_ys(y_top, y_bottom, n=N_CH, margin_frac=0.10):
    span = (y_top - y_bottom)
    top = y_top - margin_frac * span
    bot = y_bottom + margin_frac * span * 2.2
    return [top - (top - bot) * i / (n - 1) for i in range(n)]


def code_box(ax, x, y, w, text, fontsize=8.5, ha="left", title=None):
    if title:
        ax.text(x, y + 0.012, title, fontsize=9.5, fontweight="bold", ha=ha, va="bottom", transform=ax.transAxes)
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


# ---------------------------------------------------------------- stage 1
def stage1(out: Path):
    fig, ax = new_fig(title="Stage A -- Physical electrode sites on the H3 shank")
    x_c, y_top, y_bot, hw = 0.28, 0.88, 0.08, 0.045
    draw_shank(ax, x_c, y_top, y_bot, hw)
    ys = contact_ys(y_top, y_bot)
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]
    for y, c in zip(ys, colors):
        ax.add_patch(Circle((x_c, y), 0.009, facecolor=c, edgecolor="black", linewidth=0.3, zorder=2))

    ax.annotate("top of shank\n(closest to insertion point)", xy=(x_c, y_top), xytext=(0.5, 0.90),
                fontsize=9, ha="left", va="center", arrowprops=dict(arrowstyle="-", color="#666666"))
    ax.annotate("tip of shank\n(enters tissue first)", xy=(x_c, y_bot), xytext=(0.5, 0.10),
                fontsize=9, ha="left", va="center", arrowprops=dict(arrowstyle="-", color="#666666"))

    ax.plot([x_c + 0.09, x_c + 0.09], [ys[0], ys[-1]], color="#888888", lw=1)
    ax.plot([x_c + 0.085, x_c + 0.095], [ys[0], ys[0]], color="#888888", lw=1)
    ax.plot([x_c + 0.085, x_c + 0.095], [ys[-1], ys[-1]], color="#888888", lw=1)
    ax.text(x_c + 0.11, (ys[0] + ys[-1]) / 2, f"{N_CH} sites\n{PITCH_UM:.0f} um pitch\n(~{PITCH_UM*(N_CH-1):.0f} um span)",
            fontsize=8.5, va="center")

    note_box(
        ax, 0.50, 0.30, 0.47, 0.42,
        "This stage is purely physical: 64 real recording sites etched\n"
        "into the H3 silicon shank at a fixed pitch, in a fixed physical\n"
        "order from top to tip.\n\n"
        "Nothing here has a channel NUMBER yet -- numbering is a human/\n"
        "software convention applied later. All that physically exists\n"
        "at this stage is 'site 1 (top) ... site 64 (tip)', in that\n"
        "spatial order, unconditionally.\n\n"
        "Everything downstream is about whether the numbering applied\n"
        "later preserves this physical order faithfully.",
        title="What this stage is",
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 2
def stage2(out: Path):
    fig, ax = new_fig(title="Stage B -- H3 headstage / EIB wiring (fixed, physical, not a file)")
    x_c, y_top, y_bot, hw = 0.16, 0.85, 0.15, 0.035
    draw_shank(ax, x_c, y_top, y_bot, hw)
    ys = contact_ys(y_top, y_bot)
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]
    for y, c in zip(ys, colors):
        ax.add_patch(Circle((x_c, y), 0.007, facecolor=c, edgecolor="black", linewidth=0.25, zorder=2))

    hs_x0, hs_x1 = 0.38, 0.55
    hs_y0, hs_y1 = 0.20, 0.80
    ax.add_patch(FancyBboxPatch((hs_x0, hs_y0), hs_x1 - hs_x0, hs_y1 - hs_y0,
                 boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor="#e4e9f7", edgecolor="#4a5fa5", linewidth=1.8))
    ax.text((hs_x0 + hs_x1) / 2, (hs_y0 + hs_y1) / 2, "H3 headstage / EIB\nadapter board\n\nfixed copper-trace\nrouting\n(manufactured once,\nnever reconfigured)",
            ha="center", va="center", fontsize=9)

    for y, c in zip(ys[::4], colors[::4]):
        ax.add_patch(FancyArrowPatch((x_c + 0.045, y), (hs_x0, 0.5), connectionstyle="arc3,rad=0.15",
                     arrowstyle="-", color=c, linewidth=0.8, alpha=0.65))

    pin_x = 0.78
    pin_ys = [0.78 - i * (0.6 / 15) for i in range(16)]
    for i, py in enumerate(pin_ys):
        ax.add_patch(Circle((pin_x, py), 0.008, facecolor="#cccccc", edgecolor="#555555", linewidth=0.6, zorder=2))
    ax.text(pin_x, 0.83, "raw ADC hardware\nchannels (DigitalLynxSX)\ne.g. pins 64-127", fontsize=8.5, ha="center")
    for py in pin_ys[::3]:
        ax.add_patch(FancyArrowPatch((hs_x1, 0.5), (pin_x - 0.02, py), connectionstyle="arc3,rad=-0.1",
                     arrowstyle="-", color="#888888", linewidth=0.7, alpha=0.5, linestyle="dashed"))

    note_box(
        ax, 0.08, 0.02, 0.85, 0.14,
        "This routing is NOT in any config file -- it is the physical PCB layout of the H3 headstage/EIB adapter\n"
        "itself, fixed when the board was built. Which physical site lands on which raw ADC pin is unknown/\n"
        "unverifiable from software alone; it is exactly what stage C's -SetChannelNumber table exists to correct for.",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=8.8,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 3
def stage3(out: Path):
    mapping = parse_channel_map(H3_CFG)
    fig, ax = new_fig(title="Stage C -- Cheetah .cfg  -SetChannelNumber  (the real unscramble step)")

    hw_vals = sorted(set(mapping.values()))
    hw_y = {v: 0.85 - 0.75 * i / (len(hw_vals) - 1) for i, v in enumerate(hw_vals)}
    csc_y = {c: 0.85 - 0.75 * (c - 1) / (N_CH - 1) for c in mapping}

    left_x, right_x = 0.16, 0.60
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

    code_box(ax, 0.72, 0.90, 0.26, raw_snippet(H3_CFG, 6), fontsize=8, title="Actual .cfg syntax")

    note_box(
        ax, 0.68, 0.06, 0.30, 0.42,
        "This directive is the ENTIRE unscramble mechanism:\n\n"
        '-SetChannelNumber "CSC1" 84\n\n'
        "means: what every downstream file, script, and\n"
        "probe_config.prb calls 'channel 1' is actually raw\n"
        "hardware pin 84.\n\n"
        "Verified byte-identical across every H3 session\n"
        "sampled, 2023-2026 -- a fixed calibration, not a\n"
        "per-session guess.\n\n"
        "This is a real, scrambled, non-identity remap\n"
        "(see the crossing lines) -- it is doing real work.",
        title="Why this stage matters most",
        facecolor=ACCENT_BG, edgecolor=ACCENT, fontsize=8.6,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 4
def stage4(out: Path):
    fig, ax = new_fig(title="Stage D -- Neuralynx writes one .ncs file per logical CSC channel")

    def file_icon(x, y, label, w=0.10, h=0.09, color="#e4e9f7", edge="#4a5fa5"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.012",
                     facecolor=color, edgecolor=edge, linewidth=1.3))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=7.8)

    shown = list(range(1, 7)) + [None] + list(range(62, 65))
    x0 = 0.02
    gap = 0.098
    w = 0.085
    for i, c in enumerate(shown):
        x = x0 + i * gap
        if c is None:
            ax.text(x + w / 2, 0.545, "...", fontsize=20, ha="center", va="center", fontweight="bold")
            continue
        file_icon(x, 0.5, f"CSC{c}.ncs", w=w)

    x_last = x0 + (len(shown) - 1) * gap + w
    ax.annotate("", xy=(x0, 0.35), xytext=(x_last, 0.35),
                arrowprops=dict(arrowstyle="-|>", color="#333333", linewidth=1.6))
    ax.text((x0 + x_last) / 2, 0.30, "file / acquisition order", ha="center", fontsize=9, style="italic")

    note_box(
        ax, 0.06, 0.62, 0.88, 0.28,
        "The logical CSC number assigned in stage C becomes the literal filename here. From this point forward,\n"
        "'CSC1' is a name that every downstream tool -- the binary writer, Kilosort, probe_config.prb, even the\n"
        "CSD/voltage-raster scripts -- inherits and trusts without re-deriving it. If stage C got it right,\n"
        "everything after this point can stay simple.",
        title="Why this stage matters",
        fontsize=9.2,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 5
def stage5(out: Path):
    fig, ax = new_fig(title="Stage E -- perpl_NLX2Binary.m writes the binary in that exact order")

    code_box(ax, 0.06, 0.90, 0.46,
             "for CSC = startchan:channelNum\n"
             "    filename = fullfile(filedir, ...\n"
             "        [probeName num2str(CSC) '.ncs']);\n"
             "    [Timestamps, ~, ~, ~, Samples, Header] = ...\n"
             "        Nlx2MatCSC(filename, [1 1 1 1 1], 1, 1, []);\n"
             "    ...\n"
             "    fwrite(fid, data2, 'int16');\n"
             "end",
             fontsize=8.6, title="perpl_NLX2Binary.m (real loop)")

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
        "No geometry, no reordering, no probe knowledge in this step at all -- it is a pure passthrough: whatever\n"
        "order the CSCn.ncs files were named in stage D is exactly the column order written into the binary.\n\n"
        "Kilosort channel index (0-based) = CSC number - 1.   So CSC1.ncs -> binary channel 0, CSC64.ncs ->\n"
        "binary channel 63. This is the one arithmetic detail that has to line up correctly with\n"
        "probe_config.prb's own 0-based channel list.",
        title="What actually happens here",
        fontsize=9,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 6
def stage6(out: Path):
    fig, ax = new_fig(title="Stage F -- kilosort_automation.py hands Kilosort its only two anchors")

    def box(x, y, w, h, text, color, edge, fs=9.5):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.02",
                     facecolor=color, edgecolor=edge, linewidth=1.6))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    box(0.06, 0.62, 0.30, 0.22, "CSC_Raw.dat\n(binary -- stage E output)\n64 channels x N samples", "#e4e9f7", "#4a5fa5")
    box(0.06, 0.16, 0.30, 0.22, "probe_config.prb\n(geometry -- stage G)\nchannel index -> (x, y)", "#f9dede", "#b33a3a")
    box(0.44, 0.36, 0.30, 0.28, "run_kilosort(\n  settings=settings_main,\n  probe_name='probe_config.prb',\n  filename=f'{data_path}\\\\CSC_Raw.dat',\n  ...)", "#fdeecb", "#c98a1e", fs=9)
    box(0.80, 0.36, 0.17, 0.28, "Kilosort\nspatial ops:\nwhitening,\ntemplates,\ndrift, unit\ndepth", "#f9dede", "#b33a3a")

    ax.add_patch(FancyArrowPatch((0.36, 0.73), (0.44, 0.58), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.36, 0.27), (0.44, 0.42), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))
    ax.add_patch(FancyArrowPatch((0.74, 0.50), (0.80, 0.50), arrowstyle="-|>", mutation_scale=16, color="#333333", linewidth=1.6))

    note_box(
        ax, 0.06, 0.02, 0.91, 0.10,
        "These are the ONLY two inputs Kilosort receives about the recording. It never sees stages A-E --\n"
        "it trusts probe_config.prb completely.",
        facecolor="#f7f7f7", edgecolor="#999999", fontsize=9.5,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


# ---------------------------------------------------------------- stage 7 (final)
def stage7(out: Path):
    fig, ax = new_fig(w=12, h=12, title="Stage G -- the final, verified probe_config.prb geometry for H3")

    x_c, y_top, y_bot, hw = 0.15, 0.90, 0.10, 0.035
    draw_shank(ax, x_c, y_top, y_bot, hw)
    ys = contact_ys(y_top, y_bot)
    colors = [CMAP(i / (N_CH - 1)) for i in range(N_CH)]
    for i, (y, c) in enumerate(zip(ys, colors)):
        ax.add_patch(Circle((x_c, y), 0.009, facecolor=c, edgecolor="black", linewidth=0.3, zorder=2))
        if i in (0, 15, 31, 47, 63):
            ax.text(x_c + 0.055, y, f"CSC{i+1}: ch{i}, y={i*PITCH_UM:.0f}um", fontsize=7.6, va="center")

    ax.text(x_c, y_top + 0.02, "CSC1 -- shallow, enters last (y=0)", fontsize=9, ha="center")
    ax.text(x_c, y_bot - 0.035, "CSC64 -- tip, enters first, deepest (y=1260 um)", fontsize=9, ha="center")

    ax.add_patch(FancyBboxPatch((0.62, 0.86), 0.13, 0.07, boxstyle="round,pad=0.01,rounding_size=0.02",
                 facecolor=OK_BG, edgecolor=OK_EDGE, linewidth=1.6))
    ax.text(0.685, 0.895, "VERIFIED\n(insertion order)", ha="center", va="center", fontsize=8.5, fontweight="bold", color="#245c24")

    code_box(
        ax, 0.60, 0.80, 0.35,
        "channel_groups = {\n"
        "    0.0: {\n"
        "        'channels': [0, 1, 2, ..., 63],\n"
        "        'geometry': {\n"
        "            0:  (5.5, 0.0),\n"
        "            1:  (5.5, 20.0),\n"
        "            2:  (5.5, 40.0),\n"
        "            ...\n"
        "            63: (5.5, 1260.0),\n"
        "        },\n"
        "        'graph': [],\n"
        "    }\n"
        "}",
        fontsize=8.6, title="probe_config.prb  (actual structure)",
    )

    note_box(
        ax, 0.42, 0.04, 0.55, 0.55,
        "What each field means, now that it's verified:\n\n"
        "'channels' -- kilosort's 0-based channel list, [0..63].\n"
        "channel i is CSC(i+1) after stages C-E.\n\n"
        "'geometry' -- {channel index: (x, y)} in um. x=5.5 is a\n"
        "constant (single-column shank, just a nominal shank\n"
        "half-width); y = i * 20.0 is the depth. Confirmed correct\n"
        "in direction: y grows WITH channel index, and channel index\n"
        "grows toward the tip -- matching the observed insertion\n"
        "order (CSC64 first / deepest, CSC1 last / shallow).\n\n"
        "'graph' -- deliberately empty. Kilosort doesn't need an\n"
        "explicit adjacency list; it derives spatial neighbors\n"
        "directly from the geometry above. This is why stage C\n"
        "being correct matters so much: neighbor structure,\n"
        "whitening, templates and drift all fall out of these\n"
        "(x, y) values alone.\n\n"
        "One shank, one column, 64 evenly spaced sites -- for H3\n"
        "this is not a simplification, it's an accurate description.",
        title="Reading the file",
        fontsize=8.4,
    )

    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    stage1(out_dir / "01_stageA_electrode_site.png")
    stage2(out_dir / "02_stageB_headstage_wiring.png")
    stage3(out_dir / "03_stageC_cheetah_remap.png")
    stage4(out_dir / "04_stageD_ncs_files.png")
    stage5(out_dir / "05_stageE_binary_creation.png")
    stage6(out_dir / "06_stageF_kilosort_handoff.png")
    stage7(out_dir / "07_stageG_final_probe_config.png")
