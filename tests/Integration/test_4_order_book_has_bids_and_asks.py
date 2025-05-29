import requests
import time


def test_order_book_has_bids_or_asks():
    symbols = ["AD.AS", "ASML.AS", "INGA.AS", "OR.PA", "PHIA.AS", "SAN.PA"]
    found = False
    last_data = {}
    for attempt in range(10):  # Try for up to 10 seconds
        for symbol in symbols:
            resp = requests.get(f"http://localhost:8000/order_book?symbol={symbol}")
            if resp.status_code != 200:
                continue
            data = resp.json()
            last_data[symbol] = data
            if ("bids" in data and any(bid["qty"] > 0 for bid in data["bids"])) or \
               ("asks" in data and any(ask["qty"] > 0 for ask in data["asks"])):
                found = True
                break
        if found:
            break
        time.sleep(1)
    else:
        print("Order book data at test time:")
        for symbol, data in last_data.items():
            print(f"{symbol}: {data}")
    assert found, "No bids or asks with qty > 0 found for any tested symbol"