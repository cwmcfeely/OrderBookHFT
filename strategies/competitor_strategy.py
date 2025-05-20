import time
from .base_strategy import BaseStrategy
import random
import logging

# Initialise logger for this module
logger = logging.getLogger(__name__)

class PassiveLiquidityProvider(BaseStrategy):
    """
    A simple passive liquidity provider strategy that places limit buy and sell orders
    near the current best bid and ask prices, aiming to provide liquidity and earn the spread.
    It manages inventory to avoid excessive exposure.
    """
    def __init__(self, fix_engine, order_book, symbol, params=None):
        """
        Initialise the PassiveLiquidityProvider strategy.

        Args:
            fix_engine: FIX engine instance for sending orders.
            order_book: Reference to the order book object.
            symbol (str): Trading symbol.
            params (dict, optional): Strategy parameters.
        """
        # Initialise base strategy with a unique source name
        super().__init__(fix_engine, order_book, symbol, "passive_liquidity_provider", params)
        self.inventory = 0  # Track current inventory of assets held
        self.max_inventory = 100  # Maximum allowed inventory (long or short)

    def _risk_check(self, side, price, quantity):
        """
        Risk check override to prevent overexposure beyond max inventory.

        Args:
            side (str): '1' for buy, '2' for sell.
            price (float): Order price.
            quantity (int): Order quantity.

        Returns:
            bool: True if order passes risk check, False otherwise.
        """
        if side == "1":  # Buy order
            if self.inventory + quantity > self.max_inventory:
                # Reject buy if it would exceed max inventory
                return False
        elif side == "2":  # Sell order
            if self.inventory - quantity < -self.max_inventory:
                # Reject sell if it would exceed short max inventory
                return False
        # Call base class risk check for other checks
        return super()._risk_check(side, price, quantity)

    def generate_orders(self):
        """
        Generate buy and sell limit orders near best bid and ask prices.

        Returns:
            list: List of order dicts with 'side', 'price', and 'quantity' keys.
        """
        # Call base class generate_orders to handle cooldown and drawdown checks
        base_result = super().generate_orders()
        if base_result == []:
            # In cooldown, skip order generation
            return []

        orders = []

        now = time.time()
        # Enforce minimum interval between orders (cooldown)
        if now - self.last_order_time < self.min_order_interval:
            # Still cooling down, skip order generation
            return orders

        # Get current best bid and ask prices from order book
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        # Inventory rebalancing: if inventory exceeds limits, reset to zero
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        # Generate buy order if possible
        if best_bid:
            # Determine random order size within adaptive limits (1 to 10 units)
            quantity = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory + quantity <= self.max_inventory:
                # Append buy order dict to orders list (FIX side '1' = buy)
                orders.append({
                    "side": "1",  # Buy
                    "price": best_bid["price"],
                    "quantity": quantity
                })
                # Place the buy order via FIX and update inventory
                self.place_order("1", best_bid["price"], quantity)
                self.inventory += quantity

        # Generate sell order if possible
        if best_ask:
            # Determine random order size within adaptive limits (1 to 10 units)
            quantity = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory - quantity >= -self.max_inventory:
                # Append sell order dict to orders list (FIX side '2' = sell)
                orders.append({
                    "side": "2",  # Sell
                    "price": best_ask["price"],
                    "quantity": quantity
                })
                # Place the sell order via FIX and update inventory
                self.place_order("2", best_ask["price"], quantity)
                self.inventory -= quantity

        # Update last order time to now for cooldown tracking
        self.last_order_time = now

        # Return list of generated orders (used by matching engine)
        return orders
