import argparse
from pathlib import Path

import h5py
import numpy as np


def collect_groups_with_timestamps(h5file):
    groups = []

    def visit(name, obj):
        if isinstance(obj, h5py.Group):
            if "DS1_timestamps_sec" in obj and "DS2_timestamps_sec" in obj:
                groups.append(name)

    h5file.visititems(visit)
    return groups


def copy_group_structure(source_group, target_group):
    for name, obj in source_group.items():
        if isinstance(obj, h5py.Group):
            target_group.create_group(name)
        else:
            target_group.create_dataset(name, data=obj[()])


def combine_timestamps(group):
    ds1 = group["DS1_timestamps_sec"][()]
    ds2 = group["DS2_timestamps_sec"][()]
    if ds1.ndim != 1 or ds2.ndim != 1:
        raise ValueError(
            f"Expected DS1_timestamps_sec and DS2_timestamps_sec to be 1D arrays, got {ds1.shape} and {ds2.shape}"
        )
    return np.concatenate((ds1, ds2))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Combine DS1_timestamps_sec and DS2_timestamps_sec into "
            "Combined_DS_timestamps_sec for all matching groups, then save into a new HDF5 file."
        )
    )
    parser.add_argument(
        "input_hdf5",
        nargs="?",
        default="manual-only_bulk_pca_results.hdf5",
        help="Input HDF5 file path (default: manual-only_bulk_pca_results.hdf5).",
    )
    parser.add_argument(
        "output_hdf5",
        nargs="?",
        default="manual-only_bulk_pca_results_DS_combined.hdf5",
        help="Output HDF5 file path (default: manual-only_bulk_pca_results_DS_combined.hdf5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching groups without writing the output file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_hdf5)
    output_path = Path(args.output_hdf5)

    if not input_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {input_path}")

    with h5py.File(input_path, "r") as source:
        groups = collect_groups_with_timestamps(source)
        if not groups:
            print("No groups containing both DS1_timestamps_sec and DS2_timestamps_sec were found.")
            return

        print(f"Found {len(groups)} groups to process:")
        for group_name in groups:
            print(f"  {group_name}")

        if args.dry_run:
            print("Dry run complete. No output file created.")
            return

        if output_path.exists():
            output_path.unlink()

        with h5py.File(output_path, "w") as target:
            for group_name in groups:
                source_group = source[group_name]
                target_group = target.create_group(group_name)
                copy_group_structure(source_group, target_group)
                combined = combine_timestamps(source_group)
                if "Combined_DS_timestamps_sec" in target_group:
                    del target_group["Combined_DS_timestamps_sec"]
                target_group.create_dataset("Combined_DS_timestamps_sec", data=combined)
                print(f"Created Combined_DS_timestamps_sec in {group_name}")

        print(f"Saved combined results to {output_path}")


if __name__ == "__main__":
    main()
