import requests
import yaml
import json
import threading
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
import time
import pandas as pd

from app.logger import setup_logging

setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.propagate = False

DATA_DIR_RAW = Path("data/raw")
DATA_DIR_PROCESSED = Path("data/processed")

with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

API_KEY = CONFIG.get("api_key")
SYMBOLS = CONFIG.get("symbols", {})
BASE_URL = "https://eodhistoricaldata.com/api"
HEADERS = {"Content-Type": "application/json"}

api_calls_today = 0
last_call_date = date.today()
api_counter_lock = threading.Lock()
API_COUNT_FILE = Path("logs/api_calls_today.json")

CACHE_EXPIRY_SECONDS = 3600  # 1 hour cache expiry

def ensure_directories():
    DATA_DIR_RAW.mkdir(parents=True, exist_ok=True)
    DATA_DIR_PROCESSED.mkdir(parents=True, exist_ok=True)
    API_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_api_count():
    global api_calls_today, last_call_date
    try:
        if API_COUNT_FILE.exists():
            with open(API_COUNT_FILE, "r") as f:
                data = json.load(f)
                api_calls_today = data.get("api_calls_today", 0)
                last_call_date = date.fromisoformat(data["last_call_date"])
    except Exception as e:
        logger.error(f"Error loading API count: {str(e)}")

def save_api_count():
    try:
        with open(API_COUNT_FILE, "w") as f:
            json.dump({
                "api_calls_today": api_calls_today,
                "last_call_date": last_call_date.isoformat()
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving API count: {str(e)}")

def increment_api_count():
    global api_calls_today, last_call_date
    with api_counter_lock:
        today = date.today()
        if today != last_call_date:
            api_calls_today = 0
            last_call_date = today
        api_calls_today += 1
        save_api_count()

def get_last_trading_day(current_date=None):
    current_date = current_date or pd.Timestamp.today().date()
    # Use pandas BusinessDay to get last business day
    last_business_day = pd.Timestamp(current_date) - pd.tseries.offsets.BusinessDay(1)
    return last_business_day.date()

def load_cached_data(symbol):
    cache_dir = DATA_DIR_PROCESSED
    files = sorted(cache_dir.glob(f"{symbol}_*.json"), reverse=True)
    if not files:
        return None
    latest_file = files[0]
    if time.time() - latest_file.stat().st_mtime > CACHE_EXPIRY_SECONDS:
        return None
    try:
        with open(latest_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load cache {latest_file}: {e}")
        return None

def _fetch_for_day(symbol, trading_day, interval="5m"):
    start_dt = datetime.combine(trading_day, datetime.min.time())
    end_dt = datetime.combine(trading_day, datetime.max.time())

    params = {
        "api_token": API_KEY,
        "interval": interval,
        "fmt": "json",
        "from": int(start_dt.timestamp()),
        "to": int(end_dt.timestamp())
    }

    try:
        if api_calls_today >= 100000:
            raise Exception("Daily API limit (100,000) reached")

        logger.info(f"Fetching {symbol} ({interval}) for {trading_day.strftime('%Y-%m-%d')}")
        response = requests.get(f"{BASE_URL}/intraday/{symbol}", params=params, timeout=10)

        if response.status_code != 200:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return None

        increment_api_count()
        data = response.json()

        if not data:
            logger.warning(f"No data for {symbol} on {trading_day}")
            return None

        return data

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {str(e)}")
        return None

def fetch_intraday_data(symbol, interval="5m"):
    # Try cache first
    cached = load_cached_data(symbol)
    if cached:
        logger.info(f"Using cached data for {symbol}")
        return cached

    # Try last trading day
    trading_day = get_last_trading_day()
    data = _fetch_for_day(symbol, trading_day, interval)
    if data:
        # Cache raw and processed data
        cache_data(symbol, data)
        processed = sorted(data, key=lambda x: x.get('date', ''))
        cache_data(symbol, processed, processed=True)
        return data

    # Fallback to previous business day if no data
    prev_day = pd.Timestamp(trading_day) - pd.tseries.offsets.BusinessDay(1)
    prev_day = prev_day.date()
    logger.info(f"No data for {symbol} on {trading_day}, trying previous business day {prev_day}")
    data = _fetch_for_day(symbol, prev_day, interval)
    if data:
        cache_data(symbol, data)
        processed = sorted(data, key=lambda x: x.get('date', ''))
        cache_data(symbol, processed, processed=True)
    return data

def get_latest_price(symbol):
    data = fetch_intraday_data(symbol)
    if not data:
        return None
    latest = data[-1]
    return latest.get('close') or latest.get('c') or ((latest.get('bid') + latest.get('ask')) / 2)

def cache_data(symbol, data, processed=False):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = DATA_DIR_PROCESSED if processed else DATA_DIR_RAW
        filepath = directory / f"{symbol}_{ts}.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Cached {'processed' if processed else 'raw'} data for {symbol} at {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Cache failed for {symbol}: {str(e)}")
        return None

def update_all_symbols():
    ensure_directories()
    load_api_count()

    for symbol_key, symbol_code in SYMBOLS.items():
        try:
            raw_data = fetch_intraday_data(symbol_code)
            if not raw_data:
                logger.warning(f"No raw data for {symbol_key}, skipping caching.")
                continue

            cache_data(symbol_key, raw_data)
            processed = sorted(raw_data, key=lambda x: x.get('date', ''))
            cache_data(symbol_key, processed, processed=True)

        except Exception as e:
            logger.error(f"Failed processing {symbol_key}: {str(e)}")

if __name__ == "__main__":
    update_all_symbols()
