#!/usr/bin/env python3

import re
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from schema import MASTER_COLS


def _p(s: str) -> re.Pattern:
    return re.compile(s, re.IGNORECASE)

# ─────────────────────────────────────────────────────────────
# CS mapping — includes your raw headers:
# Product_Code, Product_Desc, Product_Price, ZipCode, Pull_Date
# ─────────────────────────────────────────────────────────────
CS_MAP: Dict[str, re.Pattern] = {}
CS_MAP["SKU"] = _p(r"^SKU$|^Product_Code$|^product_code$|^product\.id$|^item_id$|^product\.item_id$|^sku_code$")
CS_MAP["PRICE"] = _p(r"^PRICE$|^Product_Price$|^price$|^product\.price\.storePrices\.regular\.price$|^product\.price\.storeprices\.regular\.price$|^price\.regular$|^price_regular$|^offers\.primary\.price$|^primary\.price$|^reg\.price$|^price3$")
CS_MAP["SKU_DESCRIPTION"] = _p(r"^SKU_DESCRIPTION$|^Product_Desc$|^description$|^product\.item\.description$|^product\.title$|^title$|^product_description$")
CS_MAP["ZIP"] = _p(r"^ZIP$|^ZipCode$|^postalCode$|^zipcode$|^zip_code$|^zip$|^customer_zipcode$|^customer\.zipcode$|^zip2$")
CS_MAP["PULL_DATE"] = _p(r"^PULL_DATE$|^Pull_Date$|^date$|^pull_date$|^created_date$|^creation_date$")
CS_MAP["UPC"] = _p(r"^UPC$|^upc$|^product\.item\.upc$")
CS_MAP["STORE_ID"] = _p(r"^STORE_ID$")  # rarely present for CS; we will build it from ZIP
CS_MAP["HOME_STORE_NAME"] = _p(r"^home_store_name$|^HOME_STORE_NAME$")
CS_MAP["SIZE"] = _p(r"^SIZE$|^size$")

TAG_PATTERNS = [
    re.compile(r"^(?P<store>CS)_(?P<yy>\d{2})_(?P<mm>\d{2})$", re.IGNORECASE),
    re.compile(r"^(?P<store>CS)_(?P<yyyy>\d{4})_(?P<mm>\d{2})$", re.IGNORECASE)
]

FILE_TAG = re.compile(r"^CS_(\d{2})_(\d{2})\.(csv|json|txt)$", re.IGNORECASE)
FILE_TAG_LONG = re.compile(r"^CS_(\d{4})_(\d{2})\.(csv|json|txt)$", re.IGNORECASE)

def parse_folder_tag_local(name: str) -> Optional[str]:
    for pat in TAG_PATTERNS:
        m = pat.match(name)
        if m is None:
            continue
        if "yy" in m.groupdict():
            yy = m.group("yy")
            mm = m.group("mm")
            return f"{yy}_{mm}"
        yyyy = m.group("yyyy")
        mm = m.group("mm")
        return f"{yyyy[-2:]}_{mm}"
    return None

def yy_mm_from_file(name: str) -> Optional[str]:
    m = FILE_TAG.match(name)
    if m is not None:
        return f"{m.group(1)}_{m.group(2)}"
    m2 = FILE_TAG_LONG.match(name)
    if m2 is not None:
        return f"{m2.group(1)[-2:]}_{m2.group(2)}"
    return None

def list_source_files(folder: Path) -> List[Path]:
    cands = []
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in [".csv", ".json"]:
            cands.append(p)
    cands.sort(key = lambda x: x.stat().st_mtime, reverse = True)
    return cands

def reduce_with_map(rows: List[Dict[str, Any]],
                    mapping: Dict[str, re.Pattern],
                    master_cols: List[str]) -> List[Dict[str, Any]]:
    if len(rows) == 0:
        return rows
    headers = list(rows[0].keys())
    picked: Dict[str, Optional[str]] = {}
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
        for k in master_cols:
            new_r[k] = ""
        new_r["PULL_DATE"] = r.get("PULL_DATE", "")
        new_r["HOME_STORE_NAME"] = "CS"

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

def _zip5(s: Any) -> str:
    if s is None:
        return ""
    only = "".join(ch for ch in str(s) if ch.isdigit())
    if len(only) >= 5:
        return only[:5]
    return only

def _process_any(src: Path,
                 tag: str,
                 yy_mm: str,
                 mapping: Dict[str, re.Pattern],
                 crosswalk: Dict[Tuple[str, str], Dict[str, str]],
                 monthly: Dict[Tuple[str, str], List[Dict[str, Any]]],
                 log_line,
                 helpers) -> str:
    if src.suffix.lower() == ".csv":
        rows = helpers["read_csv_rows"](src)
    else:
        rows = helpers["read_json_rows"](src)
    rows = helpers["upper_headers"](rows)

    override_pd = helpers["pull_date_from_folder_tag"](tag)
    rows = helpers["ensure_pull_date"](rows, src, override_pd)

    for r in rows:
        if not r.get("HOME_STORE_NAME"):
            r["HOME_STORE_NAME"] = "CS"

    mapped = reduce_with_map(rows, mapping, helpers["MASTER_COLS"])

    # ── Build STORE_ID from ZIP to enable crosswalk join (CS-<ZIP>)
    for r in mapped:
        if not r.get("ZIP"):
            r["ZIP"] = ""
        r["ZIP"] = _zip5(r["ZIP"])
        built_store_id = ""
        if len(r["ZIP"]) > 0:
            built_store_id = f"CS-{r['ZIP']}"
        if not r.get("STORE_ID") or len(str(r.get("STORE_ID"))) == 0:
            r["STORE_ID"] = built_store_id

    # ── Enrich via crosswalk and finalize common fields
    original_headers_upper = list(rows[0].keys())
    for r in mapped:
        helpers["finalize_common_fields"](r, original_headers_upper, "CS", crosswalk, "AK")

    key = ("CS", yy_mm)
    if key not in monthly:
        monthly[key] = []
    monthly[key].extend(mapped)
    log_line(f"[CS][ACCUM] {tag}: +{len(mapped)} rows from {src.name}")
    return yy_mm

def process_subfolder(sub: Path,
                      mapping: Dict[str, re.Pattern],
                      crosswalk: Dict[Tuple[str, str], Dict[str, str]],
                      monthly: Dict[Tuple[str, str], List[Dict[str, Any]]],
                      log_line,
                      helpers) -> Optional[str]:
    tag = sub.name
    yy_mm = parse_folder_tag_local(tag)
    if yy_mm is None:
        log_line(f"[CS][SKIP] Folder name not recognized: {tag}")
        return None
    srcs = list_source_files(sub)
    if len(srcs) == 0:
        log_line(f"[CS][SKIP] No usable file in {tag}")
        return yy_mm
    for src in srcs:
        yy_mm = _process_any(
            src=src,
            tag=tag,
            yy_mm=yy_mm,
            mapping=mapping,
            crosswalk=crosswalk,
            monthly=monthly,
            log_line=log_line,
            helpers=helpers
        )
    return yy_mm


def run_cs(log_root: Path,
           raw_root: Path,
           clean_root: Path,
           crosswalk_path: Path,
           central_log_path: Path) -> None:
    from central_runner import read_csv_rows
    from central_runner import read_json_rows
    from central_runner import write_csv
    from central_runner import upper_headers
    from central_runner import ensure_pull_date
    from central_runner import pull_date_from_folder_tag
    from central_runner import read_crosswalk_generic
    from central_runner import finalize_common_fields
    from central_runner import log_line as central_log
    

    def log_line_local(msg: str) -> None:
        central_log(central_log_path, msg)

    helpers = {
        "read_csv_rows": read_csv_rows,
        "read_json_rows": read_json_rows,
        "write_csv": write_csv,
        "upper_headers": upper_headers,
        "ensure_pull_date": ensure_pull_date,
        "pull_date_from_folder_tag": pull_date_from_folder_tag,
        "finalize_common_fields": finalize_common_fields,
        "MASTER_COLS": MASTER_COLS
    }

    cs_root = raw_root / "CS_RAW"
    if not cs_root.exists():
        log_line_local("[CS][SKIP] Missing CS_RAW")
        return

    crosswalk = read_crosswalk_generic(crosswalk_path, central_log_path)
    monthly: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    # process files directly in CS_RAW
    files = [p for p in cs_root.iterdir() if p.is_file()]
    for f in files:
        yy_mm = yy_mm_from_file(f.name)
        if yy_mm is None:
            continue
        tag = f"CS_{yy_mm}"
        _process_any(
            src=f,
            tag=tag,
            yy_mm=yy_mm,
            mapping=CS_MAP,
            crosswalk=crosswalk,
            monthly=monthly,
            log_line=log_line_local,
            helpers=helpers
        )
        out_path = clean_root / f"CS_{yy_mm}.csv"
        rows = monthly.get(("CS", yy_mm), [])
        write_csv(out_path, rows, MASTER_COLS)
        log_line_local(f"[CS][WRITE] {out_path} ({len(rows)} rows)")

    # process month subfolders
    subs = [p for p in cs_root.iterdir() if p.is_dir()]
    for sub in subs:
        yy_mm = process_subfolder(
            sub=sub,
            mapping=CS_MAP,
            crosswalk=crosswalk,
            monthly=monthly,
            log_line=log_line_local,
            helpers=helpers
        )
        if yy_mm is None:
            continue
        out_path = clean_root / f"CS_{yy_mm}.csv"
        rows = monthly.get(("CS", yy_mm), [])
        write_csv(out_path, rows, MASTER_COLS)
        log_line_local(f"[CS][WRITE] {out_path} ({len(rows)} rows)")
