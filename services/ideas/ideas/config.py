import os


def load_config(environ=None):
    environ = os.environ if environ is None else environ
    return {
        "DATABASE_URL": environ.get("DATABASE_URL", ""),
        "PORT": int(environ.get("PORT", "") or 8000),
        "VERSION": environ.get("VERSION", "") or "dev",
        "DB_CONNECT_ATTEMPTS": int(environ.get("DB_CONNECT_ATTEMPTS", "") or 8),
        "REVIEW_URL": environ.get("REVIEW_URL", "") or "http://review:8000",
        "REVIEW_TIMEOUT_S": float(environ.get("REVIEW_TIMEOUT_S", "") or 5),
        "REVIEW_SLOW_TIMEOUT_S": float(environ.get("REVIEW_SLOW_TIMEOUT_S", "") or 90),
        "ORGANIZER_KEY": environ.get("ORGANIZER_KEY", ""),
        "UI_ORIGIN": environ.get("UI_ORIGIN", "").rstrip("/"),
    }
