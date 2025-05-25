import unittest
from unittest.mock import MagicMock
import time
from app.matching_engine import MatchingEngine, TradingHalted


# Minimal stub for OrderBook for testing
class DummyOrderBook:
    def __init__(self, symbol="TESTSYM"):
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.last_price = None

    def add_order(self, side, price, quantity, order_id, source):
        # Add an order to the bids or asks book
        book = self.bids if side == "buy" else self.asks
        if price not in book:
            from collections import deque

            book[price] = deque()
        book[price].append(
            {
                "id": order_id,
                "qty": quantity,
                "source": source,
                "order_time": 0,  # For latency test
            }
        )


# Minimal stub for Strategy for testing
class DummyStrategy:
    def __init__(self, name):
        self.source_name = name
        self.inventory = 0
        self.avg_entry_price = 0.0
        self.realised_pnl = 0.0
        self.fix_engine = MagicMock()
        self.logger = MagicMock()

    def on_trade(self, trade):
        self.last_trade = trade

    def on_execution_report(self, trade):
        self.last_exec_report = trade


class TestMatchingEngine(unittest.TestCase):
    def setUp(self):
        # Set up a dummy order book and two dummy strategies
        self.order_book = DummyOrderBook()
        self.strategies = {
            "maker": DummyStrategy("maker"),
            "taker": DummyStrategy("taker"),
        }
        self.engine = MatchingEngine(self.order_book, self.strategies)

    def test_circuit_breaker_blocks_when_limit_hit(self):
        """Test that TradingHalted is raised when circuit breaker triggers."""
        self.engine.circuit_breaker.daily_loss = -10001  # Exceed max_daily_loss
        from collections import deque

        self.order_book.asks[101.0] = deque()
        with self.assertRaises(TradingHalted):
            self.engine.match_order("buy", 101.0, 1, "oid", "taker")

    def test_simple_match_and_pnl(self):
        """Test a simple match and correct PnL calculation."""
        # Maker posts an ask at 101.0
        from collections import deque

        self.order_book.asks[101.0] = deque(
            [{"id": "maker_order", "qty": 5, "source": "maker", "order_time": 0}]
        )
        # Taker submits a buy at 101.0
        trades = self.engine.match_order("buy", 101.0, 3, "taker_order", "taker")
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["qty"], 3)
        self.assertEqual(trade["price"], 101.0)
        # Maker inventory should decrease (since they sold)
        self.assertEqual(self.strategies["maker"].inventory, -3)
        # Taker inventory should increase (since they bought)
        self.assertEqual(self.strategies["taker"].inventory, 3)
        # Realised PnL should be updated
        self.assertTrue(hasattr(self.strategies["maker"], "realised_pnl"))

    def test_self_trade_prevention(self):
        """Test that self-trading is prevented."""
        from collections import deque

        self.order_book.asks[101.0] = deque(
            [{"id": "maker_order", "qty": 5, "source": "maker", "order_time": 0}]
        )
        # Maker tries to take their own order
        trades = self.engine.match_order("buy", 101.0, 2, "maker_order2", "maker")
        # Should result in no trade (self-trade prevention)
        self.assertEqual(trades, [])

    def test_partial_and_full_fill(self):
        """Test partial and full fills are handled correctly."""
        from collections import deque

        self.order_book.asks[101.0] = deque(
            [
                {"id": "ask1", "qty": 2, "source": "maker", "order_time": 0},
                {"id": "ask2", "qty": 3, "source": "maker", "order_time": 0},
            ]
        )
        # Taker submits a buy for 4 units at 101.0
        trades = self.engine.match_order("buy", 101.0, 4, "taker_order", "taker")
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["qty"], 2)
        self.assertEqual(trades[1]["qty"], 2)
        # The remaining ask2 should have qty 1 left
        self.assertEqual(self.order_book.asks[101.0][0]["qty"], 1)

    def test_no_match_when_price_is_too_low(self):
        """Test that no match occurs if the price is not aggressive enough."""
        from collections import deque

        self.order_book.asks[102.0] = deque(
            [{"id": "maker_order", "qty": 5, "source": "maker", "order_time": 0}]
        )
        # Taker submits a buy at 101.0 (not high enough)
        trades = self.engine.match_order("buy", 101.0, 5, "taker_order", "taker")
        self.assertEqual(trades, [])

    def test_latency_tracking(self):
        """Test that latency is tracked in trade dict."""
        from collections import deque

        self.order_book.asks[101.0] = deque(
            [
                {
                    "id": "maker_order",
                    "qty": 1,
                    "source": "maker",
                    "order_time": time.time() - 0.01,  # 10ms ago
                }
            ]
        )
        trades = self.engine.match_order("buy", 101.0, 1, "taker_order", "taker")
        self.assertIn("latency_ms", trades[0])
        self.assertIsInstance(trades[0]["latency_ms"], float)

    def test_trade_history_and_last_price(self):
        """Test that last_price is updated after trade."""
        from collections import deque

        self.order_book.asks[101.0] = deque(
            [{"id": "maker_order", "qty": 1, "source": "maker", "order_time": 0}]
        )
        self.engine.match_order("buy", 101.0, 1, "taker_order", "taker")
        self.assertEqual(self.order_book.last_price, 101.0)


if __name__ == "__main__":
    unittest.main()
