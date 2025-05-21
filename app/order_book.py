from sortedcontainers import SortedDict
from collections import deque
import time


class OrderBook:
    def __init__(self, symbol):
        """
        Initialise an order book for a given trading symbol.
        Args:
            symbol (str): The trading symbol, e.g. "AAPL" or "ASML.AS".
        """
        self.symbol = symbol
        # Bids stored in descending order by price (highest bid first)
        self.bids = SortedDict(lambda x: -x)  # Price → deque of orders
        # Asks stored in ascending order by price (lowest ask first)
        self.asks = SortedDict()  # Price → deque of orders
        self.trade_history = []  # List to store recent trade prices for analytics
        self.last_price = None  # Last traded price
        self.order_map = {}  # Track all orders by order_id

    def add_order(self, side, price, quantity, order_id, source, order_time=None):
        """
        Add an order to the order book with validation and conversion.
        Args:
            side (str or bytes): '1' or '2' per FIX protocol, or 'buy'/'sell'.
            price (float or str): Price of the order.
            quantity (int or str): Quantity of the order.
            order_id (str): Unique identifier for the order.
            source (str): Source or strategy placing the order.
            order_time (float, optional): Timestamp when order was created (epoch seconds).
        """
        # Decode bytes to string if necessary
        if isinstance(side, bytes):
            side = side.decode("utf-8")

        # Convert FIX side codes to 'buy' or 'sell'
        if side == "1":
            side = "buy"
        elif side == "2":
            side = "sell"
        else:
            raise ValueError(f"Invalid FIX side '{side}': must be '1' or '2'")

        # Convert price and quantity to proper numeric types
        try:
            price = float(price)
            quantity = int(quantity)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid price/quantity: {str(e)}")

        # Select the appropriate book side (bids or asks)
        book = self.bids if side == "buy" else self.asks

        # Create a new price level if it does not exist
        if price not in book:
            book[price] = deque()  # Use deque for efficient FIFO queue of orders

        # Create order record
        order = {
            "id": order_id,
            "qty": quantity,
            "source": source,
            "order_time": order_time or time.time(),
            "price": price,
            "side": side
        }

        # Append the order to the queue for this price level
        book[price].append(order)
        self.order_map[order_id] = (price, side)

    def get_depth_snapshot(self, levels=10):
        """
        Get a snapshot of the top N levels of the order book for bids and asks.
        Args:
            levels (int): Number of price levels to include.
        Returns:
            dict: Dictionary with bids and asks lists and last traded price.
        """
        return {
            "bids": self._get_levels(self.bids, levels, descending=True),
            "asks": self._get_levels(self.asks, levels, descending=False),
            "last_price": self.last_price
        }

    def _get_levels(self, book, levels, descending):
        """
        Helper to extract price levels with cumulative quantities.
        Args:
            book (SortedDict): The bids or asks book.
            levels (int): Number of levels to extract.
            descending (bool): Whether to process in descending order.
        Returns:
            list: List of dicts with price, quantity, cumulative quantity, and order count.
        """
        cumulative = 0
        result = []
        # Get the price keys (already sorted ascending)
        prices = list(book.keys())[:levels]

        # If descending requested, reverse the price list
        if descending:
            prices = list(book.keys())[:levels]

        for price in prices:
            orders = list(book[price])
            total_qty = sum(order["qty"] for order in orders)
            cumulative += total_qty
            result.append({
                "price": price,
                "quantity": total_qty,
                "cumulative": cumulative,
                "orders": len(orders)
            })
        return result

    def get_best_bid(self):
        """
        Get the best (highest) bid price and total quantity at that level.
        Returns:
            dict or None: Dict with 'price' and 'qty' keys or None if no bids.
        """
        return self._get_best_level(self.bids, max)

    def get_best_ask(self):
        """
        Get the best (lowest) ask price and total quantity at that level.
        Returns:
            dict or None: Dict with 'price' and 'qty' keys or None if no asks.
        """
        return self._get_best_level(self.asks, min)

    def _get_best_level(self, book, extremum_func):
        """
        Generic helper to get best price level using min or max function.
        Args:
            book (SortedDict): Bids or asks book.
            extremum_func (function): min or max function.
        Returns:
            dict or None: Dict with price and qty or None if empty.
        """
        if not book:
            return None
        best_price = extremum_func(book.keys())
        return {
            "price": best_price,
            "qty": sum(order["qty"] for order in book[best_price])
        }

    def record_trade(self, price):
        """
        Record a trade price in the trade history for analytics.
        Args:
            price (float): Price at which trade occurred.
        """
        self.trade_history.append(price)
        # Keep trade history size manageable (e.g., last 1000 trades)
        if len(self.trade_history) > 1000:
            self.trade_history.pop(0)

    def get_recent_prices(self, window=30):
        """
        Get the most recent trade prices up to the specified window size.
        Args:
            window (int): Number of recent prices to return.
        Returns:
            list: List of recent trade prices.
        """
        if not self.trade_history:
            return []
        return self.trade_history[-window:]

    def seed_synthetic_depth(self, mid_price, levels=10, base_qty=100):
        """
        Seed the order book with synthetic depth around a mid price.
        Creates 'levels' price levels on both bid and ask sides with exponentially decaying quantities.
        Args:
            mid_price (float): The central price around which to seed depth.
            levels (int): Number of price levels on each side.
            base_qty (int): Base quantity for the first level; subsequent levels decay exponentially.
        """
        for i in range(2, levels + 2):  # start at i=2 to skip top-of-book
            bid_price = mid_price * (1 - 0.005 * i)  # wider spread
            ask_price = mid_price * (1 + 0.005 * i)
            qty = int(base_qty * (0.8 ** i))
            self.add_order("1", bid_price, qty, f"SEED-BID-{i}", "system")
            self.add_order("2", ask_price, qty, f"SEED-ASK-{i}", "system")

    def get_mid_price(self):
        """
        Calculate the midpoint price between the best bid and best ask.
        Returns:
            float or None: Mid-price or None if bids or asks are empty.
        """
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid["price"] + best_ask["price"]) / 2

    def expire_old_orders(self, max_age=60):
        """
        Remove orders from the book that are older than max_age seconds.
        Args:
            max_age (int): Maximum age in seconds for orders to remain valid.
        """
        now = time.time()
        # Check both bids and asks
        for book, side in [(self.bids, "buy"), (self.asks, "sell")]:
            # Iterate over price levels (copy keys to avoid modification during iteration)
            for price in list(book.keys()):
                queue = book[price]
                # Remove orders from front of queue if too old
                while queue and (now - queue[0]["order_time"]) > max_age:
                    removed_order = queue.popleft()
                    self.order_map.pop(removed_order["id"], None)
                # Remove price level if empty after expiry
                if not queue:
                    del book[price]

    def remove_order(self, order_id):
        """
        Remove an order from the book by order ID.
        Args:
            order_id (str): The unique order identifier to remove.
        Returns:
            dict: Removed order details or None if not found.
        """
        if order_id not in self.order_map:
            return None

        price, side = self.order_map[order_id]
        book = self.bids if side == "buy" else self.asks

        if price not in book:
            del self.order_map[order_id]
            return None

        # Find and remove the order
        new_queue = deque()
        removed_order = None
        for order in book[price]:
            if order["id"] == order_id:
                removed_order = order
            else:
                new_queue.append(order)

        if removed_order:
            book[price] = new_queue
            if not book[price]:
                del book[price]
            del self.order_map[order_id]

        return removed_order

    def get_order_source(self, order_id):
        """
        Retrieve the source strategy for a given order ID.
        Args:
            order_id (str): The unique order identifier.
        Returns:
            str: Source strategy name or None if not found.
        """
        if order_id not in self.order_map:
            return None
        price, side = self.order_map[order_id]
        book = self.bids if side == "buy" else self.asks
        for order in book.get(price, []):
            if order["id"] == order_id:
                return order["source"]
        return None

    def get_orders_by_source(self, side, source):
        book = self.bids if side == "buy" else self.asks
        return [order for q in book.values() for order in q if order["source"] == source]
