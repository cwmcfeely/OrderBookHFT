import time

from .base_strategy import BaseStrategy
import random

class PassiveLiquidityProvider(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "passive_liquidity_provider", params)
        self.inventory = 0  # Track inventory of assets
        self.max_inventory = 100  # Maximum number of assets to hold

    def _risk_check(self, side, price, quantity):
        # Risk check to prevent overexposing based on current inventory
        if side == "1":  # Buying
            if self.inventory + quantity > self.max_inventory:
                return False  # Prevent buying if over max inventory
        elif side == "2":  # Selling
            if self.inventory - quantity < -self.max_inventory:
                return False  # Prevent selling if not enough inventory
        # Call base class risk check as well
        return super()._risk_check(side, price, quantity)

    def generate_orders(self):
        orders = []

        # Cooldown check
        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            return orders  # Skip order generation if still in cooldown

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        if best_bid:
            quantity = random.randint(1, 10)
            if self.inventory + quantity <= self.max_inventory:
                # Generate buy order (FIX: 1 = Buy)
                orders.append({
                    "side": "1",  # Buy
                    "price": best_bid["price"],
                    "quantity": quantity
                })
                self.place_order("1", best_bid["price"], quantity)  # Place buy order
                self.inventory += quantity  # Update inventory after placing buy

        if best_ask:
            quantity = random.randint(1, 10)
            if self.inventory - quantity >= -self.max_inventory:
                # Generate sell order (FIX: 2 = Sell)
                orders.append({
                    "side": "2",  # Sell
                    "price": best_ask["price"],
                    "quantity": quantity
                })
                self.place_order("2", best_ask["price"], quantity)  # Place sell order
                self.inventory -= quantity  # Update inventory after placing sell

        return orders  # Return actual orders for matching engine
