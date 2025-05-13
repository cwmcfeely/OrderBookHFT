from .base_strategy import BaseStrategy
import random

class MarketMakerStrategy(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "market_maker", params)
        self.spread = self.params.get("spread", 0.002)  # 0.2% default spread
        self.inventory = 0
        self.max_inventory = 100

    def generate_orders(self):
        orders = []
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            return orders

        mid = (best_bid["price"] + best_ask["price"]) / 2
        bid_price = mid * (1 - self.spread / 2)
        ask_price = mid * (1 + self.spread / 2)

        # Random small size, inventory aware
        qty = random.randint(1, 10)
        if self.inventory + qty <= self.max_inventory:
            orders.append({"side": "1", "price": bid_price, "quantity": qty})
            self.place_order("1", bid_price, qty)
            self.inventory += qty

        qty = random.randint(1, 10)
        if self.inventory - qty >= 0:
            orders.append({"side": "2", "price": ask_price, "quantity": qty})
            self.place_order("2", ask_price, qty)
            self.inventory -= qty

        return orders
