import os


def test_eod_api_key_set():
    api_key = os.environ.get("EOD_API_KEY")
    print(f"EOD_API_KEY present in test: {'YES' if api_key else 'NO'} (length: {len(api_key) if api_key else 0})")
    assert api_key, "EOD_API_KEY is not set in integration test environment"