import logging
import time
import uuid
import asyncio
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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
        self.daily_loss = 0.0  # Tracks cumulative realised PnL for the day
        self.order_count = 0  # Number of orders processed today
        self.last_reset_time = time.time()  # Timestamp of last daily reset

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
            max_order_rate=1000
        )

        self.strategies = strategies if strategies else {}  # Mapping of strategy name to strategy instance
        self.trading_state = trading_state  # Shared trading state for analytics and UI
        self.state_lock = state_lock  # Lock for thread-safe state updates

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

        if side == 'buy' or side == "1":
            new_position = position + qty
            if position >= 0:
                avg_price = (avg_price * position + price * qty) / new_position if new_position != 0 else price
            else:
                close_qty = min(abs(position), qty)
                realised_pnl = close_qty * (avg_price - price)
                if qty > close_qty:
                    avg_price = price
            position = new_position
        else:
            new_position = position - qty
            if position <= 0:
                avg_price = (avg_price * abs(position) + price * qty) / abs(new_position) if new_position != 0 else price
            else:
                close_qty = min(position, qty)
                realised_pnl = close_qty * (price - avg_price)
                if qty > close_qty:
                    avg_price = price
            position = new_position

        strategy.inventory = position
        strategy.avg_entry_price = avg_price
        strategy.realised_pnl = getattr(strategy, 'realised_pnl', 0.0) + realised_pnl

        return realised_pnl

    def create_execution_report(self, fix_engine, cl_ord_id, order_id, exec_id, ord_status, exec_type, symbol, side, order_qty,
                                 last_qty=None, last_px=None, leaves_qty=None, cum_qty=None, price=None, source=None, strategy_name=None):
        """
        Create and log a FIX execution report, and append it to the trading state for UI/API.
        """
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

        if strategy_name:
            exec_logger = logging.getLogger(f"ExecReport_{strategy_name}")
            if isinstance(msg, bytes):
                fix_str = msg.decode(errors='replace').replace('\x01', '|')
            else:
                fix_str = str(msg)
            exec_logger.info(f"ExecutionReport: {fix_str}")

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
        if not self.circuit_breaker.allow_execution():
            self.logger.error("Circuit breaker triggered: halting trading")
            raise TradingHalted("Circuit breaker triggered")
        new_submission_time = time.time_ns()
        book = self.order_book.asks if side == "buy" else self.order_book.bids
        trades = []
        levels = sorted(book.keys()) if side == "buy" else sorted(book.keys(), reverse=True)
        for level_price in levels:
            if (side == "buy" and level_price > price) or (side == "sell" and level_price < price):
                break
            queue = book[level_price]
            max_attempts = len(queue)
            attempts = 0
            while queue and quantity > 0 and attempts < max_attempts:
                top_order = queue[0]
                # Self-Trade Prevention: skip if maker and taker are the same
                if top_order["source"] == source:
                    queue.rotate(-1)  # Move this order to the end of the queue
                    attempts += 1
                    continue
                trade_qty = min(quantity, top_order["qty"])
                order_time = top_order.get("order_time", None)
                current_time = time.time()
                latency_ms = (current_time - order_time) * 1000 if order_time else None
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
                pnl = self.calculate_pnl(trade)
                trade['pnl'] = pnl
                self.circuit_breaker.record_trade(pnl)
                trades.append(trade)
                maker_strategy = self.strategies.get(trade['maker_source'])
                taker_strategy = self.strategies.get(trade['taker_source'])

                symbol = self.order_book.symbol

                if maker_strategy and hasattr(maker_strategy, "logger"):
                    maker_strategy.logger.info(
                        f"WIN: {maker_strategy.source_name} filled as maker at {level_price} for {trade_qty} on {symbol} against {source}"
                    )
                if taker_strategy and hasattr(taker_strategy, "logger"):
                    taker_strategy.logger.info(
                        f"LOSS: {taker_strategy.source_name} lost maker priority at {level_price} for {trade_qty} on {symbol} to {top_order['source']}"
                    )

                if maker_strategy:
                    exec_id = str(uuid.uuid4())
                    fix_engine = maker_strategy.fix_engine

                    # Get original order quantity
                    original_qty = top_order.get("original_qty", top_order["qty"] + trade_qty)
                    leaves_qty = top_order["qty"] - trade_qty
                    if leaves_qty < 0:
                        leaves_qty = 0
                    cum_qty = original_qty - leaves_qty

                    # Determine partial/full fill status
                    if leaves_qty > 0:
                        ord_status = "1"  # Partially Filled
                        exec_type = "1"  # Partial Fill
                    else:
                        ord_status = "2"  # Filled
                        exec_type = "F"  # Fil

                    self.create_execution_report(
                        fix_engine=fix_engine,
                        cl_ord_id=top_order["id"],
                        order_id=top_order["id"],
                        exec_id=exec_id,
                        ord_status=ord_status,
                        exec_type=exec_type,
                        symbol=self.order_book.symbol,
                        side="1" if trade['side'] == "buy" else "2",
                        order_qty=original_qty,
                        last_qty=trade_qty,
                        last_px=level_price,
                        leaves_qty=leaves_qty,
                        cum_qty=cum_qty,
                        price=level_price,
                        source=trade['maker_source'],
                        strategy_name=maker_strategy.source_name
                    )
                    if hasattr(maker_strategy, 'on_execution_report'):
                        maker_strategy.on_execution_report(trade)
                    if hasattr(maker_strategy, 'on_trade'):
                        maker_strategy.on_trade(trade)

                if taker_strategy:
                    exec_id = str(uuid.uuid4())
                    fix_engine = taker_strategy.fix_engine

                    # For the taker, original_qty is the total quantity they submitted (track this if needed)
                    # Here, we use the trade_qty for this fill, but you may want to track cumulative fills
                    leaves_qty = quantity - trade_qty
                    if leaves_qty < 0:
                        leaves_qty = 0
                    cum_qty = (quantity + trade_qty) - leaves_qty

                    ord_status = "1" if leaves_qty > 0 else "2"
                    exec_type = "1" if leaves_qty > 0 else "F"

                    self.create_execution_report(
                        fix_engine=fix_engine,
                        cl_ord_id=order_id,
                        order_id=order_id,
                        exec_id=exec_id,
                        ord_status=ord_status,
                        exec_type=exec_type,
                        symbol=self.order_book.symbol,
                        side="1" if trade['side'] == "buy" else "2",
                        order_qty=quantity + trade_qty,  # Or track the taker's original order size
                        last_qty=trade_qty,
                        last_px=level_price,
                        leaves_qty=leaves_qty,
                        cum_qty=cum_qty,
                        price=level_price,
                        source=trade['taker_source'],
                        strategy_name=taker_strategy.source_name
                    )
                    if hasattr(taker_strategy, 'on_execution_report'):
                        taker_strategy.on_execution_report(trade)
                    if hasattr(taker_strategy, 'on_trade'):
                        taker_strategy.on_trade(trade)

                if self.trading_state is not None and self.state_lock is not None:
                    symbol = self.order_book.symbol
                    if latency_ms is not None:
                        with self.state_lock:
                            latency_list = self.trading_state.setdefault('latency_history', {}).setdefault(symbol, [])
                            latency_list.append({
                                "time": trade["time"],
                                "latency_ms": latency_ms,
                                "strategy": trade["maker_source"],
                                "type": "maker"
                            })

                    taker_latency = (time.time_ns() - new_submission_time) / 1e6
                    latency_list.append({
                        "time": trade["time"],
                        "latency_ms": taker_latency,
                        "strategy": trade["taker_source"],
                        "type": "taker"
                    })
                    if len(latency_list) > 500:
                        latency_list = latency_list[-500:]

                quantity -= trade_qty
                top_order["qty"] -= trade_qty
                if top_order["qty"] == 0:
                    queue.popleft()

                if quantity > 0:
                    self.order_book.add_order(side, price, quantity, order_id, source)

            # After max_attempts, break to avoid infinite loop if all orders at this level are from self
        for trade in trades:
            latency_info = f" | Latency: {trade['latency_ms']:.2f} ms" if trade['latency_ms'] is not None else ""
            self.logger.info(
                f"Trade executed: {trade['qty']}@{trade['price']} | "
                f"Maker: {trade['maker_source']} | Taker: {trade['taker_source']}{latency_info}"
            )
        self.order_book.last_price = trade["price"] if trades else None
        return trades


class AsyncMatchingEngine(MatchingEngine):
    """
    Extends MatchingEngine with asynchronous processing capabilities.
    Implements thread-safe order matching and competition logging.
    """
    def __init__(self, order_book, strategies=None, trading_state=None, state_lock=None):
        super().__init__(order_book, strategies, trading_state, state_lock)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.order_lock = threading.Lock()
        self.competition_logs = []

    async def process_order_async(self, side, price, quantity, order_id, source):
        with self.order_lock:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.executor,
                self.match_order,
                side, price, quantity, order_id, source
            )
