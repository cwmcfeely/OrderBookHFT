import unittest
from unittest.mock import patch, MagicMock, mock_open
import threading
import json
import os
import stat
from pathlib import Path
import app.market_data


class TestMarketData(unittest.TestCase):
    def setUp(self):
        # Patch logger to avoid cluttering test output
        patcher = patch("app.market_data.logger")
        self.mock_logger = patcher.start()
        self.addCleanup(patcher.stop)

        # Patch threading.Lock for latest_prices_lock and api_counter_lock
        self.lock_patch = patch(
            "app.market_data.threading.Lock",
            return_value=MagicMock(spec=threading.Lock),
        )
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)

        # Patch DATA_DIR_RAW and API_COUNT_FILE to use a temp directory
        self.temp_dir = "temp_test_data"
        os.makedirs(self.temp_dir, exist_ok=True)
        patcher_data_dir = patch(
            "app.market_data.DATA_DIR_RAW",
            new_callable=lambda: Path(os.path.abspath(self.temp_dir)),
        )
        patcher_api_count = patch(
            "app.market_data.API_COUNT_FILE",
            new_callable=lambda: Path(
                os.path.join(self.temp_dir, "api_calls_today.json")
            ),
        )
        patcher_data_dir.start()
        patcher_api_count.start()
        self.addCleanup(patcher_data_dir.stop)
        self.addCleanup(patcher_api_count.stop)

    def tearDown(self):
        # Clean up temp directory
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    @patch("app.market_data.open", new_callable=mock_open, create=True)
    def test_save_and_load_api_count(self, mock_file):
        app.market_data.api_calls_today = 42
        app.market_data.last_call_date = app.market_data.date.today()
        app.market_data.save_api_count()
        # Patch exists() to return True
        with patch("pathlib.Path.exists", return_value=True):
            mock_file().read.return_value = json.dumps(
                {
                    "api_calls_today": 42,
                    "last_call_date": app.market_data.last_call_date.isoformat(),
                }
            )
            app.market_data.api_calls_today = 0
            app.market_data.load_api_count()
            self.assertEqual(app.market_data.api_calls_today, 42)

    def test_increment_api_count_resets_on_new_day(self):
        """Test API call counter resets when the day changes."""
        app.market_data.api_calls_today = 10
        yesterday = app.market_data.date.today().replace(
            day=max(1, app.market_data.date.today().day - 1)
        )
        app.market_data.last_call_date = yesterday
        with patch("app.market_data.save_api_count"):
            app.market_data.increment_api_count()
        self.assertEqual(app.market_data.api_calls_today, 1)

    def test_get_last_trading_day(self):
        """Test calculation of last trading (business) day."""
        friday = app.market_data.date(2024, 5, 24)  # Suppose it's Friday
        last_day = app.market_data.get_last_trading_day(friday)
        self.assertLess(last_day, friday)
        self.assertEqual(last_day.weekday(), 3)  # Thursday

    @patch("app.market_data.open", new_callable=mock_open, create=True)
    @patch("app.market_data.time")
    def test_load_cached_data_expiry(self, mock_time, mock_file):
        """Test that expired cache is not loaded."""
        symbol = "TEST"
        cache_file = os.path.join(self.temp_dir, f"{symbol}_20240101_000000.json")
        with open(cache_file, "w") as f:
            json.dump({"dummy": "data"}, f)
        # Patch Path.stat to return a dummy stat object with st_mtime and st_mode

        class DummyStat:
            st_mtime = 0
            st_mode = stat.S_IFREG  # Regular file

        with patch.object(Path, "stat", return_value=DummyStat()):
            mock_time.time.return_value = 2000000000
            result = app.market_data.load_cached_data(symbol)
            self.assertIsNone(result)

    @patch("app.market_data.requests.get")
    def test__fetch_for_day_success(self, mock_get):
        """Test successful fetch from API updates latest_prices."""
        symbol = "TEST"
        trading_day = app.market_data.date(2024, 5, 24)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"date": "2024-05-24T15:00:00", "close": 123.45}
        ]
        app.market_data.api_calls_today = 0
        result = app.market_data._fetch_for_day(symbol, trading_day)
        self.assertIsInstance(result, list)
        self.assertIn(symbol, app.market_data.latest_prices)
        self.assertEqual(app.market_data.latest_prices[symbol], 123.45)

    @patch("app.market_data.requests.get")
    def test__fetch_for_day_api_limit(self, mock_get):
        """Test API call is blocked when daily limit is reached."""
        symbol = "TEST"
        trading_day = app.market_data.date(2024, 5, 24)
        app.market_data.api_calls_today = 100000
        result = app.market_data._fetch_for_day(symbol, trading_day)
        self.assertIsNone(result)

    @patch("app.market_data._fetch_for_day")
    @patch("app.market_data.cache_data")
    def test_fetch_intraday_data_api_and_cache(self, mock_cache, mock_fetch):
        """Test fetch_intraday_data uses API, falls back to cache."""
        symbol = "TEST"
        mock_fetch.side_effect = [
            [{"date": "2024-05-24T15:00:00", "close": 123.45}],
            None,
        ]
        mock_cache.return_value = True
        result = app.market_data.fetch_intraday_data(symbol)
        self.assertIsInstance(result, list)
        with patch(
            "app.market_data.load_cached_data",
            return_value=[{"date": "2024-05-23T15:00:00", "close": 120.00}],
        ):
            mock_fetch.side_effect = [None, None]
            result = app.market_data.fetch_intraday_data(symbol)
            self.assertEqual(result[0]["close"], 120.00)

    @patch("app.market_data.fetch_intraday_data")
    def test_get_latest_price(self, mock_fetch):
        """Test get_latest_price returns correct price from API or cache."""
        symbol = "TEST"
        mock_fetch.return_value = [{"close": 42.0}]
        price = app.market_data.get_latest_price(symbol)
        self.assertEqual(price, 42.0)
        mock_fetch.return_value = None
        with patch.dict(app.market_data.latest_prices, {symbol: 99.0}):
            price = app.market_data.get_latest_price(symbol)
            self.assertEqual(price, 99.0)

    @patch("app.market_data.open", new_callable=mock_open, create=True)
    def test_cache_data_success(self, mock_file):
        """Test cache_data writes data to disk and returns path."""
        symbol = "TEST"
        data = [{"date": "2024-05-24T15:00:00", "close": 123.45}]
        path = app.market_data.cache_data(symbol, data)
        self.assertIsNotNone(path)

    @patch("app.market_data.fetch_intraday_data")
    @patch("app.market_data.cache_data")
    def test_update_all_symbols(self, mock_cache, mock_fetch):
        """Test update_all_symbols processes all symbols and caches data."""
        app.market_data.SYMBOLS = {"A": "AAPL", "B": "GOOG"}
        mock_fetch.return_value = [{"date": "2024-05-24T15:00:00", "close": 123.45}]
        mock_cache.return_value = True
        app.market_data.update_all_symbols()
        self.assertTrue(mock_fetch.called)
        self.assertTrue(mock_cache.called)


if __name__ == "__main__":
    unittest.main()
