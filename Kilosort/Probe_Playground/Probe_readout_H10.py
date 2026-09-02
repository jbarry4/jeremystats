"""
Dumps only the H10-variant probes from the probeinterface vendor library
(https://github.com/SpikeInterface/probeinterface_library) to a text file,
grouped by manufacturer.

Usage:
    python Probe_readout_H10.py [output_path]
"""

import sys
from pathlib import Path

import probeinterface as pi

NON_MANUFACTURER_FOLDERS = {"apps", "scripts"}
VARIANT_FILTER = "H10"

DEFAULT_OUTPUT = Path(__file__).parent / "probe_configs_H10.txt"


def write_probe_catalog(output_path: Path) -> None:
    all_probes = pi.list_all_probes()

    manufacturers = sorted(m for m in all_probes if m not in NON_MANUFACTURER_FOLDERS)
    filtered = {
        m: sorted(name for name in all_probes[m] if VARIANT_FILTER in name)
        for m in manufacturers
    }
    filtered = {m: names for m, names in filtered.items() if names}
    total_probes = sum(len(names) for names in filtered.values())

    lines = [
        f"probeinterface probe catalog - {VARIANT_FILTER} variants only",
        f"manufacturers: {len(filtered)}  |  total probes: {total_probes}",
        "",
    ]

    for manufacturer, probe_names in filtered.items():
        lines.append(f"[{manufacturer}] ({len(probe_names)})")
        for name in probe_names:
            lines.append(f"    {name}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {total_probes} {VARIANT_FILTER} probes across {len(filtered)} manufacturers to {output_path}")


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    write_probe_catalog(out_path)
