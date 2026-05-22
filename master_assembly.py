#!/usr/bin/env python3
from schema import MASTER_COLS  # noqa: F401

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd

try:
    from ydata_profiling import ProfileReport
    HAS_YDATA = True
except Exception:
    HAS_YDATA = False

def log_line(path: Path, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{msg}"
    print(line)
    try:
        with path.open("a", encoding = "utf-8") as f:
            f.write(f"{ts} {line}\n")
    except Exception:
        pass

def read_csv_safely(path: Path) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(path, low_memory = False)
    except Exception:
        return None

def parse_month_value(val) -> Optional[pd.Timestamp]:
    if pd.isna(val):
        return None
    s = str(val).strip()
    if re.fullmatch(r"\d{6}", s):
        return pd.to_datetime(s + "01", format = "%Y%m%d", errors = "coerce")
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return pd.to_datetime(s + "-01", format = "%Y-%m-%d", errors = "coerce")
    return pd.to_datetime(s, errors = "coerce")

def derive_panel_date(df: pd.DataFrame) -> pd.DataFrame:
    d = None
    cols_try = ["PULL_DATE", "Pull_Date", "DATE", "Date"]
    for c in cols_try:
        if c in df.columns:
            d = pd.to_datetime(df[c], errors = "coerce")
            break
    if (d is None or (isinstance(d, pd.Series) and d.isna().all())) and "MONTH" in df.columns:
        d = df["MONTH"].map(parse_month_value)
    if (d is None or (isinstance(d, pd.Series) and d.isna().all())) and "Month" in df.columns:
        d = df["Month"].map(parse_month_value)
    if not isinstance(d, pd.Series):
        d = pd.Series([pd.NaT] * len(df), index = df.index)
    out = df.copy()
    out["PANEL_DATE"] = d
    return out

def _next_build_tag(builds_root: Path) -> str:
    today_tag = datetime.now().strftime("%Y%m%d")
    seq = 1
    for p in builds_root.glob(f"*{today_tag}_v*"):
        m = re.search(rf"{today_tag}_v(\d+)$", p.name)
        if m:
            try:
                seq = max(seq, int(m.group(1)) + 1)
            except Exception:
                seq = seq
    return f"{today_tag}_v{seq:02d}"

def main(clean_root: Path, central_log_path: Path) -> None:
    start_ts = datetime.now()
    builds_root = clean_root / "MASTER_builds"
    builds_root.mkdir(parents = True, exist_ok = True)
    build_tag = _next_build_tag(builds_root)
    build_dir = builds_root / build_tag
    build_dir.mkdir(parents = True, exist_ok = True)
    log_line(central_log_path, f"[MASTER] BUILD {build_tag} -> {build_dir}")


    csv_files = sorted([p for p in clean_root.glob("*.csv") if p.is_file()])
    frames = []
    log_line(central_log_path, f"[MASTER] Reading {len(csv_files)} cleaned file(s)")
    for f in csv_files:
        df = read_csv_safely(f)
        if df is None:
            log_line(central_log_path, f"[MASTER][WARN] Could not read {f.name}")
            continue
        df = df.copy()
        df["SOURCE_FILE"] = f.name
        if "PRIMARY_KEY" in df.columns:
            df["PRIMARY_KEY"] = df["PRIMARY_KEY"].astype(str)
        df = derive_panel_date(df)
        df = df.dropna(axis = 1, how = "all")
        df = df.drop_duplicates()
        frames.append(df)

    if len(frames) == 0:
        log_line(central_log_path, "[MASTER][ERROR] No CSV files loaded. Aborting.")
        raise RuntimeError("No CSV files loaded.")

    master_long = pd.concat(frames, ignore_index = True)

    # --- Normalize HOME_STORE_NAME and rebuild keys ---
    # Fix stray 'fred' / 'meyer' and enforce canonical codes
    if "HOME_STORE_NAME" in master_long.columns:
        hs = master_long["HOME_STORE_NAME"].astype(str).str.strip()
        fm_mask = hs.str.lower().isin(["fred", "meyer", "fred meyer"])
        master_long.loc[fm_mask, "HOME_STORE_NAME"] = "FM"
        master_long["HOME_STORE_NAME"] = master_long["HOME_STORE_NAME"].astype(str).str.upper()

    # Rebuild PRIMARY_STORE_KEY from HOME_STORE_NAME, CITY, ZIP
    if (
        "HOME_STORE_NAME" in master_long.columns
        and "CITY" in master_long.columns
        and "ZIP" in master_long.columns
    ):
        hs = master_long["HOME_STORE_NAME"].astype(str).str.upper()
        city = master_long["CITY"].astype(str)
        zipc = master_long["ZIP"].astype(str)
        master_long["PRIMARY_STORE_KEY"] = hs + "_" + city + "-" + zipc

    # Rebuild PRIMARY_KEY from PRIMARY_STORE_KEY and SKU/UPC
    if "PRIMARY_STORE_KEY" in master_long.columns:
        psk = master_long["PRIMARY_STORE_KEY"].astype(str)
        sku = master_long["SKU"].astype(str) if "SKU" in master_long.columns else None
        upc = master_long["UPC"].astype(str) if "UPC" in master_long.columns else None

        # Start empty, then fill with SKU-based keys, then UPC-based where still empty
        master_long["PRIMARY_KEY"] = ""

        if sku is not None:
            mask_sku = (
                psk.ne("")
                & sku.ne("")
                & psk.notna()
                & sku.notna()
            )
            master_long.loc[mask_sku, "PRIMARY_KEY"] = psk[mask_sku] + "_" + sku[mask_sku]

        if upc is not None:
            mask_upc = (
                (master_long["PRIMARY_KEY"] == "")
                & psk.ne("")
                & upc.ne("")
                & psk.notna()
                & upc.notna()
            )
            master_long.loc[mask_upc, "PRIMARY_KEY"] = psk[mask_upc] + "_" + upc[mask_upc]

    # Sanity check: PRIMARY_KEY must exist and not be entirely empty
    if "PRIMARY_KEY" not in master_long.columns or master_long["PRIMARY_KEY"].eq("").all():
        log_line(central_log_path, "[MASTER][ERROR] PRIMARY_KEY missing or empty after rebuild.")
        raise RuntimeError("PRIMARY_KEY missing or empty.")

    # Now we can safely sort by PRIMARY_KEY etc.
    master_long = master_long.sort_values(
        by = ["PRIMARY_KEY", "PANEL_DATE", "SOURCE_FILE"],
        kind = "mergesort"
    )
    # --- end HOME_STORE_NAME / key normalization ---


    panel_csv = build_dir / f"MASTER_panel_long_{build_tag}.csv"
    master_long.to_csv(panel_csv, index = False)
    log_line(central_log_path, f"[MASTER] Saved panel: {panel_csv}")

    latest_csv = build_dir / f"MASTER_latest_by_key_{build_tag}.csv"
    if master_long["PANEL_DATE"].notna().any():
        latest_idx = master_long.dropna(subset = ["PANEL_DATE"]).groupby("PRIMARY_KEY")["PANEL_DATE"].idxmax()
        master_latest = master_long.loc[latest_idx].copy()
    else:
        master_latest = master_long.groupby("PRIMARY_KEY", as_index = False).head(1).copy()
    master_latest.to_csv(latest_csv, index = False)
    log_line(central_log_path, f"[MASTER] Saved latest-by-key: {latest_csv}")

    wide_path = None
    if "PRICE" in master_long.columns:
        price_df = master_long.loc[master_long["PANEL_DATE"].notna(), ["PRIMARY_KEY", "PANEL_DATE", "PRICE"]].copy()
        price_df["PRICE"] = price_df["PRICE"].astype(str).str.replace(r"[\$,]", "", regex = True)
        price_df["PRICE"] = pd.to_numeric(price_df["PRICE"], errors = "coerce")
        price_df = price_df.dropna(subset = ["PRICE"])
        price_df["MONTH_LABEL"] = price_df["PANEL_DATE"].dt.strftime("%Y_%m")
        if len(price_df) > 0:
            price_df = price_df.groupby(["PRIMARY_KEY", "MONTH_LABEL"], as_index = False)["PRICE"].mean()
            price_wide = price_df.pivot(index = "PRIMARY_KEY", columns = "MONTH_LABEL", values = "PRICE")
            price_wide = price_wide.add_prefix("PRICE_")
            wide_path = build_dir / f"MASTER_price_by_month_wide_{build_tag}.csv"
            price_wide.to_csv(wide_path)
            log_line(central_log_path, f"[MASTER] Saved price wide: {wide_path}")

    try:
        import rpy2.robjects as ro
        from rpy2.robjects import pandas2ri
        pandas2ri.activate()
        ro.r("suppressPackageStartupMessages(library(fst))")
        def _write_fst(df: pd.DataFrame, path: Path) -> None:
            r_df = pandas2ri.py2rpy(df)
            ro.r.assign("x", r_df)
            ro.r.assign("p", str(path))
            ro.r("fst::write_fst(x, p, compress = 50)")
        fst_panel = build_dir / f"MASTER_panel_long_{build_tag}.fst"
        fst_latest = build_dir / f"MASTER_latest_by_key_{build_tag}.fst"
        _write_fst(master_long, fst_panel)
        _write_fst(master_latest, fst_latest)
        log_line(central_log_path, f"[MASTER] Wrote FST: {fst_panel}")
        log_line(central_log_path, f"[MASTER] Wrote FST: {fst_latest}")
    except Exception as e:
        log_line(central_log_path, f"[MASTER][WARN] .fst not written. Falling back to Feather. Error: {e}")
        try:
            import pyarrow.feather as feather
            feather_panel = build_dir / f"MASTER_panel_long_{build_tag}.feather"
            feather_latest = build_dir / f"MASTER_latest_by_key_{build_tag}.feather"
            feather.write_feather(master_long, feather_panel)
            feather.write_feather(master_latest, feather_latest)
            log_line(central_log_path, f"[MASTER] Wrote Feather: {feather_panel}")
            log_line(central_log_path, f"[MASTER] Wrote Feather: {feather_latest}")
        except Exception as ee:
            log_line(central_log_path, f"[MASTER][ERROR] Feather fallback failed: {ee}")

    manifest = {}
    manifest["build_tag"] = build_tag
    manifest["build_dir"] = str(build_dir)
    manifest["panel_csv"] = str(panel_csv)
    manifest["latest_csv"] = str(latest_csv)
    manifest["wide_csv"] = str(wide_path) if wide_path is not None else ""
    manifest["qa_dir"] = str(build_dir / "QA")
    manifest["qa_site_dir"] = str(build_dir / "QA_SITE")
    manifest["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    manifest_path = build_dir / f"MASTER_manifest_{build_tag}.json"
    Path(manifest_path).write_text(json.dumps(manifest, indent = 2), encoding = "utf-8")
    log_line(central_log_path, f"[MASTER] Manifest: {manifest_path}")
    # -------------------------
    # Run QA after Master Build
    # -------------------------
    from master_qa import run_master_qa
    run_master_qa(
        builds_root = builds_root,
        central_log_path = Path(central_log_path),
        build_tag = build_tag,
        manifest_path = manifest_path
    )



    


    if HAS_YDATA:
        try:
            qa_dir = build_dir / "QA"
            qa_dir.mkdir(parents = True, exist_ok = True)
            qa_profile_path = qa_dir / f"QA_ydata_profiling_master_long_{build_tag}.html"
            profile = ProfileReport(master_long, title = "ISER Food Pricing — Master Panel QA (ydata-profiling)", minimal = True, explorative = True)
            profile.to_file(qa_profile_path)
            log_line(central_log_path, f"[MASTER] ydata-profiling HTML: {qa_profile_path}")
        except Exception as e:
            log_line(central_log_path, f"[MASTER][WARN] ydata-profiling failed: {e}")

    elapsed = datetime.now() - start_ts
    log_line(central_log_path, f"[MASTER_ASSEMBLY] SUCCESS elapsed={str(elapsed).split('.')[0]}")

def run_master(LOG_ROOT: Path, RAW_ROOT: Path, CLEAN_ROOT: Path, CROSSWALK_PATH: Path, central_log_path: Path) -> None:
    main(CLEAN_ROOT, central_log_path)

if __name__ == "__main__":
    default_clean = Path(r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\CLEANED_DATA")
    default_log = Path(r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\LOGS\central_log_standalone_master.txt")
    main(default_clean, default_log)
