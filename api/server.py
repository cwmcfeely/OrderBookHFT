import logging
from app.logger import setup_logging
from api import create_app

logger = logging.getLogger(__name__)
logger.propagate = False

app = create_app()

if __name__ == "__main__":
    setup_logging(
        level=logging.INFO,
        app_log_file="logs/app.debug.log",
        fix_server_log_file="logs/fix_server.log",
        strategies=["my_strategy", "passive_liquidity_provider", "market_maker", "momentum"]
    )
    app.run(host="127.0.0.1", port=5000, debug=False)
