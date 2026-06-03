import argparse
from pathlib import Path

import h5py


def find_auto_groups(h5file):
    auto_paths = []

    def visit(name, obj):
        if isinstance(obj, h5py.Group) and Path(name).name == "auto":
            auto_paths.append(name)

    h5file.visititems(visit)
    return auto_paths


def delete_groups(h5file, paths):
    for path in sorted(paths, key=lambda p: p.count("/"), reverse=True):
        parent_path, group_name = path.rsplit("/", 1)
        parent = h5file[parent_path] if parent_path else h5file
        del parent[group_name]
        print(f"Deleted auto group: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Remove all 'auto' groups from a bulk PCA HDF5 file."
    )
    parser.add_argument(
        "hdf5_path",
        nargs="?",
        default="bulk_pca_results.h5",
        help="Path to the HDF5 file to clean (default: bulk_pca_results.h5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List auto groups without deleting them.",
    )
    args = parser.parse_args()

    hdf5_file = Path(args.hdf5_path)
    if not hdf5_file.exists():
        raise FileNotFoundError(f"HDF5 file not found: {hdf5_file}")

    with h5py.File(hdf5_file, "a") as f:
        auto_groups = find_auto_groups(f)
        if not auto_groups:
            print("No 'auto' groups found.")
            return

        print("Found the following 'auto' groups:")
        for path in auto_groups:
            print(f"  {path}")

        if args.dry_run:
            print("Dry run complete. No changes were made.")
            return

        delete_groups(f, auto_groups)


if __name__ == "__main__":
    main()
