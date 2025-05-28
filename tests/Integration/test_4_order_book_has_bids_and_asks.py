import requests


def test_order_book_has_bids_or_asks():
    symbols = ["AD.AS", "ASML.AS", "INGA.AS", "OR.PA", "PHIA.AS", "SAN.PA"]
    found = False
    for symbol in symbols:
        resp = requests.get(f"http://localhost:8000/order_book?symbol={symbol}")
        if resp.status_code != 200:
            continue
        data = resp.json()
        if ("bids" in data and any(bid["qty"] > 0 for bid in data["bids"])) or \
           ("asks" in data and any(ask["qty"] > 0 for ask in data["asks"])):
            found = True
            break
    assert found, "No bids or asks with qty > 0 found for any tested symbol"