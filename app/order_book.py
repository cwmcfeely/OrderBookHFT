from sortedcontainers import SortedDict
from collections import deque
import time

class OrderBook:
    def __init__(self, symbol):
        self.symbol = symbol
        self.bids = SortedDict(lambda x: -x)  # Price → deque of orders (descending)
        self.asks = SortedDict()  # Price → deque of orders (ascending)
        self.trade_history = []  # Store recent trade prices for volatility etc.
        self.last_price = None

    def add_order(self, side, price, quantity, order_id, source, order_time=None):
        """Add order with FIX protocol validation"""
        # Convert bytes to string if needed
        if isinstance(side, bytes):
            side = side.decode("utf-8")

        # Validate and convert FIX side codes
        if side == "1":
            side = "buy"
        elif side == "2":
            side = "sell"
        else:
            raise ValueError(f"Invalid FIX side '{side}': must be '1' or '2'")

        # Convert to numeric types
        try:
            price = float(price)
            quantity = int(quantity)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid price/quantity: {str(e)}")

        # Add to order book using deque
        book = self.bids if side == "buy" else self.asks
        if price not in book:
            book[price] = deque()  # Use deque for efficient pops from front
        book[price].append({
            "id": order_id,
            "qty": quantity,
            "source": source,
            "order_time": order_time
        })

    def get_depth_snapshot(self, levels=10):
        """Get top N levels for bids and asks with cumulative quantity"""
        return {
            "bids": self._get_levels(self.bids, levels, descending=True),
            "asks": self._get_levels(self.asks, levels, descending=False),
            "last_price": self.last_price
        }

    def _get_levels(self, book, levels, descending):
        cumulative = 0
        result = []
        prices = list(book.keys())[:levels]
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
        """Get best bid with price and quantity"""
        return self._get_best_level(self.bids, max)

    def get_best_ask(self):
        """Get best ask with price and quantity"""
        return self._get_best_level(self.asks, min)

    def _get_best_level(self, book, extremum_func):
        """Generic best price calculator"""
        if not book:
            return None
        best_price = extremum_func(book.keys())
        return {
            "price": best_price,
            "qty": sum(order["qty"] for order in book[best_price])
        }

    def record_trade(self, price):
        """Record a trade price for volatility and analytics"""
        self.trade_history.append(price)
        # Keep trade history size manageable (e.g., last 1000 trades)
        if len(self.trade_history) > 1000:
            self.trade_history.pop(0)

    def get_recent_prices(self, window=30):
        """Return the most recent trade prices up to the window size"""
        if not self.trade_history:
            return []
        return self.trade_history[-window:]

    def seed_synthetic_depth(self, mid_price, levels=10, base_qty=100):
        """
        Seed the order book with synthetic depth.
        Creates 'levels' price levels on each side with exponentially decaying quantities.
        """
        for i in range(1, levels + 1):
            bid_price = mid_price * (1 - 0.001 * i)
            ask_price = mid_price * (1 + 0.001 * i)
            qty = int(base_qty * (0.8 ** i))
            self.add_order("1", bid_price, qty, f"SEED-BID-{i}", "system")
            self.add_order("2", ask_price, qty, f"SEED-ASK-{i}", "system")

    def get_mid_price(self):
        """Return the midpoint price between best bid and best ask"""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid["price"] + best_ask["price"]) / 2

    # Expiring old orders from the book
    def expire_old_orders(self, max_age=60):
        now = time.time()
        for book in [self.bids, self.asks]:
            for price in list(book.keys()):
                queue = book[price]
                while queue and queue[0].get("order_time") and now - queue[0]["order_time"] > max_age:
                    queue.popleft()
                if not queue:
                    del book[price]