#!/usr/bin/env python3
import os
import sys
import csv
import requests
from pathlib import Path
from datetime import datetime

# ---------------- CONFIG ----------------

API_KEY = os.getenv("WM_API_KEY")
DATASET_ID = os.getenv("WM_DATASET_ID", "gd_m693oc1r1gebnayxq")
WM_MODE = os.getenv("WM_MODE", "PULL").upper()

BASE_URL = "https://api.brightdata.com/datasets/v3"
REGISTRY = Path(
    r"C:\Users\vlcollier\GITHUB_PUSH\Alaska_Food\DATA_PULL_SCRIPTS\WM\wm_snapshot_registry.csv"
)



# ---------------- HELPERS ----------------

def die(msg):
    print(msg, file=sys.stderr, flush=True)
    sys.exit(1)

def log_snapshot(snapshot_id: str):
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    new = not REGISTRY.exists()

    with REGISTRY.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["snapshot_id", "trigger_time", "last_checked", "status", "notes"])
        w.writerow([
            snapshot_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "",
            "TRIGGERED",
            ""
        ])

def trigger_snapshot():
    url = f"{BASE_URL}/trigger"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = {
        "dataset_id": DATASET_ID,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }

    payload = [
        {"keyword": item, "zip_code": z, "store_id": ""}
        for item in SEARCH_ITEMS
        for z in SEARCH_ZIPS
    ]

    r = requests.post(url, headers=headers, params=params, json=payload, timeout=120)
    r.raise_for_status()

    snapshot_id = r.json().get("snapshot_id")
    if not snapshot_id:
        die("No snapshot_id returned")

    print(f"[WM] Snapshot triggered: {snapshot_id}")
    return snapshot_id

    
# THIS loads search
    
def load_search_file(path):
    items = []
    zips = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("item"):
                items.extend([x.strip() for x in line.split("=")[1].split(",")])
            elif line.lower().startswith("zip"):
                zips.extend([x.strip() for x in line.split("=")[1].split(",")])
    return items, zips


SEARCH_FILE = os.getenv("WM_SEARCH_FILE")
if not SEARCH_FILE:
    die("WM_SEARCH_FILE not set")

SEARCH_ITEMS, SEARCH_ZIPS = load_search_file(SEARCH_FILE)


# Safeguard from silent failure:
if not SEARCH_ITEMS or not SEARCH_ZIPS:
    die(f"WM_SEARCH_FILE produced no items or zips: {SEARCH_FILE}")

# ---------------- MAIN ----------------

def main():
    if not API_KEY:
        die("WM_API_KEY missing")

    if WM_MODE != "PULL":
        die("WM_PULL_CURRENT.py only supports WM_MODE=PULL")

    snapshot_id = trigger_snapshot()
    log_snapshot(snapshot_id)

    print("[WM] PULL complete — exiting")
    sys.exit(0)

if __name__ == "__main__":
    main()
