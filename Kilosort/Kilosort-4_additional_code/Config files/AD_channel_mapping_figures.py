"""
Explains the actual AD (analog-to-digital) channel mapping mechanism found
in the Cheetah acquisition .cfg files in this folder, and why the "naive"
sequential probe_config.prb used by Kilosort may in fact be fine -- because
the unscrambling of physical electrode -> logical CSC channel number has
ALREADY happened once, upstream, inside these .cfg files, via the
"-SetChannelNumber" directive. That is a completely separate mechanism
from probeinterface's vendor library (which encodes Cambridge Neurotech's
own Omnetics/Intan-chip pin order for a DIFFERENT acquisition ecosystem,
not this lab's Neuralynx DigitalLynx SX + Cheetah setup).

Also flags a real finding: the H3 configs use an IDENTICAL SetChannelNumber
table across every session sampled (2023-2026), but the H10 configs do NOT
-- at least 3 distinct tables were found across dates, including one
explicitly named "new map". That inconsistency (not the H3/H10 geometry
question from before) is the open thing worth checking.

Usage:
    python AD_channel_mapping_figures.py [output_dir]
"""

import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

CONFIG_DIR = Path(__file__).parent

H3_CFG = CONFIG_DIR / "Cheetah2026-06-01_wheel_H3.cfg"
H3_CFG_OLDEST = CONFIG_DIR / "Cheetah2023-11-16_13-23-22_H3_Headfixed.cfg"

H10_NEW_MAP_CFG = CONFIG_DIR / "H10 Chronic new map_wheel_06-12-26.cfg"
H10_OLD_CFG = CONFIG_DIR / "Cheetah2023-10-27_14-28-44_chronicH10.cfg"
H10_CORNERS_CFG = CONFIG_DIR / "Cheetah2026-04-20_14-14-12_H10_Corners_Display.cfg"

COLOR_NEUTRAL = "#e8e8e8"
COLOR_OK = "#d9f2d9"
COLOR_OK_EDGE = "#4c9a4c"
COLOR_WARN = "#fdeecb"
COLOR_WARN_EDGE = "#c98a1e"


def parse_channel_map(cfg_path: Path, max_csc: int = 64):
    """Extract {csc_index: raw_hardware_channel} from -SetChannelNumber "CSCn" X lines."""
    pattern = re.compile(r'-SetChannelNumber\s+"CSC(\d+)"\s+(\d+)')
    mapping = {}
    for line in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.search(line)
        if m:
            csc_idx = int(m.group(1))
            if csc_idx <= max_csc:
                mapping[csc_idx] = int(m.group(2))
    return dict(sorted(mapping.items()))


def raw_snippet(cfg_path: Path, n_entries: int = 9) -> str:
    """Pull the first n_entries real -SetChannelNumber "CSCn" lines verbatim."""
    pattern = re.compile(r'-SetChannelNumber\s+"CSC\d+"\s+\d+')
    lines = [
        l.strip() for l in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if pattern.search(l)
    ]
    return f"# {cfg_path.name}\n" + "\n".join(lines[:n_entries]) + "\n..."


def add_code_panel(ax, code: str, title: str, fontsize=8):
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.text(
        0.02, 0.95, code, transform=ax.transAxes, fontfamily="monospace",
        fontsize=fontsize, va="top", ha="left",
        bbox=dict(boxstyle="round", facecolor="#f2f2f2", edgecolor="#999999"),
    )


def add_text_panel(ax, text: str, title: str, facecolor=COLOR_NEUTRAL, edgecolor="#999999", fontsize=9):
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.text(
        0.02, 0.95, text, transform=ax.transAxes,
        fontsize=fontsize, va="top", ha="left", wrap=True,
        bbox=dict(boxstyle="round,pad=0.6", facecolor=facecolor, edgecolor=edgecolor),
    )


def add_pipeline_chain(ax, stages, highlight_idx):
    ax.axis("off")
    ax.set_xlim(0, 1)
    n = len(stages)
    ax.set_ylim(0, n)
    box_h = 0.72
    for i, text in enumerate(stages):
        y = n - i - 0.5
        color = COLOR_WARN if i == highlight_idx else COLOR_NEUTRAL
        edge = COLOR_WARN_EDGE if i == highlight_idx else "#777777"
        box = FancyBboxPatch(
            (0.03, y - box_h / 2), 0.94, box_h,
            boxstyle="round,pad=0.05,rounding_size=0.06",
            facecolor=color, edgecolor=edge, linewidth=1.4,
        )
        ax.add_patch(box)
        ax.text(0.5, y, text, ha="center", va="center", fontsize=7.8, wrap=True)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch(
                (0.5, y - box_h / 2), (0.5, y - 1 + box_h / 2),
                arrowstyle="-|>", mutation_scale=12, color="#333333", linewidth=1.3,
            ))


PIPELINE_STAGES = [
    "Physical electrode site\n(fixed by headstage PCB\n/ adapter wiring)",
    "Raw ADC hardware channel\n(DigitalLynxSX input pin)",
    "Cheetah .cfg\n-SetChannelNumber remap\n(THIS is the unscramble step)",
    "Logical CSC name\n(CSC1..CSCn)",
    "used downstream:\n.ncs filename -> binary ->\nprobe_config.prb depth index",
]


def build_h3_figure(output_path: Path) -> None:
    mapping = parse_channel_map(H3_CFG)
    mapping_oldest = parse_channel_map(H3_CFG_OLDEST)
    identical = mapping == mapping_oldest

    csc_idx = list(mapping.keys())
    hw_chan = list(mapping.values())

    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.85, 1.15, 1.15], height_ratios=[3, 1.5], hspace=0.5, wspace=0.35)

    fig.suptitle(
        "H3 probe: how the AD channel mapping actually works (Cheetah2026-06-01_wheel_H3.cfg)",
        fontsize=13, fontweight="bold",
    )

    ax_chain = fig.add_subplot(gs[:, 0])
    add_pipeline_chain(ax_chain, PIPELINE_STAGES, highlight_idx=2)

    ax_scatter = fig.add_subplot(gs[0, 1])
    ax_scatter.plot(csc_idx, hw_chan, "o-", color="tab:purple", markersize=3)
    ax_scatter.set_xlabel("logical CSC channel (file / probe_config.prb index)")
    ax_scatter.set_ylabel("raw hardware ADC channel\n(-SetChannelNumber value)")
    ax_scatter.set_title("CSC index -> raw hardware channel\n(real remap, not identity)", fontsize=9.5)

    ax_code = fig.add_subplot(gs[0, 2])
    add_code_panel(ax_code, raw_snippet(H3_CFG), "Actual .cfg syntax (first 9 of 64)")

    consistency_note = (
        f"Stability check: compared against the oldest H3 config on file ({H3_CFG_OLDEST.name}, dated 2023) -- "
        f"table is {'IDENTICAL' if identical else 'DIFFERENT'} across every H3 session sampled (2023-2026). "
        "This looks like a fixed hardware constant for this headstage/adapter, not something reconfigured per session.\n\n"
        "Why probe_config.prb's sequential-depth assumption may be fine after all:\n\n"
        "The Probe_H3_sanity_check.py comparison earlier checked probe_config.prb against\n"
        "probeinterface's cambridgeneurotech 'ASSY-77-H3' library entry -- but that library\n"
        "encodes Cambridge Neurotech's own Omnetics-connector pin order, built for Intan-based\n"
        "acquisition systems (OpenEphys / SpikeGLX). It has nothing to do with this lab's Neuralynx\n"
        "DigitalLynx SX + Cheetah pipeline.\n\n"
        "This .cfg's -SetChannelNumber table performs the SAME KIND of unscramble, but for a\n"
        "totally different hardware chain -- and it happens BEFORE the .ncs files are even written.\n"
        "So 'channel index i' in the binary / probe_config.prb is only ever the raw ADC channel\n"
        "AFTER this remap has already been applied. If this table was built correctly for the H3\n"
        "headstage wiring, a simple sequential depth assumption downstream can be correct --\n"
        "not because Kilosort or the .prb file did anything smart, but because Cheetah already\n"
        "did the hard part. The earlier probeinterface mismatch compared against the wrong\n"
        "reference convention, not necessarily a real error in this lab's data."
    )
    ax_expl = fig.add_subplot(gs[1, 1:3])
    add_text_panel(ax_expl, consistency_note, "So was the earlier 'mismatch' a real bug?", COLOR_NEUTRAL, "#888888", fontsize=8.0)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")
    plt.close(fig)


def build_h10_figure(output_path: Path) -> None:
    map_new = parse_channel_map(H10_NEW_MAP_CFG)
    map_old = parse_channel_map(H10_OLD_CFG)
    map_corners = parse_channel_map(H10_CORNERS_CFG)

    fig = plt.figure(figsize=(15, 9.5))
    gs = fig.add_gridspec(2, 3, width_ratios=[0.85, 1.15, 1.15], height_ratios=[3, 1.7], hspace=0.55, wspace=0.35)

    fig.suptitle(
        "H10 probe: the AD channel mapping is NOT consistent across sessions",
        fontsize=13, fontweight="bold",
    )

    ax_chain = fig.add_subplot(gs[:, 0])
    add_pipeline_chain(ax_chain, PIPELINE_STAGES, highlight_idx=2)

    ax_overlay = fig.add_subplot(gs[0, 1:3])
    idx = list(map_new.keys())
    ax_overlay.plot(list(map_old.keys()), list(map_old.values()), "o-", color="tab:blue",
                     markersize=3, label=f"{H10_OLD_CFG.name}\n(2023-10-27 / matches 2024-01-16 jan16 config)")
    ax_overlay.plot(list(map_corners.keys()), list(map_corners.values()), "o-", color="tab:orange",
                     markersize=3, label=f"{H10_CORNERS_CFG.name}\n(2026-04-20)")
    ax_overlay.plot(idx, list(map_new.values()), "o-", color="tab:green",
                     markersize=3, label=f"{H10_NEW_MAP_CFG.name}\n(2026-06-12, 'new map')")
    ax_overlay.set_xlabel("logical CSC channel (1-64 of the array)")
    ax_overlay.set_ylabel("raw hardware ADC channel\n(-SetChannelNumber value)")
    ax_overlay.set_title("Three different H10 sessions -> three different CSC-to-hardware tables", fontsize=10)
    ax_overlay.legend(fontsize=6.8, loc="upper left")

    ax_code = fig.add_subplot(gs[1, 1])
    add_code_panel(ax_code, raw_snippet(H10_NEW_MAP_CFG), "'new map' .cfg syntax (first 9)", fontsize=7.5)

    warning = (
        "Unlike H3 (one stable table for 2023-2026), H10 sessions used at\n"
        "least 3 distinct -SetChannelNumber tables:\n"
        "  - chronicH10 (2023-10-27) == H10Chronic_jan16 (2024-01-16)\n"
        "  - H10_Corners_Display (2026-04-20): different from both\n"
        "  - 'H10 Chronic new map' (2026-06-12): different again,\n"
        "    and its filename says 'new map' -- implying a deliberate\n"
        "    revision of a previous (possibly wrong) mapping.\n\n"
        "This means probe_config.prb's depth assumption can only be trusted\n"
        "for H10 if it was regenerated per-session from that session's own\n"
        ".cfg -- reusing one probe_config.prb across all H10 recordings\n"
        "(the way it's currently structured) is the real risk here, more\n"
        "than the geometry question from before."
    )
    ax_warn = fig.add_subplot(gs[1, 2])
    add_text_panel(ax_warn, warning, "Open question worth checking", COLOR_WARN, COLOR_WARN_EDGE, fontsize=7.8)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_DIR
    build_h3_figure(out_dir / "AD_mapping_H3.png")
    build_h10_figure(out_dir / "AD_mapping_H10.png")
