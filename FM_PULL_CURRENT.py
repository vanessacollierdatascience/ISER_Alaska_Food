
#!/usr/bin/env python3

# FM9_vc.py — hardened, env-based secrets, strict JSON, retry on 401, gentle rate limit
# Purpose: Pull Kroger/Fred Meyer prices for a fixed set of UPCs across AK/PNW stores.
# Notes:
#  - Do NOT hard-code secrets. Read KROGER_CLIENT_ID / KROGER_CLIENT_SECRET from env.
#  - This script is designed to be run by central_food_pull.R which injects env vars.

import os
import time
from datetime import datetime
import requests
import pandas as pd
import numpy as np

# Display preferences
np.set_printoptions(suppress=True)
pd.options.display.float_format = lambda x: ('{:.15f}'.format(x)).rstrip('0').rstrip('.')

# ---------------------------------------------------------------------------
# Auth & HTTP helpers
# ---------------------------------------------------------------------------
TOKEN_URL = "https://api.kroger.com/v1/connect/oauth2/token"
BASE_URL  = "https://api.kroger.com/v1/products"

CLIENT_ID = os.environ.get("KROGER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("KROGER_CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError("Missing KROGER_CLIENT_ID/KROGER_CLIENT_SECRET in environment. "
                       "Set them in R (Sys.setenv) or OS before running.")

def get_token():
    r = requests.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        data={"grant_type": "client_credentials", "scope": "product.compact"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    ct = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200:
        raise RuntimeError(f"Token HTTP {r.status_code}; ct={ct}; peek={r.text[:200]!r}")
    try:
        j = r.json()
    except Exception as e:
        raise RuntimeError(f"Token JSON parse failed; ct={ct}; len={len(r.text)}") from e
    tok = j.get("access_token")
    if not tok:
        raise RuntimeError(f"No access_token in token response; keys={list(j.keys())}")
    return tok

S = requests.Session()
S.headers.update({
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0",
})

def get_json(url, headers=None, params=None, timeout=30):
    r = S.get(url, headers=headers or {}, params=params, timeout=timeout)
    ct = (r.headers.get("content-type") or "").lower()
    if r.status_code == 401:
        raise PermissionError("401 Unauthorized")
    if r.status_code == 429:
        raise TimeoutError("429 Too Many Requests")
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}; ct={ct}; peek={r.text[:200]!r}")
    if "application/json" not in ct:
        raise RuntimeError(f"Non-JSON ct={ct}; peek={r.text[:200]!r}")
    return r.json()

def fetch_product(access_token, location_id, upc, retries=2):
    url = f"{BASE_URL}?filter.term={upc}&filter.locationId={location_id}"
    hdr = {"Authorization": f"Bearer {access_token}"}
    attempt = 0
    while True:
        try:
            return get_json(url, headers=hdr)
        except PermissionError:
            # refresh token once then retry
            if attempt >= 1:
                raise
            access_token = get_token()
            hdr = {"Authorization": f"Bearer {access_token}"}
            attempt += 1
            continue
        except TimeoutError:
            # simple backoff for 429
            if retries <= 0:
                raise
            time.sleep(0.75)
            retries -= 1
            continue

# ---------------------------------------------------------------------------
# Locations and UPCs (from your prior script)
# ---------------------------------------------------------------------------
location_ids = [
    '70100011',
    '70100017',
    '70100018',
    '70100071',
    '70100158',
    '70100224',
    '70100485',
    '70100649',
    '70100653',
    '70100656',
    '70100668',
    '70100600',
    '70100122',
]

upcs = [
    '0000000003082',
    '0000000003110',
    '0000000003151',
    '0000000003283',
    '0000000003421',
    '0000000004011',
    '0000000004012',
    '0000000004017',
    '0000000004022',
    '0000000004048',
    '0000000004050',
    '0000000004053',
    '0000000004061',
    '0000000004062',
    '0000000004065',
    '0000000004066',
    '0000000004067',
    '0000000004069',
    '0000000004070',
    '0000000004072',
    '0000000004076',
    '0000000004079',
    '0000000004080',
    '0000000004087',
    '0000000004093',
    '0000000004281',
    '0000000004430',
    '0000000004550',
    '0000000004554',
    '0000000004562',
    '0000000004608',
    '0000000004640',
    '0000000004662',
    '0000000004664',
    '0000000004688',
    '0000000004784',
    '0000000004799',
    '0000000004800',
    '0000000004816',
    '0000000094011',
    '0001111000454',
    '0001111003931',
    '0001111008415',
    '0001111008450',
    '0001111008963',
    '0001111010491',
    '0001111013198',
    '0001111013199',
    '0001111013204',
    '0001111014186',
    '0001111018170',
    '0001111018183',
    '0001111018189',
    '0001111040190',
    '0001111041491',
    '0001111041550',
    '0001111061375',
    '0001111078773',
    '0001111084703',
    '0001111085004',
    '0001111085605',
    '0001111087703',
    '0001111089875',
    '0001111090406',
    '0001111091011',
    '0001111091013',
    '0001111091620',
    '0001111091622',
    '0001111091629',
    '0001111091649',
    '0001111091754',
    '0001111091871',
    '0001111096920',
    '0001111096968',
    '0001111097191',
    '0001111097209',
    '0001200000017',
    '0001300000640',
    '0001580003061',
    '0001580003062',
    '0001590013401',
    '0001600010610',
    '0001700001840',
    '0002020008511',
    '0002100060464',
    '0002400016286',
    '0002400055078',
    '0002550030445',
    '0002640022300',
    '0003000001020',
    '0003077209398',
    '0003338314616',
    '0003338320027',
    '0003338321000',
    '0003338324000',
    '0003338370154',
    '0003600049695',
    '0003600051472',
    '0003700077307',
    '0003700084997',
    '0003760013872',
    '0003800000110',
    '0003890004215',
    '0004100000287',
    '0004400004483',
    '0004470007505',
    '0004740024040',
    '0004740066181',
    '0004800000195',
    '0004800121351',
    '0004900002890',
    '0005000001011',
    '0005150001229',
    '0005150025516',
    '0005410722101',
    '0007007455958',
    '0007007458586',
    '0007040400282',
    '0007047000302',
    '0007066202603',
    '0007283000201',
    '0007283000401',
    '0007373100415',
    '0007800001180',
    '0007940049594',
    '0019600570834',
    '0020236600000',
    '0021190600000',
    '0021386300000',
    '0028334850000',
    '0028334900000',
    '0029315150000',
    '0082785400183',
    '0088828900051',
    '0212236000000',
]

# ---------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------
token = get_token()
results_list = []
today_str = datetime.now().strftime("%Y-%m-%d")

for location_id in location_ids:
    for upc in upcs:
        try:
            data = fetch_product(token, location_id, upc)
            results_list.append({
                "Location ID": location_id,
                "UPC": upc,
                "status": 200,
                "data": data,
                "Date": today_str,
            })
        except Exception as e:
            results_list.append({
                "Location ID": location_id,
                "UPC": upc,
                "status": "error",
                "error": str(e),
                "Date": today_str,
            })
        time.sleep(0.15)  # polite throttle

results = pd.concat([pd.DataFrame(results_list)], ignore_index=True)

# ---------------------------------------------------------------------------
# Save to RAW_DATA\FM_RAW (or FM_OUT_DIR from environment)
# ---------------------------------------------------------------------------
now = datetime.now()
year = now.strftime("%y")
month = now.strftime("%m")
filename = f"FM_{year}_{month}.json"

foldername = now.strftime('FM_%y_%m')


# Use FM_OUT_DIR if set in the BAT; otherwise default to RAW_DATA\FM_RAW
fm_root = os.environ.get(
    "FM_OUT_DIR",
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\FM_RAW",
)

folder_path = os.path.join(fm_root, foldername)
os.makedirs(folder_path, exist_ok=True)

out_path = os.path.join(folder_path, filename)

# Use compact JSON to keep size smaller; switch indent=2 while debugging
results.to_json(out_path, orient="records")

print(f"Results saved to {out_path}")
