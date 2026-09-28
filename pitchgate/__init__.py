from pathlib import Path

from flask import Flask

from pitchgate.db import ensure_database
from pitchgate.ideas.routes import register_routes


def create_app(config):
    app = Flask(__name__)
    app.config["DATA_DIR"] = Path(config["DATA_DIR"])
    app.config["DATABASE"] = Path(config["DATABASE"])
    app.config["PORT"] = config["PORT"]

    ensure_database(app.config["DATABASE"])
    register_routes(app)
    return app
