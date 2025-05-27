def test_fix_logging():
    # Check that FIX log file contains expected message
    with open("logs/fix_my_strategy.log") as f:
        log = f.read()
    assert "8=FIX.4.4" in log
    assert "Trade executed" in log
