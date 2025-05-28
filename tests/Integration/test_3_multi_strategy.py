import requests


def test_multi_strategy():
    # Enable two strategies (the only available endpoint is /toggle_my_strategy)
    # Note: Your backend does not support specifying the strategy or symbol in the request.
    # This test toggles "my_strategy" twice to simulate enabling/disabling.
    for _ in [("my_strategy", "PHIA.AS"), ("market_maker", "AD.AS")]:
        resp = requests.post("http://localhost:8000/toggle_my_strategy")
        assert resp.status_code == 200
