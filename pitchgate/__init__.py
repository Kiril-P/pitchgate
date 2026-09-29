from pathlib import Path

from flask import Flask

from pitchgate.db import ensure_database
from pitchgate.pages import register_routes


def create_app(config):
    app = Flask(__name__)
    app.config["DATA_DIR"] = Path(config["DATA_DIR"])
    app.config["DATABASE"] = Path(config["DATABASE"])
    app.config["PORT"] = config["PORT"]
    app.config["TYPESAFE_API_KEY"] = config.get("TYPESAFE_API_KEY", "")

    ensure_database(app.config["DATABASE"])
    register_routes(app)
    return app
