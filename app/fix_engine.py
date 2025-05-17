import simplefix
import time
import logging

class FixEngine:
    def __init__(self, symbol=None, heartbeat_interval=30):
        self.parser = simplefix.FixParser()
        self.heartbeat_interval = heartbeat_interval
        self.last_heartbeat = time.time()
        self.seq_num = 1
        self.symbol = symbol  # Symbol string, e.g. "ASML.AS" or None

        # Updated loggers
        self.server_logger = logging.getLogger("FIXServer")
        # For per-strategy logs: use the strategy name as symbol (e.g., "my_strategy")
        self.strategy_logger = logging.getLogger(f"FIX_{self.symbol}") if self.symbol else None

        # Test logging
        self.server_logger.info("===== FIX ENGINE INITIALIZED =====")
        if self.strategy_logger:
            self.strategy_logger.info("===== FIX ENGINE INITIALIZED FOR SYMBOL %s =====", self.symbol)

    def create_heartbeat(self):
        """Generate and log FIX heartbeat (MsgType=0)"""
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(49, "MY_COMPANY")
        msg.append_pair(56, "EXCHANGE")
        msg.append_pair(34, self.seq_num)
        msg.append_pair(35, "0")  # Heartbeat
        msg.append_utc_timestamp(52)
        try:
            raw_msg = msg.encode()
            self._log_heartbeat(msg, incoming=False)
            self.seq_num += 1
            return raw_msg
        except Exception as e:
            self.server_logger.error(f"Heartbeat failed: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(f"Heartbeat failed: {str(e)}", exc_info=True)
            raise

    def create_new_order(self, cl_ord_id, symbol, side, price, qty, source):
        """Create FIX NewOrderSingle with full headers and validation"""
        if not cl_ord_id or not isinstance(cl_ord_id, str):
            raise ValueError("ClOrdID (11) must be a non-empty string")
        if not symbol or not isinstance(symbol, str) or len(symbol) > 8:
            raise ValueError(f"Symbol (55) must be a non-empty string up to 8 characters. Got: {symbol}")
        if str(side) not in {"1", "2"}:
            raise ValueError(f"Side (54) must be '1' (Buy) or '2' (Sell). Got: {side}")
        try:
            price_val = float(price)
        except Exception:
            raise ValueError(f"Price (44) must be a valid float. Got: {price}")
        if not (0.01 <= price_val <= 1_000_000):
            raise ValueError(f"Price (44) out of valid range [0.01, 1,000,000]: {price_val}")
        try:
            qty_val = int(qty)
        except Exception:
            raise ValueError(f"Quantity (38) must be a valid integer. Got: {qty}")
        if not (1 <= qty_val <= 10_000):
            raise ValueError(f"Quantity (38) out of valid range [1, 10,000]: {qty_val}")

        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(49, "MY_COMPANY")
        msg.append_pair(56, "EXCHANGE")
        msg.append_pair(34, self.seq_num)
        msg.append_pair(35, "D")  # NewOrderSingle
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(55, symbol)
        msg.append_pair(54, str(side))
        msg.append_pair(44, f"{price_val:.8f}")
        msg.append_pair(38, str(qty_val))
        msg.append_utc_timestamp(52)
        msg.append_pair(6007, source)

        self._log_fix_message(msg, incoming=False)
        self.seq_num += 1
        return msg.encode()

    def parse(self, raw_msg):
        """Parse incoming FIX messages"""
        try:
            self.parser.append_buffer(raw_msg)
            msg = self.parser.get_message()
            if msg:
                self._log_fix_message(msg, incoming=True)
                seq_num = msg.get(34)
                if seq_num:
                    self.seq_num = int(seq_num.decode()) + 1
                return msg
        except Exception as e:
            self.server_logger.error(f"Parse error: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(f"Parse error: {str(e)}", exc_info=True)
            return None

    def _log_heartbeat(self, msg, incoming=True):
        """Log heartbeat messages to both FIXServer and strategy logger if available"""
        direction = "HEARTBEAT RECEIVED" if incoming else "HEARBEAT SENT"
        try:
            raw = msg.encode().decode(errors='replace').replace('\x01', '|')
            self.server_logger.info(f"{direction}: {raw}")
            if self.strategy_logger:
                self.strategy_logger.info(f"{direction}: {raw}")
        except Exception as e:
            self.server_logger.error(f"Heartbeat log error: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(f"Heartbeat log error: {str(e)}", exc_info=True)

    def _log_fix_message(self, msg, incoming=True):
        """Log non-heartbeat FIX messages to strategy-specific logger"""
        direction = "IN" if incoming else "OUT"
        try:
            if isinstance(msg, simplefix.FixMessage):
                raw = msg.encode().decode(errors='replace').replace('\x01', '|')
            elif isinstance(msg, bytes):
                raw = msg.decode(errors='replace').replace('\x01', '|')
            else:
                raw = str(msg)

            if self.strategy_logger:
                self.strategy_logger.info(f"{direction}: {raw}")
            else:
                # Fallback to FIXServer logger if no strategy logger
                self.server_logger.info(f"{direction}: {raw}")
        except Exception as e:
            if self.strategy_logger:
                self.strategy_logger.error(f"FIX message log error: {str(e)}", exc_info=True)
            else:
                self.server_logger.error(f"FIX message log error: {str(e)}", exc_info=True)

    def is_heartbeat_due(self):
        now = time.time()
        due = (now - self.last_heartbeat) >= self.heartbeat_interval
        if due:
            self.server_logger.debug(
                f"Heartbeat due after {now - self.last_heartbeat:.1f}s (interval={self.heartbeat_interval}s)"
            )
            if self.strategy_logger:
                self.strategy_logger.debug(
                    f"Heartbeat due after {now - self.last_heartbeat:.1f}s (interval={self.heartbeat_interval}s)"
                )
        return due

    def create_execution_report(self, cl_ord_id, order_id, exec_id, ord_status, exec_type, symbol, side, order_qty,
                               last_qty=None, last_px=None, leaves_qty=None, cum_qty=None, price=None, source=None):
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")
        msg.append_pair(49, "EXCHANGE")
        msg.append_pair(56, "MY_COMPANY")
        msg.append_pair(34, self.seq_num)
        msg.append_pair(35, "8")  # ExecutionReport
        msg.append_pair(11, cl_ord_id)
        msg.append_pair(37, order_id)
        msg.append_pair(17, exec_id)
        msg.append_pair(39, ord_status)
        msg.append_pair(150, exec_type)
        msg.append_pair(55, symbol)
        msg.append_pair(54, side)
        msg.append_pair(38, str(order_qty))
        if last_qty is not None:
            msg.append_pair(32, str(last_qty))
        if last_px is not None:
            msg.append_pair(31, f"{last_px:.8f}")
        if leaves_qty is not None:
            msg.append_pair(151, str(leaves_qty))
        if cum_qty is not None:
            msg.append_pair(14, str(cum_qty))
        if price is not None:
            msg.append_pair(44, f"{price:.8f}")
        if source:
            msg.append_pair(6007, source)
        msg.append_utc_timestamp(52)

        self._log_fix_message(msg, incoming=False)
        self.seq_num += 1
        return msg.encode()

    def update_heartbeat(self):
        self.last_heartbeat = time.time()
        self.server_logger.debug("Heartbeat timestamp updated")
        if self.strategy_logger:
            self.strategy_logger.debug("Heartbeat timestamp updated")
