import requests
import time

def test_order_latency():
    # Use /toggle_my_strategy as a proxy for latency measurement
    start = time.time()
    resp = requests.post("http://localhost:8000/toggle_my_strategy")
    assert resp.status_code == 200
    latency = time.time() - start
    assert latency < 2  # Example threshold (adjust as needed)
