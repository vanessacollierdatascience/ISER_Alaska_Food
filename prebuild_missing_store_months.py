#!/usr/bin/env python3
"""
Prebuild missing store-month CSVs for ACC, FM, and WM.

- ACC: merge all CSVs in ACC_RAW/ACC_YY_MM -> CLEANED_DATA/ACC_YY_MM.csv
- FM: flatten JSON in FM_RAW/FM_YY_MM -> CLEANED_DATA/FM_YY_MM.csv
- WM: merge CSVs in WM_RAW/WM_YY_MM -> CLEANED_DATA/WM_YY_MM.csv

CS is not touched.
"""
from __future__ import annotations


import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Set


ACC_RE = re.compile(r"^ACC_(\d{2})[_-](\d{2})$", re.IGNORECASE)
FM_RE  = re.compile(r"^FM_(\d{2})[_-](\d{2})$", re.IGNORECASE)
WM_RE  = re.compile(r"^WM_(\d{2})[_-](\d{2})$", re.IGNORECASE)


# ---------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------
def csv_has_data(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as f:
            next(f, None)
            for line in f:
                if line.strip():
                    return True
    except Exception:
        return False
    return False


def get_existing_cleaned_months(clean_root: Path) -> Set[Tuple[str, str, str]]:
    keys = set()
    for csv_file in clean_root.glob("*.csv"):
        parts = csv_file.stem.split("_")
        if len(parts) < 3:
            continue
        store, yy, mm = parts[0], parts[1], parts[2]
        if yy.isdigit() and mm.isdigit() and csv_has_data(csv_file):
            keys.add((store.upper(), yy, mm))
    return keys


# ---------------------------------------------------------------
# MERGE CSV FOLDERS
# ---------------------------------------------------------------
def merge_csv_folder(folder: Path, out_path: Path) -> None:
    csv_files = list(folder.glob("*.csv"))
    if not csv_files:
        return

    all_rows: List[Dict[str, str]] = []
    fields = set()

    for csv_file in sorted(csv_files):
        with csv_file.open("r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            if rdr.fieldnames:
                fields.update(rdr.fieldnames)
            for row in rdr:
                all_rows.append(row)

    if not all_rows:
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(fields)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({col: r.get(col, "") for col in fields})


# ---------------------------------------------------------------
# FLATTEN JSON FOLDER
# ---------------------------------------------------------------
def json_folder_to_csv(folder: Path, out_path: Path) -> None:
    json_files = list(folder.glob("*.json"))
    if not json_files:
        return

    all_rows = []
    fields = set()

    for jf in sorted(json_files):
        with jf.open("r", encoding="utf-8") as f:
            data = json.load(f)

        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for k in ("data", "rows", "items", "records"):
                if isinstance(data.get(k), list):
                    rows = data[k]
                    break

        for r in rows:
            if isinstance(r, dict):
                fields.update(r.keys())
                all_rows.append({k: "" if v is None else str(v) for k, v in r.items()})

    if not all_rows:
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(fields)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({col: r.get(col, "") for col in fields})


# ---------------------------------------------------------------
# MAIN LOGIC
# ---------------------------------------------------------------
def main(raw_root: Path, clean_root: Path, log_path: Path | None = None):

    acc_root = raw_root / "ACC_RAW"
    fm_root  = raw_root / "FM_RAW"
    wm_root  = raw_root / "WM_RAW"

    existing = get_existing_cleaned_months(clean_root)

    if acc_root.exists():
        for folder in acc_root.iterdir():
            m = ACC_RE.match(folder.name)
            if not m:
                continue
            yy, mm = m.group(1), m.group(2)
            out_path = clean_root / f"ACC_{yy}_{mm}.csv"
            if ("ACC", yy, mm) not in existing:
                merge_csv_folder(folder, out_path)

    if fm_root.exists():
        for folder in fm_root.iterdir():
            m = FM_RE.match(folder.name)
            if not m:
                continue
            yy, mm = m.group(1), m.group(2)
            out_path = clean_root / f"FM_{yy}_{mm}.csv"
            if ("FM", yy, mm) not in existing:
                json_folder_to_csv(folder, out_path)

    if wm_root.exists():
        for folder in wm_root.iterdir():
            m = WM_RE.match(folder.name)
            if not m:
                continue
            yy, mm = m.group(1), m.group(2)
            out_path = clean_root / f"WM_{yy}_{mm}.csv"
            if ("WM", yy, mm) not in existing:
                merge_csv_folder(folder, out_path)


# ---------------------------------------------------------------
# CENTRAL RUNNER ENTRY POINT
# ---------------------------------------------------------------
def ensure_cleaned_for_all_raw(raw_root, clean_root, log_path):
    main(Path(raw_root), Path(clean_root), Path(log_path) if log_path else None)


if __name__ == "__main__":
    raise RuntimeError(
        "This script must be invoked via central_runner (paths come from BAT)."
    )

