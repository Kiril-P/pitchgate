import logging
import sys
import time

from flask import g, jsonify, request

from review.db import connect

log = logging.getLogger("review.requests")


def configure_logging():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def check_database(connection):
    """Reads, then writes a row inside a transaction it rolls back, so a database that is
    unreachable, read-only, or missing this service's grants fails and nothing is kept."""
    connection.execute("SELECT COUNT(*) AS applied FROM schema_migrations").fetchone()
    connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", ("health-check",))
    connection.rollback()


def register_observability(app, version):
    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def log_request(response):
        started = g.get("started")
        duration_ms = (time.perf_counter() - started) * 1000 if started is not None else 0.0
        log.info("%s %s %s %.0fms", request.method, request.path, response.status_code, duration_ms)
        return response

    @app.get("/health")
    def health():
        """Only this service's own state: the other service being down never makes this fail."""
        try:
            connection = connect(app.config["DATABASE_URL"])
            try:
                check_database(connection)
            finally:
                connection.close()
        except Exception as error:
            log.warning("health check failed: %s", error)
            return jsonify(status="error", db="error", version=version), 503
        return jsonify(status="ok", db="ok", version=version)
