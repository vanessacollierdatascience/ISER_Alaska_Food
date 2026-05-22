#!/usr/bin/env python3

from pathlib import Path
import pandas as pd
import json

csv_path = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
    r"\DATA\RAW_DATA\WM_RAW\WM_25_12\sd_mjc2uwzoro56qxt8e.csv"
)

json_path = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
    r"\DATA\RAW_DATA\WM_RAW\WM_25_12\sd_mjc2uwzoro56qxt8e.json"
)



df_csv = pd.read_csv(
    csv_path,
    engine="python",        # required for malformed rows
    on_bad_lines="skip",    # skip broken lines
    encoding="utf-8",
)

print("CSV shape:", df_csv.shape)
print(df_csv.head(3))





with open(json_path, "r", encoding="utf-8") as f:
    raw_json = json.load(f)

# Bright Data JSON is usually a list of records
df_json = pd.json_normalize(raw_json)

print("JSON shape:", df_json.shape)
print(df_json.head(3))


def normalize_columns(df):
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace(".", "_")
    )
    return df

df_csv = normalize_columns(df_csv)
df_json = normalize_columns(df_json)

all_columns = sorted(set(df_csv.columns) | set(df_json.columns))

# Align columns
df_csv = df_csv.reindex(columns=all_columns)
df_json = df_json.reindex(columns=all_columns)

# Concatenate

df_all = pd.concat(
    [df_csv, df_json],
    ignore_index=True,
)

print("Combined shape:", df_all.shape)


# Basic cleaning

# Drop fully empty rows
df_all = df_all.dropna(how="all")


# Strip whitespace ONLY from actual strings
for col in df_all.select_dtypes(include="object").columns:
    df_all[col] = df_all[col].apply(
        lambda x: x.strip() if isinstance(x, str) else x
    )



for col in df_all.columns:
    df_all[col] = df_all[col].apply(
        lambda x: json.dumps(x, ensure_ascii=False)
        if isinstance(x, (dict, list))
        else x
    )

# Remove exact duplicate rows
df_all = df_all.drop_duplicates()

print("After cleaning:", df_all.shape)


# Sanity checks


likely_price_cols = [c for c in df_all.columns if "price" in c]

for col in likely_price_cols:
    df_all[col] = (
        df_all[col]
        .astype(str)
        .str.replace(r"[^\d.]", "", regex=True)
    )

    df_all[col] = pd.to_numeric(df_all[col], errors="coerce")


# SAVE OUTPUT
out_clean = csv_path.with_name("WM_25_12.csv")

df_all.to_csv(out_clean, index=False)

print("Clean file written to:")
print(out_clean)



# Inspect csv

path = Path(
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
    r"\DATA\RAW_DATA\WM_RAW\WM_25_12\WM_25_12.csv"
)

df = pd.read_csv(path, low_memory=False)

print(df.shape)

# readable view
df.dtypes.sort_index()

df.memory_usage(deep=True).sum() / (1024**2)

# Quick inspection

df.sample(10, random_state=42)

# How many stores?

df["url"].nunique()

# How many Zips?
df["input_store_id"].nunique(), df["input_zip_code"].nunique()

# Price check

df["final_price"].describe()

# Missing Data Heatmap

missing = (
    df.isna()
      .mean()
      .sort_values(ascending=False)
)

missing.head(20)

# Duplicate detection
df.duplicated().sum()

df.duplicated(
    subset=["url", "input_store_id", "input_zip_code"]
).sum()


# Inspect nested columns

spec_sample = df["specifications"].dropna().iloc[0]
json.loads(spec_sample)

# Preview
preview_path = path.with_name("WM_25_12_PREVIEW.xlsx")

df.sample(5000, random_state=42).to_excel(
    preview_path,
    index=False
)
