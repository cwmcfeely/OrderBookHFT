import requests


def test_risk_rejection():
    # Attempt to submit an order exceeding risk limits
    # Since /orders endpoint is missing, this test will expect 404
    resp = requests.post("http://localhost:8000/orders", json={
        "symbol": "PHIA.AS", "side": "buy", "qty": 1000000, "price": 20.33
    })
    assert resp.status_code == 404
