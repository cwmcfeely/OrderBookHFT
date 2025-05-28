import time
import requests

def test_order_lifecycle():
    symbol = "PHIA.AS"
    # Submit a buy order
    resp1 = requests.post("http://localhost:8000/orders", json={
        "symbol": symbol, "side": "buy", "qty": 10, "price": 100
    })
    assert resp1.status_code == 200

    # Submit a sell order
    resp2 = requests.post("http://localhost:8000/orders", json={
        "symbol": symbol, "side": "sell", "qty": 10, "price": 100
    })
    assert resp2.status_code == 200

    # Wait for the trade to be processed
    for _ in range(10):
        trades = requests.get(f"http://localhost:8000/trades?symbol={symbol}").json()
        if any(trade.get("qty", 0) > 0 for trade in trades):
            break
        time.sleep(1)
    else:
        print(f"No trades found for {symbol}: {trades}")
        assert False, "No trades with qty > 0 found for the tested symbol"
