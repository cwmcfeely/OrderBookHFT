import logging
import time
import uuid
from datetime import datetime

# Set up a logger specifically for the matching engine
logger = logging.getLogger("MatchingEngine")
logger.propagate = False  # Prevent duplicate log entries from propagation

class TradingHalted(Exception):
    """Custom exception to indicate trading is halted, e.g. by a circuit breaker."""
    pass

class CircuitBreaker:
    """
    Implements basic circuit breaker logic for risk management:
    - Halts trading if daily loss exceeds a threshold or order rate is too high.
    """
    def __init__(self, max_daily_loss, max_order_rate):
        self.max_daily_loss = max_daily_loss  # Maximum allowable loss per day (negative value)
        self.max_order_rate = max_order_rate  # Maximum number of orders allowed per day
        self.daily_loss = 0.0                 # Tracks cumulative realised PnL for the day
        self.order_count = 0                  # Number of orders processed today
        self.last_reset_time = time.time()    # Timestamp of last daily reset

    def allow_execution(self):
        """
        Check if trading is allowed under the circuit breaker rules.
        Resets counters if a new day has started.

        Returns:
            bool: True if trading is allowed, False if halted.
        """
        current_time = time.time()
        # Reset daily counters if more than 24 hours have passed
        if current_time - self.last_reset_time > 86400:
            self.daily_loss = 0.0
            self.order_count = 0
            self.last_reset_time = current_time
        # If daily loss limit is breached, halt trading
        if self.daily_loss <= self.max_daily_loss:
            return False
        # If order rate limit is breached, halt trading
        if self.order_count >= self.max_order_rate:
            return False
        return True

    def record_trade(self, pnl):
        """
        Update the circuit breaker state after a trade.

        Args:
            pnl (float): Realised profit or loss from the trade.
        """
        self.daily_loss += pnl
        self.order_count += 1

def decode_if_bytes(val):
    """
    Helper function to decode bytes to string for logging or storage.

    Args:
        val (bytes or any): Value to decode.

    Returns:
        str or original type: Decoded string if bytes, else original value.
    """
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='replace')
    return val

class MatchingEngine:
    """
    Core class for matching incoming orders against the order book,
    handling trade execution, PnL calculation, and risk controls.
    """
    def __init__(self, order_book, strategies=None, trading_state=None, state_lock=None):
        self.order_book = order_book  # Reference to the order book object
        self.logger = logging.getLogger("MatchingEngine")
        self.logger.propagate = False
        # Circuit breaker for risk management (limits daily loss and order rate)
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss=-10000,
            max_order_rate=100
        )
        self.strategies = strategies if strategies else {}  # Mapping of strategy name to strategy instance
        self.trading_state = trading_state  # Shared trading state for analytics and UI
        self.state_lock = state_lock        # Lock for thread-safe state updates

    def calculate_pnl(self, trade):
        """
        Calculate and update realised PnL for the maker strategy involved in a trade.

        Args:
            trade (dict): Trade details including maker, price, qty, and side.

        Returns:
            float: Realised PnL for this trade.
        """
        maker_source = trade['maker_source']
        strategy = self.strategies.get(maker_source)
        if strategy is None:
            return 0.0
        qty = trade['qty']
        price = trade['price']
        side = trade['side']
        position = getattr(strategy, 'inventory', 0)
        avg_price = getattr(strategy, 'avg_entry_price', 0.0)
        realised_pnl = 0.0

        # Update inventory and average entry price based on side and quantity
        if side == 'buy' or side == "1":
            new_position = position + qty
            if position >= 0:
                # Increasing or opening long position
                avg_price = (avg_price * position + price * qty) / new_position if new_position != 0 else price
            else:
                # Closing short position
                close_qty = min(abs(position), qty)
                realised_pnl = close_qty * (avg_price - price)
                if qty > close_qty:
                    avg_price = price
            position = new_position
        else:
            new_position = position - qty
            if position <= 0:
                # Increasing or opening short position
                avg_price = (avg_price * abs(position) + price * qty) / abs(new_position) if new_position != 0 else price
            else:
                # Closing long position
                close_qty = min(position, qty)
                realised_pnl = close_qty * (price - avg_price)
                if qty > close_qty:
                    avg_price = price
            position = new_position

        # Update strategy state
        strategy.inventory = position
        strategy.avg_entry_price = avg_price
        strategy.realised_pnl = getattr(strategy, 'realised_pnl', 0.0) + realised_pnl
        return realised_pnl

    def create_execution_report(self, fix_engine, cl_ord_id, order_id, exec_id, ord_status, exec_type, symbol, side, order_qty,
                               last_qty=None, last_px=None, leaves_qty=None, cum_qty=None, price=None, source=None, strategy_name=None):
        """
        Create and log a FIX execution report, and append it to the trading state for UI/API.

        Args:
            fix_engine: The FIX engine instance to use for message creation.
            cl_ord_id, order_id, exec_id, ...: Standard FIX fields.
            strategy_name (str, optional): Name of the strategy for logging.
        """
        # Generate the FIX execution report message
        msg = fix_engine.create_execution_report(
            cl_ord_id=cl_ord_id,
            order_id=order_id,
            exec_id=exec_id,
            ord_status=ord_status,
            exec_type=exec_type,
            symbol=symbol,
            side=side,
            order_qty=order_qty,
            last_qty=last_qty,
            last_px=last_px,
            leaves_qty=leaves_qty,
            cum_qty=cum_qty,
            price=price,
            source=source
        )
        # Log the execution report if a strategy name is provided
        if strategy_name:
            exec_logger = logging.getLogger(f"ExecReport_{strategy_name}")
            if isinstance(msg, bytes):
                fix_str = msg.decode(errors='replace').replace('\x01', '|')
            else:
                fix_str = str(msg)
            exec_logger.info(f"ExecutionReport: {fix_str}")

        # Append the execution report to the trading state for analytics/UI
        if self.trading_state is not None and self.state_lock is not None:
            with self.state_lock:
                exec_reports = self.trading_state.setdefault("execution_reports", {}).setdefault(symbol, [])
                exec_reports.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "cl_ord_id": decode_if_bytes(cl_ord_id),
                    "order_id": decode_if_bytes(order_id),
                    "exec_id": decode_if_bytes(exec_id),
                    "ord_status": decode_if_bytes(ord_status),
                    "exec_type": decode_if_bytes(exec_type),
                    "symbol": decode_if_bytes(symbol),
                    "side": decode_if_bytes(side),
                    "order_qty": order_qty,
                    "last_qty": last_qty,
                    "last_px": last_px,
                    "leaves_qty": leaves_qty,
                    "cum_qty": cum_qty,
                    "price": price,
                    "source": decode_if_bytes(source)
                })
                # Keep the execution report history to a manageable size
                if len(exec_reports) > 500:
                    exec_reports.pop(0)

    def match_order(self, side, price, quantity, order_id, source):
        """
        Attempt to match a new incoming order against the order book.

        Args:
            side (str): "buy" or "sell"
            price (float): Limit price of the incoming order
            quantity (int): Quantity to match
            order_id (str): Unique order identifier
            source (str): Source/strategy that submitted the order

        Returns:
            list: List of executed trades (each as a dict)
        """
        # Check circuit breaker before proceeding
        if not self.circuit_breaker.allow_execution():
            self.logger.error("Circuit breaker triggered: halting trading")
            raise TradingHalted("Circuit breaker triggered")

        # Capture submission time when order enters matching engine
        new_submission_time = time.time_ns()


        # Select the opposing side of the book for matching
        book = self.order_book.asks if side == "buy" else self.order_book.bids
        trades = []
        # Sort price levels: ascending for buys, descending for sells
        levels = sorted(book.keys()) if side == "buy" else sorted(book.keys(), reverse=True)

        for level_price in levels:
            # Stop if the price is not marketable
            if (side == "buy" and level_price > price) or (side == "sell" and level_price < price):
                break

            queue = book[level_price]
            while queue and quantity > 0:
                top_order = queue[0]
                trade_qty = min(quantity, top_order["qty"])
                order_time = top_order.get("order_time", None)
                current_time = time.time()
                latency_ms = (current_time - order_time) * 1000 if order_time else None

                # Construct the trade record
                trade = {
                    "price": level_price,
                    "qty": trade_qty,
                    "maker_id": top_order["id"],
                    "maker_source": top_order["source"],
                    "taker_id": order_id,
                    "taker_source": source,
                    "side": "buy" if side == "buy" or side == "1" else "sell",
                    "source": source,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "latency_ms": latency_ms
                }

                # Calculate and record PnL, update circuit breaker state
                pnl = self.calculate_pnl(trade)
                trade['pnl'] = pnl
                self.circuit_breaker.record_trade(pnl)
                trades.append(trade)
                self.order_book.record_trade(level_price)

                # Retrieve maker and taker strategy objects if available
                maker_strategy = self.strategies.get(trade['maker_source'])
                taker_strategy = self.strategies.get(trade['taker_source'])

                # --- Execution Report for Maker ---
                if maker_strategy:
                    exec_id = str(uuid.uuid4())
                    fix_engine = maker_strategy.fix_engine
                    self.create_execution_report(
                        fix_engine=fix_engine,
                        cl_ord_id=top_order["id"],
                        order_id=top_order["id"],
                        exec_id=exec_id,
                        ord_status="2",         # OrdStatus: Filled
                        exec_type="F",          # ExecType: Trade
                        symbol=self.order_book.symbol,
                        side="1" if trade['side'] == "buy" else "2",
                        order_qty=trade_qty,
                        last_qty=trade_qty,
                        last_px=level_price,
                        leaves_qty=0,
                        cum_qty=trade_qty,
                        price=level_price,
                        source=trade['maker_source'],
                        strategy_name=maker_strategy.source_name
                    )
                    # Notify strategy of execution/trade if callback methods exist
                    if hasattr(maker_strategy, 'on_execution_report'):
                        maker_strategy.on_execution_report(trade)
                    if hasattr(maker_strategy, 'on_trade'):
                        maker_strategy.on_trade(trade)

                # --- Execution Report for Taker ---
                if taker_strategy:
                    exec_id = str(uuid.uuid4())
                    fix_engine = taker_strategy.fix_engine
                    self.create_execution_report(
                        fix_engine=fix_engine,
                        cl_ord_id=order_id,
                        order_id=order_id,
                        exec_id=exec_id,
                        ord_status="2",
                        exec_type="F",
                        symbol=self.order_book.symbol,
                        side="1" if trade['side'] == "buy" else "2",
                        order_qty=trade_qty,
                        last_qty=trade_qty,
                        last_px=level_price,
                        leaves_qty=0,
                        cum_qty=trade_qty,
                        price=level_price,
                        source=trade['taker_source'],
                        strategy_name=taker_strategy.source_name
                    )
                    if hasattr(taker_strategy, 'on_execution_report'):
                        taker_strategy.on_execution_report(trade)
                    if hasattr(taker_strategy, 'on_trade'):
                        taker_strategy.on_trade(trade)

                # Record latency for analytics if trading_state is available
                # Record MAKER latency
                if self.trading_state is not None and self.state_lock is not None:
                    symbol = self.order_book.symbol
                    if latency_ms is not None:
                        with self.state_lock:
                            latency_list = self.trading_state.setdefault('latency_history', {}).setdefault(symbol, [])
                            latency_list.append({
                                "time": trade["time"],
                                "latency_ms": latency_ms,
                                "strategy": trade["maker_source"],
                                "type": "maker"  # Identify as maker latency
                            })

                            # ALSO record TAKER latency
                            taker_latency = (time.time_ns() - new_submission_time) / 1e6  # Convert ns to ms
                            latency_list.append({
                                "time": trade["time"],
                                "latency_ms": taker_latency,
                                "strategy": trade["taker_source"],  # Add taker source
                                "type": "taker"  # Identify as taker latency
                            })

                            # Keep latency history to a manageable size
                            if len(latency_list) > 500:
                                latency_list = latency_list[-500:]  # Keep most recent 500

                # Update remaining quantity for this match
                quantity -= trade_qty
                top_order["qty"] -= trade_qty
                if top_order["qty"] == 0:
                    queue.popleft()  # Remove fully filled order from the book

        # If there is any remaining quantity, add it to the order book as a new order
        if quantity > 0:
            self.order_book.add_order(side, price, quantity, order_id, source)

        # Log all executed trades and update the last traded price
        for trade in trades:
            latency_info = f" | Latency: {trade['latency_ms']:.2f} ms" if trade['latency_ms'] is not None else ""
            self.logger.info(
                f"Trade executed: {trade['qty']}@{trade['price']} | "
                f"Maker: {trade['maker_source']} | Taker: {trade['taker_source']}{latency_info}"
            )
            self.order_book.last_price = trade["price"]

        return trades
