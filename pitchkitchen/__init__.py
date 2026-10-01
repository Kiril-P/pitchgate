from pathlib import Path

from flask import Flask

from pitchkitchen.db import ensure_database
from pitchkitchen.pages import register_routes
from pitchkitchen.review.coach import DEFAULT_MODEL, DEFAULT_URL


def create_app(config):
    app = Flask(__name__)
    app.config["DATA_DIR"] = Path(config["DATA_DIR"])
    app.config["DATABASE"] = Path(config["DATABASE"])
    app.config["PORT"] = config["PORT"]
    app.config["TYPESAFE_API_KEY"] = config.get("TYPESAFE_API_KEY", "")
    app.config["COACH_API_KEY"] = config.get("COACH_API_KEY", "")
    app.config["COACH_URL"] = config.get("COACH_URL") or DEFAULT_URL
    app.config["COACH_MODEL"] = config.get("COACH_MODEL") or DEFAULT_MODEL
    app.config["JEV_TRANSPORT"] = config.get("JEV_TRANSPORT")
    app.config["CHEF_TRANSPORT"] = config.get("CHEF_TRANSPORT")

    ensure_database(app.config["DATABASE"])
    register_routes(app)
    return app
