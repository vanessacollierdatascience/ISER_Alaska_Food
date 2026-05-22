#!/usr/bin/env python3

import os
import sys
import requests
from pathlib import Path
from datetime import datetime

# ======================================================
# REQUIRED ENVIRONMENT VARIABLES (SET BY BAT)
# ======================================================

API_KEY = os.getenv("WM_API_KEY", "").strip()
SNAPSHOT_ID = os.getenv("WM_SNAPSHOT_ID", "").strip()
WM_RAW_ROOT = os.getenv("WM_RAW_ROOT", "").strip()

if not API_KEY:
    print("[WM] ERROR: WM_API_KEY not set", file=sys.stderr)
    sys.exit(1)

if not SNAPSHOT_ID:
    print("[WM] ERROR: WM_SNAPSHOT_ID not set", file=sys.stderr)
    sys.exit(1)

if not WM_RAW_ROOT:
    print("[WM] ERROR: WM_RAW_ROOT not set", file=sys.stderr)
    sys.exit(1)

# ======================================================
# OUTPUT PATHS (RAW_DATA ONLY — NO REPO WRITES)
# ======================================================

STORE = "WM"
YY_MM = datetime.now().strftime("%y_%m")

OUT_DIR = Path(WM_RAW_ROOT) / f"{STORE}_{YY_MM}"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_FILE = OUT_DIR / f"{SNAPSHOT_ID}.json"

# ======================================================
# BRIGHT DATA SNAPSHOT DOWNLOAD URL
# ======================================================

FORMAT = os.getenv("WM_SNAPSHOT_FORMAT", "csv").lower()

URL = (
    f"https://api.brightdata.com/datasets/v3/snapshot/"
    f"{SNAPSHOT_ID}?format={FORMAT}"
)


HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

print(f"[WM] SNAPSHOT_ID = {SNAPSHOT_ID}")
print(f"[WM] Download URL = {URL}")
print(f"[WM] Output path = {OUT_FILE}")

# ======================================================
# DOWNLOAD LOGIC (DEFENSIVE AGAINST BRIGHT DATA BUG)
# ======================================================

try:
    response = requests.get(
        URL,
        headers=HEADERS,
        stream=True,
        timeout=900
    )
    response.raise_for_status()

    # Read first chunk to determine payload type
    first_chunk = next(response.iter_content(chunk_size=2048), b"")

    # --------------------------------------------------
    # CASE 1: Bright Data returns STATUS JSON (BUG)
    # --------------------------------------------------
    if first_chunk.lstrip().startswith(b"{"):
        try:
            text = first_chunk.decode("utf-8", errors="ignore")
        except Exception:
            text = ""

        print("[WM] Bright Data returned status payload instead of dataset:")
        print(text)

        # EXIT CLEANLY so scheduler can retry later
        print("[WM] Exiting without failure — will retry later.")
        sys.exit(0)

    # --------------------------------------------------
    # CASE 2: Real dataset — write file
    # --------------------------------------------------
    with open(OUT_FILE, "wb") as f:
        f.write(first_chunk)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    size_mb = OUT_FILE.stat().st_size / (1024 * 1024)
    print(f"[WM] Snapshot downloaded successfully ({size_mb:.2f} MB)")
    print(f"[WM] Saved to: {OUT_FILE}")

except Exception as e:
    print(f"[WM] ERROR downloading snapshot: {e}", file=sys.stderr)
    sys.exit(1)

print("[WM] SUCCESS")
sys.exit(0)



