"""
Generates the verified Kilosort probe file for the H10-D setup.

Sources of truth (in order of authority):

1. SPATIAL GEOMETRY -- probeinterface, cambridgeneurotech / ASSY-77-H10.
   Every contact coordinate in the output comes from probeinterface. Nothing
   here is measured off the vendor PDF; the PDF is a raster and is used only
   for the *ordering* of connector pins down each shank (stage A below).

2. PIN ORDER -- "ASSY-77 H10-D-map.pdf" (Probe_Playground/).
   Which connector pin sits at which slot down each shank. Transcribed into
   BACK_PIN_SLOTS / FRONT_PIN_SLOTS below and then validated against the
   probeinterface geometry (see check_geometry).

3. HARDWARE MAP -- Config files/H10_D_open_Cheetah2026-07-21_16-59-03.cfg.
   `-SetChannelNumber "CSCn" <hw>` gives the Neuralynx AD channel feeding
   each CSC. Treated as infallible.

4. SCREEN LAYOUT -- Probe_Playground/screen_details.txt.
   The six Cheetah display windows, each of which is one physical column of
   one shank, listed top -> tip. Used as an independent end-to-end check
   (see check_screen_layout); this is what pins down the direction of travel
   and resolves CSC32.

THE NUMBER JOURNEY
------------------
    stage A  probe pin      vendor connector pin, 1..64      (PDF)
    stage B  NLX AD channel pin + 63                         (headstage wiring)
    stage C  CSC number     -SetChannelNumber, 1..64         (Cheetah cfg)
    stage D  .ncs file      CSCn.ncs                         (disk)
    stage E  binary row     CSC n -> row n-1                 (perpl_NLX2Binary)
    stage F  KS channel     0..63, == binary row             (this file)

TWO POINTS WORTH KNOWING
------------------------
* Skipped row. Each shank has 23 slot positions but only 22 are occupied:
  slot 21 (15 um above the tip) is empty, so the tip contact sits 30 um below
  its neighbour, not 15 um. probeinterface shows this directly -- y = 15 is
  absent from the unique y values. An earlier version of this script used flat
  22-entry pin lists, which collapsed that gap and placed both tip contacts
  15 um too shallow. The empty slot is now explicit (`None`) and is verified
  against probeinterface at runtime.

* CSC32. Its AD channel is 60, the only CSC outside the 64..127 block the
  other 63 occupy, and it is the only CSC carrying its own
  `-SetAcqEntReference`. So `pin = hw - 63` does not decode it. It is
  nonetheless a real recording site: AD channel 111 (= pin 48, the back-shank
  tip) is used by nothing in the config, leaving pin 48 as the single
  unclaimed site, and the screen layout puts CSC32 at the bottom of window W1
  -- the back-shank centre column -- where it completes an otherwise perfect
  uniform 30 um ladder of 12 contacts. It is the back tip, routed differently
  (hence the odd AD number and its own reference). Do NOT mark it bad.

COORDINATE CONVENTION
---------------------
y is HEIGHT ABOVE THE TIP, matching probeinterface and the usual Kilosort /
Neuropixels convention: y = 0 is the tip, y = 330 is the topmost contact.
Note this is flipped relative to the earlier revision of this file, which
used depth-from-top.

Outputs (next to this script):
    probe_config_H10D.prb                -- Kilosort probe file
    probe_config_H10D_channel_table.csv  -- full per-channel journey table
    probe_config_H10D_journey.png        -- the journey figure
    assy77_h10_geometry.json             -- cached probeinterface geometry

Requires probeinterface to regenerate the geometry cache (the `toothy_env`
conda env has it). If probeinterface is unavailable the cached JSON is used.
"""

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CONFIG_DIR = HERE.parent / "Config files"
H10_CFG = CONFIG_DIR / "H10_D_open_Cheetah2026-07-21_16-59-03.cfg"
GEOMETRY_CACHE = HERE / "assy77_h10_geometry.json"

MANUFACTURER = "cambridgeneurotech"
PROBE_MODEL = "ASSY-77-H10"

N_CH = 64
HW_OFFSET = 63

# CSC32 does not decode via `pin = hw - 63`; see module docstring.
SPECIAL_CSC = {32: 48}

# ---------------------------------------------------------------------------
# Stage A: connector pin order down each shank, transcribed from the PDF.
# One entry per slot, top -> tip. A single pin is a centre-column contact; a
# pair is (left, right); None is a slot with no contact.
# ---------------------------------------------------------------------------
BACK_PIN_SLOTS = [
    21, (41, 32), 43, (42, 28), 23, (44, 22), 24, (35, 26), 30, (36, 25),
    29, (49, 17), 16, (47, 19), 37, (45, 27), 33, (38, 20), 39, (46, 18),
    40, None, 48,
]
FRONT_PIN_SLOTS = [
    64, (5, 59), 2, (3, 61), 62, (1, 63), 60, (7, 57), 58, (9, 55),
    56, (11, 53), 54, (13, 51), 4, (15, 34), 6, (31, 50), 8, (14, 52),
    10, None, 12,
]

# Stage D/E cross-check: the six Cheetah display windows, top -> tip.
SCREEN_WINDOWS = {
    "W1": [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 32],
    "W3": [2, 5, 8, 11, 14, 17, 20, 23, 26, 29],
    "W4": [3, 6, 9, 12, 15, 18, 21, 24, 27, 30],
    "W2": [33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 64],
    "W6": [34, 37, 40, 43, 46, 49, 52, 55, 58, 61],
    "W5": [35, 38, 41, 44, 47, 50, 53, 56, 59, 62],
}


# ---------------------------------------------------------------------------
# Geometry, straight from probeinterface
# ---------------------------------------------------------------------------
def load_geometry():
    """Contact positions for ASSY-77-H10, from probeinterface (cached to JSON)."""
    try:
        import probeinterface as pi
    except ImportError:
        if not GEOMETRY_CACHE.exists():
            sys.exit(
                "probeinterface is not importable and no geometry cache exists at\n"
                f"  {GEOMETRY_CACHE}\n"
                "Run this once under an env that has probeinterface (e.g. toothy_env)."
            )
        print(f"probeinterface unavailable -- using cache {GEOMETRY_CACHE.name}")
        return json.loads(GEOMETRY_CACHE.read_text())

    probe = pi.get_probe(MANUFACTURER, PROBE_MODEL)
    df = probe.to_dataframe()
    geo = {
        "source": f"probeinterface {pi.__version__} :: {MANUFACTURER}/{PROBE_MODEL}",
        "positions": [[float(x), float(y)] for x, y in probe.contact_positions],
        "shank_ids": [str(s) for s in probe.shank_ids],
        "width": float(df["width"].iloc[0]),
        "height": float(df["height"].iloc[0]),
    }
    GEOMETRY_CACHE.write_text(json.dumps(geo, indent=2))
    return geo


def describe_geometry(geo):
    """Derive shanks, columns, slot pitch and the empty slot from the positions alone."""
    pos = np.asarray(geo["positions"], dtype=float)
    xs = np.unique(np.round(pos[:, 0], 3))
    ys = np.unique(np.round(pos[:, 1], 3))

    # Two shanks: split x on the largest gap between adjacent unique x values.
    gaps = np.diff(xs)
    split = int(np.argmax(gaps)) + 1
    back_x, front_x = xs[:split], xs[split:]
    if len(back_x) != 3 or len(front_x) != 3:
        raise RuntimeError(f"expected 3 columns per shank, got {back_x} / {front_x}")

    pitch = float(np.min(np.diff(ys)))          # 15 um
    y_top = float(ys.max())                     # 330 um
    n_slots = int(round(y_top / pitch)) + 1     # 23
    slot_y = [round(y_top - pitch * r, 3) for r in range(n_slots)]
    empty = [r for r, y in enumerate(slot_y) if y not in set(ys)]

    return {
        "pos": pos,
        "cols": {
            "back": {"left": back_x[0], "centre": back_x[1], "right": back_x[2]},
            "front": {"left": front_x[0], "centre": front_x[1], "right": front_x[2]},
        },
        "pitch": pitch,
        "y_top": y_top,
        "slot_y": slot_y,
        "empty_slots": empty,
        "site_w": geo["width"],
        "site_h": geo["height"],
        "unique_y": ys,
    }


def build_pin_positions(g):
    """pin -> (shank, slot, column, x, y). Coordinates come only from `g`."""
    pin_pos = {}
    for shank, slots in (("back", BACK_PIN_SLOTS), ("front", FRONT_PIN_SLOTS)):
        if len(slots) != len(g["slot_y"]):
            raise RuntimeError(
                f"{shank}: {len(slots)} pin slots but probeinterface implies "
                f"{len(g['slot_y'])}"
            )
        cols = g["cols"][shank]
        for slot, entry in enumerate(slots):
            y = g["slot_y"][slot]
            if entry is None:
                continue
            if isinstance(entry, tuple):
                pin_pos[entry[0]] = (shank, slot, "left", cols["left"], y)
                pin_pos[entry[1]] = (shank, slot, "right", cols["right"], y)
            else:
                pin_pos[entry] = (shank, slot, "centre", cols["centre"], y)
    return pin_pos


def check_geometry(pin_pos, g):
    """The pin layout must reproduce probeinterface's contact set exactly."""
    if sorted(pin_pos) != list(range(1, N_CH + 1)):
        raise RuntimeError("pin slots do not cover pins 1..64 exactly once")

    built = sorted((round(x, 3), round(y, 3)) for _, _, _, x, y in pin_pos.values())
    truth = sorted((round(x, 3), round(y, 3)) for x, y in g["pos"])
    if built != truth:
        only_built = set(built) - set(truth)
        only_truth = set(truth) - set(built)
        raise RuntimeError(
            "pin layout does not reproduce probeinterface geometry\n"
            f"  only in layout:        {sorted(only_built)}\n"
            f"  only in probeinterface:{sorted(only_truth)}"
        )
    print(f"[ok] 64 pin slots reproduce probeinterface {PROBE_MODEL} geometry exactly")
    print(f"[ok] slot pitch {g['pitch']:g} um, top contact y={g['y_top']:g} um, "
          f"empty slot(s) {g['empty_slots']} (y={[g['slot_y'][r] for r in g['empty_slots']]})")


# ---------------------------------------------------------------------------
# Stages B/C: the Neuralynx config
# ---------------------------------------------------------------------------
def parse_channel_map(cfg_path):
    pattern = re.compile(r'-SetChannelNumber\s+"CSC(\d+)"\s+(\d+)')
    mapping = {}
    for line in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = pattern.search(line)
        if m and int(m.group(1)) <= N_CH:
            mapping[int(m.group(1))] = int(m.group(2))
    if sorted(mapping) != list(range(1, N_CH + 1)):
        raise RuntimeError(f"expected CSC1..CSC{N_CH} in {cfg_path.name}")
    return mapping


def resolve_pins(hw_map):
    """CSC -> pin, via `pin = hw - 63` plus the documented CSC32 special case."""
    pin_of = {}
    for csc, hw in hw_map.items():
        pin = SPECIAL_CSC.get(csc, hw - HW_OFFSET)
        pin_of[csc] = pin
    if sorted(pin_of.values()) != list(range(1, N_CH + 1)):
        raise RuntimeError("CSC -> pin map is not a bijection onto pins 1..64")
    print(f"[ok] 64 CSCs map onto pins 1..64 bijectively "
          f"(special case: {', '.join(f'CSC{c}->pin{p}' for c, p in SPECIAL_CSC.items())})")
    return pin_of


def check_screen_layout(rows_by_csc, g):
    """Each Cheetah window must be one shank, one column, uniform, top -> tip."""
    expected_step = 2 * g["pitch"]
    for win, cscs in SCREEN_WINDOWS.items():
        entries = [rows_by_csc[c] for c in cscs]
        shanks = {e["shank"] for e in entries}
        xs = {round(e["x"], 3) for e in entries}
        ys = [e["y"] for e in entries]
        steps = {round(ys[i] - ys[i + 1], 3) for i in range(len(ys) - 1)}
        if len(shanks) != 1 or len(xs) != 1:
            raise RuntimeError(f"{win} spans {shanks} / x={xs}; expected one column")
        if steps != {expected_step}:
            raise RuntimeError(f"{win} spacing {sorted(steps)} != {expected_step} um")
        if ys != sorted(ys, reverse=True):
            raise RuntimeError(f"{win} is not ordered top -> tip")
    print(f"[ok] all 6 screen windows resolve to a single shank + column, "
          f"ordered top -> tip at a uniform {expected_step:g} um")


def build_rows(hw_map, pin_of, pin_pos):
    win_of = {csc: w for w, cscs in SCREEN_WINDOWS.items() for csc in cscs}
    rows = []
    for csc in range(1, N_CH + 1):
        pin = pin_of[csc]
        shank, slot, column, x, y = pin_pos[pin]
        rows.append({
            "channel": csc - 1,          # stage F: Kilosort channel (0-based)
            "csc": csc,                  # stage C
            "ncs": f"CSC{csc}.ncs",      # stage D
            "hw": hw_map[csc],           # stage B
            "pin": pin,                  # stage A
            "shank": shank,
            "slot": slot,
            "column": column,
            "window": win_of[csc],
            "x": round(float(x), 1),
            "y": round(float(y), 1),
            "decoded": csc not in SPECIAL_CSC,
        })
    return rows


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
def write_prb(rows, g, out_path):
    """Two channel groups, one per shank -> kcoords 0/1.

    Kilosort4's `template_centers` walks `kcoords` shank by shank and spreads
    template x-positions over each shank's own x-range. With a single group the
    range would span 0..187 um and scatter template positions across the 150 um
    dead gap between the shanks, so the split is deliberate.
    """
    by_shank = {"back": [], "front": []}
    for r in rows:
        by_shank[r["shank"]].append(r)

    L = []
    L.append("# probe_config_H10D.prb")
    L.append(f"# Cambridge NeuroTech {PROBE_MODEL} (H10-D), 64 ch, 2 shanks x 32.")
    L.append("#")
    L.append(f"# Geometry     : probeinterface {MANUFACTURER}/{PROBE_MODEL} (authoritative)")
    L.append("# Pin order    : ASSY-77 H10-D-map.pdf")
    L.append(f"# Hardware map : {H10_CFG.name}")
    L.append("# Verified vs  : screen_details.txt (6 Cheetah display windows)")
    L.append("#")
    L.append("# Journey: probe pin --(+63)--> NLX AD ch --> CSCn --> CSCn.ncs")
    L.append("#          --> binary row n-1 --> Kilosort channel n-1")
    L.append("#")
    L.append("# y is HEIGHT ABOVE THE TIP (y=0 tip, y=330 topmost), matching")
    L.append("# probeinterface. This is flipped vs. the earlier revision of this file.")
    L.append("#")
    L.append(f"# Slot pitch {g['pitch']:g} um. Each shank has {len(g['slot_y'])} slots but only")
    L.append(f"# {len(g['slot_y']) - len(g['empty_slots'])} contacts: slot(s) "
             f"{g['empty_slots']} (y={[g['slot_y'][r] for r in g['empty_slots']]}) are empty, so")
    L.append("# each tip contact sits 30 um below its neighbour, not 15 um.")
    L.append("#")
    L.append("# All 64 channels resolve to a real contact. CSC32 (AD ch 60) does not")
    L.append("# decode via pin = hw-63, but is the back-shank tip (pin 48): AD ch 111")
    L.append("# is unused, pin 48 is the only unclaimed site, and the screen layout")
    L.append("# places CSC32 at the bottom of the back centre column. Not a bad channel.")
    L.append("#")
    L.append("# Groups are shanks: 0 = back (ch 0-31), 1 = front (ch 32-63).")
    L.append("")
    L.append("channel_groups = {")
    for gid, shank in enumerate(("back", "front")):
        srows = by_shank[shank]
        chans = ", ".join(str(r["channel"]) for r in srows)
        L.append(f"    {gid}: {{  # {shank} shank")
        L.append(f"        'channels': [{chans}],")
        L.append("        'geometry': {")
        for r in sorted(srows, key=lambda r: -r["y"]):
            note = f"  # pin {r['pin']:>2}  AD {r['hw']:>3}  CSC{r['csc']:<2} {r['window']} {r['column']}"
            if not r["decoded"]:
                note += "  <- see header"
            L.append(f"            {r['channel']}: ({r['x']}, {r['y']}),{note}")
        L.append("        },")
        L.append("        'graph': [],")
        L.append("    },")
    L.append("}")
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {out_path.name}")


def write_csv(rows, out_path):
    cols = ["ks_channel_0based", "binary_row", "ncs_file", "csc", "nlx_ad_channel",
            "probe_pin", "shank", "kcoords", "column", "screen_window",
            "slot_from_top", "x_um", "y_um_above_tip", "decode"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([
                r["channel"], r["channel"], r["ncs"], f"CSC{r['csc']}", r["hw"],
                r["pin"], r["shank"], 0 if r["shank"] == "back" else 1, r["column"],
                r["window"], r["slot"], r["x"], r["y"],
                "hw-63" if r["decoded"] else "special (see header)",
            ])
    print(f"Wrote {out_path.name}")


# ---------------------------------------------------------------------------
# The journey figure
# ---------------------------------------------------------------------------
# stage key: (field, title, subtitle, fill, stroke, text)
STAGES = [
    ("pin", "Probe pin", "vendor map", "#F6E7CE", "#A8701A", "#7A5010"),
    ("hw", "NLX AD ch", "Cheetah cfg", "#DCE7F5", "#2E6BA8", "#1D4F80"),
    ("csc", "CSC / .ncs", "acquisition", "#E5DEF3", "#6B4BA8", "#4E3480"),
    ("ks", "KS channel", "this .prb", "#D8E9DD", "#2F7D57", "#1E5C3D"),
]
COL_TINT = {"left": "#6E93BE", "centre": "#C98A45", "right": "#6D9C7C"}

INK, MUTED, HAIR = "#16202B", "#6A7480", "#DDE2E8"
ALERT = "#B3261E"

# Block metrics in axes units. Every rounded box is drawn with boxstyle
# pad=0, so its drawn extent equals the rect it is given and arrow endpoints
# can be computed exactly rather than guessed.
CX = [0.105, 0.315, 0.525, 0.735]
CW, CH = 0.148, 0.60
BAND_Y0, BAND_H = -2.70, 1.00
HDR_Y, RULE_Y = -1.06, -0.74
YLIM = (12.9, -2.85)


def _chip(ax, x, y, w, h, fill, stroke, lw=0.9, z=2):
    from matplotlib.patches import FancyBboxPatch
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.028",
        facecolor=fill, edgecolor=stroke, linewidth=lw, zorder=z)
    ax.add_patch(patch)
    return patch


def build_figure(rows, g, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Polygon

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Corbel", "Arial", "DejaVu Sans"],
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "axes.linewidth": 0.8,
    })

    by_csc = {r["csc"]: r for r in rows}

    fig = plt.figure(figsize=(24.5, 16.0), dpi=200)
    fig.patch.set_facecolor("white")
    outer = fig.add_gridspec(
        2, 2, width_ratios=[1.16, 3.0], height_ratios=[0.10, 1.0],
        left=0.030, right=0.984, top=0.915, bottom=0.028, hspace=0.10, wspace=0.045,
    )

    fig.text(0.030, 0.985, "ASSY-77 H10-D — identity of every recording site",
             fontsize=23, weight=600, color=INK, va="top")
    fig.text(0.030, 0.9605,
             "Contact geometry from probeinterface (cambridgeneurotech/ASSY-77-H10); "
             "connector-pin order from the vendor map; AD channels from "
             "H10_D_open_Cheetah2026-07-21_16-59-03.cfg.",
             fontsize=12, weight=400, color=MUTED, va="top")

    # ---- stage key --------------------------------------------------------
    ax = fig.add_subplot(outer[0, :])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    bw, step, x0, by, bh = 0.128, 0.185, 0.040, 0.24, 0.46
    trans = ["+ 63", "-SetChannelNumber", "row n−1 of CSC_Raw.dat"]
    for i, (_, title, sub, fill, stroke, txt) in enumerate(STAGES):
        x = x0 + i * step
        _chip(ax, x, by, bw, bh, fill, stroke, lw=1.3)
        ax.text(x + bw / 2, by + bh * 0.63, title, ha="center", va="center",
                fontsize=12.5, weight=600, color=txt)
        ax.text(x + bw / 2, by + bh * 0.26, sub, ha="center", va="center",
                fontsize=9.8, weight=400, color=txt, alpha=0.78)
        if i < 3:
            a, b = x + bw + 0.009, x + step - 0.009
            ax.annotate("", xy=(b, by + bh / 2), xytext=(a, by + bh / 2),
                        arrowprops=dict(arrowstyle="-|>,head_width=0.16,head_length=0.34",
                                        color="#98A2AE", lw=1.1, shrinkA=0, shrinkB=0))
            ax.text((a + b) / 2, by + bh / 2 + 0.19, trans[i], ha="center", va="bottom",
                    fontsize=9.5, weight=400, style="italic", color=MUTED)

    _chip(ax, 0.775, 0.16, 0.222, 0.66, "#FBF0E6", "#C98A45", lw=1.1)
    ax.text(0.786, 0.49,
            "CSC32 is the one site not given by pin = AD − 63.\n"
            "AD 111 is unused and pin 48 unclaimed, and window W1\n"
            "places CSC32 at the tip — so it is the back-shank tip.",
            fontsize=10, weight=400, color="#7A5010", va="center", linespacing=1.62)

    # ---- panel a: probe map ----------------------------------------------
    ax = fig.add_subplot(outer[1, 0])
    ax.set_facecolor("white")
    cols = g["cols"]
    for shank, lbl in (("back", "Back shank"), ("front", "Front shank")):
        c = cols[shank]
        xc, half = c["centre"], (c["right"] - c["left"]) / 2 + 15
        ax.add_patch(Polygon(
            [(xc - half, g["y_top"] + 24), (xc + half, g["y_top"] + 24),
             (xc + half, 24), (xc, -15), (xc - half, 24)],
            closed=True, facecolor="#F4F6F9", edgecolor="#AFB8C4", lw=1.2, zorder=1))
        ax.text(xc, g["y_top"] + 38, lbl, ha="center", fontsize=12.5, weight=600, color=INK)
        ax.text(xc, g["y_top"] + 26, f"kcoords {0 if shank == 'back' else 1}",
                ha="center", fontsize=9.5, weight=400, color=MUTED)

    for yy in np.arange(0, g["y_top"] + 1, 30):
        ax.axhline(yy, color=HAIR, lw=0.5, zorder=0)

    y_empty = g["slot_y"][g["empty_slots"][0]]
    for shank in ("back", "front"):
        ax.add_patch(Rectangle(
            (cols[shank]["centre"] - g["site_w"] / 2, y_empty - g["site_h"] / 2),
            g["site_w"], g["site_h"], facecolor="none", edgecolor=ALERT,
            lw=1.1, ls=(0, (2.2, 2.2)), zorder=3))
        ax.plot([cols[shank]["centre"], cols[shank]["centre"]], [y_empty - 9, -52],
                color=ALERT, lw=0.8, ls=(0, (2.2, 2.2)), zorder=3)
    gap_x = (cols["back"]["right"] + cols["front"]["left"]) / 2
    ax.plot([cols["back"]["centre"], cols["front"]["centre"]], [-52, -52],
            color=ALERT, lw=0.8, zorder=3)
    ax.text(gap_x, -60,
            f"slot {g['empty_slots'][0]} (y = {y_empty:g} µm) carries no contact on either\n"
            "shank, so each tip sits 30 µm below its neighbour, not 15 µm",
            ha="center", va="top", fontsize=9.5, weight=400, color=ALERT, linespacing=1.6)

    for r in rows:
        ax.add_patch(Rectangle(
            (r["x"] - g["site_w"] / 2, r["y"] - g["site_h"] / 2),
            g["site_w"], g["site_h"], facecolor=COL_TINT[r["column"]],
            edgecolor=ALERT if not r["decoded"] else "#2B3A4D",
            lw=1.9 if not r["decoded"] else 0.4, zorder=4))
        ax.text(r["x"], r["y"], str(r["channel"]), ha="center", va="center",
                fontsize=6.2, weight=600, color="white", zorder=5)

    ax.set_xlim(-30, 220)
    ax.set_ylim(-116, g["y_top"] + 52)
    ax.set_aspect("equal")
    ax.set_anchor("N")
    ax.set_ylabel("y — height above tip (µm)", fontsize=11, weight=400, color=MUTED)
    ax.set_yticks(np.arange(0, g["y_top"] + 1, 30))
    ax.set_xticks([cols[s][c] for s in ("back", "front") for c in ("left", "centre", "right")])
    ax.set_xticklabels([f"{cols[s][c]:g}" for s in ("back", "front")
                        for c in ("left", "centre", "right")], fontsize=8.5)
    ax.set_xlabel("x (µm)", fontsize=11, weight=400, color=MUTED, labelpad=2)
    ax.tick_params(labelsize=9, colors=MUTED, length=3, width=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(HAIR)

    # ---- panel b: six display windows ------------------------------------
    inner = outer[1, 1].subgridspec(2, 3, hspace=0.135, wspace=0.085)
    order = [("W1", "back", "centre"), ("W3", "back", "left"), ("W4", "back", "right"),
             ("W2", "front", "centre"), ("W6", "front", "left"), ("W5", "front", "right")]
    heads = ["PIN", "AD CH", "CSC", "KS CH"]

    for k, (win, shank, column) in enumerate(order):
        a = fig.add_subplot(inner[k // 3, k % 3])
        a.set_xlim(0, 1)
        a.set_ylim(*YLIM)
        a.axis("off")
        cscs = SCREEN_WINDOWS[win]
        tint = COL_TINT[column]

        band = _chip(a, 0.012, BAND_Y0, 0.976, BAND_H, tint, "none", lw=0)
        band.set_alpha(0.20)
        a.add_patch(Rectangle((0.012, BAND_Y0), 0.0075, BAND_H,
                              facecolor=tint, edgecolor="none", zorder=3))
        cy = BAND_Y0 + BAND_H / 2
        a.text(0.040, cy, win, fontsize=14, weight=700, color=INK, va="center")
        a.text(0.108, cy,
               f"{shank} shank  ·  {column} column  ·  "
               f"x = {by_csc[cscs[0]]['x']:g} µm",
               fontsize=10.2, weight=400, color="#38424F", va="center")
        a.text(0.988, cy, "top ↓ tip", fontsize=9.5, weight=400, style="italic",
               color=MUTED, va="center", ha="right")

        for j, h in enumerate(heads):
            a.text(CX[j], HDR_Y, h, ha="center", va="center", fontsize=8.8,
                   weight=600, color=STAGES[j][5], alpha=0.85)
        a.plot([0.012, 0.988], [RULE_Y, RULE_Y], color=HAIR, lw=0.8, zorder=1)

        for i, csc in enumerate(cscs):
            r = by_csc[csc]
            tip = (i == len(cscs) - 1)
            if tip:
                a.add_patch(Rectangle((0.012, i - 0.44), 0.976, 0.88,
                                      facecolor=tint, alpha=0.13, edgecolor="none", zorder=0))
                a.add_patch(Rectangle((0.012, i - 0.44), 0.0075, 0.88,
                                      facecolor=tint, edgecolor="none", zorder=1))
            vals = [r["pin"], r["hw"], r["csc"], r["channel"]]
            for j, (stage, v) in enumerate(zip(STAGES, vals)):
                _, _, _, fill, stroke, txt = stage
                flag = (not r["decoded"]) and j < 2
                _chip(a, CX[j] - CW / 2, i - CH / 2, CW, CH, fill,
                      ALERT if flag else stroke, lw=1.9 if flag else 0.9)
                a.text(CX[j], i, str(v), ha="center", va="center",
                       fontsize=11, weight=600, color=txt, zorder=3)
                if j < 3:
                    a.annotate("", xy=(CX[j + 1] - CW / 2 - 0.010, i),
                               xytext=(CX[j] + CW / 2 + 0.010, i),
                               arrowprops=dict(arrowstyle="-|>,head_width=0.13,head_length=0.30",
                                               color="#B6BEC8", lw=0.9, shrinkA=0, shrinkB=0))
            a.text(0.988, i, f"y = {r['y']:g} µm", ha="right", va="center",
                   fontsize=9, weight=600 if tip else 400, color=INK if tip else MUTED)

    fig.text(0.030, 0.802, "a", fontsize=17, weight=700, color=INK, va="bottom")
    fig.text(0.047, 0.8035,
             "Kilosort channel index at each contact, to scale, from probeinterface",
             fontsize=11.5, weight=400, color=MUTED, va="bottom")
    fig.text(0.292, 0.802, "b", fontsize=17, weight=700, color=INK, va="bottom")
    fig.text(0.309, 0.8035,
             "each block is one Cheetah display window = one physical column of one "
             "shank; shaded row = deepest contact, which meets signal first",
             fontsize=11.5, weight=400, color=MUTED, va="bottom")

    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    fig.savefig(out_path.with_suffix(".pdf"), facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path.name} and {out_path.with_suffix('.pdf').name}")


def main():
    geo = load_geometry()
    print(f"Geometry source: {geo['source']}")
    g = describe_geometry(geo)

    pin_pos = build_pin_positions(g)
    check_geometry(pin_pos, g)

    hw_map = parse_channel_map(H10_CFG)
    pin_of = resolve_pins(hw_map)

    rows = build_rows(hw_map, pin_of, pin_pos)
    check_screen_layout({r["csc"]: r for r in rows}, g)

    write_prb(rows, g, HERE / "probe_config_H10D.prb")
    write_csv(rows, HERE / "probe_config_H10D_channel_table.csv")
    build_figure(rows, g, HERE / "probe_config_H10D_journey.png")


if __name__ == "__main__":
    main()
