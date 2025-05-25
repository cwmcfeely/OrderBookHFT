import time
import logging
from abc import ABC
import numpy as np  # Required for volatility calculations


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    Provides risk management, order placement, PnL, and performance tracking utilities.

    All custom strategies should inherit from this class and implement their own logic.
    """

    def __init__(self, fix_engine, order_book, symbol, source_name, params=None):
        """
        Core components required by all strategies
        """
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

        # Cooldown period after drawdown or risk event
        self.last_order_time = 0
        self.min_order_interval = self.params.get("min_order_interval", 1.0)  # Minimum time between orders (seconds)
        self.max_unrealised_pnl = 0.0
        self.cooldown_until = 0
        self.drawdown_limit = self.params.get("drawdown_limit", 500)  # Drawdown threshold before cooldown (£500)
        self.cooldown_period = self.params.get("cooldown_period", 60)  # Cooldown duration in seconds
        self.daily_loss_limit = self.params.get("daily_loss_limit", -10000)

        # Trailing stop parameters
        self.trailing_stop = self.params.get("trailing_stop", 0.01)  # 1% trailing stop by default
        self.highest_price = None
        self.lowest_price = None

        # Internal state for position and PnL tracking
        self.order_count = 0
        self.position_start_time = None
        self.inventory = 0  # Net position: positive=long, negative=short
        self.avg_entry_price = 0.0
        self.realised_pnl = 0.0

        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0

        # Logger for this strategy instance
        self.logger = logging.getLogger(f"FIX_{self.source_name}")

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
        self.update_unrealised_pnl_and_drawdown()

        # By default, base class does not generate orders
        return None

    def place_order(self, side, price, quantity):
        """
        Place an order via FIX and add it to the order book, after risk checks and cooldown.
        Returns True if the order was placed, False if blocked.
        Args:
            side (str): '1' (buy) or '2' (sell) per FIX standard.
            price (float): Limit price.
            quantity (int): Order quantity.
        """
        now = time.time()
        # Enforce minimum interval between orders (cooldown)
        if (now - getattr(self, 'last_order_time', 0)) < getattr(self, 'min_order_interval', 1.0):
            self.logger.info(f"{self.source_name}: Order skipped due to cooldown: {side} {quantity}@{price}")
            return False

        # Run risk checks before placing the order
        if not self._risk_check(side, price, quantity):
            self.logger.info(f"{self.source_name}: Risk check failed, order not placed: {side} {quantity}@{price}")
            return False

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
                order_time=order_time
            )

            self.order_count += 1
            if self.position_start_time is None:
                self.position_start_time = now

            self.last_order_time = now
            self.logger.info(f"{self.source_name}: Order placed: Side={side}, Qty={quantity}, Price={price}")
            return True
        else:
            self.logger.warning(f"{self.source_name}: FIX message parsing failed, order not placed.")
            return False

    def on_competition(self, taker_strategy, maker_strategy, price, qty):
        """
        Handle competition between strategies when order is matched
        """
        self.logger.info(f"{self.source_name} lost to {maker_strategy} at {price}")

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
        if self.realised_pnl + self.unrealised_pnl() <= self.daily_loss_limit:
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
        # Allow max 20% of liquidity to be taken
        return quantity <= total_liquidity * 0.2 if total_liquidity > 0 else False

    def _current_volatility(self, window=30):
        """
        Calculate recent price volatility (standard deviation) over last `window` prices.
        Ensures a minimum volatility to prevent excessive order sizes.
        Args:
            window (int): Number of recent prices to consider.
        Returns:
            float: Standard deviation of recent prices (minimum threshold applied).
        """
        min_vol = 0.01  # Minimum volatility to prevent order size spikes
        try:
            prices = self.order_book.get_recent_prices(window=window)
            if not prices or len(prices) < 2:
                return min_vol
            vol = np.std(prices)
            return max(vol, min_vol)
        except Exception as e:
            self.logger.error(f"Volatility calculation failed: {e}")
            return min_vol

    def on_trade(self, trade):
        """
        Update position, realised PnL, and win rate after a trade.
        Uses average cost method and handles all position transitions.
        """
        qty = trade['qty']
        side = trade['side']
        price = trade['price']
        pnl = trade.get('pnl', 0)  # Optional, for per-trade stop logic

        if side in ('buy', "1"):
            if self.inventory >= 0:
                # Increasing or opening a long position
                total_cost = self.avg_entry_price * self.inventory + price * qty
                self.inventory += qty
                self.avg_entry_price = total_cost / self.inventory if self.inventory != 0 else 0.0
            else:
                # Reducing or flipping a short position
                close_qty = min(abs(self.inventory), qty)
                self.realised_pnl += close_qty * (self.avg_entry_price - price)
                self.inventory += qty
                if self.inventory > 0:
                    # Flipped to long, set new avg entry price for remaining qty
                    open_qty = self.inventory
                    self.avg_entry_price = price if open_qty > 0 else 0.0
                elif self.inventory == 0:
                    self.avg_entry_price = 0.0

        elif side in ('sell', "2"):
            if self.inventory <= 0:
                # Increasing or opening a short position
                total_cost = self.avg_entry_price * abs(self.inventory) + price * qty
                self.inventory -= qty
                self.avg_entry_price = total_cost / abs(self.inventory) if self.inventory != 0 else 0.0
            else:
                # Reducing or flipping a long position
                close_qty = min(self.inventory, qty)
                self.realised_pnl += close_qty * (price - self.avg_entry_price)
                self.inventory -= qty
                if self.inventory < 0:
                    # Flipped to short, set new avg entry price for remaining qty
                    open_qty = abs(self.inventory)
                    self.avg_entry_price = price if open_qty > 0 else 0.0
                elif self.inventory == 0:
                    self.avg_entry_price = 0.0

        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1

        # Reset position start time if flat
        if self.inventory == 0:
            self.position_start_time = None

        # --- Trailing stop logic ---
        if not hasattr(self, 'highest_price'):
            self.highest_price = None
        if not hasattr(self, 'lowest_price'):
            self.lowest_price = None

        if self.inventory > 0:
            if self.highest_price is None or price > self.highest_price:
                self.highest_price = price
            trailing_stop_pct = self.params.get("trailing_stop_pct", 0.01)
            if price < self.highest_price * (1 - trailing_stop_pct):
                self.logger.info(f"{self.source_name}: Trailing stop hit on long at {price}, closing position.")
                self.reset_inventory()
                self.highest_price = None
                self.lowest_price = None
        elif self.inventory < 0:
            if self.lowest_price is None or price < self.lowest_price:
                self.lowest_price = price
            trailing_stop_pct = self.params.get("trailing_stop_pct", 0.01)
            if price > self.lowest_price * (1 + trailing_stop_pct):
                self.logger.info(f"{self.source_name}: Trailing stop hit on short at {price}, closing position.")
                self.reset_inventory()
                self.highest_price = None
                self.lowest_price = None
        else:
            self.highest_price = None
            self.lowest_price = None

        # --- Per-trade stop loss and take profit logic ---
        stop_loss = self.params.get("per_trade_stop_loss", 100)
        take_profit = self.params.get("per_trade_take_profit", 150)

        if pnl <= -abs(stop_loss):
            self.logger.warning(
                f"Per-trade stop loss triggered: trade PnL={pnl}. Closing position and resetting inventory.")
            self.reset_inventory()
        elif pnl >= abs(take_profit):
            self.logger.info(
                f"Per-trade take profit triggered: trade PnL={pnl}. Closing position and resetting inventory.")
            self.reset_inventory()

        return (self.inventory, self.avg_entry_price, self.realised_pnl, self.total_trades, self.winning_trades)

    def total_pnl(self):
        """
        Total PnL (realised + unrealised).
        """
        return self.realised_pnl + self.unrealised_pnl()

    def get_win_rate(self):
        """
        Calculate win rate as the fraction of winning trades.
        Returns:
            float: Win rate (0.0 to 1.0).
        """
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0

    def reset_inventory(self):
        """
        Reset only the position-related state (inventory, avg_entry_price, position_start_time).
        Do NOT reset realised_pnl or cumulative metrics here.
        """
        self.inventory = 0
        self.avg_entry_price = 0.0
        self.position_start_time = None

    def can_place_order(self):
        """
        Return True if enough time has passed since the last order (cooldown complete).
        """
        now = time.time()
        return (now - self.last_order_time) >= self.min_order_interval

    def get_adaptive_order_size(self, min_size=1, max_size=None, volatility_window=30):
        """
        Returns an order size inversely proportional to recent volatility.
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

    def update_unrealised_pnl_and_drawdown(self):
        """
        Update unrealised PnL and check for drawdown limit breach.
        If drawdown exceeded, enter cooldown period.
        """
        mid_price = self.order_book.get_mid_price()
        if mid_price is None or self.inventory == 0:
            return

        # Calculate current unrealised PnL
        if self.inventory > 0:
            unrealised = (mid_price - self.avg_entry_price) * self.inventory
        else:
            unrealised = (self.avg_entry_price - mid_price) * abs(self.inventory)

        self.max_unrealised_pnl = max(self.max_unrealised_pnl, unrealised)
        drawdown = self.max_unrealised_pnl - unrealised
        if drawdown >= self.drawdown_limit:
            self.logger.warning(f"{self.source_name}: Drawdown limit hit ({drawdown}), entering cooldown.")
            self.cooldown_until = time.time() + self.cooldown_period
            self.max_unrealised_pnl = unrealised  # Reset peak

    def unrealised_pnl(self, mark_price=None):
        """
        Calculate unrealised PnL based on current inventory and market price.
        Args:
            mark_price (float, optional): The price to value the position at. If None, use last price from order book.
        Returns:
            float: Unrealised PnL.
        """
        if mark_price is None:
            mark_price = self.order_book.last_price
        if self.inventory == 0 or mark_price is None:
            return 0.0
        return (mark_price - self.avg_entry_price) * self.inventory
