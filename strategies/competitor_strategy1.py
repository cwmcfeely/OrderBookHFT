import time
from .base_strategy import BaseStrategy
import random

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
        super().__init__(fix_engine, order_book, symbol, "market_maker", params)
        self.spread = self.params.get("spread", 0.002)
        self.max_inventory = 100  # Maximum allowed inventory (long or short)
        self.rebalance_pending = False  # Flag for rebalancing

    def generate_orders(self):
        """
        Generate buy and sell limit orders around the mid-price with adaptive order sizes.
        Returns:
            list: List of order dicts with 'side', 'price', and 'quantity' keys.
        """
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
            self.logger.info(f"{self.source_name}: Missing best bid or ask, skipping orders.")
            return orders

        # --- Rebalancing logic implementation ---
        if self.rebalance_pending:
            qty = min(abs(self.inventory), 10)
            if self.inventory > 0:
                # Reduce long inventory by selling
                if best_ask:
                    self.place_order("2", best_ask["price"], qty)
                    orders.append({"side": "2", "price": best_ask["price"], "quantity": qty})
            elif self.inventory < 0:
                # Reduce short inventory by buying
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

        # --- Normal market making logic ---
        # Calculate mid-price as average of best bid and ask
        mid = (best_bid["price"] + best_ask["price"]) / 2
        bid_price = mid * (1 - self.spread / 2)
        ask_price = mid * (1 + self.spread / 2)

        # Determine adaptive buy order size
        buy_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory + buy_qty <= self.max_inventory:
            orders.append({"side": "1", "price": bid_price, "quantity": buy_qty})
            self.place_order("1", bid_price, buy_qty)
            self.logger.info(f"{self.source_name}: Placed BUY order {buy_qty}@{bid_price:.4f}")
            # Do NOT update inventory here

        # Determine adaptive sell order size
        sell_qty = random.randint(1, self.get_adaptive_order_size(min_size=1, max_size=10))
        if self.inventory - sell_qty >= -self.max_inventory:
            orders.append({"side": "2", "price": ask_price, "quantity": sell_qty})
            self.place_order("2", ask_price, sell_qty)
            self.logger.info(f"{self.source_name}: Placed SELL order {sell_qty}@{ask_price:.4f}")
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
