#!/usr/bin/env python3

import ssl
import urllib.request
import json
import time

CS_OUT_DIR = os.environ.get(
    "CS_OUT_DIR",
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\CS_RAW",
)

# Bright Data Access Credentials
brd_user = 'hl_a394e9a7'
brd_zone = 'residential_proxy1'
brd_passwd = 'n51uj6o186v8'
brd_superpoxy = 'brd.superproxy.io:33335'  # Use port 33335 as per Bright Data SSL instructions
brd_connectStr = f'brd-customer-{brd_user}-zone-{brd_zone}:{brd_passwd}@{brd_superpoxy}'

# Create an SSL context that ignores certificate verification (not recommended for production)
context = ssl._create_unverified_context()

# Proxy handler with Bright Data credentials
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({
        'http': f'http://{brd_connectStr}',
        'https': f'https://{brd_connectStr}'
    }),
    urllib.request.HTTPSHandler(context=context)
)

# Mimic real browser traffic
opener.addheaders = [
    ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'),
    ('Accept', 'application/json, text/plain, */*'),
    ('Referer', 'https://www.safeway.com/'),
    ('Origin', 'https://www.safeway.com')
]

# URL for Safeway product search API
store_id = "1820"  # Example Safeway store ID
product_code = "117200002"  # Example product code
safeway_url = f"https://www.safeway.com/abs/pub/xapi/pgmsearch/v1/search/products?storeid={store_id}&q={product_code}"

# Retry logic for network or API errors
max_retries = 3
retry_count = 0

while retry_count < max_retries:
    try:
        # Make request to Safeway product search API
        response = opener.open(safeway_url)
        data = response.read().decode()

        # Attempt to parse JSON response
        if data:
            parsed_data = json.loads(data)
            print(json.dumps(parsed_data, indent=4))
        else:
            print("No data received from Safeway API.")
        break  # Success, exit loop

    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        if e.code == 403:
            print("Forbidden: Check credentials or if the IP is blocked")
        retry_count += 1
        time.sleep(2 ** retry_count)  # Exponential backoff for retries

    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
        retry_count += 1
        time.sleep(2 ** retry_count)  # Exponential backoff

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e.msg}")
        break  # No point retrying if it's a parsing error

    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        break  # Exit if other unexpected errors occur


