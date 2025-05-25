import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(
    level=logging.INFO,
    app_log_file="logs/app.debug.log",
    fix_server_log_file="logs/fix_server.log",
    strategies=None  # List of strategy names, e.g. ["my_strategy", "market_maker"]
):
    """
    Set up logging configuration for the application, including:
    - Root logger for general application and debug logs
    - Dedicated FIX server logger for FIX protocol related logs (e.g., heartbeats)
    - Per-strategy FIX loggers for isolated logging of each trading strategy

    This function ensures that log directories exist and configures rotating file handlers
    to limit log file size and maintain backups.
    """
    # Ensure the directory for the application log file exists, create if missing
    Path(app_log_file).parent.mkdir(parents=True, exist_ok=True)
    # Ensure the directory for the FIX server log file exists, create if missing
    Path(fix_server_log_file).parent.mkdir(parents=True, exist_ok=True)
    # For each strategy, ensure its dedicated log directory exists
    if strategies:
        for strat in strategies:
            Path(f"logs/fix_{strat}.log").parent.mkdir(parents=True, exist_ok=True)

    # --- Root logger setup for general application and debug logging ---
    root_logger = logging.getLogger()  # Get the root logger
    root_logger.handlers.clear()  # Clear any existing handlers to avoid duplicate logs

    # Create a rotating file handler for the application log file
    file_handler = RotatingFileHandler(
        app_log_file,
        maxBytes=1024 * 1024,  # Rotate after 1 MB
        backupCount=5,         # Keep last 5 log files as backup
        encoding='utf-8'       # Use UTF-8 encoding for log files
    )
    # Define a formatter with timestamp, log level, and message
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Create a console handler to output logs to stdout
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Set the logging level for the root logger (e.g., INFO, DEBUG)
    root_logger.setLevel(level)
    # Add both file and console handlers to the root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # --- Logger specifically for all FIX server activity (heartbeats, messages, etc) ---
    fix_server_logger = logging.getLogger("FIXServer")  # Named logger for FIX server
    fix_server_logger.handlers.clear()  # Clear existing handlers

    # Rotating file handler for FIX server logs with larger size and more backups
    fix_server_handler = RotatingFileHandler(
        fix_server_log_file,
        maxBytes=2 * 1024 * 1024,  # Rotate after 2 MB
        backupCount=10,            # Keep last 10 logs
        encoding='utf-8'
    )
    fix_server_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Set FIX server logger level to INFO (can be adjusted if needed)
    fix_server_logger.setLevel(logging.INFO)
    fix_server_logger.addHandler(fix_server_handler)
    fix_server_logger.propagate = False  # Prevent logs from propagating to root logger

    # --- Per-strategy FIX loggers for isolated logging per strategy ---
    if strategies:
        for strat in strategies:
            # Get or create a logger for the strategy, e.g. "FIX_my_strategy"
            strat_fix_logger = logging.getLogger(f"FIX_{strat}")
            strat_fix_logger.handlers.clear()  # Clear existing handlers

            # Rotating file handler for this strategy's FIX logs
            strat_fix_handler = RotatingFileHandler(
                f"logs/fix_{strat}.log",
                maxBytes=2 * 1024 * 1024,  # Rotate after 2 MB
                backupCount=10,            # Keep last 10 logs
                encoding='utf-8'
            )
            strat_fix_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

            strat_fix_logger.setLevel(logging.INFO)  # Set level to INFO
            strat_fix_logger.addHandler(strat_fix_handler)
            strat_fix_logger.propagate = False  # Prevent propagation to root logger

    # --- Optional: Disable propagation for other noisy modules ---
    # For example, disable propagation for 'market_data' module logs if too verbose
    logging.getLogger("market_data").propagate = False


def get_logger(name):
    """
    Helper function to retrieve a logger by name.
    Args:
        name (str): Name of the logger (usually module or component name)
    Returns:
        logging.Logger: The requested logger instance
    """
    return logging.getLogger(name)
