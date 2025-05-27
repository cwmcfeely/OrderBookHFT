import requests


def test_market_data():
    resp = requests.get("http://localhost:8000/order_book?symbol=PHIA.AS")
    assert resp.status_code == 200
    data = resp.json()
    assert "bids" in data and "asks" in data
