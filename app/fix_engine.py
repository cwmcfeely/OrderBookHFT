import simplefix
import time
import logging


class FixEngine:
    def __init__(self, symbol=None, heartbeat_interval=30):
        """
        Initialise the FIX engine for a given symbol and heartbeat interval.

        Args:
            symbol (str, optional): The trading symbol (e.g., "ASML.AS" or "my_strategy").
            heartbeat_interval (int): Heartbeat interval in seconds.
        """
        self.parser = simplefix.FixParser()  # Used to parse incoming FIX messages
        self.heartbeat_interval = heartbeat_interval  # Heartbeat interval in seconds
        self.last_heartbeat = (
            time.time()
        )  # Timestamp of the last heartbeat sent/received
        self.seq_num = 1  # Sequence number for outgoing FIX messages
        self.symbol = (
            symbol  # Symbol string for logging and message context per strategy
        )

        # Set up loggers: one for the FIX server, one per strategy (if symbol provided)
        self.server_logger = logging.getLogger("FIXServer")
        # For per-strategy logs: use the strategy name or symbol (e.g., "my_strategy")
        self.strategy_logger = (
            logging.getLogger(f"FIX_{self.symbol}") if self.symbol else None
        )

        # Log initialisation for diagnostics
        self.server_logger.info("===== FIX ENGINE INITIALISED =====")
        if self.strategy_logger:
            self.strategy_logger.info(
                "===== FIX ENGINE INITIALISED FOR SYMBOL %s =====", self.symbol
            )

    def create_heartbeat(self):
        """
        Generate and log a FIX heartbeat message (MsgType=0).

        Returns:
            bytes: Encoded FIX heartbeat message.
        """
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")  # BeginString: FIX version
        msg.append_pair(49, "MY_COMPANY")  # SenderCompID
        msg.append_pair(56, "EXCHANGE")  # TargetCompID
        msg.append_pair(34, self.seq_num)  # MsgSeqNum
        msg.append_pair(35, "0")  # MsgType: Heartbeat
        msg.append_utc_timestamp(52)  # SendingTime

        try:
            raw_msg = msg.encode()
            self._log_heartbeat(msg, incoming=False)  # Log the outgoing heartbeat
            self.seq_num += 1  # Increment sequence number after sending
            return raw_msg
        except Exception as e:
            # Log errors to both server and strategy loggers
            self.server_logger.error(f"Heartbeat failed: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(f"Heartbeat failed: {str(e)}", exc_info=True)
            raise

    def create_new_order(self, cl_ord_id, symbol, side, price, qty, source):
        """
        Create a FIX NewOrderSingle message with full headers and validation.

        Args:
            cl_ord_id (str): Unique client order ID.
            symbol (str): Trading symbol (up to 8 characters).
            side (str): '1' for Buy, '2' for Sell.
            price (float or str): Order price.
            qty (int or str): Order quantity.
            source (str): Source identifier (e.g., strategy name).
        Returns:
            bytes: Encoded FIX NewOrderSingle message.

        Raises:
            ValueError: If any field is invalid.
        """
        # Validate ClOrdID
        if not cl_ord_id or not isinstance(cl_ord_id, str):
            raise ValueError("ClOrdID (11) must be a non-empty string")
        # Validate symbol
        if not symbol or not isinstance(symbol, str) or len(symbol) > 8:
            raise ValueError(
                f"Symbol (55) must be a non-empty string up to 8 characters. Got: {symbol}"
            )
        # Validate side
        if str(side) not in {"1", "2"}:
            raise ValueError(f"Side (54) must be '1' (Buy) or '2' (Sell). Got: {side}")
        # Validate price
        try:
            price_val = float(price)
        except Exception:
            raise ValueError(f"Price (44) must be a valid float. Got: {price}")
        if not (0.01 <= price_val <= 1_000_000):
            raise ValueError(
                f"Price (44) out of valid range [0.01, 1,000,000]: {price_val}"
            )
        # Validate quantity
        try:
            qty_val = int(qty)
        except Exception:
            raise ValueError(f"Quantity (38) must be a valid integer. Got: {qty}")
        if not (1 <= qty_val <= 10_000):
            raise ValueError(f"Quantity (38) out of valid range [1, 10,000]: {qty_val}")

        # Construct the FIX NewOrderSingle message
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")  # BeginString
        msg.append_pair(49, "MY_COMPANY")  # SenderCompID
        msg.append_pair(56, "EXCHANGE")  # TargetCompID
        msg.append_pair(34, self.seq_num)  # MsgSeqNum
        msg.append_pair(35, "D")  # MsgType: NewOrderSingle
        msg.append_pair(11, cl_ord_id)  # ClOrdID
        msg.append_pair(55, symbol)  # Symbol
        msg.append_pair(54, str(side))  # Side
        msg.append_pair(44, f"{price_val:.8f}")  # Price, formatted to 8 decimals
        msg.append_pair(38, str(qty_val))  # OrderQty
        msg.append_utc_timestamp(52)  # SendingTime
        msg.append_pair(6007, source)  # Custom tag for source

        self._log_fix_message(msg, incoming=False)  # Log outgoing message
        self.seq_num += 1  # Increment sequence number
        return msg.encode()

    def parse(self, raw_msg):
        """
        Parse an incoming FIX message.
        Args:
            raw_msg (bytes): Raw FIX message bytes.
        Returns:
            simplefix.FixMessage or None: Parsed message object, or None on error.
        """
        try:
            self.parser.append_buffer(raw_msg)
            msg = self.parser.get_message()
            if msg:
                self._log_fix_message(msg, incoming=True)  # Log incoming message
                seq_num = msg.get(34)
                if seq_num:
                    # Update sequence number to next expected value
                    self.seq_num = int(seq_num.decode()) + 1
                return msg
        except Exception as e:
            # Log parse errors for diagnostics
            self.server_logger.error(f"Parse error: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(f"Parse error: {str(e)}", exc_info=True)
            return None

    def _log_heartbeat(self, msg, incoming=True):
        """
        Log heartbeat messages to both FIXServer and strategy logger if available.

        Args:
            msg (simplefix.FixMessage): The heartbeat message.
            incoming (bool): True if received, False if sent.
        """
        direction = "HEARTBEAT RECEIVED" if incoming else "HEARTBEAT SENT"
        try:
            # Convert FIX message to readable string (replace SOH with '|')
            raw = msg.encode().decode(errors="replace").replace("\x01", "|")
            self.server_logger.info(f"{direction}: {raw}")
            if self.strategy_logger:
                self.strategy_logger.info(f"{direction}: {raw}")
        except Exception as e:
            # Log any errors encountered during logging
            self.server_logger.error(f"Heartbeat log error: {str(e)}", exc_info=True)
            if self.strategy_logger:
                self.strategy_logger.error(
                    f"Heartbeat log error: {str(e)}", exc_info=True
                )

    def _log_fix_message(self, msg, incoming=True):
        """
        Log non-heartbeat FIX messages to the strategy-specific logger, or to the server logger.

        Args:
            msg (simplefix.FixMessage or bytes): The FIX message to log.
            incoming (bool): True if received, False if sent.
        """
        direction = "IN" if incoming else "OUT"
        try:
            # Prepare readable string for logging
            if isinstance(msg, simplefix.FixMessage):
                raw = msg.encode().decode(errors="replace").replace("\x01", "|")
            elif isinstance(msg, bytes):
                raw = msg.decode(errors="replace").replace("\x01", "|")
            else:
                raw = str(msg)

            if self.strategy_logger:
                self.strategy_logger.info(f"{direction}: {raw}")
            else:
                # Fallback to FIXServer logger if no strategy logger exists
                self.server_logger.info(f"{direction}: {raw}")
        except Exception as e:
            # Log any errors encountered during logging
            if self.strategy_logger:
                self.strategy_logger.error(
                    f"FIX message log error: {str(e)}", exc_info=True
                )
            else:
                self.server_logger.error(
                    f"FIX message log error: {str(e)}", exc_info=True
                )

    def is_heartbeat_due(self):
        """
        Determine if a heartbeat is due based on the configured interval.

        Returns:
            bool: True if heartbeat should be sent, False otherwise.
        """
        now = time.time()
        due = (now - self.last_heartbeat) >= self.heartbeat_interval
        if due:
            # Log debug message if heartbeat is due
            self.server_logger.debug(
                f"Heartbeat due after {now - self.last_heartbeat:.1f}s (interval={self.heartbeat_interval}s)"
            )
            if self.strategy_logger:
                self.strategy_logger.debug(
                    f"Heartbeat due after {now - self.last_heartbeat:.1f}s (interval={self.heartbeat_interval}s)"
                )
        return due

    def create_execution_report(
        self,
        cl_ord_id,
        order_id,
        exec_id,
        ord_status,
        exec_type,
        symbol,
        side,
        order_qty,
        last_qty=None,
        last_px=None,
        leaves_qty=None,
        cum_qty=None,
        price=None,
        source=None,
        text=None,
    ):
        """
        Create a FIX ExecutionReport message.

        Args:
            cl_ord_id (str): Client order ID.
            order_id (str): Order ID.
            exec_id (str): Execution ID.
            ord_status (str): Order status code.
            exec_type (str): Execution type code.
            symbol (str): Trading symbol.
            side (str): Side ('1' for Buy, '2' for Sell).
            order_qty (int): Original order quantity.
            last_qty (int, optional): Last filled quantity.
            last_px (float, optional): Last fill price.
            leaves_qty (int, optional): Leaves quantity.
            cum_qty (int, optional): Cumulative quantity.
            price (float, optional): Order price.
            source (str, optional): Source identifier.
            text (str, optional): Free text or rejection reason (tag 58).
        Returns:
            bytes: Encoded FIX ExecutionReport message.
        """
        msg = simplefix.FixMessage()
        msg.append_pair(8, "FIX.4.4")  # BeginString
        msg.append_pair(49, "EXCHANGE")  # SenderCompID
        msg.append_pair(56, "MY_COMPANY")  # TargetCompID
        msg.append_pair(34, self.seq_num)  # MsgSeqNum
        msg.append_pair(35, "8")  # MsgType: ExecutionReport
        msg.append_pair(11, cl_ord_id)  # ClOrdID
        msg.append_pair(37, order_id)  # OrderID
        msg.append_pair(17, exec_id)  # ExecID
        msg.append_pair(39, ord_status)  # OrdStatus
        msg.append_pair(150, exec_type)  # ExecType
        msg.append_pair(55, symbol)  # Symbol
        msg.append_pair(54, side)  # Side
        msg.append_pair(38, str(order_qty))  # OrderQty
        if last_qty is not None:
            msg.append_pair(32, str(last_qty))  # LastQty
        if last_px is not None:
            msg.append_pair(31, f"{last_px:.8f}")  # LastPx
        if leaves_qty is not None:
            msg.append_pair(151, str(leaves_qty))  # LeavesQty
        if cum_qty is not None:
            msg.append_pair(14, str(cum_qty))  # CumQty
        if price is not None:
            msg.append_pair(44, f"{price:.8f}")  # Price
        if source:
            msg.append_pair(6007, source)  # Custom source tag
        msg.append_utc_timestamp(52)  # SendingTime
        if text:
            msg.append_pair(58, text)  # Tag 58: Free text or rejection reason
        msg.append_utc_timestamp(52)  # SendingTime

        self._log_fix_message(msg, incoming=False)  # Log outgoing execution report
        self.seq_num += 1  # Increment sequence number
        return msg.encode()

    def update_heartbeat(self):
        """
        Update the timestamp of the last heartbeat to now.
        """
        self.last_heartbeat = time.time()
        self.server_logger.debug("Heartbeat timestamp updated")
        if self.strategy_logger:
            self.strategy_logger.debug("Heartbeat timestamp updated")
