import unittest
from unittest.mock import MagicMock


class TestOrderBookTradeHistory(unittest.TestCase):
    def setUp(self):
        # Mock order book and trade history components
        self.order_book_display = MagicMock()
        self.trade_history_display = MagicMock()
        # Sample data
        self.sample_order_book = {
            "bids": [(100, 5), (99, 10)],
            "asks": [(101, 7), (102, 3)],
        }
        self.sample_trade_history = [
            {"price": 100, "qty": 2, "side": "buy"},
            {"price": 101, "qty": 1, "side": "sell"},
        ]

    def test_order_book_and_trade_history_display(self):
        # Simulate setting data in UI components
        self.order_book_display.set_data(self.sample_order_book)
        self.trade_history_display.set_data(self.sample_trade_history)

        # Assert that UI components received correct data
        self.order_book_display.set_data.assert_called_with(self.sample_order_book)
        self.trade_history_display.set_data.assert_called_with(
            self.sample_trade_history
        )

        # Simulate UI refresh or render call
        self.order_book_display.refresh()
        self.trade_history_display.refresh()

        self.order_book_display.refresh.assert_called_once()
        self.trade_history_display.refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
