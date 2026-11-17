import logging
import time
from urllib.parse import parse_qs, unquote, urlparse

import pymssql

log = logging.getLogger(__name__)

FIRST_DELAY_S = 2
MAX_DELAY_S = 20


class Connection:
    """A pymssql connection shaped like sqlite3's: execute() returns a cursor whose rows are dicts."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=None):
        cursor = self.raw.cursor(as_dict=True)
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()


def parse_url(url):
    """mssql://user:password@host:port/database?encrypt=require"""
    parts = urlparse(url)
    if parts.scheme != "mssql" or not parts.hostname:
        raise ValueError("DATABASE_URL must look like mssql://user:password@host:1433/database")
    options = parse_qs(parts.query)
    return {
        "server": parts.hostname,
        "port": str(parts.port or 1433),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": parts.path.lstrip("/"),
        "encryption": options.get("encrypt", [None])[0],
    }


def connect(url, attempts=1, sleep=time.sleep):
    """Retries with backoff, because a paused Azure SQL database refuses connections while it resumes."""
    settings = parse_url(url)
    delay = FIRST_DELAY_S
    for attempt in range(1, attempts + 1):
        try:
            return Connection(pymssql.connect(login_timeout=15, timeout=60, **settings))
        except (pymssql.OperationalError, pymssql.InterfaceError) as error:
            if attempt == attempts:
                raise
            log.warning("database not ready (attempt %d of %d): %s", attempt, attempts, error)
            sleep(delay)
            delay = min(delay * 2, MAX_DELAY_S)
