import time
from .base_strategy import BaseStrategy
import random
import logging

logger = logging.getLogger(__name__)

class MarketMakerStrategy(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "market_maker", params)
        self.spread = self.params.get("spread", 0.002)  # 0.2% default spread
        self.inventory = 0
        self.max_inventory = 100

    def generate_orders(self):
        # Call the base class logic first
        base_result = super().generate_orders()
        if base_result == []:
            return []  # In cooldown, skip order generation

        orders = []

        # Cooldown check
        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            return orders  # Skip order generation if still in cooldown

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            return orders

        # Inventory rebalance logic
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        mid = (best_bid["price"] + best_ask["price"]) / 2
        bid_price = mid * (1 - self.spread / 2)
        ask_price = mid * (1 + self.spread / 2)

        # Adaptive order size based on volatility
        buy_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory + buy_qty <= self.max_inventory:
            orders.append({"side": "1", "price": bid_price, "quantity": buy_qty})
            self.place_order("1", bid_price, buy_qty)
            self.inventory += buy_qty

        sell_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory - sell_qty >= -self.max_inventory:
            orders.append({"side": "2", "price": ask_price, "quantity": sell_qty})
            self.place_order("2", ask_price, sell_qty)
            self.inventory -= sell_qty

        self.last_order_time = now
        return orders
