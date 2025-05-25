import time
from .base_strategy import BaseStrategy
import random

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
        self.max_inventory = 100  # Maximum allowed inventory (long or short)
        self.rebalance_pending = False  # Flag for rebalancing

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
                return False
        elif side == "2":  # Sell order
            if self.inventory - quantity < -self.max_inventory:
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
            self.logger.info(f"{self.source_name}: In cooldown or risk block, skipping orders.")
            return []

        orders = []

        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            self.logger.info(f"{self.source_name}: Cooldown, skipping orders.")
            return orders

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if not (best_bid and best_ask):
            self.logger.info(f"{self.source_name}: No best bid/ask, skipping orders.")
            return []

        # Rebalancing logic implementation
        if self.rebalance_pending:
            qty = min(abs(self.inventory), 10)
            if self.inventory > 0:
                best_ask = self.order_book.get_best_ask()
                if best_ask:
                    self.place_order("2", best_ask["price"], qty)
                    orders.append({"side": "2", "price": best_ask["price"], "quantity": qty})
            elif self.inventory < 0:
                best_bid = self.order_book.get_best_bid()
                if best_bid:
                    self.place_order("1", best_bid["price"], qty)
                    orders.append({"side": "1", "price": best_bid["price"], "quantity": qty})
            # Reset flag if inventory is now zero
            if self.inventory == 0:
                self.rebalance_pending = False
            return orders

        # If inventory is at or beyond limits, flag for rebalancing (do not reset directly)
        if abs(self.inventory) >= self.max_inventory:
            self.logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing required.")
            self.rebalance_pending = True
            # Skip placing further orders until rebalanced
            return orders

        # Generate buy order if possible
        if best_bid:
            quantity = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory + quantity <= self.max_inventory:
                orders.append({
                    "side": "1",  # Buy
                    "price": best_bid["price"],
                    "quantity": quantity
                })
                self.place_order("1", best_bid["price"], quantity)
                # Do NOT update inventory here

        # Generate sell order if possible
        if best_ask:
            quantity = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory - quantity >= -self.max_inventory:
                orders.append({
                    "side": "2",  # Sell
                    "price": best_ask["price"],
                    "quantity": quantity
                })
                self.place_order("2", best_ask["price"], quantity)
                # Do NOT update inventory here

        self.last_order_time = now
        return orders

    def on_trade(self, trade):
        """
        Handle trade execution events. Update inventory and log details.
        """
        super().on_trade(trade)
        self.logger.info(f"{self.source_name}: Trade executed. Side: {trade.get('side')}, "
                         f"Qty: {trade.get('qty')}, Price: {trade.get('price')}, "
                         f"New inventory: {self.inventory}, Realised PnL: {self.realised_pnl}")
