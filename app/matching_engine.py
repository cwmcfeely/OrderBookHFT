import logging
import time
import uuid
from datetime import datetime

logger = logging.getLogger("MatchingEngine")
logger.propagate = False

class TradingHalted(Exception):
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

def decode_if_bytes(val):
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='replace')
    return val

class MatchingEngine:
    def __init__(self, order_book, strategies=None, trading_state=None, state_lock=None):
        self.order_book = order_book
        self.logger = logging.getLogger("MatchingEngine")
        self.logger.propagate = False
        self.circuit_breaker = CircuitBreaker(
            max_daily_loss=-10000,
            max_order_rate=100
        )
        self.strategies = strategies if strategies else {}
        self.trading_state = trading_state
        self.state_lock = state_lock

    def calculate_pnl(self, trade):
        maker_source = trade['maker_source']
        strategy = self.strategies.get(maker_source)
        if strategy is None:
            return 0.0
        qty = trade['qty']
        price = trade['price']
        side = trade['side']
        position = getattr(strategy, 'inventory', 0)
        avg_price = getattr(strategy, 'avg_entry_price', 0.0)
        realized_pnl = 0.0
        if side == 'buy' or side == "1":
            new_position = position + qty
            if position >= 0:
                avg_price = (avg_price * position + price * qty) / new_position if new_position != 0 else price
            else:
                close_qty = min(abs(position), qty)
                realized_pnl = close_qty * (avg_price - price)
                if qty > close_qty:
                    avg_price = price
            position = new_position
        else:
            new_position = position - qty
            if position <= 0:
                avg_price = (avg_price * abs(position) + price * qty) / abs(new_position) if new_position != 0 else price
            else:
                close_qty = min(position, qty)
                realized_pnl = close_qty * (price - avg_price)
                if qty > close_qty:
                    avg_price = price
            position = new_position
        strategy.inventory = position
        strategy.avg_entry_price = avg_price
        strategy.realized_pnl = getattr(strategy, 'realized_pnl', 0.0) + realized_pnl
        return realized_pnl

    def create_execution_report(self, fix_engine, cl_ord_id, order_id, exec_id, ord_status, exec_type, symbol, side, order_qty,
                               last_qty=None, last_px=None, leaves_qty=None, cum_qty=None, price=None, source=None, strategy_name=None):
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

        # --- Append to trading_state for API/UI ---
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
                self.order_book.record_trade(level_price)

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
                        source=trade['maker_source'],
                        strategy_name=maker_strategy.source_name
                    )
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

                # Latency history for analytics
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
                            if len(latency_list) > 500:
                                latency_list.pop(0)

                quantity -= trade_qty
                top_order["qty"] -= trade_qty
                if top_order["qty"] == 0:
                    queue.popleft()

        if quantity > 0:
            self.order_book.add_order(side, price, quantity, order_id, source)

        for trade in trades:
            latency_info = f" | Latency: {trade['latency_ms']:.2f} ms" if trade['latency_ms'] is not None else ""
            self.logger.info(
                f"Trade executed: {trade['qty']}@{trade['price']} | "
                f"Maker: {trade['maker_source']} | Taker: {trade['taker_source']}{latency_info}"
            )
            self.order_book.last_price = trade["price"]

        return trades
