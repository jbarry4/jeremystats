"""
Smoke test / extraction script for a KiloSort4 + Phy output directory.

Reproduces exactly what Phy's cluster view shows in the "ch" column:
  - For each cluster, find its dominant template (the template with the most
    spikes assigned to it), matching phy.apps.base.get_template_for_cluster.
  - Take that template's best channel (the channel with max peak-to-peak
    amplitude in the unwhitened template), matching
    phy.apps.template.gui.TemplateController.get_best_channels via
    phylib.io.model.TemplateModel.get_template / _find_best_channels.
  - Map the internal channel index through channel_mapping (== channel_map.npy)
    to get the label phy displays, matching
    phy.apps.base.BaseController._get_channel_labels.

Then adds +1 to convert from Phy's 0-indexed channel numbering to 1-indexed.

Usage:
    python extract_cluster_channels.py <kilosort_dir> [output_csv_path]

If output_csv_path is omitted, the CSV is written next to this script.
"""

import sys
import csv
from pathlib import Path

import numpy as np
from phylib.io.model import load_model

SCRIPT_DIR = Path(__file__).resolve().parent

KS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
PARAMS_PATH = KS_DIR / "params.py"
OUT_CSV = Path(sys.argv[2]) if len(sys.argv) > 2 else SCRIPT_DIR / "cluster_channels.csv"


def get_template_for_cluster(model, cluster_id):
    spike_ids = np.nonzero(model.spike_clusters == cluster_id)[0]
    st = model.spike_templates[spike_ids]
    template_ids, counts = np.unique(st, return_counts=True)
    return int(template_ids[np.argmax(counts)]), len(spike_ids)


def get_best_channel(model, template_id):
    template = model.get_template(template_id)
    # channel_ids is ordered by decreasing amplitude (see phylib.io.model),
    # so the first entry is the best (peak) channel -- same as phy's "ch" column.
    return int(template.channel_ids[0])


def main():
    print(f"Loading model from: {PARAMS_PATH}")
    model = load_model(str(PARAMS_PATH))

    print(f"n_channels        = {model.n_channels}")
    print(f"n_templates        = {model.n_templates}")
    print(f"n_spikes           = {model.n_spikes}")

    cluster_ids = sorted(np.unique(model.spike_clusters).tolist())
    print(f"n_clusters (unique spike_clusters) = {len(cluster_ids)}")

    # Optional group labels, if present, for context (not required by the request).
    group_by_cluster = {}
    group_path = KS_DIR / "cluster_group.tsv"
    if group_path.exists():
        with open(group_path, newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            label_col = [c for c in reader.fieldnames if c != "cluster_id"][0]
            for row in reader:
                group_by_cluster[int(row["cluster_id"])] = row.get(label_col, "")

    rows = []
    for cluster_id in cluster_ids:
        template_id, n_spikes = get_template_for_cluster(model, cluster_id)
        best_channel_idx = get_best_channel(model, template_id)
        channel_label = int(model.channel_mapping[best_channel_idx])  # 0-indexed, as shown in phy's "ch" column
        rows.append({
            "cluster_id": cluster_id,
            "channel": channel_label,
            "channel_1indexed": channel_label + 1,
            "n_spikes": n_spikes,
            "dominant_template_id": template_id,
            "group": group_by_cluster.get(cluster_id, ""),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} clusters to: {OUT_CSV}")
    print("\nFirst 10 rows:")
    for r in rows[:10]:
        print(r)


if __name__ == "__main__":
    main()
