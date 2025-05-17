import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def setup_logging(
    level=logging.INFO,
    app_log_file="logs/app.debug.log",
    fix_server_log_file="logs/fix_server.log",
    strategies=None  # List of strategy names, e.g. ["my_strategy", "market_maker"]
):
    # Ensure log directories exist
    Path(app_log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(fix_server_log_file).parent.mkdir(parents=True, exist_ok=True)
    if strategies:
        for strat in strategies:
            Path(f"logs/fix_{strat}.log").parent.mkdir(parents=True, exist_ok=True)

    # --- Root logger for general app/debug logging ---
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    file_handler = RotatingFileHandler(
        app_log_file,
        maxBytes=1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # --- Logger for all FIX server activity (heartbeats, etc) ---
    fix_server_logger = logging.getLogger("FIXServer")
    fix_server_logger.handlers.clear()
    fix_server_handler = RotatingFileHandler(
        fix_server_log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=10,
        encoding='utf-8'
    )
    fix_server_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    fix_server_logger.setLevel(logging.INFO)
    fix_server_logger.addHandler(fix_server_handler)
    fix_server_logger.propagate = False

    # --- Per-strategy FIX loggers ---
    if strategies:
        for strat in strategies:
            strat_fix_logger = logging.getLogger(f"FIX_{strat}")
            strat_fix_logger.handlers.clear()
            strat_fix_handler = RotatingFileHandler(
                f"logs/fix_{strat}.log",
                maxBytes=2 * 1024 * 1024,
                backupCount=10,
                encoding='utf-8'
            )
            strat_fix_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            strat_fix_logger.setLevel(logging.INFO)
            strat_fix_logger.addHandler(strat_fix_handler)
            strat_fix_logger.propagate = False

    # --- Optional: other module loggers ---
    logging.getLogger("market_data").propagate = False

def get_logger(name):
    """Helper to get a logger for any module/component."""
    return logging.getLogger(name)
