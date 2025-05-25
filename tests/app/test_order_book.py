import unittest
import time
from app.order_book import OrderBook


class TestOrderBook(unittest.TestCase):
    def setUp(self):
        # Create a fresh order book for each test
        self.book = OrderBook("TESTSYM")

    def test_add_and_best_bid_ask(self):
        """Test adding orders and retrieving best bid/ask."""
        self.book.add_order("1", 100.0, 10, "bid1", "test")
        self.book.add_order("2", 101.0, 5, "ask1", "test")
        best_bid = self.book.get_best_bid()
        best_ask = self.book.get_best_ask()
        self.assertEqual(best_bid["price"], 100.0)
        self.assertEqual(best_bid["qty"], 10)
        self.assertEqual(best_ask["price"], 101.0)
        self.assertEqual(best_ask["qty"], 5)

    def test_empty_order_book_best_bid_ask(self):
        """Test best bid/ask returns None on empty order book."""
        self.assertIsNone(self.book.get_best_bid())
        self.assertIsNone(self.book.get_best_ask())

    def test_add_order_invalid_side(self):
        """Test that invalid side raises ValueError."""
        with self.assertRaises(ValueError):
            self.book.add_order("X", 100.0, 10, "bad", "test")

    def test_add_order_invalid_price_qty(self):
        """Test that invalid price/quantity raises ValueError."""
        with self.assertRaises(ValueError):
            self.book.add_order("1", "not_a_price", 10, "bad", "test")
        with self.assertRaises(ValueError):
            self.book.add_order("1", 100.0, "not_a_qty", "bad", "test")

    def test_depth_snapshot(self):
        """Test that get_depth_snapshot returns correct levels."""
        self.book.add_order("1", 100.0, 10, "bid1", "test")
        self.book.add_order("1", 99.5, 5, "bid2", "test")
        self.book.add_order("2", 101.0, 8, "ask1", "test")
        snap = self.book.get_depth_snapshot(levels=2)
        self.assertEqual(len(snap["bids"]), 2)
        self.assertEqual(len(snap["asks"]), 1)
        self.assertEqual(snap["bids"][0]["price"], 100.0)
        self.assertEqual(snap["bids"][1]["price"], 99.5)

    def test_record_and_get_recent_prices(self):
        """Test recording and retrieving recent trade prices."""
        for price in range(50, 60):
            self.book.record_trade(price)
        recent = self.book.get_recent_prices(window=5)
        self.assertEqual(recent, [55, 56, 57, 58, 59])
        # Test with window larger than history
        all_prices = self.book.get_recent_prices(window=20)
        self.assertEqual(all_prices, list(range(50, 60)))

    def test_seed_synthetic_depth(self):
        """Test seeding synthetic depth creates expected levels."""
        self.book.seed_synthetic_depth(mid_price=100.0, levels=3, base_qty=100)
        snap = self.book.get_depth_snapshot(levels=3)
        self.assertEqual(len(snap["bids"]), 3)
        self.assertEqual(len(snap["asks"]), 3)
        # Check that seeded orders have correct side and source
        for bid in snap["bids"]:
            self.assertTrue(bid["price"] < 100.0)
        for ask in snap["asks"]:
            self.assertTrue(ask["price"] > 100.0)

    def test_get_mid_price(self):
        """Test mid price calculation."""
        self.book.add_order("1", 99.0, 10, "bid1", "test")
        self.book.add_order("2", 101.0, 10, "ask1", "test")
        mid = self.book.get_mid_price()
        self.assertEqual(mid, 100.0)
        # If one side missing, should return None
        empty_book = OrderBook("EMPTY")
        self.assertIsNone(empty_book.get_mid_price())

    def test_expire_old_orders(self):
        """Test that old orders are expired correctly."""
        now = time.time()
        # Add a fresh and an old order
        self.book.add_order("1", 100.0, 10, "bid1", "test", order_time=now - 120)
        self.book.add_order("2", 101.0, 5, "ask1", "test", order_time=now)
        self.book.expire_old_orders(max_age=60)
        # Old bid should be gone, ask should remain
        self.assertIsNone(self.book.get_best_bid())
        self.assertIsNotNone(self.book.get_best_ask())

    def test_remove_order(self):
        """Test removing an order by order ID."""
        self.book.add_order("1", 100.0, 10, "bid1", "test")
        removed = self.book.remove_order("bid1")
        self.assertIsNotNone(removed)
        self.assertEqual(removed["id"], "bid1")
        # Removing again should return None
        self.assertIsNone(self.book.remove_order("bid1"))

    def test_get_order_source(self):
        """Test retrieving the source of an order."""
        self.book.add_order("1", 100.0, 10, "bid1", "strategyA")
        self.assertEqual(self.book.get_order_source("bid1"), "strategyA")
        self.assertIsNone(self.book.get_order_source("nonexistent"))

    def test_get_orders_by_source(self):
        """Test retrieving all orders for a given side and source."""
        self.book.add_order("1", 100.0, 10, "bid1", "A")
        self.book.add_order("1", 99.5, 5, "bid2", "B")
        self.book.add_order("2", 101.0, 8, "ask1", "A")
        bids_A = self.book.get_orders_by_source("buy", "A")
        asks_A = self.book.get_orders_by_source("sell", "A")
        self.assertEqual(len(bids_A), 1)
        self.assertEqual(bids_A[0]["id"], "bid1")
        self.assertEqual(len(asks_A), 1)
        self.assertEqual(asks_A[0]["id"], "ask1")


if __name__ == "__main__":
    unittest.main()
