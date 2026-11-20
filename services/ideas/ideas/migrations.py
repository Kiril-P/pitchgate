import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

FOLDER = Path(__file__).resolve().parent.parent / "migrations"

TRACKING = """
IF OBJECT_ID('schema_migrations') IS NULL
    CREATE TABLE schema_migrations (
        version NVARCHAR(255) NOT NULL PRIMARY KEY,
        applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
    )
"""


def batches(text):
    """SQL Server runs some statements only alone in a batch, so a line holding just GO splits a file."""
    return [part.strip() for part in re.split(r"^\s*GO\s*$", text, flags=re.MULTILINE | re.IGNORECASE) if part.strip()]


def applied(connection):
    connection.execute(TRACKING)
    connection.commit()
    return {row["version"] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}


def migrate(connection, folder=FOLDER):
    """Applies every file in `folder` that is not yet recorded, in name order, each in its own
    transaction together with its schema_migrations row. Returns the names it applied."""
    done = applied(connection)
    ran = []
    for path in sorted(Path(folder).glob("*.sql")):
        if path.name in done:
            continue
        try:
            for batch in batches(path.read_text()):
                connection.execute(batch)
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            connection.commit()
        except Exception:
            connection.rollback()
            log.error("migration %s failed and was rolled back", path.name)
            raise
        log.info("applied migration %s", path.name)
        ran.append(path.name)
    if not ran:
        log.info("schema up to date (%d migrations applied before)", len(done))
    return ran
