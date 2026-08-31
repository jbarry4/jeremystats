"""
Generates the verified Kilosort probe_config.prb for the H10-D setup,
using this session's config:
    Config files/H10_D_open_Cheetah2026-07-21_16-59-03.cfg
cross-referenced against the real vendor pinout:
    Probe_Playground/ASSY-77 H10-D-map.pdf

Decoding rule (verified, see H10_channel_journey_diagrams/):
    probe_pin = raw_hw_channel - 63
    CSC1-32  -> 'Back' shank, top (insertion) to tip, in order
    CSC33-64 -> 'Front' shank, top (insertion) to tip, in order
    63 of 64 channels decode to a real pin position exactly.

The one exception is CSC32 (raw hw=60, kilosort channel index 31):
it does not decode to a valid probe pin. The single real pin position
left unclaimed by every other channel is pin 48 -- the physical TIP of
the Back shank -- so that position is used as a geometric placeholder
for channel 31, but this channel should be treated as unverified until
cross-checked against real recorded data. Two hypotheses to check against
real data:
    (a) it really is the Back-tip site (pin 48), routed some other way
    (b) raw hw=60 is a dedicated REF/GND tap (the PDF documents several
        connector pins as REF/GND rather than recording sites), in which
        case this channel's trace should look flat / reference-like
        rather than like a normal tip-depth neural/LFP signal.

Outputs (next to this script):
    probe_config_H10D.prb              -- Kilosort/klusta-style probe file
    probe_config_H10D_channel_table.csv -- channel index -> CSC/shank/depth
    probe_config_H10D_figure.png        -- reference figure for cross-checking
"""

import csv
import re
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Circle

HERE = Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "Config files"
H10_CFG = CONFIG_DIR / "H10_D_open_Cheetah2026-07-21_16-59-03.cfg"

OFFSET = 63
N_CH = 64
ROW_PITCH = 15.0     # um, real contact height
COL_OFFSET = 18.5    # um, real column half-spacing
BACK_XC = 18.5        # um, real Back-shank center x
FRONT_XC = 168.5      # um, real Front-shank center x (150 um shank gap)
UNRESOLVED_CSC = 32
UNRESOLVED_PLACEHOLDER_PIN = 48  # Back-shank tip; see module docstring

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
N_ROWS = len(BACK_ROWS)

PIN_POS = {}  # pin -> (shank, row, col)
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


def pin_xy(shank: str, row: int, col: int):
    xc = BACK_XC if shank == "back" else FRONT_XC
    x = xc + col * COL_OFFSET
    y = row * ROW_PITCH
    return round(x, 1), round(y, 1)


def build_channel_table():
    """Returns list of dicts: kilosort_channel(0-based), csc, hw, shank, row, col, x, y, resolved(bool)."""
    mapping = parse_channel_map(H10_CFG)
    rows = []
    for csc in range(1, N_CH + 1):
        ch = csc - 1
        hw = mapping[csc]
        pin = hw - OFFSET
        resolved = 1 <= pin <= 64 and pin in PIN_POS
        if resolved:
            shank, row, col = PIN_POS[pin]
        elif csc == UNRESOLVED_CSC:
            shank, row, col = PIN_POS[UNRESOLVED_PLACEHOLDER_PIN]
            pin = UNRESOLVED_PLACEHOLDER_PIN
        else:
            raise RuntimeError(f"Unexpected unresolved channel CSC{csc} (hw={hw}) -- only CSC{UNRESOLVED_CSC} is expected to need a placeholder.")
        x, y = pin_xy(shank, row, col)
        rows.append(dict(
            channel=ch, csc=csc, hw=hw, pin=pin, shank=shank, row=row, col=col,
            x=x, y=y, resolved=resolved,
        ))
    return rows


def write_prb(rows, out_path: Path):
    lines = []
    lines.append("# probe_config_H10D.prb")
    lines.append("# Cambridge NeuroTech ASSY-77 H10-D, verified against ASSY-77 H10-D-map.pdf")
    lines.append(f"# Source session: {H10_CFG.name}")
    lines.append("# Decode: probe_pin = raw_hw_channel - 63; CSC1-32 = Back top->tip, CSC33-64 = Front top->tip")
    lines.append(f"# WARNING: channel {UNRESOLVED_CSC - 1} (CSC{UNRESOLVED_CSC}) did not decode (raw hw=60).")
    lines.append(f"#   Placeholder geometry uses the one unclaimed real site (Back-shank tip, pin {UNRESOLVED_PLACEHOLDER_PIN}).")
    lines.append("#   Treat as unverified until cross-checked against real recorded data --")
    lines.append("#   it may instead be a REF/GND tap with no real spatial position (flat/reference-like trace).")
    lines.append("#   Recommended: pass bad_channels=[%d] to run_kilosort until resolved." % (UNRESOLVED_CSC - 1))
    lines.append("")
    lines.append("channel_groups = {")
    lines.append("    0.0: {")
    ch_list = ", ".join(str(r["channel"]) for r in rows)
    lines.append(f"        'channels': [{ch_list}],")
    lines.append("        'geometry': {")
    for r in rows:
        flag = "  # UNRESOLVED -- see header" if r["csc"] == UNRESOLVED_CSC else ""
        lines.append(f"            {r['channel']}: ({r['x']}, {r['y']}),{flag}")
    lines.append("        },")
    lines.append("        'graph': [],")
    lines.append("    }")
    lines.append("}")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


def write_csv(rows, out_path: Path):
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kilosort_channel_0based", "csc_name", "raw_hw_channel", "probe_pin",
                    "shank", "row_from_top", "x_um", "y_um_depth", "resolved"])
        for r in rows:
            w.writerow([r["channel"], f"CSC{r['csc']}", r["hw"], r["pin"], r["shank"],
                        r["row"], r["x"], r["y"], "yes" if r["resolved"] else "NO (placeholder)"])
    print(f"Wrote {out_path}")


def draw_shank(ax, x_center, y_top, y_bottom, half_w, tip_frac=0.05):
    taper_start_y = y_bottom + tip_frac * (y_top - y_bottom)
    pts = [
        (x_center - half_w, y_top), (x_center + half_w, y_top),
        (x_center + half_w, taper_start_y), (x_center, y_bottom), (x_center - half_w, taper_start_y),
    ]
    ax.add_patch(Polygon(pts, closed=True, facecolor="#eef1f8", edgecolor="#3a4a6b", linewidth=1.8, zorder=1))


def build_figure(rows, out_path: Path):
    cmap = plt.get_cmap("viridis")
    fig, ax = plt.subplots(figsize=(15, 12.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.suptitle("probe_config_H10D.prb -- reference figure for cross-checking against real data",
                 fontsize=14, fontweight="bold", y=0.975)

    x0, x1 = 0.24, 0.42
    y_top, y_bot = 0.90, 0.42
    draw_shank(ax, x0, y_top, y_bot, 0.045)
    draw_shank(ax, x1, y_top, y_bot, 0.045)
    ax.text(x0, 0.94, "Back  (ch 0-31)", ha="center", fontsize=10, fontweight="bold")
    ax.text(x1, 0.94, "Front (ch 32-63)", ha="center", fontsize=10, fontweight="bold")

    def row_to_y(row):
        return y_top - row / (N_ROWS - 1) * (y_top - y_bot)

    col_jitter = 0.022
    for r in rows:
        xc = x0 if r["shank"] == "back" else x1
        x = xc + r["col"] * col_jitter
        y = row_to_y(r["row"])
        color = cmap(r["channel"] / (N_CH - 1))
        edge = "red" if not r["resolved"] else "black"
        lw = 1.8 if not r["resolved"] else 0.3
        ax.add_patch(Circle((x, y), 0.010, facecolor=color, edgecolor=edge, linewidth=lw, zorder=2))
        if r["channel"] % 8 == 0 or not r["resolved"]:
            ax.text(x - 0.05 if r["shank"] == "back" else x + 0.05, y,
                     f"ch{r['channel']} (CSC{r['csc']})", fontsize=7.2,
                     ha="right" if r["shank"] == "back" else "left", va="center")

    ax.text(0.25, 0.385, "black outline = verified (63/64)   |   red outline = unresolved placeholder (ch31 / CSC32)",
            ha="center", va="top", fontsize=8.5, style="italic")

    ax.add_patch(FancyBboxPatch((0.02, 0.03), 0.50, 0.32, boxstyle="round,pad=0.015,rounding_size=0.02",
                 facecolor="#f9dede", edgecolor="#b33a3a", linewidth=1.6))
    ax.text(0.04, 0.33, "Cross-check with real data", fontsize=10.5, fontweight="bold")
    ax.text(
        0.04, 0.27,
        "1. Insertion order (as done for H3): confirm signal reaches\n"
        "   Back ch0 (shallowest) before Back ch31/Front, and Front ch63\n"
        "   (deepest) last -- both shanks enter tissue together, so this\n"
        "   checks depth order within each shank, not shank identity.\n\n"
        "2. Channel 31 (CSC32): compare its trace to its neighbors\n"
        "   (ch30, ch32). If it looks like a normal tip-depth signal,\n"
        "   hypothesis (a) -- real Back-tip site -- gains support.\n"
        "   If it's flat / reference-like, hypothesis (b) -- REF/GND\n"
        "   tap, not a real electrode -- gains support. Either way,\n"
        "   update the .prb header and bad_channels list accordingly.\n\n"
        "3. Shank identity (Back vs Front): if you have any way to tell\n"
        "   which physical shank is which once implanted (histology,\n"
        "   asymmetric reference lesion, etc.), confirm ch0-31 vs\n"
        "   ch32-63 land on the shanks you expect.",
        fontsize=8.3, va="top", linespacing=1.5,
    )

    ax.add_patch(FancyBboxPatch((0.54, 0.03), 0.44, 0.32, boxstyle="round,pad=0.015,rounding_size=0.02",
                 facecolor="#f2f2f2", edgecolor="#666666", linewidth=1.4))
    ax.text(0.56, 0.33, "Files generated", fontsize=10.5, fontweight="bold")
    ax.text(
        0.56, 0.27,
        "probe_config_H10D.prb\n"
        "  -- drop-in replacement for probe_config.prb in\n"
        "     kilosort_automation.py's probe_name argument\n\n"
        "probe_config_H10D_channel_table.csv\n"
        "  -- channel/CSC/shank/depth lookup, for cross-\n"
        "     referencing against whatever you pull from the\n"
        "     recording (e.g. per-channel signal QC)\n\n"
        "Recommended run_kilosort call for this session:\n"
        "  bad_channels=[31]   (until channel 31 is resolved)",
        fontsize=8.3, va="top", linespacing=1.5, fontfamily="monospace",
    )

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
    rows = build_channel_table()
    write_prb(rows, out_dir / "probe_config_H10D.prb")
    write_csv(rows, out_dir / "probe_config_H10D_channel_table.csv")
    build_figure(rows, out_dir / "probe_config_H10D_figure.png")
