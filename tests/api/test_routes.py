import unittest
from unittest.mock import patch, MagicMock
from api import create_app


class TestRoutes(unittest.TestCase):
    def setUp(self):
        # Create a test app and client for each test
        self.app = create_app()
        self.client = self.app.test_client()

        # Patch the global trading_state and state_lock to avoid threading issues
        patcher_state = patch(
            "api.routes.trading_state",
            {
                "exchange_halted": False,
                "my_strategy_enabled": True,
                "current_symbol": "TESTSYM",
                "order_books": {},
                "trades": {},
                "log": [],
                "order_book_history": {},
                "spread_history": {},
                "liquidity_history": {},
                "latency_history": {},
                "execution_reports": {},
                "competition_logs": {},
            },
        )
        patcher_lock = patch("api.routes.state_lock", MagicMock())
        self.mock_state = patcher_state.start()
        self.mock_lock = patcher_lock.start()
        self.addCleanup(patcher_state.stop)
        self.addCleanup(patcher_lock.stop)

    def test_toggle_exchange(self):
        response = self.client.post("/toggle_exchange")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("exchange_halted", data)

    def test_toggle_my_strategy(self):
        response = self.client.post("/toggle_my_strategy")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("my_strategy_enabled", data)

    def test_cancel_mystrategy_orders_invalid_symbol(self):
        response = self.client.post(
            "/cancel_mystrategy_orders", json={"symbol": "INVALID"}
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["status"], "error")

    def test_get_status(self):
        response = self.client.get("/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("exchange_halted", data)
        self.assertIn("my_strategy_enabled", data)
        self.assertIn("symbol", data)

    def test_get_order_book(self):
        from api.routes import trading_state

        class DummyOrderBook:
            def __init__(self):
                self.bids = {100: [{"qty": 10, "source": "my_strategy"}]}
                self.asks = {101: [{"qty": 5, "source": "my_strategy"}]}
                self.last_price = 100.5

        trading_state["order_books"] = {"TESTSYM": DummyOrderBook()}
        trading_state["current_symbol"] = "TESTSYM"
        response = self.client.get("/order_book")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("bids", data)
        self.assertIn("asks", data)
        self.assertIn("last_price", data)

    def test_get_trades(self):
        from api.routes import trading_state

        trading_state["trades"] = {
            "TESTSYM": [{"side": "1", "source": "my_strategy", "price": 100}]
        }
        response = self.client.get("/trades")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_get_order_book_history(self):
        from api.routes import trading_state

        trading_state["order_book_history"] = {
            "TESTSYM": [
                {
                    "time": "now",
                    "snapshot": {
                        "bids": [{"price": 100, "quantity": 10}],
                        "asks": [{"price": 101, "quantity": 5}],
                    },
                }
            ]
        }
        response = self.client.get("/order_book_history")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_get_spread_history(self):
        from api.routes import trading_state

        trading_state["spread_history"] = {
            "TESTSYM": [{"time": "now", "mid": 100, "spread": 1}]
        }
        response = self.client.get("/spread_history")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_get_liquidity_history(self):
        from api.routes import trading_state

        trading_state["liquidity_history"] = {
            "TESTSYM": [{"time": "now", "liquidity": 1000}]
        }
        response = self.client.get("/liquidity_history")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_strategy_status(self):
        from api.routes import trading_state, strategy_instances

        # Define a dummy order book with required attributes/methods
        class DummyOrderBook:
            last_price = 101

            def get_mid_price(self):
                return 101

        # Define DummyStrategy with an order_book attribute
        class DummyStrategy:
            def __init__(self):
                self.realised_pnl = 100
                self.initial_capital = 10000
                self.max_inventory = 100
                self.inventory = 10
                self.order_book = DummyOrderBook()  # Add this line

            def get_win_rate(self):
                return 0.5

            def unrealised_pnl(self):
                return 50

            def total_pnl(self):
                return 150

        strategy_instances["TESTSYM"] = {"my_strategy": DummyStrategy()}
        trading_state["trades"] = {"TESTSYM": [{"source": "my_strategy"}]}
        response = self.client.get("/strategy_status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("my_strategy", data)

    def test_get_execution_reports(self):
        from api.routes import trading_state

        trading_state["execution_reports"] = {"TESTSYM": [{"source": "my_strategy"}]}
        response = self.client.get("/execution_reports")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_select_symbol_valid_and_invalid(self):
        from api.routes import symbols

        symbols["SYM1"] = "TESTSYM"
        # Valid symbol
        response = self.client.post("/select_symbol", json={"symbol": "TESTSYM"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "symbol_changed")
        # Invalid symbol
        response = self.client.post("/select_symbol", json={"symbol": "INVALID"})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"], "Invalid symbol")

    def test_order_latency_history(self):
        from api.routes import trading_state

        trading_state["latency_history"] = {"TESTSYM": [{"latency": 10}]}
        response = self.client.get("/order_latency_history")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)

    def test_index(self):
        from api.routes import symbols

        symbols["SYM1"] = "TESTSYM"
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)  # Should return HTML

    def test_get_competition_logs(self):
        from api.routes import trading_state

        trading_state["competition_logs"] = {"TESTSYM": [{"log": "test"}]}
        response = self.client.get("/competition_logs")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
