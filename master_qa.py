#!/usr/bin/env python3
"""
Lightweight QA module for ISER Food Pricing master build.

This replaces a corrupted previous version but keeps the same public API:

    run_master_qa(builds_root, central_log_path, build_tag, manifest_path)

and the same manifest fields written by master_assembly.py:

    build_tag, build_dir, qa_dir, qa_site_dir, panel_csv

Outputs (all CSVs go into qa_dir):

    QA_missing_by_column_{tag}.csv
    QA_missing_by_row_count_distribution_{tag}.csv
    QA_missing_overall_summary_{tag}.csv
    QA_missing_by_source_file_{tag}.csv      (if SOURCE_FILE column exists)
    QA_missing_by_month_{tag}.csv           (HOME_STORE_NAME x MONTH_LABEL)

    QA_counts_overall_{tag}.csv
    QA_counts_by_home_store_{tag}.csv
    QA_counts_by_year_{tag}.csv             (if YEAR exists)
    QA_counts_by_month_{tag}.csv            (if YEAR/MONTH exist)
    QA_counts_by_month_home_store_{tag}.csv (if HOME_STORE_NAME & dates exist)
    QA_counts_by_month_primary_store_key_{tag}.csv
                                           (if PRIMARY_STORE_KEY & dates exist)

It also writes a static PNG barplot of missingness by column and
a simple HTML "QA site" page linking to all outputs.
"""

from __future__ import annotations
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# -------------------------------------------------------------------
# Logging helpers
# -------------------------------------------------------------------
def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_line(central_log_path: Optional[Path], msg: str) -> None:
    """
    Write a log line to stdout and to central_log_path (if provided).
    """
    line = f"{_timestamp()} {msg}"
    print(line)
    if central_log_path is not None:
        try:
            central_log_path.parent.mkdir(parents = True, exist_ok = True)
            with central_log_path.open("a", encoding = "utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            # Logging failure should never break the pipeline
            pass


# -------------------------------------------------------------------
# Manifest / data loading
# -------------------------------------------------------------------
def _load_manifest(builds_root: Path, build_tag: Optional[str]) -> Path:
    """
    Fallback manifest lookup if run_master_qa is called from CLI
    without manifest_path. It picks the manifest for build_tag,
    or the latest manifest if build_tag is None.
    """
    builds_root = Path(builds_root)
    if build_tag:
        cand = list(builds_root.glob(f"{build_tag}/MASTER_manifest_{build_tag}.json"))
        if cand:
            return cand[0]

    # Fall back to latest manifest by mtime
    manifests: List[Path] = list(builds_root.glob("*/MASTER_manifest_*.json"))
    if not manifests:
        raise FileNotFoundError(f"No manifest JSON files found under {builds_root}")
    manifests.sort(key = lambda p: p.stat().st_mtime, reverse = True)
    return manifests[0]


def _read_df(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    return df


# -------------------------------------------------------------------
# Date helpers
# -------------------------------------------------------------------
def _derive_panel_date(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure PANEL_DATE, YEAR, and MONTH exist when possible.
    """
    out = df.copy()

    # Prefer an existing PANEL_DATE
    d = None
    if "PANEL_DATE" in out.columns:
        d = pd.to_datetime(out["PANEL_DATE"], errors = "coerce")
    else:
        for c in ["PULL_DATE", "Pull_Date", "DATE", "Date"]:
            if c in out.columns:
                d = pd.to_datetime(out[c], errors = "coerce")
                break

    if d is None or (isinstance(d, pd.Series) and d.isna().all()):
        # Try to build from YEAR / MONTH if available
        if "YEAR" in out.columns and "MONTH" in out.columns:
            y = pd.to_numeric(out["YEAR"], errors = "coerce")
            m = pd.to_numeric(out["MONTH"], errors = "coerce")
            d = pd.to_datetime(
                dict(year = y, month = m, day = 1),
                errors = "coerce",
            )
        elif "MONTH" in out.columns:
            # Best-effort month-only dates (no real year information)
            m = pd.to_numeric(out["MONTH"], errors = "coerce")
            d = pd.to_datetime(
                {"year": 2000, "month": m, "day": 1},
                errors = "coerce",
            )

    if not isinstance(d, pd.Series):
        d = pd.Series([pd.NaT] * len(out), index = out.index)

    out["PANEL_DATE"] = d

    if "YEAR" not in out.columns:
        out["YEAR"] = out["PANEL_DATE"].dt.year

    if "MONTH" not in out.columns:
        out["MONTH"] = out["PANEL_DATE"].dt.month

    return out


def _safe_month_label(year_series: pd.Series, month_series: pd.Series) -> pd.Series:
    """
    Build a YYYY-MM label safely, without failing on NaNs.

    Any row with missing YEAR or MONTH gets MONTH_LABEL = 'UNKNOWN'.
    """
    if year_series is None or month_series is None:
        return pd.Series(["UNKNOWN"] * len(year_series), index = year_series.index)

    y = pd.to_numeric(year_series, errors = "coerce")
    m = pd.to_numeric(month_series, errors = "coerce")

    labels = pd.Series(["UNKNOWN"] * len(y), index = y.index)
    mask = y.notna() & m.notna()
    if mask.any():
        labels.loc[mask] = (
            y.loc[mask].astype(int).astype(str)
            + "-"
            + m.loc[mask].astype(int).astype(str).str.zfill(2)
        )
    return labels


# -------------------------------------------------------------------
# Core QA calculations
# -------------------------------------------------------------------
def _write_qa_csvs(master_long: pd.DataFrame, qa_dir: Path, tag: str) -> Dict[str, Any]:
    qa_dir.mkdir(parents = True, exist_ok = True)

    # --- Paths ---
    missing_by_col_path = qa_dir / f"QA_missing_by_column_{tag}.csv"
    missing_by_row_dist_path = qa_dir / f"QA_missing_by_row_count_distribution_{tag}.csv"
    overall_summary_path = qa_dir / f"QA_missing_overall_summary_{tag}.csv"
    missing_by_source_file_path = qa_dir / f"QA_missing_by_source_file_{tag}.csv"

    # NOTE: we will repurpose QA_missing_by_month_* as an alias for
    #       the new QA_Audit_by_Month_Year_* table so existing Excel
    #       workbooks still function.
    missing_by_month_path = qa_dir / f"QA_missing_by_month_{tag}.csv"
    audit_by_month_year_path = qa_dir / f"QA_Audit_by_Month_Year_{tag}.csv"

    counts_overall_path = qa_dir / f"QA_counts_overall_{tag}.csv"
    counts_by_home_store_path = qa_dir / f"QA_counts_by_home_store_{tag}.csv"
    counts_by_year_path = qa_dir / f"QA_counts_by_year_{tag}.csv"
    counts_by_month_path = qa_dir / f"QA_counts_by_month_{tag}.csv"
    counts_by_month_store_path = qa_dir / f"QA_counts_by_month_home_store_{tag}.csv"
    counts_by_month_storekey_path = qa_dir / f"QA_counts_by_month_primary_store_key_{tag}.csv"

    # --- Basic missingness ---
    total_rows = int(master_long.shape[0])
    total_columns = int(master_long.shape[1])
    total_cells = int(total_rows * total_columns)
    total_missing = int(master_long.isna().sum().sum())

    col_miss = master_long.isna().sum().rename("missing_cells").reset_index()
    col_miss = col_miss.rename(columns = {"index": "column"})
    col_miss["total_rows"] = total_rows
    if total_rows > 0:
        col_miss["pct_missing_cells"] = col_miss["missing_cells"] / col_miss["total_rows"]
    else:
        col_miss["pct_missing_cells"] = np.nan
    col_miss = col_miss.sort_values("pct_missing_cells", ascending = False)
    col_miss.to_csv(missing_by_col_path, index = False)

    row_missing_counts = master_long.isna().sum(axis = 1)
    row_dist = (
        row_missing_counts.value_counts()
        .rename_axis("n_missing_cells")
        .reset_index(name = "n_rows")
        .sort_values("n_missing_cells")
    )
    row_dist.to_csv(missing_by_row_dist_path, index = False)

    overall = pd.DataFrame(
        [
            {
                "total_rows": total_rows,
                "total_columns": total_columns,
                "total_cells": total_cells,
                "total_missing_cells": total_missing,
                "pct_missing_cells": (total_missing / total_cells) if total_cells > 0 else np.nan
            }
        ]
    )
    overall.to_csv(overall_summary_path, index = False)

    # --- Missingness by source file (if column exists) ---
    if "SOURCE_FILE" in master_long.columns:
        tmp_source = master_long.copy()
        tmp_source["row_missing"] = row_missing_counts
        miss_by_source = (
            tmp_source.groupby("SOURCE_FILE", as_index = False)
            .agg(
                n_rows = ("row_missing", "size"),
                missing_cells = ("row_missing", "sum")
            )
        )
        if total_columns > 0:
            miss_by_source["pct_missing_cells"] = (
                miss_by_source["missing_cells"] / (miss_by_source["n_rows"] * total_columns)
            )
        else:
            miss_by_source["pct_missing_cells"] = np.nan
        miss_by_source = miss_by_source.sort_values("pct_missing_cells", ascending = False)
        miss_by_source.to_csv(missing_by_source_file_path, index = False)
    else:
        miss_by_source = pd.DataFrame(
            columns = ["SOURCE_FILE", "n_rows", "missing_cells", "pct_missing_cells"]
        )
        miss_by_source.to_csv(missing_by_source_file_path, index = False)

    # --- Date and month labels for coverage tables ---
    tmp_dates = _derive_panel_date(master_long)
    tmp_dates["MONTH_LABEL"] = _safe_month_label(
        tmp_dates.get("YEAR"),
        tmp_dates.get("MONTH")
    )

    # --- Counts overall ---
    counts_overall = overall.copy()
    counts_overall.to_csv(counts_overall_path, index = False)

    # --- Counts by home store ---
    if "HOME_STORE_NAME" in tmp_dates.columns:
        counts_by_store = (
            tmp_dates.groupby("HOME_STORE_NAME", as_index = False)
            .agg(n_records = ("HOME_STORE_NAME", "size"))
            .sort_values("HOME_STORE_NAME")
        )
        counts_by_store.to_csv(counts_by_home_store_path, index = False)
    else:
        counts_by_store = pd.DataFrame(columns = ["HOME_STORE_NAME", "n_records"])
        counts_by_store.to_csv(counts_by_home_store_path, index = False)

    # --- Counts by YEAR ---
    if "YEAR" in tmp_dates.columns:
        counts_by_year = (
            tmp_dates.groupby("YEAR", as_index = False)
            .agg(n_records = ("YEAR", "size"))
            .sort_values("YEAR")
        )
        counts_by_year.to_csv(counts_by_year_path, index = False)
    else:
        counts_by_year = pd.DataFrame(columns = ["YEAR", "n_records"])
        counts_by_year.to_csv(counts_by_year_path, index = False)

    # --- Counts by MONTH_LABEL ---
    if "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month = (
            tmp_dates.groupby("MONTH_LABEL", as_index = False)
            .agg(n_records = ("MONTH_LABEL", "size"))
            .sort_values("MONTH_LABEL")
        )
        counts_by_month.to_csv(counts_by_month_path, index = False)
    else:
        counts_by_month = pd.DataFrame(columns = ["MONTH_LABEL", "n_records"])
        counts_by_month.to_csv(counts_by_month_path, index = False)

    # --- Counts by MONTH_LABEL & HOME_STORE_NAME (raw counts) ---
    if "HOME_STORE_NAME" in tmp_dates.columns and "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month_store = (
            tmp_dates.groupby(["HOME_STORE_NAME", "MONTH_LABEL"], as_index = False)
            .agg(n_records = ("HOME_STORE_NAME", "size"))
            .sort_values(["HOME_STORE_NAME", "MONTH_LABEL"])
        )
        # STATUS here is just for this table; the true missing logic is in the audit below
        counts_by_month_store["STATUS"] = np.where(
            counts_by_month_store["n_records"] > 0,
            "OK",
            "MISSING"
        )
        counts_by_month_store.to_csv(counts_by_month_store_path, index = False)
    else:
        counts_by_month_store = pd.DataFrame(
            columns = ["HOME_STORE_NAME", "MONTH_LABEL", "n_records", "STATUS"]
        )
        counts_by_month_store.to_csv(counts_by_month_store_path, index = False)

    # --- Counts by MONTH_LABEL & PRIMARY_STORE_KEY ---
    if "PRIMARY_STORE_KEY" in tmp_dates.columns and "MONTH_LABEL" in tmp_dates.columns:
        counts_by_month_storekey = (
            tmp_dates.groupby(["PRIMARY_STORE_KEY", "MONTH_LABEL"], as_index = False)
            .agg(n_records = ("PRIMARY_STORE_KEY", "size"))
            .sort_values(["PRIMARY_STORE_KEY", "MONTH_LABEL"])
        )
        counts_by_month_storekey.to_csv(counts_by_month_storekey_path, index = False)
    else:
        counts_by_month_storekey = pd.DataFrame(
            columns = ["PRIMARY_STORE_KEY", "MONTH_LABEL", "n_records"]
        )
        counts_by_month_storekey.to_csv(counts_by_month_storekey_path, index = False)

    # ----------------------------------------------------------------
    # NEW: Audit table by HOME_STORE_NAME x MONTH_YEAR (02-23 to TODAY)
    # ----------------------------------------------------------------
    from datetime import datetime as _dt

    # Canonical store list for the audit
    expected_stores = ["ACC", "CS", "FM", "WM"]

    # Month range: 2023-02 through current month
    start_month = pd.Timestamp(year = 2023, month = 2, day = 1)
    now_dt = _dt.now()
    end_month = pd.Timestamp(year = now_dt.year, month = now_dt.month, day = 1)

    month_range = pd.date_range(start = start_month, end = end_month, freq = "MS")
    month_labels_full = [f"{d.year:04d}-{d.month:02d}" for d in month_range]

    # Create a lookup from counts_by_month_store
    if not counts_by_month_store.empty:
        counts_lookup = (
            counts_by_month_store
            .set_index(["HOME_STORE_NAME", "MONTH_LABEL"])
            .sort_index()
        )
    else:
        counts_lookup = pd.DataFrame(
            columns = ["HOME_STORE_NAME", "MONTH_LABEL", "n_records", "STATUS"]
        )
        if not counts_lookup.empty:
            counts_lookup = counts_lookup.set_index(["HOME_STORE_NAME", "MONTH_LABEL"])

    audit_rows = []

    for store in expected_stores:
        store_upper = str(store).upper()
        for lbl in month_labels_full:
            year_str = lbl[0:4]
            month_str = lbl[5:7]
            yy_str = year_str[2:4]
            month_year = f"{yy_str}-{month_str}"

            key = (store_upper, lbl)
            if counts_lookup is not None and not counts_lookup.empty and key in counts_lookup.index:
                n_records_val = int(counts_lookup.loc[key, "n_records"])
                has_data_flag = 1
                status_val = "OK"
            else:
                n_records_val = 0
                has_data_flag = 0
                status_val = "MISSING"

            audit_rows.append(
                {
                    "HOME_STORE_NAME": store_upper,
                    "YEAR": int(year_str),
                    "MONTH": int(month_str),
                    "MONTH_YEAR": month_year,
                    "N_RECORDS": n_records_val,
                    "HAS_DATA_FLAG": has_data_flag,
                    "STATUS": status_val
                }
            )

    audit_df = pd.DataFrame(audit_rows)
    audit_df = audit_df.sort_values(
        by = ["HOME_STORE_NAME", "YEAR", "MONTH"]
    )

    # Write the new audit output (preferred name)
    audit_df.to_csv(audit_by_month_year_path, index = False)

    # For backward compatibility, also write it to QA_missing_by_month_*
    audit_df.to_csv(missing_by_month_path, index = False)

    return {
        "col_miss_df": col_miss,
        "row_missing_counts": row_missing_counts,
        "overall_summary": overall,
        "miss_by_source": miss_by_source,
        "counts_overall": counts_overall,
        "counts_by_store": counts_by_store,
        "counts_by_year": counts_by_year,
        "counts_by_month": counts_by_month,
        "counts_by_month_store": counts_by_month_store,
        "counts_by_month_storekey": counts_by_month_storekey,
        "audit_by_month_year": audit_df
    }


# -------------------------------------------------------------------
# Static plot and HTML QA site
# -------------------------------------------------------------------
def _write_static_plot(col_miss_df: pd.DataFrame, qa_dir: Path, tag: str) -> Path:
    qa_dir.mkdir(parents = True, exist_ok = True)
    plot_path = qa_dir / f"QA_missing_by_column_{tag}.png"

    if col_miss_df.empty:
        # Create an empty placeholder plot
        plt.figure(figsize = (6, 4))
        plt.text(0.5, 0.5, "No data", ha = "center", va = "center")
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(plot_path, dpi = 120)
        plt.close()
        return plot_path

    df = col_miss_df.sort_values("pct_missing_cells", ascending = False)
    plt.figure(figsize = (max(6, len(df) * 0.3), 4))
    plt.bar(df["column"], df["pct_missing_cells"])
    plt.xticks(rotation = 90)
    plt.ylabel("Pct missing cells")
    plt.tight_layout()
    plt.savefig(plot_path, dpi = 120)
    plt.close()
    return plot_path


def _write_html_site(qa_dir: Path, qa_site_dir: Path, tag: str, plot_path: Optional[Path] = None) -> Path:
    qa_site_dir.mkdir(parents = True, exist_ok = True)
    html_path = qa_site_dir / f"MASTER_QA_site_{tag}.html"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ISER Food Pricing — QA Site {tag}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
</head>
<body class="bg-light">
<div class="container my-4">
  <h1 class="mb-3">ISER Food Pricing — QA Site {tag}</h1>
  <p class="text-muted">Quick overview of missingness and record counts for master build <code>{tag}</code>.</p>

  <h2 class="h4 mt-4">Missing by Column</h2>
  <p><a href="../{qa_dir.name}/QA_missing_by_column_{tag}.csv">Download CSV</a></p>

  <h2 class="h4 mt-4">Missingness Summary</h2>
  <ul>
    <li><a href="../{qa_dir.name}/QA_missing_overall_summary_{tag}.csv">Overall summary</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_row_count_distribution_{tag}.csv">Row missing-count distribution</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_source_file_{tag}.csv">Missing by source file</a></li>
    <li><a href="../{qa_dir.name}/QA_missing_by_month_{tag}.csv">Missing / counts by month &amp; store</a></li>
  </ul>

  <h2 class="h4 mt-4">Record Counts</h2>
  <ul>
    <li><a href="../{qa_dir.name}/QA_counts_overall_{tag}.csv">Counts overall</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_home_store_{tag}.csv">Counts by home store</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_year_{tag}.csv">Counts by year</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_{tag}.csv">Counts by month</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_home_store_{tag}.csv">Counts by month &amp; home store</a></li>
    <li><a href="../{qa_dir.name}/QA_counts_by_month_primary_store_key_{tag}.csv">Counts by month &amp; primary store key</a></li>
  </ul>
</div>
</body>
</html>
"""
    html_path.write_text(html, encoding = "utf-8")
    return html_path


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def run_master_qa(
    builds_root: Path,
    central_log_path: Optional[Path],
    build_tag: Optional[str],
    manifest_path: Optional[Path],
) -> None:
    start = datetime.now()
    try:
        if manifest_path is None:
            manifest_path = _load_manifest(builds_root, build_tag)

        manifest = json.loads(Path(manifest_path).read_text(encoding = "utf-8"))
        tag = manifest["build_tag"]
        qa_dir = Path(manifest["qa_dir"])
        qa_site_dir = Path(manifest["qa_site_dir"])
        panel_csv = Path(manifest["panel_csv"])

        log_line(central_log_path, f"[MASTER_QA] START tag={tag}")

        df = _read_df(panel_csv)
        df = _derive_panel_date(df)
        qa = _write_qa_csvs(df, qa_dir, tag)
        # Plot generation is optional; HTML does not embed a graph (per handoff requirement)
        plot_path = _write_static_plot(qa["col_miss_df"], qa_dir, tag)
        html_path = _write_html_site(qa_dir, qa_site_dir, tag, plot_path)

        elapsed = datetime.now() - start
        log_line(
            central_log_path,
            f"[MASTER_QA] SUCCESS tag={tag} elapsed={str(elapsed).split('.')[0]} HTML={html_path}",
        )
    except Exception as e:
        elapsed = datetime.now() - start
        log_line(
            central_log_path,
            f"[MASTER_QA] FAIL elapsed={str(elapsed).split('.')[0]} error={e}",
        )
        raise


# -------------------------------------------------------------------
# CLI entry point (optional)
# -------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--clean-root", type = str, required = True)
    p.add_argument("--central-log", type = str, default = "")
    p.add_argument("--build-tag", type = str, default = "")
    p.add_argument("--manifest", type = str, default = "")
    args = p.parse_args()

    builds_root = Path(args.clean_root) / "MASTER_builds"
    central_log_path = Path(args.central_log) if args.central_log else None
    build_tag = args.build_tag if args.build_tag else None
    manifest_path = Path(args.manifest) if args.manifest else None

    run_master_qa(builds_root, central_log_path, build_tag, manifest_path)


if __name__ == "__main__":
    main()