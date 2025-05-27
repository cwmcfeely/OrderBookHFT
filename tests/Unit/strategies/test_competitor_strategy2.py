import unittest
from unittest.mock import MagicMock, patch

from strategies.base_strategy import BaseStrategy
from strategies.competitor_strategy2 import MomentumStrategy


class DummyOrderBook:
    def __init__(self):
        self.bids = {
            100: [{"qty": 500, "order_id": "bid1"}],
            99: [{"qty": 300, "order_id": "bid2"}],
        }
        self.asks = {
            101: [{"qty": 400, "order_id": "ask1"}],
            102: [{"qty": 200, "order_id": "ask2"}],
        }
        self.last_price = 100.5

    def get_best_bid(self):
        return {"price": 100, "order_id": "bid1"}

    def get_best_ask(self):
        return {"price": 101, "order_id": "ask1"}

    def get_recent_prices(self, window=0):
        # Return a list of prices for testing trend calculation
        return [100 + i for i in range(window)]

    def get_mid_price(self):
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid["price"] + best_ask["price"]) / 2


class DummyFixEngine:
    def create_new_order(self, **kwargs):
        return {"fake": "msg"}

    def parse(self, **kwargs):
        return {
            54: kwargs.get("side", "1"),
            44: kwargs.get("price", 100),
            38: kwargs.get("qty", 1),
            11: "OID",
        }


class TestMomentumStrategy(unittest.TestCase):
    def setUp(self):
        self.fix_engine = DummyFixEngine()
        self.order_book = DummyOrderBook()
        self.symbol = "TEST"
        self.params = {
            "min_order_interval": 0.1,
            "max_inventory": 100,
            "lookback": 5,
            "base_spread": 0.002,
            "momentum_skew": 0.001,
            "size_skew": 2,
        }
        self.strategy = MomentumStrategy(
            self.fix_engine, self.order_book, self.symbol, self.params
        )

    def test_initialization(self):
        self.assertEqual(self.strategy.max_inventory, 100)
        self.assertEqual(self.strategy.lookback, 5)
        self.assertEqual(self.strategy.base_spread, 0.002)
        self.assertEqual(self.strategy.momentum_skew, 0.001)
        self.assertEqual(self.strategy.size_skew, 2)
        self.assertFalse(self.strategy.rebalance_pending)

    def test_calculate_trend(self):
        prices_up = [1, 2, 3, 4, 5]
        prices_down = [5, 4, 3, 2, 1]
        prices_flat = [3, 3, 3, 3, 3]
        self.assertGreater(self.strategy._calculate_trend(prices_up), 0)
        self.assertLess(self.strategy._calculate_trend(prices_down), 0)
        self.assertAlmostEqual(self.strategy._calculate_trend(prices_flat), 0, places=5)

    def test_risk_check_buy_inventory_limit(self):
        self.strategy.inventory = 95
        self.assertFalse(self.strategy._risk_check("1", 100, 10))

    def test_risk_check_sell_inventory_limit(self):
        self.strategy.inventory = -95
        self.assertFalse(self.strategy._risk_check("2", 100, 10))

    def test_risk_check_quantity_limit(self):
        self.assertFalse(self.strategy._risk_check("1", 100, 501))

    @patch("time.time", return_value=1000)
    @patch.object(MomentumStrategy, "place_order", return_value=True)
    @patch.object(MomentumStrategy, "get_adaptive_order_size", return_value=5)
    def test_generate_orders_normal(
        self, mock_adaptive_size, mock_place_order, mock_time
    ):
        self.strategy.inventory = 0
        self.strategy.last_order_time = 900
        with patch("random.randint", return_value=3):
            orders = self.strategy.generate_orders()
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0]["side"], "1")
        self.assertEqual(orders[1]["side"], "2")
        self.assertTrue(1 <= orders[0]["quantity"] <= 10)
        self.assertTrue(1 <= orders[1]["quantity"] <= 10)

    @patch("time.time", return_value=1000)
    def test_generate_orders_cooldown(self, mock_time):
        self.strategy.last_order_time = 999.95
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])

    @patch("time.time", return_value=1000)
    def test_generate_orders_not_enough_price_history(self, mock_time):
        self.strategy.lookback = 10
        self.strategy.order_book.get_recent_prices = MagicMock(return_value=[100, 101])
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])

    @patch("time.time", return_value=1000)
    def test_generate_orders_no_best_bid_ask(self, mock_time):
        self.strategy.order_book.get_best_bid = MagicMock(return_value=None)
        self.strategy.order_book.get_best_ask = MagicMock(return_value=None)
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])

    @patch("time.time", return_value=1000)
    @patch.object(MomentumStrategy, "place_order", return_value=True)
    def test_generate_orders_rebalance_pending_long(self, mock_place_order, mock_time):
        self.strategy.rebalance_pending = True
        self.strategy.inventory = 10
        self.strategy.order_book.get_best_ask = MagicMock(
            return_value={"price": 101, "order_id": "ask1"}
        )
        orders = self.strategy.generate_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "2")
        self.assertEqual(orders[0]["price"], 101)
        self.assertEqual(orders[0]["quantity"], 10)
        self.assertEqual(orders[0]["order_id"], "ask1")

    @patch("time.time", return_value=1000)
    @patch.object(MomentumStrategy, "place_order", return_value=True)
    def test_generate_orders_rebalance_pending_short(self, mock_place_order, mock_time):
        self.strategy.rebalance_pending = True
        self.strategy.inventory = -10
        self.strategy.order_book.get_best_bid = MagicMock(
            return_value={"price": 100, "order_id": "bid1"}
        )
        orders = self.strategy.generate_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "1")
        self.assertEqual(orders[0]["price"], 100)
        self.assertEqual(orders[0]["quantity"], 10)
        self.assertEqual(orders[0]["order_id"], "bid1")

    @patch("time.time", return_value=1000)
    def test_generate_orders_inventory_limit_sets_rebalance(self, mock_time):
        self.strategy.inventory = 100
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])
        self.assertTrue(self.strategy.rebalance_pending)

    def test_on_trade_calls_super_and_logs(self):
        self.strategy.logger = MagicMock()
        trade = {"side": "1", "qty": 5, "price": 100}
        with patch.object(BaseStrategy, "on_trade"):
            self.strategy.on_trade(trade)
            self.strategy.logger.info.assert_called()


if __name__ == "__main__":
    unittest.main()
