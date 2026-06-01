import csv
from pathlib import Path

INPUT  = r"c:\Users\Z390\Desktop\jeremystats\Colony Management\VOS Exports\VOS Report to CSV\VOS Report 052226.csv"
STAMP  = "052226"

# Columns to pull first (renamed with date stamp), in desired order
FRONT = [
    ("Extracted Sorting ID", f"Extracted Sorting ID {STAMP}"),
    ("Cage Card",            f"Cage Card {STAMP}"),
    ("DOB",                  f"DOB {STAMP}"),
    ("Sex",                  f"Sex {STAMP}"),
]
FRONT_ORIG = [orig for orig, _ in FRONT]

p = Path(INPUT)
out_path = p.parent / f"{p.stem}_reformatted.csv"

with open(p, newline="", encoding="utf-8-sig") as fin, \
     open(out_path, "w", newline="", encoding="utf-8-sig") as fout:

    reader = csv.DictReader(fin)
    rest   = [c for c in reader.fieldnames if c not in FRONT_ORIG]
    out_fields = [new for _, new in FRONT] + rest

    writer = csv.DictWriter(fout, fieldnames=out_fields)
    writer.writeheader()

    for row in reader:
        new_row = {new: row[orig] for orig, new in FRONT}
        new_row.update({c: row[c] for c in rest})
        writer.writerow(new_row)

print(f"Saved: {out_path}")
