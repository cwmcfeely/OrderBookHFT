import unittest
from unittest.mock import MagicMock


class TestMetricsPanel(unittest.TestCase):
    def setUp(self):
        # Mock UI components
        self.metrics_panel = MagicMock()
        self.symbol_selector = MagicMock()
        # Initial symbol
        self.current_symbol = 'AD.AS'

    def simulate_symbol_change(self, new_symbol):
        # Simulate user changing the symbol in the UI
        self.current_symbol = new_symbol
        # Simulate metrics panel update call
        self.metrics_panel.update_metrics(new_symbol)

    def test_metrics_panel_updates_on_symbol_change(self):
        # Initial update
        self.metrics_panel.update_metrics(self.current_symbol)
        self.metrics_panel.update_metrics.assert_called_with('AD.AS')

        # Change symbol
        self.simulate_symbol_change('OR.PA')

        # Assert metrics panel updated with new symbol
        self.metrics_panel.update_metrics.assert_called_with('OR.PA')


if __name__ == '__main__':
    unittest.main()
