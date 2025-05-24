import time
import random
import numpy as np
import logging
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class MomentumStrategy(BaseStrategy):
    """
    A market making strategy that uses momentum signals to skew its quotes.
    It always provides liquidity (does not cross the spread), but will:
    - Tighten its quote on the side favored by momentum
    - Widen its quote (or reduce size) on the opposite side
    - Manage inventory to avoid excessive exposure
    """

    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "momentum", params)
        self.inventory = 0
        self.max_inventory = self.params.get("max_inventory", 100)
        self.lookback = self.params.get("lookback", 0)
        self.base_spread = self.params.get("base_spread", 0.002)
        self.momentum_skew = self.params.get("momentum_skew", 0.001)
        self.size_skew = self.params.get("size_skew", 2)
        self.rebalance_pending = False  # Flag for rebalancing

    def _calculate_trend(self, prices):
        if len(prices) < 2:
            return 0.0
        return np.polyfit(range(len(prices)), prices, 1)[0]

    def generate_orders(self):
        base_result = super().generate_orders()
        if base_result == []:
            self.logger.info(f"{self.source_name}: In cooldown or risk block, skipping orders.")
            return []

        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            self.logger.info(f"{self.source_name}: Cooldown, skipping orders.")
            return []

        prices = self.order_book.get_recent_prices(window=self.lookback)
        if len(prices) < self.lookback:
            self.logger.info(
                f"{self.source_name}: Not enough price history ({len(prices)} < {self.lookback}), skipping orders.")
            return []

        trend = self._calculate_trend(prices)
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            self.logger.info(f"{self.source_name}: No best bid/ask, skipping orders.")
            return []

        if abs(self.inventory) >= self.max_inventory:
            self.logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing required.")
            self.rebalance_pending = True
            # Optionally, generate offsetting order here or in a separate rebalancing routine
            return []

        spread = self.base_spread
        skew = self.momentum_skew if trend > 0 else -self.momentum_skew if trend < 0 else 0.0

        mid = (best_bid["price"] + best_ask["price"]) / 2
        bid_price = mid * (1 - spread / 2 + skew)
        ask_price = mid * (1 + spread / 2 + skew)

        base_size = self.get_adaptive_order_size(min_size=1, max_size=10)
        buy_qty = base_size + self.size_skew if trend > 0 else base_size
        sell_qty = base_size + self.size_skew if trend < 0 else base_size

        orders = []

        if self.inventory + buy_qty <= self.max_inventory:
            orders.append({"side": "1", "price": bid_price, "quantity": buy_qty})
            self.place_order("1", bid_price, buy_qty)
            self.logger.info(f"{self.source_name}: Placed BID {buy_qty}@{bid_price:.4f} (trend={trend:.4f})")
            # Do NOT update inventory here

        if self.inventory - sell_qty >= -self.max_inventory:
            orders.append({"side": "2", "price": ask_price, "quantity": sell_qty})
            self.place_order("2", ask_price, sell_qty)
            self.logger.info(f"{self.source_name}: Placed ASK {sell_qty}@{ask_price:.4f} (trend={trend:.4f})")
            # Do NOT update inventory here

        self.last_order_time = now
        return orders
