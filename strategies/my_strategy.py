import time
import random
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class MyStrategy(BaseStrategy):
    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "my_strategy", params)
        self.spread_factor = self.params.get("spread_factor", 0.01)
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
        if quantity > 500:
            return False
        # Call base class risk check as well
        return super()._risk_check(side, price, quantity)

    def generate_orders(self):
        # Call the base class logic first
        base_result = super().generate_orders()
        if base_result == []:
            return []  # In cooldown, skip order generation


        orders = []

        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        # Inventory rebalance logic: if at limit, reset (simulation only)
        if abs(self.inventory) >= self.max_inventory:
            logger.info(f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing to 0.")
            self.inventory = 0

        if best_bid and best_ask:
            adjusted_bid = best_bid["price"] * (1 - self.spread_factor)
            adjusted_ask = best_ask["price"] * (1 + self.spread_factor)

            # Use adaptive position sizing based on volatility
            buy_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory + buy_qty <= self.max_inventory:
                orders.append({
                    "side": "1",  # Buy
                    "price": adjusted_bid,
                    "quantity": buy_qty
                })
                self.place_order("1", adjusted_bid, buy_qty)
                self.inventory += buy_qty

            sell_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
            if self.inventory - sell_qty >= -self.max_inventory:
                orders.append({
                    "side": "2",  # Sell
                    "price": adjusted_ask,
                    "quantity": sell_qty
                })
                self.place_order("2", adjusted_ask, sell_qty)
                self.inventory -= sell_qty

        return orders  # Return actual orders for matching engine