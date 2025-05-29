import os


def test_eod_api_key_set():
    API_KEY = os.environ.get("EOD_API_KEY")
    print(f"EOD_API_KEY present in test: {'YES' if API_KEY else 'NO'} (length: {len(API_KEY) if API_KEY else 0})")
    assert API_KEY, "EOD_API_KEY is not set in integration test environment"