import time


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