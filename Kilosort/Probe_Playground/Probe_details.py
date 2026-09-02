"""
Dumps full geometric/config details for a single probeinterface probe
(manufacturer, name, shank/contact layout, per-contact coordinates) to a
text file. Useful for building a Kilosort channel map.

Usage:
    python Probe_details.py [manufacturer] [probe_name] [output_path]

Defaults to cambridgeneurotech / ASSY-77-H10.
"""

import sys
from pathlib import Path

import probeinterface as pi

DEFAULT_MANUFACTURER = "cambridgeneurotech"
DEFAULT_PROBE_NAME = "ASSY-77-H10"


def write_probe_details(manufacturer: str, probe_name: str, output_path: Path) -> None:
    probe = pi.get_probe(manufacturer, probe_name)
    df = probe.to_dataframe()

    lines = [
        f"Probe: {manufacturer} / {probe_name}",
        f"ndim: {probe.ndim}   units: {probe.si_units}",
        f"contacts: {probe.get_contact_count()}   shanks: {df['shank_ids'].nunique()}",
        f"annotations: {probe.annotations}",
        "",
        "per-contact layout:",
        df.to_string(index=False),
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote details for {manufacturer}/{probe_name} to {output_path}")


if __name__ == "__main__":
    manufacturer = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MANUFACTURER
    probe_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROBE_NAME
    out_path = (
        Path(sys.argv[3])
        if len(sys.argv) > 3
        else Path(__file__).parent / f"probe_details_{probe_name}.txt"
    )
    write_probe_details(manufacturer, probe_name, out_path)
