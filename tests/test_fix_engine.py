import unittest
from app.fix_engine import FixEngine

class TestFixEngine(unittest.TestCase):

    def setUp(self):
        # Initialize FixEngine instance
        self.fix_engine = FixEngine()

    def test_parse_valid_message(self):
        # Test parsing a valid FIX message
        fix_message = "8=FIX.4.2|9=99|35=D|49=SenderCompID|56=TargetCompID|34=1|52=2025-05-10 12:34:56|11=12345|21=1|54=1|38=100|55=ASML.AS|10=128|"
        parsed_message = self.fix_engine.parse_message(fix_message)
        self.assertIsNotNone(parsed_message)
        self.assertEqual(parsed_message['8'], "FIX.4.2")
        self.assertEqual(parsed_message['35'], "D")
        self.assertEqual(parsed_message['11'], "12345")

    def test_parse_invalid_message(self):
        # Test parsing an invalid FIX message (missing fields or corrupted)
        invalid_fix_message = "8=FIX.4.2|9=99|35=D|49=SenderCompID|56=TargetCompID|34=1|52=2025-05-10 12:34:56|"
        parsed_message = self.fix_engine.parse_message(invalid_fix_message)
        self.assertIsNone(parsed_message)

    def test_validate_heartbeat(self):
        # Test heartbeat message
        heartbeat_message = "8=FIX.4.2|9=99|35=0|49=SenderCompID|56=TargetCompID|34=2|52=2025-05-10 12:34:57|10=130|"
        is_heartbeat = self.fix_engine.validate_heartbeat(heartbeat_message)
        self.assertTrue(is_heartbeat)

    def test_validate_order_message(self):
        # Test an order message
        order_message = "8=FIX.4.2|9=99|35=D|49=SenderCompID|56=TargetCompID|34=1|52=2025-05-10 12:34:56|11=12345|21=1|54=1|38=100|55=ASML.AS|10=128|"
        is_valid_order = self.fix_engine.validate_order_message(order_message)
        self.assertTrue(is_valid_order)

    def test_heartbeat_tracking(self):
        # Test the tracking of heartbeats
        heartbeat_message = "8=FIX.4.2|9=99|35=0|49=SenderCompID|56=TargetCompID|34=2|52=2025-05-10 12:34:57|10=130|"
        self.fix_engine.receive_message(heartbeat_message)
        self.assertIn("heartbeat", self.fix_engine.heartbeat_log)
        self.assertEqual(len(self.fix_engine.heartbeat_log), 1)

    def test_handle_invalid_message(self):
        # Test invalid message handling
        invalid_message = "Invalid FIX Message"
        response = self.fix_engine.receive_message(invalid_message)
        self.assertEqual(response, "Invalid message format")

if __name__ == '__main__':
    unittest.main()
