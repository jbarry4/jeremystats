"""
Builds a figure illustrating the area of concern found by
Probe_H3_sanity_check.py: the manual probe_config.prb assumes a
sequential channel-index -> depth mapping, but the vendor library's
ASSY-*-H3 wiring is not sequential. Same physical geometry, different
channel order.

The figure embeds the actual code snippets (what the manual file assumes
vs. how to pull/verify the real wiring) directly on the figure, next to
schematic plots of both channel maps.

Usage:
    python Probe_H3_mismatch_figure.py [manufacturer] [probe_name] [output_path]

Defaults to cambridgeneurotech / ASSY-77-H3.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import probeinterface as pi

from Probe_H3_sanity_check import DEFAULT_PRB, load_manual_prb

DEFAULT_MANUFACTURER = "cambridgeneurotech"
DEFAULT_PROBE_NAME = "ASSY-77-H3"

MANUAL_SNIPPET = '''# probe_config.prb  (manual, as built)
geometry = {
    i: (5.5, i * 20.0)
    for i in range(64)
}
channels = list(range(64))
# assumes channel index == depth rank'''

LIBRARY_SNIPPET = '''# vendor ground truth
import probeinterface as pi
probe = pi.get_probe(
    "cambridgeneurotech", "ASSY-77-H3"
)
df = probe.to_dataframe()
# df row order = real headstage wiring
# (NOT range(64))'''

CHECK_SNIPPET = '''# verify before trusting a manual chanMap
manual_y = [g[1] for g in geometry.values()]
lib_y = df["y"].to_numpy()
assert (manual_y == lib_y).all(), (
    "channel order does not match "
    "vendor wiring!"
)'''


def add_code_panel(ax, code: str, title: str):
    ax.axis("off")
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
    ax.text(
        0.02, 0.95, code,
        transform=ax.transAxes,
        fontfamily="monospace",
        fontsize=8,
        va="top", ha="left",
        bbox=dict(boxstyle="round", facecolor="#f2f2f2", edgecolor="#999999"),
    )


def build_figure(manufacturer: str, probe_name: str, output_path: Path) -> None:
    channels, manual_positions = load_manual_prb(DEFAULT_PRB)
    manual_y = [p[1] for p in manual_positions]

    probe = pi.get_probe(manufacturer, probe_name)
    df = probe.to_dataframe()
    lib_y = df["y"].to_numpy()
    lib_x = df["x"].to_numpy()
    manual_x = [p[0] for p in manual_positions]

    idx = list(range(len(channels)))
    cmap = plt.get_cmap("viridis")

    fig = plt.figure(figsize=(15, 7.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[3, 1.3], hspace=0.5, wspace=0.35)

    # --- Row 1: schematic scatter plots + index-vs-depth comparison ---
    ax_manual = fig.add_subplot(gs[0, 0])
    ax_manual.scatter(manual_x, manual_y, c=idx, cmap=cmap, s=60, edgecolor="k", linewidth=0.5)
    ax_manual.set_title("Manual probe_config.prb\n(color = channel index)", fontsize=10)
    ax_manual.set_xlabel("x (um)")
    ax_manual.set_ylabel("depth y (um)")
    ax_manual.invert_yaxis()

    ax_lib = fig.add_subplot(gs[0, 1])
    sc = ax_lib.scatter(lib_x, lib_y, c=idx, cmap=cmap, s=60, edgecolor="k", linewidth=0.5)
    ax_lib.set_title(f"Vendor library {probe_name}\n(color = channel index)", fontsize=10)
    ax_lib.set_xlabel("x (um)")
    ax_lib.set_ylabel("depth y (um)")
    ax_lib.invert_yaxis()
    fig.colorbar(sc, ax=ax_lib, label="channel index", fraction=0.08, pad=0.04)

    ax_line = fig.add_subplot(gs[0, 2])
    ax_line.plot(idx, manual_y, "o-", color="tab:orange", label="manual (assumed)", markersize=3)
    ax_line.plot(idx, lib_y, "o-", color="tab:blue", label="vendor (actual)", markersize=3)
    ax_line.set_title("Channel index -> depth mapping", fontsize=10)
    ax_line.set_xlabel("channel index")
    ax_line.set_ylabel("depth y (um)")
    ax_line.legend(fontsize=8)

    fig.suptitle(
        f"Area of concern: {probe_name} channel order — manual .prb assumes a\n"
        "sequential (linear) map, vendor wiring is not sequential (same geometry, different order)",
        fontsize=12, fontweight="bold",
    )

    # --- Row 2: code snippets explaining each panel ---
    ax_code_manual = fig.add_subplot(gs[1, 0])
    add_code_panel(ax_code_manual, MANUAL_SNIPPET, "What the manual file assumes")

    ax_code_lib = fig.add_subplot(gs[1, 1])
    add_code_panel(ax_code_lib, LIBRARY_SNIPPET, "How to pull the real wiring")

    ax_code_check = fig.add_subplot(gs[1, 2])
    add_code_panel(ax_code_check, CHECK_SNIPPET, "How to verify before trusting it")

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Wrote figure to {output_path}")


if __name__ == "__main__":
    manufacturer = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MANUFACTURER
    probe_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROBE_NAME
    out_path = (
        Path(sys.argv[3])
        if len(sys.argv) > 3
        else Path(__file__).parent / f"probe_{probe_name}_mismatch_figure.png"
    )
    build_figure(manufacturer, probe_name, out_path)
