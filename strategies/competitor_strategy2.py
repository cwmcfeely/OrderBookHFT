import time
from .base_strategy import BaseStrategy
import random
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MomentumStrategy(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "momentum", params)
        self.inventory = 0
        self.max_inventory = 100
        self.lookback = self.params.get("lookback", 5)

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

        prices = self.order_book.get_recent_prices(window=self.lookback)
        if len(prices) < self.lookback:
            return orders

        trend = np.polyfit(range(len(prices)), prices, 1)[0]  # Slope of price trend

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            return orders

        # Inventory rebalance logic
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        # Buy if trend is up, sell if trend is down
        if trend > 0 and self.inventory + qty <= self.max_inventory:
            orders.append({"side": "1", "price": best_ask["price"], "quantity": qty})
            self.place_order("1", best_ask["price"], qty)
            self.inventory += qty
        elif trend < 0 and self.inventory - qty >= -self.max_inventory:
            orders.append({"side": "2", "price": best_bid["price"], "quantity": qty})
            self.place_order("2", best_bid["price"], qty)
            self.inventory -= qty

        self.last_order_time = now
        return orders
