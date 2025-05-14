import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)
logger.propagate = False

class TradingHalted(Exception):
    """Exception raised when trading is halted by the circuit breaker."""
    pass

class CircuitBreaker:
    def __init__(self, max_daily_loss, max_order_rate):
        self.max_daily_loss = max_daily_loss
        self.max_order_rate = max_order_rate
        self.daily_loss = 0.0
        self.order_count = 0
        self.last_reset_time = time.time()

    def allow_execution(self):
        current_time = time.time()
        # Reset daily counters every 24 hours
        if current_time - self.last_reset_time > 86400:
            self.daily_loss = 0.0
            self.order_count = 0
            self.last_reset_time = current_time

        if self.daily_loss <= self.max_daily_loss:
            return False
        if self.order_count >= self.max_order_rate:
            return False
        return True

    def record_trade(self, pnl):
        self.daily_loss += pnl
        self.order_count += 1


class MatchingEngine:
    def __init__(self, order_book, strategies=None, trading_state=None, state_lock=None):
        """
        :param order_book: OrderBook instance
        :param strategies: dict mapping source_name -> strategy instance
        :param trading_state: dict for global state tracking (must contain 'latency_history')
        :param state_lock: threading.Lock() to protect shared state
        """
        self.order_book = order_book
        self.logger = logging.getLogger("MatchingEngine")
        self.logger.propagate = False
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss=-10000,  # Example max daily loss limit
            max_order_rate=100      # Max orders per second
        )
        self.strategies = strategies if strategies else {}
        self.trading_state = trading_state
        self.state_lock = state_lock

    def calculate_pnl(self, trade):
        """
        Calculate realized PnL for the maker strategy based on the trade.
        This updates the strategy's position and realized PnL.

        :param trade: dict with keys including 'qty', 'price', 'maker_source', 'side'
        :return: realized PnL for this trade
        """
        maker_source = trade['maker_source']
        strategy = self.strategies.get(maker_source)
        if strategy is None:
            return 0.0  # No strategy found, no PnL update

        qty = trade['qty']
        price = trade['price']
        side = trade['side']

        # Use position and avg_entry_price from strategy
        position = getattr(strategy, 'inventory', 0)
        avg_price = getattr(strategy, 'avg_entry_price', 0.0)
        realized_pnl = 0.0

        if side == 'buy' or side == "1":
            new_position = position + qty
            if position >= 0:
                # Increasing long position: update average price
                avg_price = (avg_price * position + price * qty) / new_position if new_position != 0 else price
            else:
                # Closing short position: realize PnL
                close_qty = min(abs(position), qty)
                realized_pnl = close_qty * (avg_price - price)
                if qty > close_qty:
                    avg_price = price
            position = new_position
        else:
            new_position = position - qty
            if position <= 0:
                # Increasing short position: update average price
                avg_price = (avg_price * abs(position) + price * qty) / abs(new_position) if new_position != 0 else price
            else:
                # Closing long position: realize PnL
                close_qty = min(position, qty)
                realized_pnl = close_qty * (price - avg_price)
                if qty > close_qty:
                    avg_price = price
            position = new_position

        # Update strategy attributes
        strategy.inventory = position
        strategy.avg_entry_price = avg_price
        strategy.realized_pnl = getattr(strategy, 'realized_pnl', 0.0) + realized_pnl

        return realized_pnl

    def match_order(self, side, price, quantity, order_id, source):
        if not self.circuit_breaker.allow_execution():
            self.logger.error("Circuit breaker triggered: halting trading")
            raise TradingHalted("Circuit breaker triggered")

        book = self.order_book.asks if side == "buy" else self.order_book.bids
        trades = []

        levels = sorted(book.keys()) if side == "buy" else sorted(book.keys(), reverse=True)

        for level_price in levels:
            if (side == "buy" and level_price > price) or (side == "sell" and level_price < price):
                break

            queue = book[level_price]
            while queue and quantity > 0:
                top_order = queue[0]
                trade_qty = min(quantity, top_order["qty"])

                # Calculate latency if order_time is available
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
                    "latency_ms": latency_ms  # Add latency in milliseconds
                }

                # Calculate PnL and record for circuit breaker
                pnl = self.calculate_pnl(trade)
                trade['pnl'] = pnl
                self.circuit_breaker.record_trade(pnl)

                trades.append(trade)

                # Record trade price for volatility calculations
                self.order_book.record_trade(level_price)

                # Notify maker and taker strategies about the trade
                maker_strategy = self.strategies.get(trade['maker_source'])
                taker_strategy = self.strategies.get(trade['taker_source'])
                if maker_strategy and hasattr(maker_strategy, 'on_trade'):
                    maker_strategy.on_trade(trade)
                if taker_strategy and hasattr(taker_strategy, 'on_trade'):
                    taker_strategy.on_trade(trade)

                # Append latency info to global trading_state for visualization
                if self.trading_state is not None and self.state_lock is not None:
                    symbol = self.order_book.symbol
                    if latency_ms is not None:
                        with self.state_lock:
                            latency_list = self.trading_state.setdefault('latency_history', {}).setdefault(symbol, [])
                            latency_list.append({
                                "time": trade["time"],
                                "latency_ms": latency_ms,
                                "strategy": trade["maker_source"]
                            })
                            # Limit history size to last 500 entries
                            if len(latency_list) > 500:
                                latency_list.pop(0)

                quantity -= trade_qty
                top_order["qty"] -= trade_qty

                if top_order["qty"] == 0:
                    queue.popleft()

        # Add remaining quantity to order book
        if quantity > 0:
            self.order_book.add_order(side, price, quantity, order_id, source)

        # Log trades with source information and latency if available
        for trade in trades:
            latency_info = f" | Latency: {trade['latency_ms']:.2f} ms" if trade['latency_ms'] is not None else ""
            self.logger.info(
                f"Trade executed: {trade['qty']}@{trade['price']} | "
                f"Maker: {trade['maker_source']} | Taker: {trade['taker_source']}{latency_info}"
            )
            self.order_book.last_price = trade["price"]

        return trades
