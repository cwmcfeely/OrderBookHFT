import time
import requests

def test_order_lifecycle():
    symbols = ["PHIA.AS", "ASML.AS", "SAN.PA", "AS.AS"]
    found_trade = False

    for symbol in symbols:
        # Try to submit a buy order directly
        payload = {"symbol": symbol, "side": "buy", "qty": 10, "price": 100}
        resp = requests.post("http://localhost:8000/order", json=payload)
        assert resp.status_code == 200

        # Optionally submit a matching sell order for guaranteed matching
        # payload_sell = {"symbol": symbol, "side": "sell", "qty": 10, "price": 100}
        # requests.post("http://localhost:8000/order", json=payload_sell)

        for _ in range(5):
            time.sleep(1)
            trades = requests.get(f"http://localhost:8000/trades?symbol={symbol}").json()
            if any(trade.get("qty", 0) > 0 for trade in trades):
                found_trade = True
                break
        if found_trade:
            break

    if not found_trade:
        print("--- No trades found for any symbol ---")
        for symbol in symbols:
            trades = requests.get(f"http://localhost:8000/trades?symbol={symbol}").json()
            print(f"{symbol}: {trades}")
        assert False, "No trades with qty > 0 found for any tested symbol"