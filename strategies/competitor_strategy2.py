from .base_strategy import BaseStrategy
import random
import numpy as np

class MomentumStrategy(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "momentum", params)
        self.inventory = 0
        self.max_inventory = 100
        self.lookback = self.params.get("lookback", 5)

    def generate_orders(self):
        orders = []
        prices = self.order_book.get_recent_prices(window=self.lookback)
        if len(prices) < self.lookback:
            return orders

        trend = np.polyfit(range(len(prices)), prices, 1)[0]  # Slope of price trend

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            return orders

        qty = random.randint(1, 10)
        # Buy if trend is up, sell if trend is down
        if trend > 0 and self.inventory + qty <= self.max_inventory:
            orders.append({"side": "1", "price": best_ask["price"], "quantity": qty})
            self.place_order("1", best_ask["price"], qty)
            self.inventory += qty
        elif trend < 0 and self.inventory - qty >= 0:
            orders.append({"side": "2", "price": best_bid["price"], "quantity": qty})
            self.place_order("2", best_bid["price"], qty)
            self.inventory -= qty

        return orders
