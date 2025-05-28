import time
import requests

def test_order_lifecycle():
    symbols = ["AD.AS", "ASML.AS", "INGA.AS", "OR.PA", "PHIA.AS", "SAN.PA"]
    found_trade = False

    # Wait a little to allow background strategies to generate orders/trades
    for _ in range(60):  # Try for up to 10 seconds
        for symbol in symbols:
            trades = requests.get(f"http://localhost:8000/trades?symbol={symbol}").json()
            if any(trade.get("qty", 0) > 0 for trade in trades):
                found_trade = True
                break
        if found_trade:
            break
        time.sleep(1)

    if not found_trade:
        print("--- No trades found for any symbol ---")
        for symbol in symbols:
            trades = requests.get(f"http://localhost:8000/trades?symbol={symbol}").json()
            print(f"{symbol}: {trades}")
    assert found_trade, "No trades with qty > 0 found for any tested symbol"