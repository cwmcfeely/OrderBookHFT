import simplefix
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logger.propagate = False

class FixEngine:
    def __init__(self, heartbeat_interval=30, log_file="logs/fix_messages.log"):
        self.parser = simplefix.FixParser()
        self.heartbeat_interval = heartbeat_interval
        self.last_heartbeat = time.time()  # Tracks last heartbeat time persistently
        self.seq_num = 1
        self.log_file = Path(log_file).resolve()

        # Ensure directory exists and is writable
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.parent.is_dir():
            raise RuntimeError(f"Directory {self.log_file.parent} not created")

        # Configure logger (single handler per instance)
        self.logger = logging.getLogger(f"FIXEngine_{id(self)}")  # Unique logger per instance
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Prevent propagation to root logger

        # Clear existing handlers (if any)
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Configure file handler with append mode
        file_handler = logging.FileHandler(
            self.log_file,
            encoding="utf-8",
            mode="a"  # Append to avoid overwriting
        )
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(file_handler)

        # Test logging
        self.logger.info("===== FIX ENGINE INITIALIZED =====")
        file_handler.flush()

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
            self._log_message(msg, incoming=False)
            self.seq_num += 1
            return raw_msg
        except Exception as e:
            self.logger.error(f"Heartbeat failed: {str(e)}", exc_info=True)
            raise

    def create_new_order(self, cl_ord_id, symbol, side, price, qty, source):
        """Create FIX NewOrderSingle with full headers and validation"""

        # Validate input types and values
        if not cl_ord_id or not isinstance(cl_ord_id, str):
            raise ValueError("ClOrdID (11) must be a non-empty string")

        if not symbol or not isinstance(symbol, str) or len(symbol) > 8:
            raise ValueError(f"Symbol (55) must be a non-empty string up to 8 characters. Got: {symbol}")

        # Side must be '1' (Buy) or '2' (Sell)
        if str(side) not in {"1", "2"}:
            raise ValueError(f"Side (54) must be '1' (Buy) or '2' (Sell). Got: {side}")

        # Price validation: positive and reasonable upper bound
        try:
            price_val = float(price)
        except Exception:
            raise ValueError(f"Price (44) must be a valid float. Got: {price}")

        if not (0.01 <= price_val <= 1_000_000):
            raise ValueError(f"Price (44) out of valid range [0.01, 1,000,000]: {price_val}")

        # Quantity validation: positive integer and reasonable upper bound
        try:
            qty_val = int(qty)
        except Exception:
            raise ValueError(f"Quantity (38) must be a valid integer. Got: {qty}")

        if not (1 <= qty_val <= 10_000):
            raise ValueError(f"Quantity (38) out of valid range [1, 10,000]: {qty_val}")

        # Construct FIX message
        msg = simplefix.FixMessage()

        # Required FIX headers
        msg.append_pair(8, "FIX.4.4")  # BeginString
        msg.append_pair(49, "MY_COMPANY")  # SenderCompID
        msg.append_pair(56, "EXCHANGE")  # TargetCompID
        msg.append_pair(34, self.seq_num)  # MsgSeqNum

        # Message body
        msg.append_pair(35, "D")  # MsgType (NewOrderSingle)
        msg.append_pair(11, cl_ord_id)  # ClOrdID
        msg.append_pair(55, symbol)  # Symbol
        msg.append_pair(54, str(side))  # Side (1=Buy, 2=Sell)
        msg.append_pair(44, f"{price_val:.8f}")  # Price (formatted with 8 decimals)
        msg.append_pair(38, str(qty_val))  # OrderQty
        msg.append_utc_timestamp(52)  # SendingTime (UTC)
        msg.append_pair(6007, source)  # Custom source tag

        # Log outgoing FIX message
        self._log_message(msg, incoming=False)

        # Increment sequence number for next message
        self.seq_num += 1

        # Return encoded FIX message bytes
        return msg.encode()

    def parse(self, raw_msg):
        """Parse incoming FIX messages with error handling"""
        try:
            self.parser.append_buffer(raw_msg)
            msg = self.parser.get_message()
            if msg:
                self._log_message(msg, incoming=True)
                # Handle sequence number synchronization
                seq_num = msg.get(34)
                if seq_num:
                    self.seq_num = int(seq_num.decode()) + 1
            return msg
        except Exception as e:
            self.logger.error(f"Parse error: {str(e)}", exc_info=True)
            return None

    def _log_message(self, msg, incoming=True):
        """Log FIX message with error handling"""
        direction = "IN" if incoming else "OUT"
        try:
            if isinstance(msg, simplefix.FixMessage):
                raw_bytes = msg.encode()
                raw = raw_bytes.decode().replace('\x01', '|')
            elif isinstance(msg, bytes):
                raw = msg.decode().replace('\x01', '|')
            else:
                raw = str(msg)
            self.logger.info(f"{direction}: {raw}")
            # Force immediate write
            for handler in self.logger.handlers:
                handler.flush()
        except Exception as e:
            self.logger.error(f"Log error: {str(e)}", exc_info=True)

    def is_heartbeat_due(self):
        """Check if heartbeat needs to be sent (with optimized logging)"""
        now = time.time()
        due = (now - self.last_heartbeat) >= self.heartbeat_interval
        if due:
            self.logger.debug("Heartbeat due after %.1fs (interval=%ds)",
                              now - self.last_heartbeat, self.heartbeat_interval)
        return due

    def update_heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()
        self.logger.debug("Heartbeat timestamp updated")
