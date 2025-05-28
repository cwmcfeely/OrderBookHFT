import time
import requests


def test_order_book_has_bids_and_asks():
    resp = requests.get("http://localhost:8000/order_book?symbol=PHIA.AS")
    assert resp.status_code == 200
    data = resp.json()
    assert "bids" in data and "asks" in data
    assert any(bid["qty"] > 0 for bid in data["bids"])
    assert any(ask["qty"] > 0 for ask in data["asks"])

