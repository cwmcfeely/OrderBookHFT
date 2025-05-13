import logging
import time
from datetime import datetime
from collections import deque

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
    def __init__(self, order_book, strategies=None):
        """
        :param order_book: OrderBook instance
        :param strategies: dict mapping source_name -> strategy instance
        """
        self.order_book = order_book
        self.logger = logging.getLogger("MatchingEngine")
        self.logger.propagate = False
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss=-10000,  # Example max daily loss limit
            max_order_rate=100      # Max orders per second
        )
        self.strategies = strategies if strategies else {}

    def calculate_pnl(self, trade):
        """
        Placeholder for PnL calculation.
        Implement your own logic based on position tracking.
        """
        # Example: zero PnL for now
        return 0.0

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

                trade = {
                    "price": level_price,
                    "qty": trade_qty,
                    "maker_id": top_order["id"],
                    "maker_source": top_order["source"],
                    "taker_id": order_id,
                    "taker_source": source,
                    "side": "buy" if side == "buy" or side == "1" else "sell",
                    "source": source,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                trades.append(trade)

                # Record trade price for volatility calculations
                self.order_book.record_trade(level_price)

                # Calculate PnL and record for circuit breaker
                pnl = self.calculate_pnl(trade)
                trade['pnl'] = pnl
                self.circuit_breaker.record_trade(pnl)

                # Notify maker and taker strategies about the trade
                maker_strategy = self.strategies.get(trade['maker_source'])
                taker_strategy = self.strategies.get(trade['taker_source'])
                if maker_strategy and hasattr(maker_strategy, 'on_trade'):
                    maker_strategy.on_trade(trade)
                if taker_strategy and hasattr(taker_strategy, 'on_trade'):
                    taker_strategy.on_trade(trade)

                quantity -= trade_qty
                top_order["qty"] -= trade_qty

                if top_order["qty"] == 0:
                    queue.popleft()

        # Add remaining quantity to order book
        if quantity > 0:
            self.order_book.add_order(side, price, quantity, order_id, source)

        # Log trades with source information
        for trade in trades:
            self.logger.info(
                f"Trade executed: {trade['qty']}@{trade['price']} | "
                f"Maker: {trade['maker_source']} | Taker: {trade['taker_source']}"
            )
            self.order_book.last_price = trade["price"]

        return trades
