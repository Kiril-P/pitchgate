from pathlib import Path

from flask import Flask, render_template

from pitchgate.db import ensure_database


def create_app(config):
    app = Flask(__name__)
    app.config["DATA_DIR"] = Path(config["DATA_DIR"])
    app.config["DATABASE"] = Path(config["DATABASE"])
    app.config["PORT"] = config["PORT"]

    ensure_database(app.config["DATABASE"])

    @app.get("/")
    def home():
        return render_template("home.html")

    return app
