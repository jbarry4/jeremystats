"""
End-to-end flowchart, specific to the H3 probe: traces one channel from
its physical electrode site all the way to the (x, y) Kilosort actually
uses, with the real code/config syntax from this repo quoted at each
stage, and a verdict on whether probe_config.prb's linear/sequential
depth assumption is a reasonable one for H3.

Usage:
    python H3_channel_journey_flowchart.py [output_path]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

COLOR_NEUTRAL = "#e8e8e8"
COLOR_HW = "#e4e9f7"
COLOR_HW_EDGE = "#4a5fa5"
COLOR_KEY = "#fdeecb"
COLOR_KEY_EDGE = "#c98a1e"
COLOR_KS = "#f9dede"
COLOR_KS_EDGE = "#b33a3a"
COLOR_OK = "#d9f2d9"
COLOR_OK_EDGE = "#4c9a4c"

STAGES = [
    dict(
        title="A. Physical electrode site",
        body="One recording site on the H3 silicon shank,\nat some real depth along the probe.",
        code=None,
        color=COLOR_NEUTRAL, edge="#777777",
    ),
    dict(
        title="B. H3 headstage / EIB wiring",
        body="Fixed copper-trace routing on the physical\nadapter board. Not a file -- set once when\nthe H3 headstage was built. Electrode ->\nraw ADC hardware pin (e.g. pin 84).",
        code=None,
        color=COLOR_NEUTRAL, edge="#777777",
    ),
    dict(
        title="C. Cheetah .cfg  -SetChannelNumber",
        body="THE unscramble step. Software-configurable remap:\nraw hardware pin -> logical CSC name. Verified\nIDENTICAL across every H3 session sampled, 2023-2026.",
        code='# Cheetah2026-06-01_wheel_H3.cfg\n-CreateCscAcqEnt "CSC1" "AcqSystem1"\n-SetChannelNumber "CSC1" 84\n-SetChannelNumber "CSC2" 86\n-SetChannelNumber "CSC3" 87\n...',
        color=COLOR_KEY, edge=COLOR_KEY_EDGE,
    ),
    dict(
        title="D. Neuralynx writes CSCn.ncs",
        body="The logical CSC number from stage C becomes\nthe file identity used by everything downstream.",
        code="CSC1.ncs   CSC2.ncs   CSC3.ncs  ...  CSC64.ncs",
        color=COLOR_HW, edge=COLOR_HW_EDGE,
    ),
    dict(
        title="E. perpl_NLX2Binary.m",
        body="Loops CSC 1->64 in that exact numeric order and\nwrites each channel's samples sequentially.\nNo geometry, no reordering -- pure passthrough.",
        code='for CSC = startchan:channelNum\n    filename = fullfile(filedir, ...\n        [probeName num2str(CSC) \'.ncs\']);\n    ...\n    fwrite(fid, data2, \'int16\');\nend',
        color=COLOR_HW, edge=COLOR_HW_EDGE,
    ),
    dict(
        title="F. CSC_Raw.dat  (binary)  ->  Kilosort",
        body="Binary channel index (0-based) = CSC number - 1.\nkilosort_automation.py hands Kilosort the binary\nAND probe_config.prb -- its only two anchors.",
        code="run_kilosort(settings=settings_main,\n    probe_name='probe_config.prb',\n    filename=f'{data_path}\\\\CSC_Raw.dat',\n    ...)",
        color=COLOR_KS, edge=COLOR_KS_EDGE,
    ),
    dict(
        title="G. probe_config.prb geometry",
        body="Channel index i -> depth y = i x 20 um,\non a single shank. A straight line.\nZero reference to stages A-E.",
        code="geometry = {\n    i: (5.5, i * 20.0)\n    for i in range(64)\n}\nchannels = list(range(64))",
        color=COLOR_KS, edge=COLOR_KS_EDGE,
    ),
]

VERDICT_TITLE = "Does the linear assumption make sense for H3?  --  CONFIRMED"
VERDICT_TEXT = (
    "Yes, and it's now empirically confirmed, not just plausible:\n\n"
    "- Stage C is the ONLY point in this chain where physical channel chaos gets untangled into a "
    "logical order -- and for H3 that table is IDENTICAL across every session sampled, 2023 through "
    "2026 (AD_mapping_H3.png). A deliberate, one-time hardware calibration, not per-session guesswork.\n\n"
    "- Independent ground truth (in vivo, from real recordings): during probe insertion, signal "
    "appears on CSC64 first, then CSC63, CSC62, ... down to CSC1 last. CSC64 is the tip (enters "
    "tissue first, deepest); CSC1 is the top (enters last, shallowest). That means consecutive CSC "
    "numbers really are consecutive physical sites along the shank -- stage C's table is monotonic "
    "in depth, not merely stable across sessions.\n\n"
    "- The sign matches too: probe_config.prb puts channel index 0 (CSC1) at y=0 and channel index 63 "
    "(CSC64) at the largest y (1260 um). Since CSC64 is the deep tip, 'larger y = deeper' is correctly "
    "oriented -- the geometry isn't mirrored.\n\n"
    "Bottom line: for H3 specifically, probe_config.prb's linear assumption is correct in both order "
    "and direction, verified against real insertion data -- not an unfounded guess the way it would be "
    "for a multi-shank probe like H10, where a single straight line can't represent 2 shanks at all."
)


def add_stage_box(ax, y, stage, box_h=1.5):
    box = FancyBboxPatch(
        (0.02, y - box_h / 2), 0.46, box_h,
        boxstyle="round,pad=0.05,rounding_size=0.07",
        facecolor=stage["color"], edgecolor=stage["edge"], linewidth=1.5,
    )
    ax.add_patch(box)
    ax.text(0.25, y + box_h / 2 - 0.16, stage["title"], ha="center", va="top",
            fontsize=9, fontweight="bold", wrap=True)
    ax.text(0.25, y - 0.12, stage["body"], ha="center", va="center", fontsize=7.6)

    if stage["code"]:
        ax.text(
            0.53, y, stage["code"], ha="left", va="center",
            fontsize=7.3, fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f5f5", edgecolor="#999999"),
        )


def build_figure(output_path: Path) -> None:
    n = len(STAGES)
    box_h = 1.5
    gap = 0.55
    row_h = box_h + gap
    total_h = n * row_h + 6.7

    fig, ax = plt.subplots(figsize=(14, total_h * 0.62))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, total_h)
    ax.axis("off")

    ax.text(0.5, total_h - 0.5, "H3 probe: one channel's journey from electrode to Kilosort's (x, y)",
            ha="center", fontsize=13, fontweight="bold", transform=ax.transAxes if False else ax.transData)

    top_y = total_h - 1.3
    ys = [top_y - i * row_h for i in range(n)]
    for y, stage in zip(ys, STAGES):
        add_stage_box(ax, y, stage, box_h=box_h)
    for y1, y2 in zip(ys[:-1], ys[1:]):
        ax.add_patch(FancyArrowPatch(
            (0.25, y1 - box_h / 2), (0.25, y2 + box_h / 2),
            arrowstyle="-|>", mutation_scale=14, color="#333333", linewidth=1.6,
        ))

    verdict_y_top = ys[-1] - box_h / 2 - 0.5
    verdict_h = 5.8
    verdict_box = FancyBboxPatch(
        (0.02, verdict_y_top - verdict_h), 0.96, verdict_h,
        boxstyle="round,pad=0.08,rounding_size=0.1",
        facecolor=COLOR_OK, edgecolor=COLOR_OK_EDGE, linewidth=1.8,
    )
    ax.add_patch(verdict_box)
    ax.add_patch(FancyArrowPatch(
        (0.25, ys[-1] - box_h / 2), (0.25, verdict_y_top),
        arrowstyle="-|>", mutation_scale=14, color="#333333", linewidth=1.6,
    ))
    ax.text(0.5, verdict_y_top - 0.35, VERDICT_TITLE, ha="center", va="top",
            fontsize=11, fontweight="bold")
    ax.text(0.5, verdict_y_top - 0.75, VERDICT_TEXT, ha="center", va="top",
            fontsize=8.4, wrap=True, linespacing=1.5)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "H3_channel_journey_flowchart.png"
    build_figure(out_path)
