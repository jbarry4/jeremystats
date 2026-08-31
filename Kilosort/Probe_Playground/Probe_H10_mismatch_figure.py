"""
Same "area of concern" illustration as Probe_H3_mismatch_figure.py, but
applied to ASSY-77-H10 under a hypothetical: what if a manual .prb had
been built for this probe using the same naive assumption used for the
H3 file (single shank, sequential channel index -> depth, 20 um pitch)?

Unlike H3 (which really is a single straight 64-site shank, just wired
non-sequentially), H10 is a genuinely different physical layout: 2
shanks of 32 staggered contacts each. So the naive assumption is wrong
in TWO ways here -- channel order AND the shank/x geometry itself.

No real manual .prb exists for H10 in this repo; the "manual" geometry
below is synthesized with the exact same formula that produced the real
probe_config.prb, to show what that same mistake would look like here.

Usage:
    python Probe_H10_mismatch_figure.py [manufacturer] [probe_name] [output_path]

Defaults to cambridgeneurotech / ASSY-77-H10.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import probeinterface as pi

DEFAULT_MANUFACTURER = "cambridgeneurotech"
DEFAULT_PROBE_NAME = "ASSY-77-H10"

MANUAL_SNIPPET = '''# hypothetical probe_config.prb for H10
# (same formula used for the real H3 file)
geometry = {
    i: (5.5, i * 20.0)
    for i in range(64)
}
channels = list(range(64))
# assumes: 1 shank, sequential depth'''

LIBRARY_SNIPPET = '''# vendor ground truth
import probeinterface as pi
probe = pi.get_probe(
    "cambridgeneurotech", "ASSY-77-H10"
)
df = probe.to_dataframe()
# df["shank_ids"] -> 2 shanks (32 ch each)
# df row order = real headstage wiring'''

CHECK_SNIPPET = '''# verify shank count too, not just depth
assert df["shank_ids"].nunique() == 1, (
    "manual .prb assumes 1 shank, "
    f"vendor has {df['shank_ids'].nunique()}"
)
assert (manual_y == df["y"].to_numpy()).all(), (
    "channel order does not match vendor wiring!"
)'''


def naive_sequential_geometry(n_channels: int, x: float = 5.5, pitch: float = 20.0):
    return [(x, i * pitch) for i in range(n_channels)]


def build_figure(manufacturer: str, probe_name: str, output_path: Path) -> None:
    probe = pi.get_probe(manufacturer, probe_name)
    df = probe.to_dataframe()
    n_channels = probe.get_contact_count()

    manual_positions = naive_sequential_geometry(n_channels)
    manual_x = [p[0] for p in manual_positions]
    manual_y = [p[1] for p in manual_positions]

    lib_x = df["x"].to_numpy()
    lib_y = df["y"].to_numpy()
    shank_ids = df["shank_ids"].to_numpy()
    n_shanks = df["shank_ids"].nunique()

    idx = list(range(n_channels))
    cmap = plt.get_cmap("viridis")
    shank_markers = {shank: marker for shank, marker in zip(sorted(set(shank_ids)), ["o", "s", "^", "D"])}

    fig = plt.figure(figsize=(19, 7.5))
    gs = fig.add_gridspec(2, 4, height_ratios=[3, 1.3], hspace=0.5, wspace=0.4)

    # --- Row 1: schematic scatters + index-vs-depth + index-vs-shank(x) ---
    ax_manual = fig.add_subplot(gs[0, 0])
    ax_manual.scatter(manual_x, manual_y, c=idx, cmap=cmap, s=55, edgecolor="k", linewidth=0.5)
    ax_manual.set_title(f"Hypothetical manual .prb for {probe_name}\n(1 shank assumed, color = channel index)", fontsize=9)
    ax_manual.set_xlabel("x (um)")
    ax_manual.set_ylabel("depth y (um)")
    ax_manual.invert_yaxis()

    ax_lib = fig.add_subplot(gs[0, 1])
    for shank in sorted(set(shank_ids)):
        mask = shank_ids == shank
        sc = ax_lib.scatter(
            lib_x[mask], lib_y[mask], c=[i for i in idx if shank_ids[i] == shank],
            cmap=cmap, vmin=0, vmax=n_channels - 1, s=55, edgecolor="k", linewidth=0.5,
            marker=shank_markers[shank], label=f"shank {shank}",
        )
    ax_lib.set_title(f"Vendor library {probe_name}\n({n_shanks} shanks, marker = shank, color = channel index)", fontsize=9)
    ax_lib.set_xlabel("x (um)")
    ax_lib.set_ylabel("depth y (um)")
    ax_lib.legend(fontsize=7, loc="upper right")
    fig.colorbar(sc, ax=ax_lib, label="channel index", fraction=0.08, pad=0.04)

    ax_line = fig.add_subplot(gs[0, 2])
    ax_line.plot(idx, manual_y, "o-", color="tab:orange", label="manual (assumed)", markersize=3)
    ax_line.plot(idx, lib_y, "o-", color="tab:blue", label="vendor (actual)", markersize=3)
    ax_line.set_title("Channel index -> depth", fontsize=9)
    ax_line.set_xlabel("channel index")
    ax_line.set_ylabel("depth y (um)")
    ax_line.legend(fontsize=8)

    ax_shank = fig.add_subplot(gs[0, 3])
    ax_shank.plot(idx, manual_x, "o-", color="tab:orange", label="manual (assumed)", markersize=3)
    ax_shank.plot(idx, lib_x, "o-", color="tab:blue", label="vendor (actual)", markersize=3)
    ax_shank.set_title("Channel index -> x / shank", fontsize=9)
    ax_shank.set_xlabel("channel index")
    ax_shank.set_ylabel("x (um)")
    ax_shank.legend(fontsize=8)

    fig.suptitle(
        f"Area of concern: {probe_name} — a manual .prb built the same way as the H3 one would get\n"
        "BOTH the channel order AND the shank geometry wrong (1 shank assumed vs. 2 real shanks)",
        fontsize=12, fontweight="bold",
    )

    # --- Row 2: code snippets ---
    def add_code_panel(ax, code, title):
        ax.axis("off")
        ax.set_title(title, fontsize=10, fontweight="bold", loc="left")
        ax.text(
            0.02, 0.95, code, transform=ax.transAxes, fontfamily="monospace",
            fontsize=8, va="top", ha="left",
            bbox=dict(boxstyle="round", facecolor="#f2f2f2", edgecolor="#999999"),
        )

    add_code_panel(fig.add_subplot(gs[1, 0]), MANUAL_SNIPPET, "What the same assumption would produce")
    add_code_panel(fig.add_subplot(gs[1, 1]), LIBRARY_SNIPPET, "How to pull the real wiring")
    add_code_panel(fig.add_subplot(gs[1, 2:4]), CHECK_SNIPPET, "How to verify before trusting it")

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
