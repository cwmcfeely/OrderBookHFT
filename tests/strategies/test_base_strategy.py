import time
import unittest
from unittest.mock import MagicMock, patch

# Assume BaseStrategy is imported from the file
from strategies.base_strategy import BaseStrategy


class DummyOrderBook:
    def __init__(self):
        self.bids = {100: [{"qty": 500}], 99: [{"qty": 300}]}
        self.asks = {101: [{"qty": 400}], 102: [{"qty": 200}]}
        self.last_price = 100.5
        self._recent_prices = [100, 101, 100.5, 99.5, 100.2]

    def get_best_bid(self):
        return {"price": 100}

    def get_best_ask(self):
        return {"price": 101}

    def get_mid_price(self):
        return 100.5

    def add_order(self, **kwargs):
        pass

    def get_recent_prices(self, window=30):
        return self._recent_prices[-window:]


class DummyFixEngine:
    def create_new_order(self, **kwargs):
        return {"fake": "msg"}

    def parse(self, **kwargs):
        # Simulate parsed FIX message
        return {
            54: kwargs.get("side", "1"),
            44: kwargs.get("price", 100),
            38: kwargs.get("qty", 1),
            11: "OID",
        }


class TestBaseStrategy(unittest.TestCase):
    def setUp(self):
        self.fix_engine = DummyFixEngine()
        self.order_book = DummyOrderBook()
        self.symbol = "TEST"
        self.source_name = "TestSource"
        self.params = {
            "max_order_qty": 100,
            "max_price_deviation": 0.05,
            "max_daily_orders": 5,
            "max_position_duration": 60,
            "min_order_interval": 0.1,
            "drawdown_limit": 50,
            "cooldown_period": 1,
            "daily_loss_limit": -1000,
            "trailing_stop": 0.01,
        }
        self.strategy = BaseStrategy(
            self.fix_engine, self.order_book, self.symbol, self.source_name, self.params
        )

    def test_initialization_defaults(self):
        self.assertEqual(self.strategy.max_order_qty, 100)
        self.assertEqual(self.strategy.max_price_deviation, 0.05)
        self.assertEqual(self.strategy.max_daily_orders, 5)
        self.assertEqual(self.strategy.inventory, 0)
        self.assertEqual(self.strategy.avg_entry_price, 0.0)

    def test_risk_check_quantity_limit(self):
        # Exceed max_order_qty
        self.assertFalse(self.strategy._risk_check("1", 101, 200))

    def test_risk_check_price_deviation(self):
        # Price too far from best ask
        self.assertFalse(self.strategy._risk_check("1", 120, 10))

    def test_risk_check_daily_order_limit(self):
        self.strategy.order_count = 5
        self.assertFalse(self.strategy._risk_check("1", 101, 10))

    def test_risk_check_position_duration(self):
        self.strategy.position_start_time = time.time() - 120
        self.assertFalse(self.strategy._risk_check("1", 101, 10))

    def test_risk_check_daily_loss_limit(self):
        self.strategy.realised_pnl = -2000
        self.assertFalse(self.strategy._risk_check("1", 101, 10))

    def test_risk_check_liquidity(self):
        # Order larger than 20% of top 5 liquidity
        self.assertFalse(self.strategy._risk_check("1", 101, 1000))

    def test_risk_check_volatility(self):
        with patch.object(self.strategy, "_current_volatility", return_value=0.2):
            self.assertFalse(self.strategy._risk_check("1", 101, 10))

    @patch("time.time", return_value=1000)
    def test_place_order_success(self, mock_time):
        # Patch fix_engine and order_book to simulate order placement
        self.strategy.last_order_time = 998
        self.strategy._risk_check = MagicMock(return_value=True)
        self.strategy.fix_engine.create_new_order = MagicMock(return_value={})
        self.strategy.fix_engine.parse = MagicMock(
            return_value={54: "1", 44: 101, 38: 10, 11: "OID"}
        )
        self.strategy.order_book.add_order = MagicMock()
        self.assertTrue(self.strategy.place_order("1", 101, 10))
        self.assertEqual(self.strategy.order_count, 1)

    @patch("time.time", return_value=1000)
    def test_place_order_cooldown(self, mock_time):
        self.strategy.last_order_time = 999.95
        self.assertFalse(self.strategy.place_order("1", 101, 10))

    def test_on_trade_long_open_and_close(self):
        trade = {"qty": 10, "side": "1", "price": 100, "pnl": 120}
        self.strategy.on_trade(trade)
        self.assertEqual(self.strategy.inventory, 10)
        self.assertEqual(self.strategy.avg_entry_price, 100)
        # Now close
        trade2 = {"qty": 10, "side": "2", "price": 110, "pnl": 100}
        self.strategy.on_trade(trade2)
        self.assertEqual(self.strategy.inventory, 0)
        self.assertEqual(self.strategy.avg_entry_price, 0.0)

    def test_on_trade_short_open_and_close(self):
        trade = {"qty": 5, "side": "2", "price": 105, "pnl": 0}
        self.strategy.on_trade(trade)
        self.assertEqual(self.strategy.inventory, -5)
        self.assertEqual(self.strategy.avg_entry_price, 105)
        trade2 = {"qty": 5, "side": "1", "price": 100, "pnl": 25}
        self.strategy.on_trade(trade2)
        self.assertEqual(self.strategy.inventory, 0)
        self.assertEqual(self.strategy.avg_entry_price, 0.0)

    def test_trailing_stop_logic(self):
        # Open long, simulate price drop for trailing stop
        self.strategy.inventory = 10
        self.strategy.avg_entry_price = 100
        self.strategy.highest_price = 110
        trade = {"qty": 0, "side": "1", "price": 109, "pnl": 0}
        self.strategy.on_trade(trade)
        # Should not reset
        self.assertEqual(self.strategy.inventory, 10)
        trade = {"qty": 0, "side": "1", "price": 109, "pnl": 0}
        self.strategy.on_trade(trade)
        # Drop below trailing stop
        trade = {"qty": 0, "side": "1", "price": 109, "pnl": 0}
        self.strategy.highest_price = 110
        self.strategy.on_trade({"qty": 0, "side": "1", "price": 109, "pnl": 0})
        # Now drop below trailing stop
        trade = {"qty": 0, "side": "1", "price": 107, "pnl": 0}
        self.strategy.on_trade(trade)
        # Inventory should reset
        self.assertEqual(self.strategy.inventory, 0)

    def test_total_pnl_and_unrealised(self):
        self.strategy.inventory = 10
        self.strategy.avg_entry_price = 100
        self.order_book.last_price = 110
        self.strategy.realised_pnl = 50
        self.assertAlmostEqual(self.strategy.total_pnl(), 150)

    def test_win_rate(self):
        self.strategy.total_trades = 10
        self.strategy.winning_trades = 7
        self.assertAlmostEqual(self.strategy.get_win_rate(), 0.7)

    def test_reset_inventory(self):
        self.strategy.inventory = 5
        self.strategy.avg_entry_price = 100
        self.strategy.position_start_time = 1234
        self.strategy.reset_inventory()
        self.assertEqual(self.strategy.inventory, 0)
        self.assertEqual(self.strategy.avg_entry_price, 0.0)
        self.assertIsNone(self.strategy.position_start_time)

    def test_adaptive_order_size(self):
        with patch.object(self.strategy, "_current_volatility", return_value=0.05):
            size = self.strategy.get_adaptive_order_size(min_size=1, max_size=10)
            self.assertTrue(1 <= size <= 10)

    def test_update_unrealised_pnl_and_drawdown(self):
        self.strategy.inventory = 10
        self.strategy.avg_entry_price = 100
        self.strategy.max_unrealised_pnl = 100
        self.strategy.drawdown_limit = 10
        self.strategy.cooldown_period = 1
        self.strategy.cooldown_until = 0
        self.strategy.update_unrealised_pnl_and_drawdown()
        self.assertTrue(self.strategy.cooldown_until > 0)


if __name__ == "__main__":
    unittest.main()
