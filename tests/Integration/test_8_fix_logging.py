import time


def test_fix_logging():
    found = False
    log_content = ""
    for _ in range(20):  # Try for up to 20 seconds
        with open("logs/fix_my_strategy.log") as f:
            log_content = f.read()
        if "===== FIX ENGINE INITIALISED FOR SYMBOL my_strategy =====" in log_content:
            found = True
            break
        time.sleep(1)
    if not found:
        print("--- Fix log content at failure ---")
        print(log_content)
    assert found, "Expected FIX message not found in log"