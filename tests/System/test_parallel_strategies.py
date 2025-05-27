import threading
import time
import unittest

from app.fix_engine import FixEngine
from app.order_book import OrderBook
from strategies.competitor_strategy import PassiveLiquidityProvider
from strategies.competitor_strategy1 import MarketMakerStrategy
from strategies.competitor_strategy2 import MomentumStrategy


class TestParallelStrategiesSystem(unittest.TestCase):
    def setUp(self):
        # Shared order book and symbol for all strategies
        self.symbol = "TESTSYM"
        self.order_book = OrderBook(symbol=self.symbol)
        self.fix_engine_mm = FixEngine(symbol="market_maker")
        self.fix_engine_mom = FixEngine(symbol="momentum")
        self.fix_engine_pas = FixEngine(symbol="passive")
        # Patch parse for deterministic behaviour
        self.fix_engine_mm.parse = lambda msg: {54: "1", 44: 100, 38: 5, 11: "OID_MM"}
        self.fix_engine_mom.parse = lambda msg: {54: "2", 44: 101, 38: 7, 11: "OID_MOM"}
        self.fix_engine_pas.parse = lambda msg: {54: "1", 44: 99, 38: 3, 11: "OID_PAS"}
        # Instantiate strategies
        self.market_maker = MarketMakerStrategy(
            fix_engine=self.fix_engine_mm,
            order_book=self.order_book,
            symbol=self.symbol,
            params={"max_order_qty": 100, "max_price_deviation": 0.02},
        )
        self.momentum = MomentumStrategy(
            fix_engine=self.fix_engine_mom,
            order_book=self.order_book,
            symbol=self.symbol,
            params={"max_order_qty": 100, "max_price_deviation": 0.02},
        )
        self.passive = PassiveLiquidityProvider(
            fix_engine=self.fix_engine_pas,
            order_book=self.order_book,
            symbol=self.symbol,
        )
        # Initial market data
        self.order_book.asks = {100: [{"qty": 200}]}
        self.order_book.bids = {99: [{"qty": 200}]}
        self.order_book.last_price = 99.5

    def run_strategy(self, strategy, n_iters=3):
        for _ in range(n_iters):
            strategy.last_order_time = time.time() - 10  # ensure not in cooldown
            strategy.generate_orders()
            time.sleep(0.1)  # Simulate time between cycles

    def test_parallel_strategies(self):
        # Run all strategies in parallel threads
        threads = [
            threading.Thread(target=self.run_strategy, args=(self.market_maker,)),
            threading.Thread(target=self.run_strategy, args=(self.momentum,)),
            threading.Thread(target=self.run_strategy, args=(self.passive,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Simulate trade fills for each strategy
        self.market_maker.on_trade({"side": "1", "qty": 5, "price": 100})
        self.momentum.on_trade({"side": "2", "qty": 7, "price": 101})
        self.passive.on_trade({"side": "1", "qty": 3, "price": 99})

        mm_inventory = self.market_maker.inventory
        mom_inventory = self.momentum.inventory
        pas_inventory = self.passive.inventory
        print("Market Maker Inventory:", mm_inventory)
        print("Momentum Inventory:", mom_inventory)
        print("Passive Provider Inventory:", pas_inventory)

        # Check that orders from all strategies are present in the order book
        all_orders = []
        for book in [self.order_book.bids, self.order_book.asks]:
            for price, queue in book.items():
                all_orders.extend(queue)
        oids = {
            o.get("order_id") or o.get("id") for o in all_orders if isinstance(o, dict)
        }
        self.assertIn("OID_MM", oids)
        self.assertIn("OID_MOM", oids)
        self.assertIn("OID_PAS", oids)

        # Assert that each strategy's inventory is non-zero (i.e., each placed and filled orders)
        self.assertNotEqual(mm_inventory, 0)
        self.assertNotEqual(mom_inventory, 0)
        self.assertNotEqual(pas_inventory, 0)


if __name__ == "__main__":
    unittest.main()
