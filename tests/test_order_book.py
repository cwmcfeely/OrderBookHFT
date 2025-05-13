import unittest
from app.order_book import OrderBook

class TestOrderBook(unittest.TestCase):

    def setUp(self):
        # Initialize an OrderBook instance
        self.order_book = OrderBook("ASML.AS")

    def test_add_order(self):
        # Add a simple order and check if it's in the book
        order = {"type": "buy", "price": 150, "quantity": 10}
        self.order_book.add_order(order)
        self.assertEqual(len(self.order_book.bids), 1)

    def test_get_best_bid(self):
        # Add bid and ask, and check the best bid
        self.order_book.add_order({"type": "buy", "price": 150, "quantity": 10})
        self.order_book.add_order({"type": "buy", "price": 155, "quantity": 5})
        best_bid = self.order_book.get_best_bid("ASML.AS")
        self.assertEqual(best_bid["price"], 155)

    def test_get_best_ask(self):
        # Add ask orders and check the best ask
        self.order_book.add_order({"type": "sell", "price": 160, "quantity": 10})
        self.order_book.add_order({"type": "sell", "price": 158, "quantity": 5})
        best_ask = self.order_book.get_best_ask("ASML.AS")
        self.assertEqual(best_ask["price"], 158)

    def test_order_matching(self):
        # Add orders and perform matching
        self.order_book.add_order({"type": "buy", "price": 150, "quantity": 10})
        self.order_book.add_order({"type": "sell", "price": 150, "quantity": 10})
        self.order_book.match_orders("ASML.AS")
        self.assertEqual(len(self.order_book.bids), 0)
        self.assertEqual(len(self.order_book.asks), 0)

if __name__ == '__main__':
    unittest.main()
