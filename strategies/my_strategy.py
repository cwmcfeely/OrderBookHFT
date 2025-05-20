import time
import random
import logging

from .base_strategy import BaseStrategy

# Initialise logger for this module
logger = logging.getLogger(__name__)

class MyStrategy(BaseStrategy):
    """
    Custom trading strategy named 'MyStrategy'.
    Places buy and sell limit orders with a configurable spread factor,
    managing inventory to avoid excessive exposure.
    """
    def __init__(self, fix_engine, order_book, symbol, params=None):
        """
        Initialise MyStrategy instance.

        Args:
            fix_engine: FIX engine instance for sending orders.
            order_book: Reference to the order book object.
            symbol (str): Trading symbol.
            params (dict, optional): Strategy parameters.
        """
        # Initialise base strategy with source name "my_strategy"
        super().__init__(fix_engine, order_book, symbol, "my_strategy", params)
        # Spread factor to adjust bid and ask prices (default 1%)
        self.spread_factor = self.params.get("spread_factor", 0.01)
        self.inventory = 0  # Track current inventory of assets held
        self.max_inventory = 100  # Maximum allowed inventory (long or short)

    def _risk_check(self, side, price, quantity):
        """
        Risk check override to prevent overexposure and large orders.

        Args:
            side (str): '1' for buy, '2' for sell.
            price (float): Order price.
            quantity (int): Order quantity.

        Returns:
            bool: True if order passes risk checks, False otherwise.
        """
        if side == "1":  # Buy order
            if self.inventory + quantity > self.max_inventory:
                # Reject buy if it would exceed max inventory
                return False
        elif side == "2":  # Sell order
            if self.inventory - quantity < -self.max_inventory:
                # Reject sell if it would exceed short max inventory
                return False
        if quantity > 500:
            # Reject orders larger than 500 units as additional risk control
            return False
        # Call base class risk check for other checks
        return super()._risk_check(side, price, quantity)

    def generate_orders(self):
        """
        Generate buy and sell orders with adjusted prices based on spread factor.

        Returns:
            list: List of order dicts with 'side', 'price', and 'quantity' keys.
        """
        # Call base class generate_orders to handle cooldown and drawdown checks
        base_result = super().generate_orders()
        if base_result == []:
            # In cooldown period, skip order generation
            return []

        orders = []

        # Get current best bid and ask prices from order book
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        # Inventory rebalancing: reset inventory if limits exceeded (simulation only)
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        if best_bid and best_ask:
            # Adjust bid price downward by spread factor to be more competitive
            adjusted_bid = best_bid["price"] * (1 - self.spread_factor)
            # Adjust ask price upward by spread factor
            adjusted_ask = best_ask["price"] * (1 + self.spread_factor)

            # Determine adaptive buy order size based on recent volatility (1 to 10 units)
            buy_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory + buy_qty <= self.max_inventory:
                # Append buy order dict to orders list (FIX side '1' = buy)
                orders.append({
                    "side": "1",  # Buy
                    "price": adjusted_bid,
                    "quantity": buy_qty
                })
                # Place the buy order via FIX and update inventory
                self.place_order("1", adjusted_bid, buy_qty)
                self.inventory += buy_qty

            # Determine adaptive sell order size based on recent volatility (1 to 10 units)
            sell_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory - sell_qty >= -self.max_inventory:
                # Append sell order dict to orders list (FIX side '2' = sell)
                orders.append({
                    "side": "2",  # Sell
                    "price": adjusted_ask,
                    "quantity": sell_qty
                })
                # Place the sell order via FIX and update inventory
                self.place_order("2", adjusted_ask, sell_qty)
                self.inventory -= sell_qty

        # Return list of generated orders (used by matching engine)
        return orders
