import time

import requests


def test_order_lifecycle():
    # Submit a new order
    resp = requests.post("http://localhost:8000/toggle_my_strategy")
    assert resp.status_code == 200

    # Wait for matching/execution
    time.sleep(1)

    # Fetch order book and trades
    trades = requests.get("http://localhost:8000/trades?symbol=PHIA.AS").json()
    assert any(trade["qty"] > 0 for trade in trades)
