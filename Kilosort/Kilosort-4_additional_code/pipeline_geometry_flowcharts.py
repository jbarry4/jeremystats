"""
Two flowcharts explaining why the wrong probe_config.prb geometry
(see Probe_Playground/Probe_H3_sanity_check.py) corrupted Kilosort's
unit-level output but never touched the CSD / voltage-raster figures.

Figure 1: the whole pipeline, from raw .ncs files to both downstream
           consumers -- showing where geometry is (and isn't) attached.
Figure 2: zooms into Kilosort itself -- exactly which internal stages
           consume chanMap (x, y) and how the wrong geometry propagates,
           contrasted with the CSD path that bypasses it entirely.

Usage:
    python pipeline_geometry_flowcharts.py [output_dir]
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.patches import FancyArrowPatch

COLOR_NEUTRAL = "#e8e8e8"
COLOR_OK = "#d9f2d9"
COLOR_OK_EDGE = "#4c9a4c"
COLOR_BAD = "#f9dede"
COLOR_BAD_EDGE = "#b33a3a"
COLOR_WARN = "#fdeecb"
COLOR_WARN_EDGE = "#c98a1e"


def add_box(ax, center, width, height, text, facecolor=COLOR_NEUTRAL, edgecolor="#555555", fontsize=9, fontweight="normal"):
    x, y = center
    box = FancyBboxPatch(
        (x - width / 2, y - height / 2), width, height,
        boxstyle="round,pad=0.08,rounding_size=0.08",
        facecolor=facecolor, edgecolor=edgecolor, linewidth=1.3,
    )
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, fontweight=fontweight)
    return box


def add_arrow(ax, start, end, color="#333333", style="-|>", lw=1.6, ls="solid"):
    arrow = FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=14,
        color=color, linewidth=lw, linestyle=ls, shrinkA=2, shrinkB=2,
    )
    ax.add_patch(arrow)


def add_side_note(ax, x, y, text, color="#555555", fontsize=7.5, ha="left"):
    ax.text(x, y, text, ha=ha, va="center", fontsize=fontsize, color=color, style="italic")


def build_figure_1(output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 11))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 15.5)
    ax.axis("off")

    ax.text(6, 15, "Where probe geometry enters the pipeline (and where it doesn't)",
            ha="center", fontsize=13, fontweight="bold")

    add_box(ax, (6, 13.6), 7.6, 1.0,
            "Raw .ncs files (Neuralynx CSC 1-64)\nphysical acquisition-order channels", COLOR_NEUTRAL)

    add_arrow(ax, (6, 13.1), (6, 12.3))
    add_box(ax, (6, 11.7), 7.6, 1.1,
            "perpl_NLX2Binary.m\nwrites each CSC channel in fixed order\nNO geometry file read or used", COLOR_NEUTRAL, fontsize=8.5)

    add_arrow(ax, (6, 11.15), (6, 10.35))
    add_box(ax, (6, 9.75), 7.6, 1.0,
            "CSC_Raw.dat  (binary)\nchannel N = raw trace of acquisition channel N\nstill no spatial info attached", COLOR_NEUTRAL, fontsize=8.5)

    # fork
    add_arrow(ax, (6, 9.25), (2.8, 8.2))
    add_arrow(ax, (6, 9.25), (9.2, 8.2))

    # left branch: CSD / voltage raster
    add_box(ax, (2.8, 7.6), 5.0, 1.15,
            "IED / DS Analysis scripts\n(CSDRaster_Avg.m, visualize_biting.m, ...)\nreads binary directly", COLOR_NEUTRAL, fontsize=8)
    add_arrow(ax, (2.8, 7.0), (2.8, 6.2))
    add_box(ax, (2.8, 5.6), 5.0, 1.3,
            "Own built-in assumption:\nrow index i == depth rank i\nnever reads probe_config.prb", COLOR_OK, COLOR_OK_EDGE, fontsize=8)
    add_arrow(ax, (2.8, 4.95), (2.8, 4.15))
    add_box(ax, (2.8, 3.55), 5.0, 1.3,
            "CSD / voltage-raster figures\nlook fine -- self-consistent\n(nothing else disagrees with it)", COLOR_OK, COLOR_OK_EDGE, fontsize=8.5, fontweight="bold")

    # right branch: kilosort
    add_box(ax, (9.2, 7.6), 5.0, 1.15,
            "kilosort_automation.py\nrun_kilosort(probe_name=\n'probe_config.prb', ...)", COLOR_NEUTRAL, fontsize=8)
    add_arrow(ax, (9.2, 7.0), (9.2, 6.2))
    add_box(ax, (9.2, 5.6), 5.0, 1.3,
            "probe_config.prb  (manual)\nassumes 1 shank, sequential\ndepth per channel index", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8)
    add_arrow(ax, (9.2, 4.95), (9.2, 4.15))
    add_box(ax, (9.2, 3.4), 5.0, 1.6,
            "Kilosort spatial ops:\nwhitening / template building /\ndrift registration / unit depth", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8)
    add_arrow(ax, (9.2, 2.6), (9.2, 1.8))
    add_box(ax, (9.2, 1.2), 5.0, 1.3,
            "Unit-level outputs corrupted:\nwaveforms, depths,\ndrift-corrected spike trains", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5, fontweight="bold")

    ax.text(6, 0.15,
            "Only Kilosort ever reads probe_config.prb's (x, y) values -- CSD / voltage scripts never do.",
            ha="center", fontsize=9.5, fontweight="bold", color="#333333")

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")
    plt.close(fig)


def build_figure_2(output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 11))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 15.5)
    ax.axis("off")

    ax.text(6, 15, "Inside Kilosort: how the wrong chanMap propagates",
            ha="center", fontsize=13, fontweight="bold")

    add_box(ax, (5, 13.8), 7.6, 1.1,
            "chanMap: (x_i, y_i) per channel index i\n<- probe_config.prb (WRONG: 1 shank,\nsequential depth assumed)", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5)

    add_arrow(ax, (5, 13.2), (5, 12.4))
    add_box(ax, (5, 11.7), 7.6, 1.15,
            "Whitening matrix\nbuilt from channels declared 'nearby'\nusing (x_i, y_i)", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5)
    add_side_note(ax, 9.1, 11.7, "real neighbors excluded;\nfar-apart channels\nwhitened together")

    add_arrow(ax, (5, 11.1), (5, 10.3))
    add_box(ax, (5, 9.6), 7.6, 1.15,
            "Template building / clustering\npools waveforms across channels\nbelieved to be adjacent", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5)
    add_side_note(ax, 9.1, 9.6, "templates blurred /\nwrong channels combined\n-> messy or merged units")

    add_arrow(ax, (5, 9.0), (5, 8.2))
    add_box(ax, (5, 7.5), 7.6, 1.15,
            "Drift registration\ntracks spike positions along\ny (declared depth) over time", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5)
    add_side_note(ax, 9.1, 7.5, "drift tracked along\nthe WRONG depth axis")

    add_arrow(ax, (5, 6.9), (5, 6.1))
    add_box(ax, (5, 5.4), 7.6, 1.15,
            "Final unit depth / shank labels\nreported per sorted unit", COLOR_BAD, COLOR_BAD_EDGE, fontsize=8.5, fontweight="bold")
    add_side_note(ax, 9.1, 5.4, "unit depth & shank\nassignment unreliable")

    add_arrow(ax, (5, 4.8), (5, 4.0))
    add_box(ax, (5, 3.15), 7.6, 1.5,
            "Kilosort never validates chanMap against real wiring --\nit trusts probe_config.prb as ground truth.\nNo automatic check catches this.",
            COLOR_WARN, COLOR_WARN_EDGE, fontsize=9, fontweight="bold")

    add_box(ax, (5, 1.15), 8.6, 1.5,
            "For comparison -- CSD / voltage raster:\nnever touches chanMap, uses raw row/channel index\nas depth directly -> unaffected by this error",
            COLOR_OK, COLOR_OK_EDGE, fontsize=8.5)

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    build_figure_1(out_dir / "pipeline_dataflow_flowchart.png")
    build_figure_2(out_dir / "kilosort_geometry_propagation_flowchart.png")
