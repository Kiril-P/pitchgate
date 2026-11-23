import re
from pathlib import Path

import yaml

from ideas import create_app
from ideas.config import load_config

DOCUMENT = Path(__file__).resolve().parent.parent / "openapi.yaml"
METHODS = {"get", "post", "put", "patch", "delete"}


def routes(app):
    found = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", rule.rule)
        found |= {(method.lower(), path) for method in rule.methods if method.lower() in METHODS}
    return found


def documented():
    paths = yaml.safe_load(DOCUMENT.read_text())["paths"]
    return {(method, path) for path, item in paths.items() for method in item if method in METHODS}


def test_every_route_is_in_the_openapi_document_and_nothing_else(db, database_url):
    app = create_app(load_config({"DATABASE_URL": database_url}))
    assert routes(app) == documented()
