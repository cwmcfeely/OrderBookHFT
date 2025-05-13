import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger(__name__)
logger.propagate = False

def setup_logging(level=logging.INFO, log_file="logs/app_debug.log"):
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Clear existing handlers to avoid duplicates

    # Configure file handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1024 * 1024,  # 1 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    # Add handlers to root logger
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Disable propagation for all custom loggers to prevent duplicate logs
    logging.getLogger("FIXEngine").propagate = False
    logging.getLogger("MatchingEngine").propagate = False
    logging.getLogger("market_data").propagate = False
