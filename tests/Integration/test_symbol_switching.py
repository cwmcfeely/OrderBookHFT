import requests


def test_symbol_switching():
    # Switch symbol to PHIA.AS
    resp = requests.post("http://localhost:8000/select_symbol", json={"ticker": "PHIA.AS"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('status') == 'symbol_changed'
    assert data.get('symbol') == 'PHIA.AS'

    # Now fetch order book for PHIA.AS
    resp = requests.get("http://localhost:8000/order_book?symbol=PHIA.AS")
    assert resp.status_code == 200
    data = resp.json()
    assert "bids" in data and "asks" in data

    # Switch symbol to AD.AS
    resp = requests.post("http://localhost:8000/select_symbol", json={"ticker": "AD.AS"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get('status') == 'symbol_changed'
    assert data.get('symbol') == 'AD.AS'

    # Now fetch order book for AD.AS
    resp = requests.get("http://localhost:8000/order_book?symbol=AD.AS")
    assert resp.status_code == 200
    data = resp.json()
    assert "bids" in data and "asks" in data
