import logging

from api import create_app
from app.logger import setup_logging

# Set up logging before app creation
setup_logging(
    level=logging.INFO,
    app_log_file="logs/app.debug.log",
    fix_server_log_file="logs/fix_server.log",
    strategies=[
        "my_strategy",
        "passive_liquidity_provider",
        "market_maker",
        "momentum",
    ],
)

# Create the Flask app instance using the factory function
app = create_app()

# Configure a logger for this module
logger = logging.getLogger(__name__)
logger.propagate = False

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
