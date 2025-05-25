import time
import random
from .base_strategy import BaseStrategy


class MyStrategy(BaseStrategy):
    """
    Custom trading strategy named 'MyStrategy'.
    Places buy and sell limit orders with a configurable spread factor,
    managing inventory to avoid excessive exposure.
    """

    def __init__(self, fix_engine, order_book, symbol, params=None):
        super().__init__(fix_engine, order_book, symbol, "my_strategy", params)
        self.spread_factor = self.params.get("spread_factor", 0.01)
        self.max_inventory = 100
        self.rebalance_pending = False  # Flag for rebalancing

    def _risk_check(self, side, price, quantity):
        """
        Risk check override to prevent overexposure and large orders.
        """
        if side == "1":  # Buy order
            if self.inventory + quantity > self.max_inventory:
                self.logger.warning(
                    f"{self.source_name}: Buy order rejected (would exceed max inventory)."
                )
                return False
        elif side == "2":  # Sell order
            if self.inventory - quantity < -self.max_inventory:
                self.logger.warning(
                    f"{self.source_name}: Sell order rejected (would exceed short max inventory)."
                )
                return False
        if quantity > 500:
            self.logger.warning(f"{self.source_name}: Order rejected (quantity > 500).")
            return False
        return super()._risk_check(side, price, quantity)

    def generate_orders(self):
        """
        Generate buy and sell orders with adjusted prices based on spread factor.
        """
        base_result = super().generate_orders()
        if base_result == []:
            self.logger.info(
                f"{self.source_name}: In cooldown or risk block, skipping orders."
            )
            return []

        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            self.logger.info(f"{self.source_name}: Cooldown, skipping orders.")
            return []

        orders = []

        # Get current best bid and ask prices from order book
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()

        # Rebalancing logic implementation
        if self.rebalance_pending:
            qty = min(abs(self.inventory), 10)
            if self.inventory > 0:
                best_ask = self.order_book.get_best_ask()
                if best_ask:
                    self.place_order("2", best_ask["price"], qty)
                    orders.append(
                        {"side": "2", "price": best_ask["price"], "quantity": qty}
                    )
            elif self.inventory < 0:
                best_bid = self.order_book.get_best_bid()
                if best_bid:
                    self.place_order("1", best_bid["price"], qty)
                    orders.append(
                        {"side": "1", "price": best_bid["price"], "quantity": qty}
                    )
            # **Add this block to reset rebalance_pending if inventory is zero**
            if self.inventory == 0:
                self.rebalance_pending = False
            return orders

        # If inventory is at or beyond limits, flag for rebalancing (do not reset directly)
        if abs(self.inventory) >= self.max_inventory:
            self.logger.info(
                f"{self.source_name}: Inventory at limit ({self.inventory}), rebalancing required."
            )
            self.rebalance_pending = True
            # Skip placing further orders until rebalanced
            return orders

        if best_bid and best_ask:
            adjusted_bid = best_bid["price"] * (1 - self.spread_factor)
            adjusted_ask = best_ask["price"] * (1 + self.spread_factor)

            buy_qty = random.randint(
                1, self.get_adaptive_order_size(min_size=1, max_size=10)
            )
            if self.inventory + buy_qty <= self.max_inventory:
                orders.append({"side": "1", "price": adjusted_bid, "quantity": buy_qty})
                self.place_order("1", adjusted_bid, buy_qty)
                self.logger.info(
                    f"{self.source_name}: Placed BUY order {buy_qty}@{adjusted_bid:.4f}"
                )

            sell_qty = random.randint(
                1, self.get_adaptive_order_size(min_size=1, max_size=10)
            )
            if self.inventory - sell_qty >= -self.max_inventory:
                orders.append(
                    {"side": "2", "price": adjusted_ask, "quantity": sell_qty}
                )
                self.place_order("2", adjusted_ask, sell_qty)
                self.logger.info(
                    f"{self.source_name}: Placed SELL order {sell_qty}@{adjusted_ask:.4f}"
                )

        self.last_order_time = now
        return orders

    def on_trade(self, trade):
        """
        Handle trade execution events. Update inventory and log details.
        """
        super().on_trade(trade)
        self.logger.info(
            f"{self.source_name}: Trade executed. Side: {trade.get('side')}, "
            f"Qty: {trade.get('qty')}, Price: {trade.get('price')}, "
            f"New inventory: {self.inventory}, Realised PnL: {self.realised_pnl}"
        )
