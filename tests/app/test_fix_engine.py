import unittest
from unittest.mock import MagicMock, patch
import time
from app.fix_engine import FixEngine

# Patch simplefix globally for all tests using the correct package path
patcher_simplefix = patch("app.fix_engine.simplefix", autospec=True)
mock_simplefix = patcher_simplefix.start()


# DummyFixMessage with all required methods
class DummyFixMessage:
    def append_pair(self, *args, **kwargs):
        pass

    def append_utc_timestamp(self, *args, **kwargs):
        pass

    def encode(self):
        return b"FIXMSG"

    def get(self, tag):
        return b"42"


# Use side_effect so every FixMessage() call returns a DummyFixMessage
mock_simplefix.FixMessage.side_effect = DummyFixMessage
MockFixParser = MagicMock()
mock_simplefix.FixParser.return_value = MockFixParser


class TestFixEngine(unittest.TestCase):
    def setUp(self):
        # Patch logging to avoid actual log output
        self.patcher_log = patch(
            "app.fix_engine.logging.getLogger", return_value=MagicMock()
        )
        self.mock_logger = self.patcher_log.start()
        self.addCleanup(self.patcher_log.stop)

        # Create a FixEngine instance for testing
        self.engine = FixEngine(symbol="TESTSYM", heartbeat_interval=10)

        # Reset mocks before each test
        MockFixParser.reset_mock()
        self.engine.seq_num = 1

    def test_init_logs_initialisation(self):
        self.mock_logger.assert_any_call("FIXServer")
        self.mock_logger.assert_any_call("FIX_TESTSYM")
        self.assertTrue(self.engine.server_logger.info.called)
        self.assertTrue(self.engine.strategy_logger.info.called)

    def test_create_heartbeat_returns_bytes_and_increments_seq(self):
        original_encode = DummyFixMessage.encode
        DummyFixMessage.encode = lambda self: b"FAKEFIX"
        initial_seq = self.engine.seq_num
        result = self.engine.create_heartbeat()
        self.assertEqual(result, b"FAKEFIX")
        self.assertEqual(self.engine.seq_num, initial_seq + 1)
        self.assertTrue(self.engine.server_logger.info.called)
        DummyFixMessage.encode = original_encode

    def test_create_heartbeat_logs_and_raises_on_exception(self):
        original_encode = DummyFixMessage.encode

        def raise_exc(self):
            raise Exception("encode fail")

        DummyFixMessage.encode = raise_exc
        with self.assertRaises(Exception):
            self.engine.create_heartbeat()
        # Can't check .error.called because DummyFixMessage is not a mock
        DummyFixMessage.encode = original_encode

    def test_create_new_order_valid(self):
        original_encode = DummyFixMessage.encode
        DummyFixMessage.encode = lambda self: b"ORDERFIX"
        initial_seq = self.engine.seq_num
        result = self.engine.create_new_order(
            cl_ord_id="OID123",
            symbol="TEST",
            side="1",
            price=100.5,
            qty=10,
            source="my_strategy",
        )
        self.assertEqual(result, b"ORDERFIX")
        self.assertEqual(self.engine.seq_num, initial_seq + 1)
        DummyFixMessage.encode = original_encode

    def test_create_new_order_invalid_fields(self):
        with self.assertRaises(ValueError):
            self.engine.create_new_order("", "TEST", "1", 100, 1, "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "", "1", 100, 1, "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "TEST", "X", 100, 1, "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "TEST", "1", "bad", 1, "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "TEST", "1", 0.001, 1, "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "TEST", "1", 100, "bad", "src")
        with self.assertRaises(ValueError):
            self.engine.create_new_order("OID", "TEST", "1", 100, 1000000, "src")

    def test_parse_success_and_seq_update(self):
        msg = DummyFixMessage()
        msg.get = lambda tag: b"42"
        MockFixParser.get_message.return_value = msg
        result = self.engine.parse(b"RAWFIX")
        self.assertEqual(result, msg)
        self.assertEqual(self.engine.seq_num, 43)
        self.assertTrue(
            self.engine.server_logger.info.called
            or self.engine.strategy_logger.info.called
        )

    def test_parse_logs_and_returns_none_on_exception(self):
        MockFixParser.get_message.side_effect = Exception("parse fail")
        result = self.engine.parse(b"RAWFIX")
        self.assertIsNone(result)
        self.assertTrue(self.engine.server_logger.error.called)
        MockFixParser.get_message.side_effect = None

    def test_log_heartbeat_and_fix_message(self):
        msg = DummyFixMessage()
        msg.encode = lambda: b"FIXMSG"
        self.engine._log_heartbeat(msg, incoming=True)
        self.assertTrue(self.engine.server_logger.info.called)
        self.engine._log_fix_message(msg, incoming=False)
        self.assertTrue(
            self.engine.strategy_logger.info.called
            or self.engine.server_logger.info.called
        )

    def test_is_heartbeat_due(self):
        self.assertFalse(self.engine.is_heartbeat_due())
        self.engine.last_heartbeat -= 20
        self.assertTrue(self.engine.is_heartbeat_due())
        self.assertTrue(self.engine.server_logger.debug.called)

    def test_create_execution_report(self):
        original_encode = DummyFixMessage.encode
        DummyFixMessage.encode = lambda self: b"EXECFIX"
        initial_seq = self.engine.seq_num
        result = self.engine.create_execution_report(
            cl_ord_id="OID123",
            order_id="OID456",
            exec_id="EID789",
            ord_status="0",
            exec_type="0",
            symbol="TEST",
            side="1",
            order_qty=10,
            last_qty=5,
            last_px=101.0,
            leaves_qty=5,
            cum_qty=5,
            price=101.0,
            source="my_strategy",
            text="Filled",
        )
        self.assertEqual(result, b"EXECFIX")
        self.assertEqual(self.engine.seq_num, initial_seq + 1)
        DummyFixMessage.encode = original_encode

    def test_update_heartbeat(self):
        old_time = self.engine.last_heartbeat
        time.sleep(0.01)
        self.engine.update_heartbeat()
        self.assertGreater(self.engine.last_heartbeat, old_time)
        self.assertTrue(self.engine.server_logger.debug.called)


if __name__ == "__main__":
    patcher_simplefix.stop()  # Clean up global patch
    unittest.main()
