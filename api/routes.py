import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime

import yaml
from flask import jsonify, render_template, request

from app.fix_engine import FixEngine
from app.market_data import get_latest_price
from app.matching_engine import MatchingEngine, TradingHalted
from app.order_book import OrderBook
from strategies.competitor_strategy import PassiveLiquidityProvider
from strategies.competitor_strategy1 import MarketMakerStrategy
from strategies.competitor_strategy2 import MomentumStrategy
from strategies.my_strategy import MyStrategy

# Set up logger for this module
logger = logging.getLogger(__name__)
logger.propagate = False

# Load configuration file and extract symbols to be traded
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
    symbols = config.get("symbols", {})

# Initialize the global trading state used by all routes and background threads

trading_state: dict[str, object] = {
    "exchange_halted": False,  # Whether the exchange is halted
    "my_strategy_enabled": True,  # Whether the user's strategy is enabled
    "current_symbol": next(iter(symbols.values()), None),  # Currently selected symbol
    "order_books": {
        symbol: OrderBook(symbol) for symbol in symbols.values()
    },  # Order books per symbol
    "trades": {symbol: [] for symbol in symbols.values()},  # Trades per symbol
    "log": [],  # Log for UI or audit
    "order_book_history": {
        symbol: [] for symbol in symbols.values()
    },  # Order book snapshots
    "spread_history": {
        symbol: [] for symbol in symbols.values()
    },  # Bid-ask spread history
    "liquidity_history": {
        symbol: [] for symbol in symbols.values()
    },  # Liquidity at top levels
    "latency_history": {
        symbol: [] for symbol in symbols.values()
    },  # Order latency records
    "execution_reports": {
        symbol: [] for symbol in symbols.values()
    },  # Execution reports per symbol
    "competition_logs": [],  # Strategy competition logs (NEW)
}

# Threading lock to ensure thread-safe access to trading_state

state_lock = threading.Lock()

# Instantiate a FIX engine for each symbol

fix_engines = {symbol: FixEngine(symbol=symbol) for symbol in symbols.values()}

# Dictionary to store strategy instances per symbol

strategy_instances = {}


def append_order_book_snapshot(symbol, order_book):
    """
    Take a snapshot of the order book, spread, and liquidity for a symbol.
    Truncate history to keep memory usage manageable.
    """
    snapshot = order_book.get_depth_snapshot(levels=10)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with state_lock:
        trading_state["order_book_history"][symbol].append(
            {"time": now, "snapshot": snapshot}
        )

    # Calculate and store mid price and spread
    best_bid = order_book.get_best_bid()
    best_ask = order_book.get_best_ask()
    if best_bid and best_ask:
        mid = (best_bid["price"] + best_ask["price"]) / 2
        spread = best_ask["price"] - best_bid["price"]
    else:
        mid = None
        spread = None
    trading_state["spread_history"][symbol].append(
        {"time": now, "mid": mid, "spread": spread}
    )

    # Calculate and store total liquidity at top N levels
    total_liquidity = 0
    if snapshot:
        bids = snapshot.get("bids", [])
        asks = snapshot.get("asks", [])
        total_liquidity = sum(level["quantity"] for level in bids) + sum(
            level["quantity"] for level in asks
        )
    trading_state["liquidity_history"][symbol].append(
        {"time": now, "liquidity": total_liquidity}
    )

    # Truncate histories to last 500 entries for efficiency
    for key in ["order_book_history", "spread_history", "liquidity_history"]:
        if len(trading_state[key][symbol]) > 500:
            trading_state[key][symbol].pop(0)


def auto_update_order_books():
    """
    Background thread function to keep order books updated, reseed synthetic depth,
    run strategies, and process trades.
    """
    min_levels = 3  # Minimum price levels required on each side
    min_qty = 20  # Minimum total quantity required on each side
    reseed_interval = 120  # Periodic reseed interval in seconds
    # Track last reseed time per symbol
    last_reseed_time = {symbol: 0 for symbol in symbols.values()}

    while True:
        with state_lock:
            if trading_state["exchange_halted"]:
                time.sleep(1)
                continue

        for symbol in symbols.values():
            try:
                order_book = trading_state["order_books"][symbol]

                # Expire old orders from the order book
                order_book.expire_old_orders(max_age=60)

                # Create or retrieve strategy instances for this symbol
                with state_lock:
                    if symbol not in strategy_instances:
                        strategy_instances[symbol] = {}

                    # MyStrategy (user-controlled, can be toggled)
                    if trading_state["my_strategy_enabled"]:
                        if "my_strategy" not in strategy_instances[symbol]:
                            strategy_instances[symbol]["my_strategy"] = MyStrategy(
                                FixEngine(symbol="my_strategy"), order_book, symbol
                            )
                    else:
                        strategy_instances[symbol].pop("my_strategy", None)

                    # Competitor strategies (always on)
                    if "passive_liquidity_provider" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["passive_liquidity_provider"] = (
                            PassiveLiquidityProvider(
                                FixEngine(symbol="passive_liquidity_provider"),
                                order_book,
                                symbol,
                            )
                        )

                    if "market_maker" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["market_maker"] = (
                            MarketMakerStrategy(
                                FixEngine(symbol="market_maker"), order_book, symbol
                            )
                        )

                    if "momentum" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["momentum"] = MomentumStrategy(
                            FixEngine(symbol="momentum"), order_book, symbol
                        )

                # Create a matching engine for this symbol
                matching_engine = MatchingEngine(
                    order_book,
                    strategies=strategy_instances[symbol],
                    trading_state=trading_state,
                    state_lock=state_lock,
                )

                # Check if order book needs reseeding (insufficient liquidity or time-based)
                bids_ok = (
                    len(order_book.bids) >= min_levels
                    and sum(
                        sum(order["qty"] for order in q)
                        for q in order_book.bids.values()
                    )
                    >= min_qty
                )
                asks_ok = (
                    len(order_book.asks) >= min_levels
                    and sum(
                        sum(order["qty"] for order in q)
                        for q in order_book.asks.values()
                    )
                    >= min_qty
                )
                now = time.time()
                need_reseed = not bids_ok or not asks_ok
                time_for_reseed = now - last_reseed_time[symbol] > reseed_interval

                if need_reseed or time_for_reseed:
                    price = get_latest_price(symbol)
                    if price:
                        order_book.last_price = price
                        order_book.seed_synthetic_depth(
                            mid_price=price, levels=10, base_qty=100
                        )
                        last_reseed_time[symbol] = now
                        logger.info(
                            f"Reseeded synthetic depth for {symbol} at mid price {price} "
                            f"(bids_ok={bids_ok}, asks_ok={asks_ok}, time_for_reseed={time_for_reseed})"
                        )

                # Record order book, spread, and liquidity snapshots
                append_order_book_snapshot(symbol, order_book)

                # Generate and process orders from all strategies
                strategies = list(strategy_instances[symbol].values())
                for strategy in strategies:
                    try:
                        for order in strategy.generate_orders():
                            trades = matching_engine.match_order(
                                side=order["side"],
                                price=order["price"],
                                quantity=order["quantity"],
                                order_id=str(uuid.uuid4()),
                                source=strategy.source_name,
                            )
                            with state_lock:
                                trading_state["trades"][symbol].extend(trades)
                            if trades:
                                order_book.last_price = trades[-1]["price"]
                    except TradingHalted as e:
                        logger.error(f"Trading halted for {symbol}: {e}")
                        with state_lock:
                            trading_state["exchange_halted"] = True
                    except Exception as e:
                        logger.error(
                            f"Strategy {strategy.source_name} error: {str(e)}",
                            exc_info=True,
                        )

                # Handle FIX heartbeats for each strategy
                for strategy in strategies:
                    if hasattr(strategy, "fix_engine"):
                        fix_engine = strategy.fix_engine
                        if fix_engine.is_heartbeat_due():
                            fix_engine.create_heartbeat()
                            fix_engine.update_heartbeat()

            except Exception as e:
                logger.error(f"Error updating {symbol}: {str(e)}", exc_info=True)
        time.sleep(5)


# Start the background thread to update order books and run strategies
threading.Thread(target=auto_update_order_books, daemon=True).start()


def filter_trades(trades, side=None, source=None, min_price=None, max_price=None):
    """
    Filter trades by side, source, and price range.
    """
    filtered = []
    for trade in trades:
        if side and trade.get("side") != side:
            continue
        if source and trade.get("source") != source:
            continue
        price = trade.get("price")
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        filtered.append(trade)
    return filtered


def register_routes(app):
    """
    Register all Flask routes for the trading dashboard and API.
    """
    app.route("/toggle_exchange", methods=["POST"])(toggle_exchange)
    app.route("/toggle_my_strategy", methods=["POST"])(toggle_my_strategy)
    app.route("/cancel_mystrategy_orders", methods=["POST"])(cancel_mystrategy_orders)
    app.route("/status")(get_status)
    app.route("/order_book")(get_order_book)
    app.route("/trades")(get_trades)
    app.route("/order_book_history")(get_order_book_history)
    app.route("/spread_history")(get_spread_history)
    app.route("/liquidity_history")(get_liquidity_history)
    app.route("/strategy_status")(strategy_status)
    app.route("/execution_reports")(get_execution_reports)
    app.route("/select_symbol", methods=["POST"])(select_symbol)
    app.route("/order_latency_history")(order_latency_history)
    app.route("/")(index)
    app.route("/competition_logs")(get_competition_logs)


def toggle_exchange():
    """
    Toggle the exchange halted/active state.
    """
    with state_lock:
        trading_state["exchange_halted"] = not trading_state["exchange_halted"]
    status = "halted" if trading_state["exchange_halted"] else "active"
    trading_state["log"].append(f"Exchange {status}")

    # Logging to the general application log
    app_logger = logging.getLogger()
    app_logger.info(f"Exchange has been {status} by user action.")

    # Optional: Logging to the per-strategy FIX log for audit trail
    logging.getLogger("FIX_my_strategy").info(
        f"EXCHANGE: Exchange has been {status} by user action."
    )

    return jsonify({"exchange_halted": trading_state["exchange_halted"]})


def toggle_my_strategy():
    """
    Enable or pause MyStrategy (user's strategy).
    """
    with state_lock:
        trading_state["my_strategy_enabled"] = not trading_state["my_strategy_enabled"]
    status = "enabled" if trading_state["my_strategy_enabled"] else "paused"
    trading_state["log"].append(f"MyStrategy {status}")

    # Logging
    app_logger = logging.getLogger()  # Root logger for app.debug.log
    strat_logger = logging.getLogger("FIX_my_strategy")  # Per-strategy logger

    if trading_state["my_strategy_enabled"]:
        app_logger.info("my_strategy has been started/enabled by user action.")
        strat_logger.info("START: my_strategy has been started/enabled by user action.")
    else:
        app_logger.info("my_strategy has been paused by user action.")
        strat_logger.info("PAUSE: my_strategy has been paused by user action.")

    return jsonify({"my_strategy_enabled": trading_state["my_strategy_enabled"]})


def cancel_mystrategy_orders():
    """
    Cancel all orders in the order book that were submitted by MyStrategy.
    """
    logger = logging.getLogger("FIX_my_strategy")
    data = request.get_json() or {}
    symbol = data.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        if symbol not in trading_state["order_books"]:
            return jsonify({"status": "error", "error": "Invalid symbol"}), 400
        order_book = trading_state["order_books"][symbol]
        removed_orders = []
        for book_side in [order_book.bids, order_book.asks]:
            # Determine side for FIX (1=Buy for bids, 2=Sell for asks)
            side_value = "1" if book_side is order_book.bids else "2"
            for price in list(book_side.keys()):
                queue = book_side[price]
                new_queue = [
                    order for order in queue if order.get("source") != "my_strategy"
                ]
                if len(new_queue) != len(queue):
                    cancelled = [
                        order for order in queue if order.get("source") == "my_strategy"
                    ]
                    removed_orders.extend(cancelled)
                    for order in cancelled:
                        # Use order's side if present, otherwise infer
                        side = order.get("side", side_value)
                        # Format price to 8 decimals if it's a float
                        price_val = order.get("price")
                        if isinstance(price_val, float):
                            price_val = f"{price_val:.8f}"
                        # Tag 52: SendingTime in FIX UTC format
                        sending_time = datetime.utcnow().strftime("%Y%m%d-%H:%M:%S.%f")[
                            :-3
                        ]
                        logger.info(
                            f"8=FIX.4.4|35=8|39=4|150=4|11={order.get('id')}|55={symbol}|54={side}|38={order.get('qty')}|44={price_val}|58=Order cancelled by my_strategy|52={sending_time}|10=000"
                        )
                if new_queue:
                    book_side[price] = deque(new_queue)
                else:
                    del book_side[price]
        decoded_removed_orders = decode_bytes(removed_orders)
        return jsonify({"status": "success", "removed_orders": decoded_removed_orders})


def get_status():
    """
    Get the current status of the exchange and MyStrategy.
    """
    with state_lock:
        return jsonify(
            {
                "exchange_halted": trading_state["exchange_halted"],
                "my_strategy_enabled": trading_state["my_strategy_enabled"],
                "symbol": trading_state["current_symbol"],
            }
        )


def safe_get_data(data_dict, symbol):
    """
    Safely get data for a symbol from a dictionary.
    Returns empty list if symbol not found or data is None.
    """
    if symbol not in data_dict:
        return []
    data = data_dict.get(symbol)
    if data is None:
        return []
    return data


def get_order_book():
    """
    Get the current order book for the selected symbol.
    """
    symbol = trading_state["current_symbol"]
    req_symbol = request.args.get("symbol")
    if req_symbol and req_symbol in symbols.values():
        symbol = req_symbol
    with state_lock:
        ob = trading_state["order_books"][symbol]
        return jsonify(
            {
                "bids": [
                    {
                        "price": p,
                        "qty": sum(o["qty"] for o in q),
                        "sources": [o["source"] for o in q],
                    }
                    for p, q in ob.bids.items()
                ],
                "asks": [
                    {
                        "price": p,
                        "qty": sum(o["qty"] for o in q),
                        "sources": [o["source"] for o in q],
                    }
                    for p, q in ob.asks.items()
                ],
                "last_price": (
                    float(ob.last_price) if ob.last_price is not None else None
                ),
            }
        )


def decode_bytes(obj):
    """
    Recursively decode bytes to UTF-8 in nested lists/dicts for JSON serialization.
    """
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {k: decode_bytes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decode_bytes(i) for i in obj]
    return obj


def get_trades():
    """
    Get trades for the selected symbol, optionally filtered by side, source, and price.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    side = request.args.get("side")
    source = request.args.get("source")
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    with state_lock:
        trades = safe_get_data(trading_state["trades"], symbol)
        filtered_trades = filter_trades(trades, side, source, min_price, max_price)
        trades_decoded = decode_bytes(filtered_trades)
        return jsonify(trades_decoded)


def get_order_book_history():
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        history = safe_get_data(trading_state["order_book_history"], symbol)
        if not history:
            return jsonify([])  # Return empty list if no data
        processed = []
        for entry in history:
            snapshot = entry["snapshot"]
            bids = snapshot.get("bids", [])
            asks = snapshot.get("asks", [])
            price_levels = [b["price"] for b in bids] + [a["price"] for a in asks]
            quantities = [b["quantity"] for b in bids] + [a["quantity"] for a in asks]
            processed.append(
                {
                    "time": entry["time"],
                    "price_levels": price_levels,
                    "quantities": quantities,
                }
            )
        return jsonify(processed)


def get_spread_history():
    """
    Get historical bid-ask spread and mid price for the selected symbol.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        spread_history = safe_get_data(trading_state["spread_history"], symbol)
        return jsonify(spread_history)


def get_liquidity_history():
    """
    Get historical liquidity at top levels for the selected symbol.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        liquidity_history = safe_get_data(trading_state["liquidity_history"], symbol)
        return jsonify(liquidity_history)


def strategy_status():
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        strategies = strategy_instances.get(symbol, {})
        status = {}
        for name, strat in strategies.items():
            # Get current market price for unrealised PnL
            try:
                current_price = strat.order_book.get_mid_price()
            except Exception:
                current_price = strat.order_book.last_price

            # Defensive fallback
            if current_price is None:
                current_price = 0.0
            # Defensive: Ensure all attributes exist
            realised_pnl = getattr(strat, "realised_pnl", 0.0)
            initial_capital = getattr(strat, "initial_capital", 100000)
            max_inventory = getattr(strat, "max_inventory", 1)
            inventory = getattr(strat, "inventory", 0)
            win_rate = strat.get_win_rate() if hasattr(strat, "get_win_rate") else 0.0
            # Use per-symbol trades if available (for accurate trade count)
            symbol_trades = trading_state["trades"].get(symbol, [])
            strat_trades = [t for t in symbol_trades if t.get("source") == name]
            total_trades = len(strat_trades)
            # Calculate metrics for the strategy
            status[name] = {
                "inventory": inventory,
                "realised_pnl": realised_pnl,
                "realised_pnl_percent": (
                    (realised_pnl / initial_capital * 100) if initial_capital else 0
                ),
                "unrealised_pnl": (
                    strat.unrealised_pnl() if hasattr(strat, "unrealised_pnl") else 0.0
                ),
                "unrealised_pnl_percent": (
                    (strat.unrealised_pnl() / initial_capital * 100)
                    if initial_capital
                    else 0
                ),
                "total_pnl": (
                    strat.total_pnl() if hasattr(strat, "total_pnl") else realised_pnl
                ),
                "total_pnl_percent": (
                    (strat.total_pnl() / initial_capital * 100)
                    if initial_capital and hasattr(strat, "total_pnl")
                    else 0
                ),
                "inventory_percent": (
                    (inventory / max_inventory * 100) if max_inventory else 0
                ),
                "total_trades": total_trades,
                "win_rate": win_rate,
            }
        return jsonify(status)


def get_execution_reports():
    """
    Get execution reports for the selected symbol, optionally filtered by source.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    source = request.args.get("source")
    with state_lock:
        reports = trading_state.get("execution_reports", {}).get(symbol, [])
        if source:
            reports = [r for r in reports if r.get("source") == source]
        return jsonify(reports)


def select_symbol():
    """
    Change the currently selected trading symbol.
    """
    data = request.get_json()
    symbol = data.get("symbol") or data.get("ticker")
    with state_lock:
        if symbol in symbols.values():
            trading_state["current_symbol"] = symbol
            trading_state["log"].append(f"Symbol selected: {symbol}")
            logging.getLogger("FIX_my_strategy").info(
                f"SYMBOL: Symbol changed to: {symbol}"
            )
            return jsonify({"status": "symbol_changed", "symbol": symbol})
    return jsonify({"error": "Invalid symbol"}), 400


def order_latency_history():
    """
    Get order latency history for the selected symbol.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        latency_data = trading_state.get("latency_history", {}).get(symbol, [])
        return jsonify(latency_data)


def index():
    """
    Render the main dashboard page.
    """
    return render_template("index.html", symbols=symbols)


def get_competition_logs():
    """
    Get strategy competition logs for the selected symbol.
    """
    symbol = request.args.get("symbol") or trading_state["current_symbol"]
    with state_lock:
        return jsonify(trading_state.get("competition_logs", {}).get(symbol, []))
