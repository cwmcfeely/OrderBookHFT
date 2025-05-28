import time
import os


def test_eod_api_key_set():
    api_key = os.environ.get("EOD_API_KEY")
    print(f"EOD_API_KEY present in test: {'YES' if api_key else 'NO'} (length: {len(api_key) if api_key else 0})")
    assert api_key, "EOD_API_KEY is not set in integration test environment"


def test_fix_logging():
    found = False
    for _ in range(20):  # Try for up to 10 seconds
        with open("logs/fix_my_strategy.log") as f:
            log = f.read()
        if "8=FIX.4.4" in log:
            found = True
            break
        time.sleep(1)
    assert found, "Expected FIX message not found in log"