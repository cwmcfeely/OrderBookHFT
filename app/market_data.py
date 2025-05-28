import json
import logging
import threading
import time
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
import yaml

from app.logger import setup_logging

# Initialise logging with INFO level
setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.propagate = False  # Prevent double logging if root logger also logs

DATA_DIR_RAW = Path("data/raw")

# Load configuration from YAML file
with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

# Extract API key and symbols dictionary from config
API_KEY = os.environ.get("EOD_API_KEY", "")
SYMBOLS = CONFIG.get("symbols", {})
BASE_URL = "https://eodhistoricaldata.com/api"
HEADERS = {"Content-Type": "application/json"}

# Variables to track API usage to respect rate limits
api_calls_today = 0
last_call_date = date.today()
api_counter_lock = threading.Lock()  # Lock to synchronise access to API call counters
API_COUNT_FILE = Path(
    "logs/api_calls_today.json"
)  # File to persist API call count across restarts

CACHE_EXPIRY_SECONDS = 3600  # Cache expiry time in seconds (1 hour)

# Global dictionary to hold latest prices per symbol for quick access
latest_prices = {}
latest_prices_lock = threading.Lock()  # Lock for thread-safe access to latest_prices


def ensure_directories():
    """
    Ensure that the required directories for raw data
    and logs exist, creating them if necessary.
    """
    DATA_DIR_RAW.mkdir(parents=True, exist_ok=True)
    API_COUNT_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_api_count():
    """
    Load the API call count and last call date from a JSON file.
    This helps to persist API usage count across application restarts.
    """
    global api_calls_today, last_call_date
    logger.info("Attempting to load API usage count from file...")

    try:
        if API_COUNT_FILE.exists():
            logger.debug(f"API count file found at: {API_COUNT_FILE}")
            with open(API_COUNT_FILE, "r") as f:
                data = json.load(f)
                api_calls_today = data.get("api_calls_today", 0)
                last_call_date_str = data.get("last_call_date")

                if last_call_date_str:
                    last_call_date = date.fromisoformat(last_call_date_str)
                    logger.info(
                        f"Loaded API count: {api_calls_today}, Last call date: {last_call_date}"
                    )
                else:
                    logger.warning("Missing 'last_call_date' in API count file.")
        else:
            logger.warning(f"API count file does not exist at path: {API_COUNT_FILE}")

    except json.JSONDecodeError as e:
        logger.error(f"JSON decoding error while loading API count file: {e}")
    except FileNotFoundError as e:
        logger.error(f"API count file not found: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading API count: {str(e)}")


def save_api_count():
    """
    Save the current API call count and last call date to a JSON file.
    """
    try:
        with open(API_COUNT_FILE, "w") as f:
            json.dump(
                {
                    "api_calls_today": api_calls_today,
                    "last_call_date": last_call_date.isoformat(),
                },
                f,
                indent=2,
            )
    except Exception as e:
        logger.error(f"Error saving API count: {str(e)}")


def increment_api_count():
    """
    Increment the API call count in a thread-safe manner.
    Reset the count if the day has changed.
    """
    global api_calls_today, last_call_date
    with api_counter_lock:
        today = date.today()
        if today != last_call_date:
            api_calls_today = 0
            last_call_date = today
        api_calls_today += 1
        save_api_count()


def get_last_trading_day(current_date=None):
    """
    Get the last business (trading) day before the given date.
    Uses pandas BusinessDay offset to skip weekends and holidays.

    Args:
        current_date (date, optional): Reference date. Defaults to today.

    Returns:
        date: The last trading day date.
    """
    current_date = current_date or pd.Timestamp.today().date()
    last_business_day = pd.Timestamp(current_date) - pd.tseries.offsets.BusinessDay(1)
    return last_business_day.date()


def load_cached_data(symbol):
    """
    Load cached intraday data for a symbol if available and not expired.
    Args:
        symbol (str): Trading symbol.
    Returns:
        dict or None: Cached JSON data or None if no valid cache.
    """
    cache_dir = DATA_DIR_RAW
    files = sorted(cache_dir.glob(f"{symbol}_*.json"), reverse=True)  # Latest first
    if not files:
        return None
    latest_file = files[0]
    # Check if cache file is expired based on modification time
    if time.time() - latest_file.stat().st_mtime > CACHE_EXPIRY_SECONDS:
        return None
    try:
        with open(latest_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load cache {latest_file}: {e}")
        return None


def _fetch_for_day(symbol, trading_day, interval="5m"):
    """
    Fetch intraday data for a given symbol and trading day from the EOD Historical Data API.

    Args:
        symbol (str): Trading symbol.
        trading_day (date): Date for which to fetch data.
        interval (str): Data interval (e.g., "5m").

    Returns:
        list or None: List of intraday data points or None on failure.
    """
    start_dt = datetime.combine(trading_day, datetime.min.time())
    end_dt = datetime.combine(trading_day, datetime.max.time())

    params = {
        "api_token": API_KEY,
        "interval": interval,
        "fmt": "json",
        "from": int(start_dt.timestamp()),
        "to": int(end_dt.timestamp()),
    }

    try:
        # Enforce daily API call limit
        if api_calls_today >= 100000:
            raise Exception("Daily API limit (100,000) reached")

        logger.info(
            f"Fetching {symbol} ({interval}) for {trading_day.strftime('%Y-%m-%d')}"
        )
        response = requests.get(
            f"{BASE_URL}/intraday/{symbol}", params=params, timeout=10
        )

        if response.status_code != 200:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return None

        increment_api_count()
        data = response.json()

        if not data:
            logger.warning(f"No data for {symbol} on {trading_day}")
            return None

        # Update latest price cache with last tick's close price or midpoint of bid/ask
        with latest_prices_lock:
            latest_tick = data[-1] if isinstance(data, list) and len(data) > 0 else None
            if latest_tick:
                price = (
                    latest_tick.get("close")
                    or latest_tick.get("c")
                    or ((latest_tick.get("bid", 0) + latest_tick.get("ask", 0)) / 2)
                )
                if price:
                    latest_prices[symbol] = price

        return data

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {str(e)}")
        return None


def fetch_intraday_data(symbol, interval="5m"):
    # Try to fetch fresh data from the API for the last trading day
    trading_day = get_last_trading_day()
    data = _fetch_for_day(symbol, trading_day, interval)
    if data:
        cache_data(symbol, data)
        processed = sorted(data, key=lambda x: x.get("date", ""))
        cache_data(symbol, processed, processed=True)
        return data

    # Fallback: try previous business day if no data on last trading day
    prev_day = pd.Timestamp(trading_day) - pd.tseries.offsets.BusinessDay(1)
    prev_day = prev_day.date()
    logger.info(
        f"No data for {symbol} on {trading_day}, trying previous business day {prev_day}"
    )
    data = _fetch_for_day(symbol, prev_day, interval)
    if data:
        cache_data(symbol, data)
        processed = sorted(data, key=lambda x: x.get("date", ""))
        cache_data(symbol, processed, processed=True)
        return data

    # If API fails for both days, use cached data as a last resort
    cached = load_cached_data(symbol)
    if cached:
        logger.warning(f"API unavailable for {symbol}, using cached data.")
        return cached

    logger.error(f"No data available for {symbol} from API or cache.")
    return None


def get_latest_price(symbol: str) -> float | None:
    """
    Always attempt to fetch the latest price from the API first.
    If API fails, use the in-memory cache as a fallback.
    Args:
        symbol (str): Trading symbol.
    Returns:
        float or None: Latest price or None if unavailable.
    """
    # Try to fetch fresh intraday data (API-first)
    data = fetch_intraday_data(symbol)
    if data:
        latest = data[-1]
        price = (
            latest.get("close")
            or latest.get("c")
            or ((latest.get("bid", 0) + latest.get("ask", 0)) / 2)
        )
        if price is not None:
            # Optionally update the in-memory cache
            with latest_prices_lock:
                latest_prices[symbol] = price
            return price

    # Fallback: use in-memory cache if API/data fails
    with latest_prices_lock:
        price = latest_prices.get(symbol)
    return price


def cache_data(symbol, data, processed=False):
    """
    Cache data to disk as JSON file in appropriate directory.
    Args:
        symbol (str): Trading symbol.
        data (list or dict): Data to cache.
    Returns:
        Path or None: Path to cached file or None if failed.
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        directory = DATA_DIR_RAW
        filepath = directory / f"{symbol}_{ts}.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Cached 'raw' data for {symbol} at {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Cache failed for {symbol}: {str(e)}")
        return None


def update_all_symbols():
    """
    Update intraday data for all configured symbols.
    Ensures directories and API count are loaded, then fetches and caches data.
    """
    ensure_directories()
    load_api_count()

    for symbol_key, symbol_code in SYMBOLS.items():
        try:
            raw_data = fetch_intraday_data(symbol_code)
            if not raw_data:
                logger.warning(f"No raw data for {symbol_key}, skipping caching.")
                continue

            cache_data(symbol_key, raw_data)
            processed = sorted(raw_data, key=lambda x: x.get("date", ""))
            cache_data(symbol_key, processed, processed=True)

        except Exception as e:
            logger.error(f"Failed processing {symbol_key}: {str(e)}")


# If this module is run as the main program, update all symbols immediately
if __name__ == "__main__":
    update_all_symbols()
