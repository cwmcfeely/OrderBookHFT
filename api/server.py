# Import the logging module to handle logging across the application
import logging

# Import the custom logging setup function from the app.logger module
from app.logger import setup_logging

# Import the create_app factory function from the api package to create the Flask app instance
from api import create_app

# Create a logger specific to this module
logger = logging.getLogger(__name__)

# Disable propagation to avoid duplicate log messages if the root logger is also configured
logger.propagate = False

# Instantiate the Flask application using the factory function
app = create_app()

# This block ensures that the code only runs if this script is executed directly,
# not if it's imported as a module
if __name__ == "__main__":
    # - Setting the logging level to INFO
    # - Writing application logs to 'logs/app.debug.log'
    # - Writing FIX server logs to 'logs/fix_server.log'
    # - Applying logging for specified trading strategies
    setup_logging(
        level=logging.INFO,
        app_log_file="logs/app.debug.log",
        fix_server_log_file="logs/fix_server.log",
        strategies=["my_strategy", "passive_liquidity_provider", "market_maker", "momentum"]
    )

    # Run the Flask web application
    # - host="127.0.0.1" runs the app locally (localhost)
    # - port=5000 is the default port for Flask
    # - debug=False disables the Flask debugger for production safety
    app.run(host="127.0.0.1", port=5000, debug=False)
