import time
from .base_strategy import BaseStrategy
import random
import numpy as np
import logging

# Initialise logger for this module
logger = logging.getLogger(__name__)

class MomentumStrategy(BaseStrategy):
    """
    Momentum trading strategy that analyses recent price trends and places buy orders
    when prices are trending upwards and sell orders when prices are trending downwards.
    Inventory is managed to avoid excessive exposure.
    """
    def __init__(self, fix_engine, order_book, symbol, params=None):
        """
        Initialise the MomentumStrategy.

        Args:
            fix_engine: FIX engine instance for sending orders.
            order_book: Reference to the order book object.
            symbol (str): Trading symbol.
            params (dict, optional): Strategy parameters.
        """
        # Initialise base strategy with source name "momentum"
        super().__init__(fix_engine, order_book, symbol, "momentum", params)
        self.inventory = 0  # Track current inventory position
        self.max_inventory = 100  # Maximum allowed inventory (long or short)
        # Lookback window for trend calculation, default 5 price points
        self.lookback = self.params.get("lookback", 5)

    def generate_orders(self):
        """
        Generate buy or sell orders based on recent price trend.

        Returns:
            list: List of order dicts with 'side', 'price', and 'quantity' keys.
        """
        # Call base class generate_orders to respect cooldown and risk checks
        base_result = super().generate_orders()
        if base_result == []:
            # In cooldown period, skip order generation
            return []

        orders = []

        now = time.time()
        # Enforce minimum interval between orders (cooldown)
        if now - self.last_order_time < self.min_order_interval:
            # Still cooling down, skip order generation
            return orders

        # Retrieve recent prices from the order book for trend analysis
        prices = self.order_book.get_recent_prices(window=self.lookback)
        if len(prices) < self.lookback:
            # Not enough data points to calculate trend, skip
            return orders

        # Calculate slope of price trend using linear regression (polyfit degree 1)
        trend = np.polyfit(range(len(prices)), prices, 1)[0]

        # Get current best bid and ask prices from order book
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            # Missing bid or ask data, cannot place orders reliably
            return orders

        # Inventory rebalancing: reset inventory if limits exceeded
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        # Determine adaptive order size based on recent volatility (1 to 10 units)
        qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))

        # If price trend is upwards, place buy order at best ask price
        if trend > 0 and self.inventory + qty <= self.max_inventory:
            orders.append({"side": "1", "price": best_ask["price"], "quantity": qty})
            self.place_order("1", best_ask["price"], qty)
            self.inventory += qty
        # If price trend is downwards, place sell order at best bid price
        elif trend < 0 and self.inventory - qty >= -self.max_inventory:
            orders.append({"side": "2", "price": best_bid["price"], "quantity": qty})
            self.place_order("2", best_bid["price"], qty)
            self.inventory -= qty

        # Update last order time to now for cooldown tracking
        self.last_order_time = now

        # Return list of generated orders (used by matching engine)
        return orders
