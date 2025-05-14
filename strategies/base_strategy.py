import time
import logging
from abc import ABC, abstractmethod
import numpy as np  # Ensure numpy is in your requirements.txt

class BaseStrategy(ABC):
    def __init__(self, fix_engine, order_book, symbol, source_name, params=None):
        self.fix_engine = fix_engine
        self.order_book = order_book
        self.symbol = symbol
        self.source_name = source_name
        self.params = params if params else {}

        self.max_order_qty = self.params.get("max_order_qty", 1000)
        self.max_price_deviation = self.params.get("max_price_deviation", 0.05)  # 5%

        # New risk parameters
        self.max_daily_orders = self.params.get("max_daily_orders", 1000)
        self.max_position_duration = self.params.get("max_position_duration", 300)  # seconds
        self.daily_loss_limit = self.params.get("daily_loss_limit", -5000)  # currency units

        self.initial_capital = self.params.get("initial_capital", 100000) # Inital capital

        # Internal state
        self.order_count = 0
        self.position_start_time = None
        self.inventory = 0  # Position size: +long, -short
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0

        # Logger for risk messages
        self.logger = logging.getLogger(f"Strategy.{self.source_name}")

    @abstractmethod
    def generate_orders(self):
        """Abstract method to generate orders for the strategy."""
        pass

    def place_order(self, side, price, quantity):
        """Send order via FIX and add to order book, after risk checks"""
        if not self._risk_check(side, price, quantity):
            self.logger.warning(f"[RISK BLOCKED] {side} order for {quantity}@{price} rejected.")
            return

        fix_msg = self.fix_engine.create_new_order(
            cl_ord_id=f"{self.source_name}-{time.time()}",
            symbol=self.symbol,
            side=side,
            price=price,
            qty=quantity,
            source=self.source_name
        )

        order_time = time.time()

        parsed_order = self.fix_engine.parse(fix_msg)
        if parsed_order:
            self.order_book.add_order(
                side=parsed_order.get(54),
                price=parsed_order.get(44),
                quantity=parsed_order.get(38),
                order_id=parsed_order.get(11),
                source=self.source_name,
                order_time=order_time  # Capture order submission timestamp
            )
            self.order_count += 1
            if self.position_start_time is None:
                self.position_start_time = time.time()

    def _risk_check(self, side, price, quantity):
        """Comprehensive risk checks"""

        # Quantity limit
        if quantity > self.max_order_qty:
            self.logger.error(f"Order quantity {quantity} exceeds max {self.max_order_qty}")
            return False

        # Price deviation check (against best bid/ask)
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        reference_price = None
        if side == "2":  # Sell checks against bid
            reference_price = best_bid["price"] if best_bid else None
        else:  # Buy checks against ask
            reference_price = best_ask["price"] if best_ask else None

        if reference_price:
            deviation = abs(price - reference_price) / reference_price
            if deviation > self.max_price_deviation:
                self.logger.warning(f"Price deviation {deviation:.2%} exceeds max {self.max_price_deviation:.2%}")
                return False

        # Daily order limit
        if self.order_count >= self.max_daily_orders:
            self.logger.error("Daily order limit reached")
            return False

        # Position duration check
        if self.position_start_time and (time.time() - self.position_start_time) > self.max_position_duration:
            self.logger.warning("Position held beyond max duration")
            return False

        # Daily loss limit check
        if self.realized_pnl + self.unrealized_pnl() <= self.daily_loss_limit:
            self.logger.critical("Daily loss limit exceeded")
            return False

        # Liquidity check: do not take more than 10% of top 5 levels
        if not self._check_liquidity(side, quantity):
            self.logger.warning("Order size exceeds available liquidity")
            return False

        # Volatility check (optional, requires price history)
        if self._current_volatility() > self.params.get("max_volatility", 0.1):
            self.logger.warning("Volatility threshold exceeded")
            return False

        return True

    def _check_liquidity(self, side, quantity):
        """Check order size against available liquidity in top 5 levels"""
        book = self.order_book.bids if side == "2" else self.order_book.asks
        total_liquidity = 0
        levels = list(book.values())[:5]
        for orders_at_level in levels:
            total_liquidity += sum(order["qty"] for order in orders_at_level)
        # Allow max 10% of liquidity to be taken
        return quantity <= total_liquidity * 0.1 if total_liquidity > 0 else False

    def _current_volatility(self):
        """Calculate recent price volatility (std dev) over last 30 prices"""
        try:
            prices = self.order_book.get_recent_prices(window=30)  # You need to implement this method
            if len(prices) < 2:
                return 0.0
            return np.std(prices)
        except Exception as e:
            self.logger.error(f"Volatility calculation failed: {e}")
            return 0.0

    def on_trade(self, trade):
        """Update position, realized PnL, daily P&L, and win rate after a trade"""
        qty = trade['qty']
        side = trade['side']
        price = trade['price']
        pnl = trade.get('pnl', 0)  # PnL should be calculated and passed in trade dict

        # Update position and realized PnL (average cost method)
        if side == 'buy' or side == "1":
            new_position = self.inventory + qty
            if self.inventory >= 0:
                # Increasing long position: update average price
                self.avg_entry_price = (self.avg_entry_price * self.inventory + price * qty) / new_position
            else:
                # Closing short position: realize PnL
                close_qty = min(abs(self.inventory), qty)
                self.realized_pnl += close_qty * (self.avg_entry_price - price)
                if qty > close_qty:
                    # New long position for remainder
                    self.avg_entry_price = price
            self.inventory = new_position
        else:
            new_position = self.inventory - qty
            if self.inventory <= 0:
                # Increasing short position: update average price
                self.avg_entry_price = (self.avg_entry_price * abs(self.inventory) + price * qty) / abs(new_position)
            else:
                # Closing long position: realize PnL
                close_qty = min(self.inventory, qty)
                self.realized_pnl += close_qty * (price - self.avg_entry_price)
                if qty > close_qty:
                    # New short position for remainder
                    self.avg_entry_price = price
            self.inventory = new_position

        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1

    def unrealized_pnl(self):
        """Calculate unrealized PnL based on current mid-price"""
        mid_price = self.order_book.get_mid_price()
        if mid_price is None or self.inventory == 0:
            return 0.0
        if self.inventory > 0:
            return (mid_price - self.avg_entry_price) * self.inventory
        else:
            return (self.avg_entry_price - mid_price) * abs(self.inventory)

    def total_pnl(self):
        return self.realized_pnl + self.unrealized_pnl()

    def get_win_rate(self):
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0

    def reset_inventory(self):
        self.inventory = 0
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0
        self.order_count = 0
        self.position_start_time = None
        self.total_trades = 0
        self.winning_trades = 0
