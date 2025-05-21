import time
from .base_strategy import BaseStrategy
import random
import logging

# Initialise logger for this module
logger = logging.getLogger(__name__)

class MarketMakerStrategy(BaseStrategy):
    """
    Market Maker strategy that places buy and sell limit orders around the mid-price,
    aiming to profit from the bid-ask spread while managing inventory risk.
    """
    def __init__(self, fix_engine, order_book, symbol, params=None):
        """
        Initialise the MarketMakerStrategy.

        Args:
            fix_engine: FIX engine instance for sending orders.
            order_book: Reference to the order book object.
            symbol (str): Trading symbol.
            params (dict, optional): Strategy parameters.
        """
        # Initialise base strategy with source name "market_maker"
        super().__init__(fix_engine, order_book, symbol, "market_maker", params)
        # Spread to apply around mid-price for bid and ask orders (default 0.2%)
        self.spread = self.params.get("spread", 0.002)
        self.inventory = 0  # Track current inventory position
        self.max_inventory = 100  # Maximum allowed inventory (long or short)

    def generate_orders(self):
        """
        Generate buy and sell limit orders around the mid-price with adaptive order sizes.

        Returns:
            list: List of order dicts with 'side', 'price', and 'quantity' keys.
        """
        # Call base class generate_orders to respect cooldown and risk checks
        base_result = super().generate_orders()
        if base_result == []:
            self.logger.info(f"{self.source_name}: In cooldown or risk block, skipping orders.")
            # In cooldown period, skip order generation
            return []

        orders = []

        now = time.time()
        # Enforce minimum interval between orders (cooldown)
        if now - self.last_order_time < self.min_order_interval:
            self.logger.info(f"{self.source_name}: Cooldown, skipping orders.")
            # Still cooling down, skip order generation
            return orders

        # Get current best bid and ask prices from order book
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            self.logger.info(f"{self.source_name}: Missing best bid or ask, skipping orders.")
            # If either side is missing, cannot calculate mid-price; skip
            return orders

        # Inventory rebalancing: reset inventory if limits exceeded
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        # Calculate mid-price as average of best bid and ask
        mid = (best_bid["price"] + best_ask["price"]) / 2
        # Calculate bid and ask prices by applying half the spread below and above mid-price
        bid_price = mid * (1 - self.spread / 2)
        ask_price = mid * (1 + self.spread / 2)

        # Determine adaptive buy order size based on recent volatility (1 to 10 units)
        buy_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory + buy_qty <= self.max_inventory:
            # Append buy order dict to orders list (FIX side '1' = buy)
            orders.append({"side": "1", "price": bid_price, "quantity": buy_qty})
            # Place the buy order via FIX and update inventory
            self.place_order("1", bid_price, buy_qty)
            self.logger.info(f"{self.source_name}: Placed BUY order {buy_qty}@{bid_price:.4f}")
            self.inventory += buy_qty

        # Determine adaptive sell order size based on recent volatility (1 to 10 units)
        sell_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory - sell_qty >= -self.max_inventory:
            # Append sell order dict to orders list (FIX side '2' = sell)
            orders.append({"side": "2", "price": ask_price, "quantity": sell_qty})
            # Place the sell order via FIX and update inventory
            self.place_order("2", ask_price, sell_qty)
            self.logger.info(f"{self.source_name}: Placed SELL order {sell_qty}@{ask_price:.4f}")
            self.inventory -= sell_qty

        # Update last order time to now for cooldown tracking
        self.last_order_time = now

        # Return list of generated orders (used by matching engine)
        return orders
