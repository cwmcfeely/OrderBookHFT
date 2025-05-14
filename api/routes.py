import threading
import time
import uuid
import yaml
import logging
from flask import request, jsonify, render_template

from app.market_data import get_latest_price
from app.matching_engine import MatchingEngine, TradingHalted
from app.order_book import OrderBook
from strategies.my_strategy import MyStrategy
from strategies.competitor_strategy import PassiveLiquidityProvider
from strategies.competitor_strategy1 import MarketMakerStrategy
from strategies.competitor_strategy2 import MomentumStrategy
from app.fix_engine import FixEngine
from datetime import datetime

logger = logging.getLogger(__name__)
logger.propagate = False

# Load config and symbols
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)
symbols = config.get("symbols", {})

# Initialise trading state
trading_state = {
    "exchange_halted": False,
    "my_strategy_enabled": True,
    "current_symbol": next(iter(symbols.values()), None),
    "order_books": {symbol: OrderBook(symbol) for symbol in symbols.values()},
    "trades": {symbol: [] for symbol in symbols.values()},
    "log": [],
    "order_book_history": {symbol: [] for symbol in symbols.values()},
    "spread_history": {symbol: [] for symbol in symbols.values()},
    "liquidity_history": {symbol: [] for symbol in symbols.values()},
    "latency_history": {symbol: [] for symbol in symbols.values()},
}

state_lock = threading.Lock()

fix_engines = {
    symbol: FixEngine(log_file=f"logs/fix_messages_{symbol}.log")
    for symbol in symbols.values()
}

# Store strategy instances per symbol for status reporting and trade notification
strategy_instances = {}

def append_order_book_snapshot(symbol, order_book):
    snapshot = order_book.get_depth_snapshot(levels=10)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with state_lock:
        trading_state["order_book_history"][symbol].append({"time": now, "snapshot": snapshot})

        # Calculate mid price and spread
        best_bid = order_book.get_best_bid()
        best_ask = order_book.get_best_ask()
        if best_bid and best_ask:
            mid = (best_bid["price"] + best_ask["price"]) / 2
            spread = best_ask["price"] - best_bid["price"]
        else:
            mid = None
            spread = None

        trading_state["spread_history"][symbol].append({"time": now, "mid": mid, "spread": spread})

        # Calculate total liquidity at top N levels
        total_liquidity = 0
        if snapshot:
            bids = snapshot.get("bids", [])
            asks = snapshot.get("asks", [])
            total_liquidity = sum(level["quantity"] for level in bids) + sum(level["quantity"] for level in asks)

        trading_state["liquidity_history"][symbol].append({"time": now, "liquidity": total_liquidity})

        # Keep history length manageable (e.g., last 500 snapshots)
        for key in ["order_book_history", "spread_history", "liquidity_history"]:
            if len(trading_state[key][symbol]) > 500:
                trading_state[key][symbol].pop(0)

def auto_update_order_books():
    while True:
        with state_lock:
            if trading_state["exchange_halted"]:
                time.sleep(1)
                continue

        for symbol, fix_engine in fix_engines.items():
            try:
                order_book = trading_state["order_books"][symbol]

                # Create or retrieve strategy instances for this symbol
                with state_lock:
                    if symbol not in strategy_instances:
                        strategy_instances[symbol] = {}
                    # MyStrategy (user-controlled)
                    if trading_state["my_strategy_enabled"]:
                        if "my_strategy" not in strategy_instances[symbol]:
                            strategy_instances[symbol]["my_strategy"] = MyStrategy(fix_engine, order_book, symbol)
                    else:
                        strategy_instances[symbol].pop("my_strategy", None)
                    # Competitor strategies (always on)
                    if "passive_liquidity_provider" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["passive_liquidity_provider"] = PassiveLiquidityProvider(fix_engine, order_book, symbol)
                    if "market_maker" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["market_maker"] = MarketMakerStrategy(fix_engine, order_book, symbol)
                    if "momentum" not in strategy_instances[symbol]:
                        strategy_instances[symbol]["momentum"] = MomentumStrategy(fix_engine, order_book, symbol)

                matching_engine = MatchingEngine(
                    order_book,
                    strategies=strategy_instances[symbol],
                    trading_state=trading_state,
                    state_lock=state_lock
                )

                # Seed order book with synthetic depth if empty
                if not order_book.bids and not order_book.asks:
                    price = get_latest_price(symbol)
                    if price:
                        order_book.last_price = price
                        order_book.seed_synthetic_depth(mid_price=price, levels=10, base_qty=100)
                        logger.info(f"Seeded synthetic depth for {symbol} with mid price {price}")

                # Record order book, spread, and liquidity snapshots
                append_order_book_snapshot(symbol, order_book)

                # Initialize strategies list for order generation
                strategies = list(strategy_instances[symbol].values())

                # Process orders
                for strategy in strategies:
                    try:
                        for order in strategy.generate_orders():
                            trades = matching_engine.match_order(
                                side=order["side"],
                                price=order["price"],
                                quantity=order["quantity"],
                                order_id=str(uuid.uuid4()),
                                source=strategy.source_name
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
                        logger.error(f"Strategy {strategy.source_name} error: {str(e)}", exc_info=True)

                # Handle FIX heartbeats
                if fix_engine.is_heartbeat_due():
                    fix_engine.create_heartbeat()
                    fix_engine.update_heartbeat()

            except Exception as e:
                logger.error(f"Error updating {symbol}: {str(e)}", exc_info=True)
        time.sleep(5)

# Start background thread once
threading.Thread(target=auto_update_order_books, daemon=True).start()

def filter_trades(trades, side=None, source=None, min_price=None, max_price=None):
    filtered = []
    for trade in trades:
        if side and trade.get('side') != side:
            continue
        if source and trade.get('source') != source:
            continue
        price = trade.get('price')
        if min_price is not None and price < min_price:
            continue
        if max_price is not None and price > max_price:
            continue
        filtered.append(trade)
    return filtered

def register_routes(app):
    @app.route("/toggle_exchange", methods=["POST"])
    def toggle_exchange():
        with state_lock:
            trading_state["exchange_halted"] = not trading_state["exchange_halted"]
            status = "halted" if trading_state["exchange_halted"] else "active"
            trading_state["log"].append(f"Exchange {status}")
        return jsonify({"exchange_halted": trading_state["exchange_halted"]})

    @app.route("/toggle_my_strategy", methods=["POST"])
    def toggle_my_strategy():
        with state_lock:
            trading_state["my_strategy_enabled"] = not trading_state["my_strategy_enabled"]
            status = "enabled" if trading_state["my_strategy_enabled"] else "paused"
            trading_state["log"].append(f"MyStrategy {status}")
        return jsonify({"my_strategy_enabled": trading_state["my_strategy_enabled"]})

    @app.route("/status")
    def get_status():
        with state_lock:
            return jsonify({
                "exchange_halted": trading_state["exchange_halted"],
                "my_strategy_enabled": trading_state["my_strategy_enabled"],
                "symbol": trading_state["current_symbol"]
            })

    @app.route("/order_book")
    def get_order_book():
        symbol = trading_state["current_symbol"]
        req_symbol = request.args.get("symbol")
        if req_symbol and req_symbol in symbols.values():
            symbol = req_symbol
        with state_lock:
            ob = trading_state["order_books"][symbol]
            return jsonify({
                "bids": [{"price": p, "qty": sum(o["qty"] for o in q)} for p, q in ob.bids.items()],
                "asks": [{"price": p, "qty": sum(o["qty"] for o in q)} for p, q in ob.asks.items()],
                "last_price": ob.last_price
            })

    def decode_bytes(obj):
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        if isinstance(obj, dict):
            return {k: decode_bytes(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [decode_bytes(i) for i in obj]
        return obj

    @app.route("/trades")
    def get_trades():
        symbol = request.args.get("symbol") or trading_state["current_symbol"]
        side = request.args.get("side")
        source = request.args.get("source")
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        with state_lock:
            if symbol not in trading_state["trades"]:
                return jsonify({'error': 'Invalid or missing symbol'}), 400
            trades = trading_state["trades"][symbol]
            filtered_trades = filter_trades(trades, side, source, min_price, max_price)
            trades = decode_bytes(filtered_trades)
            return jsonify(trades)

    @app.route("/order_book_history")
    def get_order_book_history():
        symbol = request.args.get('symbol') or trading_state["current_symbol"]
        with state_lock:
            if symbol not in trading_state['order_book_history']:
                return jsonify({'error': 'Invalid or missing symbol'}), 400
            history = []
            for entry in trading_state['order_book_history'][symbol]:
                snapshot = entry['snapshot']
                bids = snapshot.get('bids', [])
                asks = snapshot.get('asks', [])
                price_levels = [b['price'] for b in bids] + [a['price'] for a in asks]
                quantities = [b['quantity'] for b in bids] + [a['quantity'] for a in asks]
                history.append({
                    "time": entry['time'],
                    "price_levels": price_levels,
                    "quantities": quantities
                })
            return jsonify(history)

    @app.route("/spread_history")
    def get_spread_history():
        symbol = request.args.get('symbol') or trading_state["current_symbol"]
        with state_lock:
            if symbol not in trading_state['spread_history']:
                return jsonify({'error': 'Invalid or missing symbol'}), 400
            return jsonify(trading_state['spread_history'][symbol])

    @app.route("/liquidity_history")
    def get_liquidity_history():
        symbol = request.args.get('symbol') or trading_state["current_symbol"]
        with state_lock:
            if symbol not in trading_state['liquidity_history']:
                return jsonify({'error': 'Invalid or missing symbol'}), 400
            return jsonify(trading_state['liquidity_history'][symbol])

    @app.route("/strategy_status")
    def strategy_status():
        symbol = request.args.get("symbol") or trading_state["current_symbol"]
        with state_lock:
            strategies = strategy_instances.get(symbol, {})
            status = {}
            for name, strat in strategies.items():
                # Get current market price for unrealized PnL
                try:
                    current_price = strat.order_book.get_mid_price()
                except Exception:
                    current_price = strat.order_book.last_price
                # Defensive fallback
                if current_price is None:
                    current_price = 0.0
                status[name] = {
                    "inventory": getattr(strat, "inventory", 0),
                    "realized_pnl": strat.realized_pnl,
                    "realized_pnl_percent": strat.realized_pnl / strat.initial_capital * 100 if strat.initial_capital else 0,
                    "unrealized_pnl": strat.unrealized_pnl(),
                    "unrealized_pnl_percent": strat.unrealized_pnl() / strat.initial_capital * 100 if strat.initial_capital else 0,
                    "total_pnl": strat.total_pnl(),
                    "total_pnl_percent": strat.total_pnl() / strat.initial_capital * 100 if strat.initial_capital else 0,
                    "inventory_percent": strat.inventory / strat.max_inventory * 100 if hasattr(strat, "max_inventory") and strat.max_inventory else 0,
                    "total_trades": strat.total_trades,
                    "win_rate": getattr(strat, "get_win_rate", lambda: 0.0)()
                }
            return jsonify(status)

    @app.route("/select_symbol", methods=["POST"])
    def select_symbol():
        data = request.get_json()
        symbol = data.get("symbol") or data.get("ticker")
        with state_lock:
            if symbol in symbols.values():
                trading_state["current_symbol"] = symbol
                trading_state["log"].append(f"Symbol selected: {symbol}")
                return jsonify({"status": "symbol_changed", "symbol": symbol})
            return jsonify({"error": "Invalid symbol"}), 400

    @app.route('/order_latency_history')
    def order_latency_history():
        symbol = request.args.get('symbol') or trading_state['current_symbol']
        with state_lock:
            latency_data = trading_state.get('latency_history', {}).get(symbol, [])
            return jsonify(latency_data)

    @app.route("/")
    def index():
        return render_template("index.html", symbols=symbols)
