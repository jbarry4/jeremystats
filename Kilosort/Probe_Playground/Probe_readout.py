"""
Dumps every probe geometry available in the probeinterface vendor library
(https://github.com/SpikeInterface/probeinterface_library) to a text file,
grouped by manufacturer.

Usage:
    python Probe_readout.py [output_path]

To actually load a probe's geometry for a Kilosort channel map:
    import probeinterface as pi
    probe = pi.get_probe('cambridgeneurotech', 'ASSY-77-H2')
"""

import sys
from pathlib import Path

import probeinterface as pi

# Folders in the library repo that are not manufacturers (tooling, docs, etc.)
NON_MANUFACTURER_FOLDERS = {"apps", "scripts"}

DEFAULT_OUTPUT = Path(__file__).parent / "probe_configs.txt"


def write_probe_catalog(output_path: Path) -> None:
    all_probes = pi.list_all_probes()

    manufacturers = sorted(m for m in all_probes if m not in NON_MANUFACTURER_FOLDERS)
    total_probes = sum(len(all_probes[m]) for m in manufacturers)

    lines = [
        "probeinterface probe catalog",
        f"manufacturers: {len(manufacturers)}  |  total probes: {total_probes}",
        "",
    ]

    for manufacturer in manufacturers:
        probe_names = sorted(all_probes[manufacturer])
        lines.append(f"[{manufacturer}] ({len(probe_names)})")
        for name in probe_names:
            lines.append(f"    {name}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {total_probes} probes across {len(manufacturers)} manufacturers to {output_path}")


if __name__ == "__main__":
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    write_probe_catalog(out_path)
