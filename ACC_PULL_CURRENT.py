#!/usr/bin/env python3

import os
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
import time
import json
import pandas as pd
import requests

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ──────────────────────────────────────────────────────────────────────────────
# 0. SET UP A SIMPLE FILE-BASED LOG
# ──────────────────────────────────────────────────────────────────────────────
LOG_DIR = os.environ.get(
    "SCRAPE_LOG_DIR",
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg"
    r"\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING"
    r"\DATA_PULL_SCRIPTS\Scraping_Logs"
)
os.makedirs(LOG_DIR, exist_ok=True)


today_str = datetime.now().strftime("%Y%m%d")
log_path = os.path.join(LOG_DIR, f"scraping_{today_str}.log")

logging.basicConfig(
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

# ──────────────────────────────────────────────────────────────────────────────
# 1. EMAIL NOTIFICATION FUNCTION
# ──────────────────────────────────────────────────────────────────────────────
def send_email(store_id: str, record_count: int, csv_path: str):
    subject = f"ACC_{store_id}_{datetime.now().strftime('%Y-%m-%d')}.csv is saved"
    body = (
        f"Hello,\n\n"
        f"The ACC store {store_id} dataset has been saved successfully.\n"
        f"Record count: {record_count}\n"
        f"Location: {csv_path}\n\n"
        f"— Your scraper"
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = "vlcollier@alaska.edu"
    msg["To"] = "vlcollier@alaska.edu"

    smtp_server = "smtp.alaska.edu"
    smtp_port = 465
    smtp_user = "vlcollier@alaska.edu"
    smtp_pass = "gefk toly yukl yfkq" # Replace with your actual app password

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logging.info(f"Email sent for store {store_id}")
    except Exception as e:
        logging.error(f"Failed to send email for store {store_id}: {e}")


# Root output directory for ACC raw files (override via ACC_OUT_DIR env)
ACC_OUT_DIR = os.environ.get(
    "ACC_OUT_DIR",
    r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\GITHUB\ISER\MJones\FOOD_SECURITY\FOOD_PRICING\DATA\RAW_DATA\ACC_RAW",
)

# ──────────────────────────────────────────────────────────────────────────────
# 2. SAVE + EMAIL + LOG RESULTS
# ──────────────────────────────────────────────────────────────────────────────
def save_payload_results_with_log_and_email(df: pd.DataFrame, store: str):
    now = datetime.now()
    year_last2 = now.strftime("%y")
    month_str = now.strftime("%m")

    base_path = ACC_OUT_DIR

    folder_name = f"ACC_{year_last2}_{month_str}"
    folder_path = os.path.join(
    ACC_OUT_DIR,
    f"ACC_{now.strftime('%y')}_{now.strftime('%m')}"
)

    os.makedirs(folder_path, exist_ok=True)

    file_name = f"ACC_{store}_{month_str}_{year_last2}.csv"
    file_path = os.path.join(folder_path, file_name)

    df.to_csv(file_path, index=False)
    print(f"Payload results saved to {file_path}")

    record_count = len(df)
    logging.info(f"Store {store}: saved {record_count} records to {file_path}")

    try:
        send_email(store, record_count, file_path)
    except Exception as e:
        logging.error(f"Email failed for store {store}: {e}")

# ──────────────────────────────────────────────────────────────────────────────
def retrieve_token(driver, zip_code):
    try:
        driver.get("https://shopalaskacommercial.com/")
        time.sleep(5)
        wait = WebDriverWait(driver, 10)
        zip_input_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[2]/input"
        zip_input = wait.until(EC.presence_of_element_located((By.XPATH, zip_input_xpath)))
        zip_input.clear()
        zip_input.send_keys(zip_code)

        special_xpaths = {
            '99574': "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span"
        }
        select_xpath = special_xpaths.get(zip_code, "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/div[3]/div/button/span")
        select_button = wait.until(EC.element_to_be_clickable((By.XPATH, select_xpath)))
        select_button.click()

        save_button_xpath = "/html/body/p-dynamicdialog/div/div/div/app-store-location/div/div/button"
        save_button = wait.until(EC.element_to_be_clickable((By.XPATH, save_button_xpath)))
        save_button.click()

        time.sleep(10)
        token = driver.execute_script("return window.localStorage.getItem('token');")
        return token.replace('"', '') if token else None
    except Exception as e:
        logging.error(f"Token retrieval failed for ZIP {zip_code}: {e}")
        return None


def search_keyword_payload(token, keyword, store):
    url = "https://backend.shopalaskacommercial.com/storeItem/algolia"
    params = {"STORE": store, "PAGE": "1", "LIMIT": "30", "TRENDING_SEARCH": "false", "PARTY_TRAY_FLAG": "false"}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {"SEARCH_STRING": keyword}
    response = requests.post(url, params=params, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    logging.warning(f"Keyword '{keyword}' request failed for store {store}: {response.status_code}")
    return None

def save_original_json(json_data, store):
    now = datetime.now()
    folder_path = os.path.join(
        r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC",
        f"ACC_{now.strftime('%y')}_{now.strftime('%m')}"
    )
    os.makedirs(folder_path, exist_ok=True)
    file_path = os.path.join(folder_path, f"ACC_{store}_{now.strftime('%m')}_{now.strftime('%y')}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=4)

def collapse_response_column(json_data):
    if not json_data:
        return pd.DataFrame()
    meta_keys = [k for k in json_data[0].keys() if k not in ['response', 'algoliaResponse']]
    try:
        df_flat = pd.json_normalize(json_data, record_path='response', meta=meta_keys, sep='_')
        if 'item' in df_flat.columns:
            df_flat['item'] = df_flat['item'].apply(lambda x: x[0] if isinstance(x, list) and x else {})
            df_item = pd.json_normalize(df_flat['item'], sep='_')
            df_flat = pd.concat([df_flat.drop(columns=['item']), df_item], axis=1)
        return df_flat
    except Exception as e:
        logging.error(f"Flattening error: {e}")
        return pd.DataFrame()

def main():
    print("Starting ACC data scraping...")
    keywords_csv_path = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data_Scraping\ACC\ACC_Keyword_Data_Restored.csv"
    crosswalk_csv = r"G:\.shortcut-targets-by-id\10hwxlrEnEox7VqS6tvo44Q8rX59qZcSg\Drones_MV\UAV Rural Essential Goods Delivery\FOOD_PRICING\Data\CROSSWALKS\Stores_Crosswalk.csv"

    keywords = pd.read_csv(keywords_csv_path)["ACC_Keywords"].dropna().tolist()
    store_df = pd.read_csv(crosswalk_csv)
    store_df = store_df[store_df['HOME_STORE_NAME'] == 'ACC'].drop_duplicates(subset=['STORE_ID'])

    for _, row in store_df.iterrows():
        zip_code = str(row['ZIP'])
        store_id = str(row['STORE_ID'])
        print(f"\nProcessing ZIP {zip_code} (store {store_id})")

        options = Options()
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        token = retrieve_token(driver, zip_code)
        driver.quit()

        if not token:
            print(f"  Failed to retrieve token for ZIP {zip_code}, skipping.")
            logging.warning(f"Skipping store {store_id} (ZIP {zip_code}) — token not found")
            continue

        all_payload_results = []
        for i, keyword in enumerate(keywords, start=1):
            print(f"  ({i}/{len(keywords)}) Searching keyword: '{keyword}'")
            data = search_keyword_payload(token, keyword, store=store_id)
            if data:
                data["searched_keyword"] = keyword
                data["zip_code"] = zip_code
                all_payload_results.append(data)

        if not all_payload_results:
            print(f"  No results found for store {store_id}, skipping.")
            logging.info(f"No results for store {store_id}, skipping")
            continue

        save_original_json(all_payload_results, store_id)
        df_flat = collapse_response_column(all_payload_results)
        if df_flat.empty:
            print(f"  Flattened dataframe is empty for store {store_id}, skipping CSV.")
            logging.warning(f"Flattened dataframe empty for store {store_id}")
            continue

        print(f"  Saving and emailing results for store {store_id}...")
        save_payload_results_with_log_and_email(df_flat, store_id)
        time.sleep(10)

if __name__ == "__main__":
    main()
