from .base_strategy import BaseStrategy
import random

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
        orders = []
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        if best_bid and best_ask:
            adjusted_bid = best_bid["price"] * (1 - self.spread_factor)
            adjusted_ask = best_ask["price"] * (1 + self.spread_factor)

            # Calculate dynamic max order size based on volatility
            volatility = self._current_volatility()
            max_size = min(
                self.max_order_qty,
                max(1, int(1000 / (volatility + 0.01)))  # Avoid division by zero
            )

            # Generate and store buy order
            quantity = random.randint(1, min(10, max_size))
            if self.inventory + quantity <= self.max_inventory:
                orders.append({
                    "side": "1",  # Buy
                    "price": adjusted_bid,
                    "quantity": quantity
                })
                self.place_order("1", adjusted_bid, quantity)  # Place buy order
                self.inventory += quantity  # Update inventory after placing buy

            # Generate and store sell order
            quantity = random.randint(1, min(10, max_size))
            if self.inventory - quantity >= -self.max_inventory:
                orders.append({
                    "side": "2",  # Sell
                    "price": adjusted_ask,
                    "quantity": quantity
                })
                self.place_order("2", adjusted_ask, quantity)  # Place sell order
                self.inventory -= quantity  # Update inventory after placing sell

        return orders  # Return actual orders for matching engine
