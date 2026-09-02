"""
Sanity-checks a manually built .prb probe config against the probeinterface
vendor library. Compares contact count and (offset-normalized) contact
geometry against every "H3" probe variant in the library, and separately
reports whether the channel-index-to-position ORDER also matches (i.e.
whether the manual channel map uses the same wiring order as the vendor
file, not just the same physical layout).

Usage:
    python Probe_H3_sanity_check.py [prb_path] [output_path]

Defaults to comparing
    Kilosort-4_additional_code/Probes/probe_config.prb
against every cambridgeneurotech *-H3 probe in the library.
"""

import ast
import sys
from pathlib import Path

import probeinterface as pi

DEFAULT_PRB = (
    Path(__file__).resolve().parent.parent
    / "Kilosort-4_additional_code" / "Probes" / "probe_config.prb"
)
VARIANT_FILTER = "H3"


def load_manual_prb(prb_path: Path):
    text = prb_path.read_text(encoding="utf-8")
    prefix = "channel_groups ="
    assert text.strip().startswith(prefix), f"unexpected .prb format in {prb_path}"
    channel_groups = ast.literal_eval(text.strip()[len(prefix):].strip())

    group = next(iter(channel_groups.values()))
    channels = group["channels"]
    geometry = group["geometry"]
    positions = [geometry[ch] for ch in channels]
    return channels, positions


def normalize(positions):
    """Shift positions so the minimum x and y are 0, so a constant probe
    offset (e.g. shank half-width) doesn't cause a false mismatch."""
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    x0, y0 = min(xs), min(ys)
    return [(round(x - x0, 3), round(y - y0, 3)) for x, y in positions]


def find_library_variants(filter_str: str):
    all_probes = pi.list_all_probes()
    matches = []
    for manufacturer, names in all_probes.items():
        for name in names:
            if filter_str in name:
                matches.append((manufacturer, name))
    return matches


def compare(manual_positions, manufacturer, probe_name):
    probe = pi.get_probe(manufacturer, probe_name)
    df = probe.to_dataframe()
    lib_positions = list(zip(df["x"].tolist(), df["y"].tolist()))

    same_count = len(manual_positions) == len(lib_positions)
    same_geometry_set = False
    same_channel_order = False
    if same_count:
        manual_norm = normalize(manual_positions)
        lib_norm = normalize(lib_positions)
        same_geometry_set = set(manual_norm) == set(lib_norm)
        same_channel_order = manual_norm == lib_norm

    return {
        "manufacturer": manufacturer,
        "probe_name": probe_name,
        "lib_contacts": len(lib_positions),
        "same_count": same_count,
        "same_geometry_set": same_geometry_set,
        "same_channel_order": same_channel_order,
    }


def write_report(prb_path: Path, output_path: Path) -> None:
    channels, manual_positions = load_manual_prb(prb_path)
    variants = find_library_variants(VARIANT_FILTER)

    lines = [
        f"Sanity check: {prb_path}",
        f"manual probe: {len(channels)} channels",
        f"comparing against library probes matching '{VARIANT_FILTER}' ({len(variants)} found)",
        "",
    ]

    results = [compare(manual_positions, manufacturer, name) for manufacturer, name in variants]

    for r in results:
        if not r["same_count"]:
            status = f"contact count differs ({r['lib_contacts']} vs {len(channels)})"
        elif r["same_channel_order"]:
            status = "EXACT MATCH (geometry + channel order)"
        elif r["same_geometry_set"]:
            status = "same geometry, DIFFERENT channel order"
        else:
            status = "geometry differs"
        lines.append(f"[{r['manufacturer']}] {r['probe_name']}: {status}")

    exact = [r["probe_name"] for r in results if r["same_channel_order"]]
    geom_only = [r["probe_name"] for r in results if r["same_geometry_set"] and not r["same_channel_order"]]

    lines.append("")
    if exact:
        lines.append("Result: exact match with " + ", ".join(exact))
    elif geom_only:
        lines.append(
            "Result: no exact channel-order match. Same physical layout, different wiring "
            "order found in: " + ", ".join(geom_only)
            + " -- double check the channel map ordering used in the manual .prb."
        )
    else:
        lines.append(f"Result: no match found among library '{VARIANT_FILTER}' variants.")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote sanity check to {output_path}")
    print(lines[-1])


if __name__ == "__main__":
    prb_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PRB
    out_path = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path(__file__).parent / "probe_H3_sanity_check.txt"
    )
    write_report(prb_path, out_path)
