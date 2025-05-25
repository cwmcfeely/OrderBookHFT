import unittest
from unittest.mock import MagicMock, patch
from strategies.base_strategy import BaseStrategy
from strategies.competitor_strategy import PassiveLiquidityProvider


class DummyOrderBook:
    def __init__(self):
        self.bids = {100: [{"qty": 500}], 99: [{"qty": 300}]}
        self.asks = {101: [{"qty": 400}], 102: [{"qty": 200}]}
        self.last_price = 100.5

    def get_best_bid(self):
        return {"price": 100}

    def get_best_ask(self):
        return {"price": 101}

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


class TestPassiveLiquidityProvider(unittest.TestCase):
    def setUp(self):
        self.fix_engine = DummyFixEngine()
        self.order_book = DummyOrderBook()
        self.symbol = "TEST"
        self.params = {"min_order_interval": 0.1}
        self.strategy = PassiveLiquidityProvider(
            self.fix_engine, self.order_book, self.symbol, self.params
        )

    def test_initialization(self):
        self.assertEqual(self.strategy.max_inventory, 100)
        self.assertFalse(self.strategy.rebalance_pending)

    def test_risk_check_buy_inventory_limit(self):
        self.strategy.inventory = 95
        self.assertFalse(self.strategy._risk_check("1", 100, 10))

    def test_risk_check_sell_inventory_limit(self):
        self.strategy.inventory = -95
        self.assertFalse(self.strategy._risk_check("2", 100, 10))

    def test_risk_check_quantity_limit(self):
        self.assertFalse(self.strategy._risk_check("1", 100, 501))

    @patch("time.time", return_value=1000)
    @patch.object(PassiveLiquidityProvider, "place_order", return_value=True)
    @patch.object(PassiveLiquidityProvider, "get_adaptive_order_size", return_value=10)
    def test_generate_orders_normal(
        self, mock_adaptive_size, mock_place_order, mock_time
    ):
        self.strategy.inventory = 0
        self.strategy.last_order_time = 900
        orders = self.strategy.generate_orders()
        self.assertTrue(len(orders) > 0)
        for order in orders:
            self.assertIn(order["side"], ["1", "2"])
            self.assertTrue(1 <= order["quantity"] <= 10)

    @patch("time.time", return_value=1000)
    def test_generate_orders_cooldown(self, mock_time):
        self.strategy.last_order_time = 999.95
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])

    @patch("time.time", return_value=1000)
    def test_generate_orders_no_best_bid_ask(self, mock_time):
        self.strategy.order_book.get_best_bid = MagicMock(return_value=None)
        self.strategy.order_book.get_best_ask = MagicMock(return_value=None)
        orders = self.strategy.generate_orders()
        self.assertEqual(orders, [])

    @patch("time.time", return_value=1000)
    @patch.object(PassiveLiquidityProvider, "place_order", return_value=True)
    def test_generate_orders_rebalance_pending(self, mock_place_order, mock_time):
        self.strategy.rebalance_pending = True
        self.strategy.inventory = 10
        self.strategy.order_book.get_best_ask = MagicMock(return_value={"price": 101})
        orders = self.strategy.generate_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["side"], "2")

    def test_on_trade_calls_super_and_logs(self):
        self.strategy.logger = MagicMock()
        trade = {"side": "1", "qty": 5, "price": 100}
        with patch.object(BaseStrategy, "on_trade"):
            self.strategy.on_trade(trade)
            self.strategy.logger.info.assert_called()


if __name__ == "__main__":
    unittest.main()
