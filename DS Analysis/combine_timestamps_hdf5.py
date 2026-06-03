import argparse
from pathlib import Path

import h5py


def move_combined_dataset_up(h5file):
    candidates = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.endswith("/Combined_DS_timestamps_sec"):
            group_path = name.rsplit("/", 1)[0]
            if group_path.endswith("/manual"):
                parent_path = group_path.rsplit("/", 1)[0]
                if parent_path == "":
                    parent_path = "/"
                candidates.append((group_path, parent_path, obj[()], dict(obj.attrs)))

    h5file.visititems(visit)

    moved = []
    for group_path, parent_path, data, attrs in candidates:
        source_group = h5file[group_path]
        parent_group = h5file[parent_path]

        if "Combined_DS_timestamps_sec" in parent_group:
            del parent_group["Combined_DS_timestamps_sec"]

        target_ds = parent_group.create_dataset("Combined_DS_timestamps_sec", data=data)
        for key, value in attrs.items():
            target_ds.attrs[key] = value

        del source_group["Combined_DS_timestamps_sec"]
        moved.append((group_path, parent_path))

    return moved


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Move Combined_DS_timestamps_sec from any manual subgroup up to its parent group "
            "inside an HDF5 file."
        )
    )
    parser.add_argument(
        "input_hdf5",
        nargs="?",
        default="manual-only_bulk_pca_results_DS_combined.hdf5",
        help="Input HDF5 file path (default: manual-only_bulk_pca_results_DS_combined.hdf5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the datasets that would be moved without modifying the file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_hdf5)
    if not input_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {input_path}")

    mode = "r" if args.dry_run else "a"
    with h5py.File(input_path, mode) as h5file:
        moved = move_combined_dataset_up(h5file)

        if moved:
            print("Moved Combined_DS_timestamps_sec from manual subgroups to parent groups:")
            for old_group, new_group in moved:
                print(f"  {old_group} -> {new_group}")
        else:
            print("No Combined_DS_timestamps_sec datasets found inside manual groups.")

        if args.dry_run and moved:
            print("Dry run complete. No changes were written.")


if __name__ == "__main__":
    main()
