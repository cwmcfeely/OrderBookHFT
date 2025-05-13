import logging
from app.logger import setup_logging
from api import create_app

logger = logging.getLogger(__name__)
logger.propagate = False

app = create_app()

if __name__ == "__main__":
    setup_logging(level=logging.DEBUG)  # Initialize once
    app.run(host="127.0.0.1", port=5000, debug=False)
