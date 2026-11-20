from flask import Flask

from ideas.api import register_api
from ideas.db import connect
from ideas.migrations import migrate
from ideas.review_client import ReviewClient


def create_app(config):
    app = Flask(__name__)
    if not config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set")
    app.config["DATABASE_URL"] = config["DATABASE_URL"]
    app.config["PORT"] = config.get("PORT", 8000)
    app.config["ORGANIZER_KEY"] = config.get("ORGANIZER_KEY", "")
    app.config["TODAY"] = config.get("TODAY")
    app.config["REVIEW"] = ReviewClient(
        config["REVIEW_URL"],
        config["REVIEW_TIMEOUT_S"],
        config["REVIEW_SLOW_TIMEOUT_S"],
        transport=config.get("REVIEW_TRANSPORT"),
    )

    connection = connect(app.config["DATABASE_URL"], attempts=config.get("DB_CONNECT_ATTEMPTS", 1))
    try:
        migrate(connection)
    finally:
        connection.close()

    register_api(app)
    return app
