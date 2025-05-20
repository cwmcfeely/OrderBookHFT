import time
import logging
from abc import ABC, abstractmethod
import numpy as np  # Required for volatility calculations

class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.
    Provides risk management, order placement, PnL, and performance tracking utilities.
    All custom strategies should inherit from this class and implement their own logic.
    """
    def __init__(self, fix_engine, order_book, symbol, source_name, params=None):
        # Core components required by all strategies
        self.fix_engine = fix_engine
        self.order_book = order_book
        self.symbol = symbol
        self.source_name = source_name
        self.params = params if params else {}

        # Risk and trading parameters (with sensible defaults)
        self.max_order_qty = self.params.get("max_order_qty", 1000)
        self.max_price_deviation = self.params.get("max_price_deviation", 0.02)  # 2% price deviation allowed
        self.max_daily_orders = self.params.get("max_daily_orders", 1000)
        self.max_position_duration = self.params.get("max_position_duration", 60)  # seconds
        self.daily_loss_limit = self.params.get("daily_loss_limit", -10000)  # Max daily loss allowed
        self.initial_capital = self.params.get("initial_capital", 100000)  # Starting capital

        # Cooldown period after drawdown or risk event
        self.last_order_time = 0
        self.min_order_interval = self.params.get("min_order_interval", 1.0)  # Minimum time between orders (seconds)
        self.max_unrealized_pnl = 0.0
        self.cooldown_until = 0
        self.drawdown_limit = self.params.get("drawdown_limit", 500)  # Drawdown threshold before cooldown (£500)
        self.cooldown_period = self.params.get("cooldown_period", 60)  # Cooldown duration in seconds

        # Trailing stop parameters
        self.trailing_stop = self.params.get("trailing_stop", 0.01)  # 1% trailing stop by default
        self.highest_price = None
        self.lowest_price = None

        # Internal state for position and PnL tracking
        self.order_count = 0
        self.position_start_time = None
        self.inventory = 0  # Net position: positive=long, negative=short
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0

        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0

        # Logger for this strategy instance
        self.logger = logging.getLogger(f"Strategy.{self.source_name}")

    def generate_orders(self):
        """
        Entry point for strategy order generation.
        Handles cooldown logic and drawdown checks.
        Override in subclasses to implement specific trading logic.
        """
        now = time.time()
        if now < getattr(self, "cooldown_until", 0):
            self.logger.info(f"{self.source_name}: In cooldown until {self.cooldown_until}, skipping orders.")
            return []
        # Optionally update unrealised PnL and check drawdown
        self.update_unrealized_pnl_and_drawdown()
        # By default, base class does not generate orders
        return None

    def place_order(self, side, price, quantity):
        """
        Place an order via FIX and add it to the order book, after risk checks and cooldown.

        Args:
            side (str): '1' (buy) or '2' (sell) per FIX standard.
            price (float): Limit price.
            quantity (int): Order quantity.
        """
        # Enforce minimum interval between orders (cooldown)
        now = time.time()
        if (now - getattr(self, 'last_order_time', 0)) < getattr(self, 'min_order_interval', 1.0):
            self.logger.info(f"Order skipped due to cooldown: {side} {quantity}@{price}")
            return

        # Run risk checks before placing the order
        if not self._risk_check(side, price, quantity):
            self.logger.warning(f"[RISK BLOCKED] {side} order for {quantity}@{price} rejected.")
            return

        # Create and send FIX new order message
        fix_msg = self.fix_engine.create_new_order(
            cl_ord_id=f"{self.source_name}-{now}",
            symbol=self.symbol,
            side=side,
            price=price,
            qty=quantity,
            source=self.source_name
        )

        order_time = now

        # Parse the FIX message and add the order to the order book
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
                self.position_start_time = now

            # Update last_order_time to enforce cooldown
            self.last_order_time = now

    def _risk_check(self, side, price, quantity):
        """
        Comprehensive risk checks before order placement.

        Returns:
            bool: True if order passes all risk checks, False otherwise.
        """
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
        """
        Check order size against available liquidity in top 5 levels.

        Args:
            side (str): '1' (buy) or '2' (sell).
            quantity (int): Order quantity.

        Returns:
            bool: True if order size is within 10% of top 5 levels' liquidity.
        """
        book = self.order_book.bids if side == "2" else self.order_book.asks
        total_liquidity = 0
        levels = list(book.values())[:5]
        for orders_at_level in levels:
            total_liquidity += sum(order["qty"] for order in orders_at_level)
        # Allow max 10% of liquidity to be taken
        return quantity <= total_liquidity * 0.1 if total_liquidity > 0 else False

    def _current_volatility(self, window=30):
        """
        Calculate recent price volatility (standard deviation) over last `window` prices.

        Args:
            window (int): Number of recent prices to consider.

        Returns:
            float: Standard deviation of recent prices.
        """
        try:
            prices = self.order_book.get_recent_prices(window=window)
            if len(prices) < 2:
                return 0.0
            return np.std(prices)
        except Exception as e:
            self.logger.error(f"Volatility calculation failed: {e}")
            return 0.0

    def on_trade(self, trade):
        """
        Update position, realised PnL, daily PnL, and win rate after a trade.
        Implements per-trade stop loss, take profit, and trailing stop logic.

        Args:
            trade (dict): Trade details, including side, price, qty, and pnl.

        Returns:
            tuple: (inventory, avg_entry_price, realised_pnl, total_trades, winning_trades)
        """
        qty = trade['qty']
        side = trade['side']
        price = trade['price']
        pnl = trade.get('pnl', 0)  # PnL should be calculated and passed in trade dict

        # Update position and realised PnL using average cost method
        if side == 'buy' or side == "1":
            new_position = self.inventory + qty
            if new_position == 0:
                self.avg_entry_price = 0.0
            elif self.inventory >= self.max_order_qty or self.inventory >= 0:
                self.avg_entry_price = (self.avg_entry_price * self.inventory + price * qty) / new_position
            else:
                close_qty = min(abs(self.inventory), qty)
                self.realized_pnl += close_qty * (self.avg_entry_price - price)
                if qty > close_qty:
                    self.avg_entry_price = price
            self.inventory = new_position
        else:
            new_position = self.inventory - qty
            if new_position == 0:
                self.avg_entry_price = 0.0
            elif self.inventory <= self.max_order_qty or self.inventory <= 0.0 or self.inventory <= -self.max_order_qty or self.inventory <= -1.0 * self.max_order_qty:
                self.avg_entry_price = (self.avg_entry_price * abs(self.inventory) + price * qty) / abs(new_position)
            else:
                close_qty = min(self.inventory, qty)
                self.realized_pnl += close_qty * (price - self.avg_entry_price)
                if qty > close_qty:
                    self.avg_entry_price = price
            self.inventory = new_position

        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1

        # --- Trailing stop logic initialisation ---
        if not hasattr(self, 'highest_price'):
            self.highest_price = None
        if not hasattr(self, 'lowest_price'):
            self.lowest_price = None

        # --- Update trailing stop prices ---
        if self.inventory > 0:  # Long position
            if self.highest_price is None or price > self.highest_price:
                self.highest_price = price
            trailing_stop_pct = self.params.get("trailing_stop_pct", 0.01)  # 1% default
            # Check trailing stop for long
            if price < self.highest_price * (1 - trailing_stop_pct):
                self.logger.info(f"{self.source_name}: Trailing stop hit on long at {price}, closing position.")
                self.reset_inventory()
                self.highest_price = None
                self.lowest_price = None
        elif self.inventory < 0:  # Short position
            if self.lowest_price is None or price < self.lowest_price:
                self.lowest_price = price
            trailing_stop_pct = self.params.get("trailing_stop_pct", 0.01)  # 1% default
            # Check trailing stop for short
            if price > self.lowest_price * (1 + trailing_stop_pct):
                self.logger.info(f"{self.source_name}: Trailing stop hit on short at {price}, closing position.")
                self.reset_inventory()
                self.highest_price = None
                self.lowest_price = None
        else:
            # No position, reset trailing stop trackers
            self.highest_price = None
            self.lowest_price = None

        # --- Per-trade stop loss and take profit logic ---
        stop_loss = self.params.get("per_trade_stop_loss", 100)  # Example: 100 currency units
        take_profit = self.params.get("per_trade_take_profit", 150)  # Example: 150 currency units

        if pnl <= -abs(stop_loss):
            self.logger.warning(
                f"Per-trade stop loss triggered: trade PnL={pnl}. Closing position and resetting inventory.")
            self.reset_inventory()
        elif pnl >= abs(take_profit):
            self.logger.info(
                f"Per-trade take profit triggered: trade PnL={pnl}. Closing position and resetting inventory.")
            self.reset_inventory()

        return (self.inventory, self.avg_entry_price, self.realized_pnl, self.total_trades, self.winning_trades)

    def unrealized_pnl(self):
        """
        Calculate unrealised PnL based on current mid-price.

        Returns:
            float: Unrealised profit or loss.
        """
        mid_price = self.order_book.get_mid_price()
        if mid_price is None or self.inventory == 0:
            return 0.0
        if self.inventory > 0:
            return (mid_price - self.avg_entry_price) * self.inventory
        else:
            return (self.avg_entry_price - mid_price) * abs(self.inventory)

    def total_pnl(self):
        """
        Total PnL (realised + unrealised).
        """
        return self.realized_pnl + self.unrealized_pnl()

    def get_win_rate(self):
        """
        Calculate win rate as the fraction of winning trades.

        Returns:
            float: Win rate (0.0 to 1.0).
        """
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0

    def reset_inventory(self):
        """
        Reset all position and PnL state for this strategy.
        """
        self.inventory = 0
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0
        self.order_count = 0
        self.position_start_time = None
        self.total_trades = 0
        self.winning_trades = 0

    def can_place_order(self):
        """
        Return True if enough time has passed since the last order (cooldown complete).
        """
        now = time.time()
        return (now - self.last_order_time) >= self.min_order_interval

    def get_adaptive_order_size(self, min_size=1, max_size=None, volatility_window=30):
        """
        Returns an order size inversely proportional to recent volatility.
        This helps reduce risk in volatile markets.

        Args:
            min_size (int): Minimum order size.
            max_size (int or None): Maximum order size.
            volatility_window (int): Number of prices to use for volatility.

        Returns:
            int: Adaptive order size.
        """
        vol = self._current_volatility(window=volatility_window)
        max_qty = max_size if max_size is not None else self.max_order_qty
        # Avoid division by zero and cap size
        adaptive_size = max(min_size, int(max_qty / (vol + 0.01)))
        return min(adaptive_size, max_qty)

    def update_unrealized_pnl_and_drawdown(self):
        """
        Update unrealised PnL and check for drawdown limit breach.
        If drawdown exceeded, enter cooldown period.
        """
        mid_price = self.order_book.get_mid_price()
        if mid_price is None or self.inventory == 0:
            return
        # Calculate current unrealised PnL
        if self.inventory > 0:
            unrealized = (mid_price - self.avg_entry_price) * self.inventory
        else:
            unrealized = (self.avg_entry_price - mid_price) * abs(self.inventory)
        self.max_unrealized_pnl = max(self.max_unrealized_pnl, unrealized)
        drawdown = self.max_unrealized_pnl - unrealized
        if drawdown >= self.drawdown_limit:
            self.logger.warning(f"{self.source_name}: Drawdown limit hit ({drawdown}), entering cooldown.")
            self.cooldown_until = time.time() + self.cooldown_period
            self.max_unrealized_pnl = unrealized  # Reset peak
