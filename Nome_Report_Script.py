#!/usr/bin/env python3
import tempfile
import time
import argparse
import os
import re
from datetime import datetime
from glob import glob
import pandas as pd
import numpy as np
import xlsxwriter

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
DEFAULT_MASTER_DIR = (
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\MASTER_DATA"
)

NOME_SKU_LIST = [
    "8810272", "1510190", "97412936", "97402947", "92739363", "8310918",
    "8310927", "90594398", "610066", "93018577", "8310909", "8311356",
    "1610028", "95949415", "95949424", "316777", "316768"
]

# ──────────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build a Nome Nugget Excel report from the master CSV.")
    p.add_argument("--input", default="", help="Optional path to master file (.csv or .parquet).")
    p.add_argument("--input-dir", default=os.environ.get("MASTER_DIR", DEFAULT_MASTER_DIR),
                   help="Directory to scan for latest master CSV when --input not provided.")
    p.add_argument("--city", default="Nome", help="City filter. Default: Nome.")
    p.add_argument("--outdir",
                   default=(r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
                            r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
                            r"\DATA\REPORTS\Nome_Nugget"),
                   help="Output directory for Excel report.")
    return p.parse_args()


def find_latest_csv(dir_path: str, pattern: str = "*.csv") -> str:
    candidates = glob(os.path.join(dir_path, pattern))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found in: {dir_path}")
    return max(candidates, key=os.path.getmtime)


def read_master(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".parquet":
        return pd.read_parquet(path)
    if ext == ".csv":
        return pd.read_csv(path, low_memory=False)
    raise ValueError("Unsupported input format. Use .csv or .parquet")


def ensure_datetime(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    fmts = ["%Y-%m-%d", "%y-%m-%d", "%m-%d-%y", "%m/%d/%y", "%d-%m-%Y", "%d/%m/%Y"]
    for fmt in fmts:
        mask = out.isna()
        if not mask.any():
            break
        parsed = pd.to_datetime(s[mask], format=fmt, errors="coerce")
        out.loc[mask] = parsed
    mask = out.isna()
    if mask.any():
        out.loc[mask] = pd.to_datetime(s[mask], errors="coerce", utc=False)
    return out


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def extract_multiplier(text: str) -> float:
    if text is None:
        return 1.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1)) * float(m.group(2))
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*[xX]", text)
    if m2:
        return float(m2.group(1))
    return 1.0


def size_to_ounces(size_text: str) -> float:
    if not isinstance(size_text, str):
        return np.nan
    text = size_text.strip().upper()
    mult = extract_multiplier(text)
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(FL\s*OZ|FLOZ|OZ|OUNCE|OZ\.)", 1.0),
        (r"(\d+(?:\.\d+)?)\s*(LB|LBS|POUND|LB\.)", 16.0),
        (r"(\d+(?:\.\d+)?)\s*(KG|KGS|KG\.)", 35.27396195),
        (r"(\d+(?:\.\d+)?)\s*(G|GR|GRAM|G\.)", 1 / 28.349523125),
        (r"(\d+(?:\.\d+)?)\s*(L|LITER|LITRE|L\.)", 33.8140227),
        (r"(\d+(?:\.\d+)?)\s*(ML|ML\.)", 1 / 29.5735296)
    ]
    for pat, mult_factor in patterns:
        m = re.search(pat, text)
        if m:
            return float(m.group(1)) * mult * mult_factor
    return np.nan


def add_price_per_oz(df: pd.DataFrame) -> pd.DataFrame:
    size_col = next((c for c in ["SIZE", "Item_Size", "item_size", "Size",
                                 "ITEM_SIZE", "PRODUCT_SIZE"] if c in df.columns), None)
    price_col = next((c for c in ["PRICE", "Price", "price",
                                  "Unit_Price", "UNIT_PRICE"] if c in df.columns), None)
    if price_col is None:
        raise KeyError("No price column found.")
    df["__ounces"] = df[size_col].apply(size_to_ounces) if size_col else np.nan
    df["__price_num"] = to_number(df[price_col])
    df["PRICE_PER_OZ"] = np.where(df["__ounces"] > 0,
                                  df["__price_num"] / df["__ounces"], np.nan)
    return df


def build_summary_for_month(df: pd.DataFrame, month_start: pd.Timestamp) -> pd.DataFrame:
    mask = df["PULL_DATE"].dt.to_period("M") == month_start.to_period("M")
    month_df = df.loc[mask].copy()
    rows = [
        {"Metric": "Month", "Value": month_start.strftime("%B %Y")},
        {"Metric": "Total Rows", "Value": len(month_df)},
        {"Metric": "Unique UPCs", "Value": month_df.get("UPC", pd.Series()).nunique(dropna=True)},
        {"Metric": "Unique SKUs", "Value": month_df.get("SKU", pd.Series()).nunique(dropna=True)},
        {"Metric": "Mean Price", "Value": round(month_df["__price_num"].mean(skipna=True), 4)},
        {"Metric": "Median Price", "Value": round(month_df["__price_num"].median(skipna=True), 4)},
        {"Metric": "Mean Price per oz", "Value": round(month_df["PRICE_PER_OZ"].mean(skipna=True), 6)},
        {"Metric": "Median Price per oz", "Value": round(month_df["PRICE_PER_OZ"].median(skipna=True), 6)},
    ]
    return pd.DataFrame(rows)


def sanitize_sheet_name(name: str) -> str:
    return re.sub(r'[][*?:/\\]', "_", name)[:31]


def autofit_columns(ws, headers):
    for i, col in enumerate(headers):
        ws.set_column(i, i, max(12, min(40, len(str(col)) + 2)))


def unique_out_path(outdir: str, base_name: str) -> str:
    root, ext = os.path.splitext(base_name)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(outdir, f"{root}_{ts}{ext}")


def safe_replace(src: str, dst: str) -> str:
    try:
        os.replace(src, dst)
        return dst
    except Exception:
        return src

# ──────────────────────────────────────────────────────────────
# Main report generation
# ──────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    in_path = args.input.strip() or find_latest_csv(args.input_dir.strip(), "*.csv")
    os.makedirs(args.outdir, exist_ok=True)

    df = read_master(in_path)
    if "PULL_DATE" not in df.columns:
        raise KeyError("Master dataframe must include PULL_DATE.")
    df["PULL_DATE"] = ensure_datetime(df["PULL_DATE"])
    if "CITY" not in df.columns:
        raise KeyError("Master dataframe must include CITY.")

    city = args.city
    filtered = df.loc[df["CITY"].astype(str) == str(city)].copy()
    filtered = filtered.sort_values("PULL_DATE", ascending=True)
    filtered = add_price_per_oz(filtered)

    latest_ts = filtered["PULL_DATE"].dropna().max()
    if pd.isna(latest_ts):
        raise ValueError("No valid PULL_DATE values after filtering.")
    month_start = pd.Timestamp(latest_ts.year, latest_ts.month, 1)
    month_text = month_start.strftime("%B_%Y")

    file_name = f"Nome_Nugget_{month_text}.xlsx"
    out_path = os.path.join(args.outdir, file_name)
    if os.path.exists(out_path):
        out_path = unique_out_path(args.outdir, file_name)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx", dir=args.outdir)
    tmp_path = tmp.name
    tmp.close()

    with pd.ExcelWriter(tmp_path, engine="xlsxwriter",
                        datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as writer:

        # --- Tab 1: Summary ---
        summary_df = build_summary_for_month(filtered, month_start)
        tab1 = sanitize_sheet_name(f"Summary_for_{month_start.strftime('%B_%Y')}")
        summary_df.to_excel(writer, index=False, sheet_name=tab1)
        ws1 = writer.sheets[tab1]
        autofit_columns(ws1, list(summary_df.columns))

        # --- Tab 2: All Nome data ---
        drop_helpers = ["__ounces", "__price_num"]
        keep_cols = [c for c in filtered.columns if c not in drop_helpers]
        tab2 = sanitize_sheet_name(f"All_Data_for_{city}")
        filtered[keep_cols].to_excel(writer, index=False, sheet_name=tab2)
        ws2 = writer.sheets[tab2]
        autofit_columns(ws2, list(filtered[keep_cols].columns))

        # --- Tab 3: Selected SKUs (ALL time) ---
        sku_all = filtered.loc[filtered["SKU"].astype(str).isin(NOME_SKU_LIST)].copy()
        sku_all = sku_all.sort_values(["PULL_DATE", "SKU"])
        tab3 = "Selected_SKUs_All_Time"
        if len(sku_all) > 0:
            sku_all.to_excel(writer, index=False, sheet_name=tab3)
            ws3 = writer.sheets[tab3]
            autofit_columns(ws3, list(sku_all.columns))
        else:
            pd.DataFrame({"Note": ["No matching SKUs found."]}).to_excel(writer, index=False, sheet_name=tab3)

        # --- Tab 4: Time-series data ---
        month_index = pd.period_range(start=filtered["PULL_DATE"].min().to_period("M"),
                                      end=filtered["PULL_DATE"].max().to_period("M"), freq="M")
        month_labels = month_index.strftime("%m-%y")

        sku_subset = filtered.loc[filtered["SKU"].astype(str).isin(NOME_SKU_LIST)].copy()
        sku_subset["MONTH"] = sku_subset["PULL_DATE"].dt.to_period("M")
        price_col = "__price_num" if "__price_num" in sku_subset.columns else "PRICE"

        desc_map = (sku_subset[["SKU", "SKU_DESCRIPTION"]]
                    .dropna(subset=["SKU"])
                    .drop_duplicates(subset=["SKU"])
                    .set_index("SKU")["SKU_DESCRIPTION"]
                    .to_dict())

        sku_month_means = (sku_subset.groupby(["SKU", "MONTH"], dropna=False)[price_col]
                           .mean()
                           .reset_index()
                           .pivot(index="MONTH", columns="SKU", values=price_col)
                           .reindex(month_index))

        new_cols, seen = [], set()
        for sku in sku_month_means.columns:
            name = str(desc_map.get(sku, sku))
            if name in seen:
                name = f"{name} ({sku})"
            seen.add(name)
            new_cols.append(name)
        sku_month_means.columns = new_cols

        all_month_avg = (filtered.assign(MONTH=filtered["PULL_DATE"].dt.to_period("M"))
                         .groupby("MONTH", dropna=False)["__price_num"]
                         .mean()
                         .reindex(month_index))

        ts_table = sku_month_means.copy()
        ts_table.insert(0, "MONTH_YEAR", month_labels)
        ts_table["All Products Avg Price"] = all_month_avg.values

        tab4 = "SKU_Time_SeriesData"
        ts_table.to_excel(writer, index=False, sheet_name=tab4)
        ws4 = writer.sheets[tab4]
        autofit_columns(ws4, list(ts_table.columns))

        # --- Chart sheet ---
        chart_ws = writer.book.add_worksheet("SKU_TimeSeries")
        chart = writer.book.add_chart({"type": "line"})
        n_rows, n_cols = len(ts_table.index), len(ts_table.columns)

        for col_idx in range(1, n_cols - 1):
            chart.add_series({
                "name": [tab4, 0, col_idx],
                "categories": [tab4, 1, 0, n_rows, 0],
                "values": [tab4, 1, col_idx, n_rows, col_idx],
                "line": {"width": 1.5}
            })

        avg_col = n_cols - 1
        chart.add_series({
            "name": [tab4, 0, avg_col],
            "categories": [tab4, 1, 0, n_rows, 0],
            "values": [tab4, 1, avg_col, n_rows, avg_col],
            "line": {"width": 3.0, "color": "red"}
        })

        chart.set_title({"name": "Nome — Selected SKUs vs Monthly Average"})
        chart.set_x_axis({"name": "MONTH_YEAR"})
        chart.set_y_axis({"name": "Average Price"})
        chart.set_size({"width": 980, "height": 520})
        chart_ws.insert_chart("B2", chart)

    final_path = safe_replace(tmp_path, out_path)
    if final_path != out_path:
        print(f"Target locked, kept temp: {final_path}")

    print(f"Input file: {in_path}")
    print(f"Report written to: {out_path}")


if __name__ == "__main__":
    main()
