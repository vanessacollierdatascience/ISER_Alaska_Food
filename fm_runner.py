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
from central_runner import parse_folder_tag
from central_runner import log_line


from schema import MASTER_COLS


def _p(s: str) -> re.Pattern:
    return re.compile(s, re.IGNORECASE)

FM_MAP = {}
FM_MAP["SKU"] = _p(r"^SKU$|^product\.id$|^item_id$|^product\.item_id$|^sku_code$")
FM_MAP["PRICE"] = _p(r"^PRICE$|^price$|^product\.price\.storePrices\.regular\.price$|^product\.price\.storeprices\.regular\.price$|^price\.regular$|^price_regular$|^offers\.primary\.price$|^primary\.price$|^reg\.price$|^price3$")
FM_MAP["SKU_DESCRIPTION"] = _p(r"^SKU_DESCRIPTION$|^description$|^product\.item\.description$|^product\.title$|^title$|^product_description$")
FM_MAP["ZIP"] = _p(r"^ZIP$|^postalCode$|^zipcode$|^ZipCode$|^zip_code$|^zip$|^customer_zipcode$|^customer\.zipcode$|^zip2$")
FM_MAP["PULL_DATE"] = _p(r"^PULL_DATE$|^date$|^pull_date$|^created_date$|^creation_date$")
FM_MAP["UPC"] = _p(r"^UPC$|^upc$|^product\.item\.upc$")
FM_MAP["STORE_ID"] = _p(r"^STORE_ID$|^storeId$|^location_id$|^location\.id$|^store\.id$|^store_id$|^store_id3$")
FM_MAP["HOME_STORE_NAME"] = _p(r"^home_store_name$|^HOME_STORE_NAME$")
FM_MAP["SIZE"] = _p(r"^SIZE$|^size$")

def list_source_files(folder: Path) -> List[Path]:
    cands = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in [".csv", ".json"]:
            cands.append(p)
    cands.sort(key = lambda x: x.stat().st_mtime, reverse = True)
    return cands

def reduce_with_map(rows: List[Dict[str, Any]], mapping: Dict[str, re.Pattern]) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return rows
    headers = list(rows[0].keys())
    picked = {}
    for tgt, patt in mapping.items():
        src = None
        for h in headers:
            if patt.match(h):
                src = h
                break
        picked[tgt] = src
    out = []
    for r in rows:
        new_r = {}
        for k in MASTER_COLS:
            new_r[k] = ""
            new_r["PULL_DATE"] = r.get("PULL_DATE", "")
            new_r["HOME_STORE_NAME"] = "FM"

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
    yy_mm = parse_folder_tag(tag, "FM")
    if yy_mm is None:
        log_line(log_path, "[FM][SKIP] " + tag)
        return None

    sources = [
        p for p in sub.iterdir()
        if p.is_file() and p.suffix.lower() in [".csv", ".json"]
    ]

    if not sources:
        log_line(log_path, "[FM][SKIP] No files in " + tag)
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
        log_line(log_path, "[FM][SKIP] No rows in " + tag)
        return yy_mm

    rows = upper_headers(all_rows)
    override_pd = pull_date_from_folder_tag(tag)
    rows = ensure_pull_date(rows, sources[0], override_pd)

    for r in rows:
        r["HOME_STORE_NAME"] = "FM"

    mapped = reduce_with_map(rows, mapping)
    for r in mapped:
        finalize_common_fields(r, list(rows[0].keys()), "FM", crosswalk, "AK")

    key = ("FM", yy_mm)
    monthly.setdefault(key, []).extend(mapped)
    log_line(log_path, f"[FM][ACCUM] {tag}: +{len(mapped)} rows")

    return yy_mm


def run_fm(log_root: Path,
           raw_root: Path,
           clean_root: Path,
           crosswalk_path: Path,
           central_log_path: Path) -> None:
    fm_root = raw_root / "FM_RAW"
    if not fm_root.exists():
        log_line(central_log_path, "[FM][SKIP] Missing FM_RAW")
        return
    crosswalk = read_crosswalk_generic(crosswalk_path, central_log_path)
    monthly = {}
    for sub in fm_root.iterdir():
        if not sub.is_dir():
            continue
        yy_mm = process_subfolder(sub, FM_MAP, crosswalk, monthly, central_log_path)
        if yy_mm is None:
            continue
        key = ("FM", yy_mm)
        rows = monthly.get(key, [])
        out_path = clean_root / f"FM_{yy_mm}.csv"
        write_csv(out_path, rows, MASTER_COLS)
        log_line(central_log_path, f"[FM][WRITE] {out_path} ({len(rows)})")