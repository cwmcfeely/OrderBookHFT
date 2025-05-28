import time
import requests

def test_order_lifecycle():
    symbols = ["PHIA.AS", "ASML.AS", "SAN.PA", "AS.AS"]  # Add any symbols you expect to be available
    found_trade = False

    for symbol in symbols:
        # Submit a new order (optionally, parameterize endpoint for symbol)
        resp = requests.post("http://localhost:8000/toggle_my_strategy")
        assert resp.status_code == 200

        # Wait and poll for trades
        for _ in range(5):  # Try for up to 5 seconds per symbol
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