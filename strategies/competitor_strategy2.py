import time

import numpy as np

from .base_strategy import BaseStrategy


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
        base_result = super().generate_orders()
        if base_result == []:
            self.logger.info(
                f"{self.source_name}: In cooldown or risk block, skipping orders."
            )
            return []

        orders = []

        now = time.time()
        if now - self.last_order_time < self.min_order_interval:
            self.logger.info(f"{self.source_name}: Cooldown, skipping orders.")
            return []

        prices = self.order_book.get_recent_prices(window=self.lookback)
        if len(prices) < self.lookback:
            self.logger.info(
                f"{self.source_name}: Not enough price history ({len(prices)} < {self.lookback}), skipping orders."
            )
            return []

        trend = self._calculate_trend(prices)
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
                    orders.append(
                        {
                            "side": "2",
                            "price": best_ask["price"],
                            "quantity": qty,
                            "order_id": best_ask["order_id"],
                        }
                    )
            elif self.inventory < 0:
                best_bid = self.order_book.get_best_bid()
                if best_bid:
                    self.place_order("1", best_bid["price"], qty)
                    orders.append(
                        {
                            "side": "1",
                            "price": best_bid["price"],
                            "quantity": qty,
                            "order_id": best_bid["order_id"],
                        }
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
            return []

        spread = self.base_spread
        skew = (
            self.momentum_skew
            if trend > 0
            else -self.momentum_skew if trend < 0 else 0.0
        )

        mid = (best_bid["price"] + best_ask["price"]) / 2
        bid_price = mid * (1 - spread / 2 + skew)
        ask_price = mid * (1 + spread / 2 + skew)

        base_size = self.get_adaptive_order_size(min_size=1, max_size=10)
        buy_qty = base_size + self.size_skew if trend > 0 else base_size
        sell_qty = base_size + self.size_skew if trend < 0 else base_size

        if self.inventory + buy_qty <= self.max_inventory:
            orders.append({"side": "1", "price": bid_price, "quantity": buy_qty})
            self.place_order("1", bid_price, buy_qty)
            self.logger.info(
                f"{self.source_name}: Placed BID {buy_qty}@{bid_price:.4f} (trend={trend:.4f})"
            )
            # Do NOT update inventory here

        if self.inventory - sell_qty >= -self.max_inventory:
            orders.append({"side": "2", "price": ask_price, "quantity": sell_qty})
            self.place_order("2", ask_price, sell_qty)
            self.logger.info(
                f"{self.source_name}: Placed ASK {sell_qty}@{ask_price:.4f} (trend={trend:.4f})"
            )
            # Do NOT update inventory here

        self.last_order_time = now
        return orders

    def on_trade(self, trade):
        """
        Handle trade execution events. Update inventory and log details.
        """
        super().on_trade(trade)
        self.logger.info(
            f"{self.source_name}: Trade executed. Side: {trade.get('side')}, Qty: {trade.get('qty')}, Price: {trade.get('price')}, New inventory: {self.inventory}, Realised PnL: {self.realised_pnl}"
        )
