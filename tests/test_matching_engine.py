import unittest
from app.matching_engine import MatchingEngine
from app.order_book import OrderBook

class TestMatchingEngine(unittest.TestCase):

    def setUp(self):
        # Create order book and matching engine
        self.order_book = OrderBook("ASML.AS")
        self.matching_engine = MatchingEngine(self.order_book)

    def test_match_orders(self):
        # Add orders and test the matching engine
        self.order_book.add_order({"type": "buy", "price": 150, "quantity": 10})
        self.order_book.add_order({"type": "sell", "price": 150, "quantity": 10})
        self.matching_engine.match_orders()
        self.assertEqual(len(self.order_book.bids), 0)
        self.assertEqual(len(self.order_book.asks), 0)

    def test_partial_fill(self):
        # Add orders and test partial fill
        self.order_book.add_order({"type": "buy", "price": 150, "quantity": 10})
        self.order_book.add_order({"type": "sell", "price": 150, "quantity": 5})
        self.matching_engine.match_orders()
        self.assertEqual(len(self.order_book.bids), 1)  # Remaining buy order
        self.assertEqual(len(self.order_book.asks), 0)  # No more sell orders

if __name__ == '__main__':
    unittest.main()
