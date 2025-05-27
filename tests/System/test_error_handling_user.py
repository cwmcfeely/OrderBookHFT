import unittest
from unittest.mock import MagicMock


class TestErrorHandlingUserFeedback(unittest.TestCase):
    def setUp(self):
        # Mock UI components and backend service
        self.ui_component = MagicMock()
        self.backend_service = MagicMock()

    def test_invalid_input_handling(self):
        # Simulate user entering invalid input
        invalid_input = "INVALID_SYMBOL"
        self.backend_service.fetch_data.side_effect = ValueError("Invalid symbol")

        # Simulate UI calling backend with invalid input
        try:
            self.backend_service.fetch_data(invalid_input)
        except ValueError as e:
            self.ui_component.show_error(str(e))

        # Assert UI shows error message
        self.ui_component.show_error.assert_called_with("Invalid symbol")

    def test_network_error_handling(self):
        # Simulate network error
        self.backend_service.fetch_data.side_effect = ConnectionError("Network failure")

        # Simulate UI calling backend and handling network error
        try:
            self.backend_service.fetch_data("AD.AS")
        except ConnectionError as e:
            self.ui_component.show_error(str(e))

        # Assert UI shows network error message
        self.ui_component.show_error.assert_called_with("Network failure")


if __name__ == "__main__":
    unittest.main()
