import argparse
from pathlib import Path

import h5py
from scipy.io import savemat


def find_manual_groups(h5file):
    manual_paths = []

    def visit(name, obj):
        if isinstance(obj, h5py.Group) and Path(name).name == "manual":
            manual_paths.append(name)

    h5file.visititems(visit)
    return manual_paths


def delete_groups(h5file, paths):
    for path in sorted(paths, key=lambda p: p.count("/"), reverse=True):
        parent_path, group_name = path.rsplit("/", 1)
        parent = h5file[parent_path] if parent_path else h5file
        del parent[group_name]
        print(f"Deleted manual group: {path}")


def hdf5_group_to_dict(group):
    result = {}
    for name, obj in group.items():
        if isinstance(obj, h5py.Group):
            result[name] = hdf5_group_to_dict(obj)
        else:
            result[name] = obj[()]
    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Remove all groups named 'manual' from an HDF5 file and save the remaining "
            "contents to a MATLAB .mat file."
        )
    )
    parser.add_argument(
        "input_hdf5",
        nargs="?",
        default="manual-only_bulk_pca_results_DS_combined.hdf5",
        help=(
            "Input HDF5 file path (default: manual-only_bulk_pca_results_DS_combined.hdf5)."
        ),
    )
    parser.add_argument(
        "--output-mat",
        default="bulk_pca_results_DS_combined.mat",
        help="Output MATLAB .mat filename (default: bulk_pca_results_DS_combined.mat).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List manual groups without deleting them or creating the MAT file.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_hdf5)
    if not input_path.exists():
        raise FileNotFoundError(f"Input HDF5 file not found: {input_path}")

    with h5py.File(input_path, "r" if args.dry_run else "a") as h5file:
        manual_groups = find_manual_groups(h5file)
        if not manual_groups:
            print("No 'manual' groups found.")
            if args.dry_run:
                return
        else:
            print("Found the following 'manual' groups:")
            for path in manual_groups:
                print(f"  {path}")

        if args.dry_run:
            print("Dry run complete. No changes were made.")
            return

        if manual_groups:
            delete_groups(h5file, manual_groups)

        mat_data = hdf5_group_to_dict(h5file)
        output_mat = Path(args.output_mat)
        savemat(str(output_mat), mat_data, do_compression=True)
        print(f"Saved MATLAB file: {output_mat}")


if __name__ == "__main__":
    main()
