from flask import Flask

from review.api import register_api
from review.config import DEFAULT_JEV_BUDGET
from review.cors import allow_origin
from review.db import connect
from review.migrations import migrate
from review.observe import configure_logging, register_observability


def create_app(config):
    configure_logging()
    app = Flask(__name__)
    if not config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set")
    app.config["DATABASE_URL"] = config["DATABASE_URL"]
    app.config["PORT"] = config.get("PORT", 8000)
    app.config["TYPESAFE_API_KEY"] = config.get("TYPESAFE_API_KEY", "")
    app.config["JEV_BUDGET_PER_IDEA"] = config.get("JEV_BUDGET_PER_IDEA", DEFAULT_JEV_BUDGET)
    app.config["COACH_API_KEY"] = config.get("COACH_API_KEY", "")
    app.config["COACH_URL"] = config["COACH_URL"]
    app.config["COACH_MODEL"] = config["COACH_MODEL"]
    app.config["JEV_TRANSPORT"] = config.get("JEV_TRANSPORT")
    app.config["CHEF_TRANSPORT"] = config.get("CHEF_TRANSPORT")
    app.config["SEARCH_TRANSPORT"] = config.get("SEARCH_TRANSPORT")

    connection = connect(app.config["DATABASE_URL"], attempts=config.get("DB_CONNECT_ATTEMPTS", 1))
    try:
        migrate(connection)
    finally:
        connection.close()

    register_observability(app, config.get("VERSION") or "dev")
    register_api(app)
    allow_origin(app, config.get("UI_ORIGIN", ""))
    return app
