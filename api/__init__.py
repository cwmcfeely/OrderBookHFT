# Import the Flask class from the flask package
from flask import Flask

# Import the register_routes function from the routes module in the current package
# This function is assumed to define and register all the routes (endpoints) of the web application
from .routes import register_routes

# Define a factory function to create and configure a new Flask application instance
def create_app():
    # Create a new Flask app instance
    # __name__ helps Flask determine the root path of the application
    app = Flask(__name__)

    # Register all routes (URL patterns and their associated view functions) to the app
    # This separates the routing logic from the app creation, promoting modularity
    register_routes(app)

    # Return the configured Flask app instance
    return app
