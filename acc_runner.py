#!/usr/bin/env python3

import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from central_runner import read_csv_rows
from central_runner import read_json_rows
from central_runner import write_csv
from central_runner import upper_headers
from central_runner import ensure_pull_date
from central_runner import pull_date_from_folder_tag
from central_runner import read_crosswalk_generic
from central_runner import finalize_common_fields
from central_runner import log_line


from schema import MASTER_COLS


def _p(s: str) -> re.Pattern:
    return re.compile(s, re.IGNORECASE)

ACC_MAP: Dict[str, re.Pattern] = {}
ACC_MAP["PULL_DATE"] = _p(r"^PULL_DATE$")
ACC_MAP["HOME_STORE_NAME"] = _p(r"^HOME_STORE_NAME$")
ACC_MAP["STORE_ID"] = _p(r"^STORE_ID$")
ACC_MAP["STORE_NAME"] = _p(r"^STORE_NAME$")
ACC_MAP["ADDRESS"] = _p(r"^ADDRESS$")
ACC_MAP["CITY"] = _p(r"^CITY$")
ACC_MAP["STATE"] = _p(r"^STATE$")
ACC_MAP["ZIP"] = _p(r"^ZIP$")
ACC_MAP["STORE_REGION"] = _p(r"^STORE_REGION$")
ACC_MAP["LONGITUDE"] = _p(r"^LONGITUDE$")
ACC_MAP["LATITUDE"] = _p(r"^LATITUDE$")
ACC_MAP["PRIMARY_STORE_KEY"] = _p(r"^PRIMARY_STORE_KEY$")
ACC_MAP["PRIMARY_KEY"] = _p(r"^PRIMARY_KEY$")
ACC_MAP["UPC"] = _p(r"^UPC$")
ACC_MAP["SKU"] = _p(r"^SKU$")
ACC_MAP["SKU_DESCRIPTION"] = _p(r"^SKU_DESCRIPTION$")
ACC_MAP["SIZE"] = _p(r"^SIZE$")
ACC_MAP["PRICE"] = _p(r"^PRICE$")
ACC_MAP["INTERNAL_PROD_CODE"] = _p(r"^INTERNAL_PROD_CODE$")
ACC_MAP["MONTH"] = _p(r"^MONTH$")
ACC_MAP["YEAR"] = _p(r"^YEAR$")
ACC_MAP["MONTH_YEAR"] = _p(r"^MONTH_YEAR$")
ACC_MAP["SALES_TAX_FED_FLAG"] = _p(r"^response\.SALES_TAX_FED_FLAG$|^SALES_TAX_FED_FLAG$")
ACC_MAP["SALES_TAX_CITY_FLAG"] = _p(r"^response\.SALES_TAX_CITY_FLAG$|^SALES_TAX_CITY_FLAG$")
ACC_MAP["SALES_TAX_MUNI_FLAG"] = _p(r"^response\.SALES_TAX_MUNI_FLAG$|^SALES_TAX_MUNI_FLAG$")
ACC_MAP["SALES_TAX_FLAT_FLAG"] = _p(r"^response\.SALES_TAX_FLAT_FLAG$|^SALES_TAX_FLAT_FLAG$")
ACC_MAP["SNAP_FLAG"] = _p(r"^response\.item\.SNAP_FLAG$|^SNAP_FLAG$")
ACC_MAP["ITEM_WEIGHT"] = _p(r"^response\.ITEM_WEIGHT$|^ITEM_WEIGHT$")
ACC_MAP["FREIGHT_TYPE"] = _p(r"^FREIGHT_TYPE$")

RECOVERY_FOLDERS = set(["ACC_24_09", "ACC_24_10"])
FOLDER_TAG = re.compile(r"^ACC_(\d{2})_(\d{2})$", re.IGNORECASE)

def list_source_files(folder: Path) -> List[Path]:
    cands = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in [".csv", ".json"]:
            cands.append(p)
    cands.sort(key = lambda x: x.stat().st_mtime, reverse = True)
    return cands

def yy_mm_from_name(name: str) -> Optional[str]:
    m = FOLDER_TAG.match(name)
    if m is None:
        return None
    return f"{m.group(1)}_{m.group(2)}"

def reduce_with_map(rows: List[Dict[str, Any]],
                    mapping: Dict[str, re.Pattern]) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return []
    headers = list(rows[0].keys())
    picked: Dict[str, Optional[str]] = {}
    for tgt, pat in mapping.items():
        src_match = None
        for h in headers:
            if pat.match(h):
                src_match = h
                break
        picked[tgt] = src_match
    out = []
    for r in rows:
        new_r: Dict[str, Any] = {}
        for k in MASTER_COLS:
            new_r[k] = ""
        new_r["PULL_DATE"] = r.get("PULL_DATE", "")
        new_r["HOME_STORE_NAME"] = "ACC"
        for tgt, src in picked.items():
            if tgt == "HOME_STORE_NAME":
                continue
            if tgt == "PULL_DATE":
                continue
            if src is not None:
                val = r.get(src, "")
                new_r[tgt] = "" if val is None else str(val)
        out.append(new_r)
    return out



def process_subfolder(sub: Path,
                      mapping: Dict[str, re.Pattern],
                      crosswalk: Dict[Tuple[str, str], Dict[str, str]],
                      monthly: Dict[Tuple[str, str], List[Dict[str, Any]]],
                      log_path: Path) -> Optional[str]:
    tag = sub.name
    yy_mm = yy_mm_from_name(tag)
    if yy_mm is None:
        log_line(log_path, "[ACC][SKIP] " + tag)
        return None

    sources = [
        p for p in sub.iterdir()
        if p.is_file() and p.suffix.lower() in [".csv", ".json"]
    ]

    if not sources:
        log_line(log_path, "[ACC][SKIP] No files in " + tag)
        return yy_mm

    all_rows: List[Dict[str, Any]] = []
    for src in sorted(sources, key=lambda x: x.name):
        if src.suffix.lower() == ".csv":
            part = read_csv_rows(src)
        else:
            part = read_json_rows(src)
        if part:
            all_rows.extend(part)

    if not all_rows:
        log_line(log_path, "[ACC][SKIP] No rows in " + tag)
        return yy_mm

    rows = upper_headers(all_rows)
    override_pd = pull_date_from_folder_tag(tag)
    rows = ensure_pull_date(rows, sources[0], override_pd)

    for r in rows:
        r["HOME_STORE_NAME"] = "ACC"

    mapped = reduce_with_map(rows, mapping)
    for r in mapped:
        finalize_common_fields(r, list(rows[0].keys()), "ACC", crosswalk, "AK")

    key = ("ACC", yy_mm)
    monthly.setdefault(key, []).extend(mapped)
    log_line(log_path, f"[ACC][ACCUM] {tag}: +{len(mapped)} rows")

    return yy_mm


def run_acc(log_root: Path,
            raw_root: Path,
            clean_root: Path,
            crosswalk_path: Path,
            central_log_path: Path) -> None:
    acc_root = raw_root / "ACC_RAW"
    if not acc_root.exists():
        log_line(central_log_path, "[ACC][SKIP] Missing ACC_RAW")
        return
    crosswalk = read_crosswalk_generic(crosswalk_path, central_log_path)
    mapping = ACC_MAP

    monthly: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    
    for sub in acc_root.iterdir():
        process_subfolder(
            sub=sub,
            mapping=mapping,
            crosswalk=crosswalk,
            monthly=monthly,
            log_path=central_log_path
     )

    # Second pass: normal processing (including 24_11, 25_11 etc.)
    for sub in acc_root.iterdir():
        if not sub.is_dir():
            continue
        if sub.name in RECOVERY_FOLDERS:
            yy_mm = yy_mm_from_name(sub.name)
            if yy_mm is None:
                continue
            rows = monthly.get(("ACC", yy_mm), [])
            out_path = clean_root / f"ACC_{yy_mm}.csv"
            write_csv(out_path, rows, MASTER_COLS)
            log_line(central_log_path, f"[ACC][WRITE] {out_path} ({len(rows)}) [RECOVERY]")
            continue
        yy_mm = process_subfolder(sub, ACC_MAP, crosswalk, monthly, central_log_path)
        if yy_mm is None:
            continue
        key = ("ACC", yy_mm)
        rows = monthly.get(key, [])
        out_path = clean_root / f"ACC_{yy_mm}.csv"
        write_csv(out_path, rows, MASTER_COLS)
        log_line(central_log_path, f"[ACC][WRITE] {out_path} ({len(rows)})")