import os

from review.coach import DEFAULT_MODEL, DEFAULT_URL

DEFAULT_JEV_BUDGET = 15


def load_config(environ=None):
    environ = os.environ if environ is None else environ
    return {
        "DATABASE_URL": environ.get("DATABASE_URL", ""),
        "PORT": int(environ.get("PORT", "") or 8000),
        "DB_CONNECT_ATTEMPTS": int(environ.get("DB_CONNECT_ATTEMPTS", "") or 8),
        "TYPESAFE_API_KEY": environ.get("TYPESAFE_API_KEY", ""),
        "JEV_BUDGET_PER_IDEA": int(environ.get("JEV_BUDGET_PER_IDEA", "") or DEFAULT_JEV_BUDGET),
        "COACH_API_KEY": environ.get("COACH_API_KEY", ""),
        "COACH_URL": environ.get("COACH_URL", "") or DEFAULT_URL,
        "COACH_MODEL": environ.get("COACH_MODEL", "") or DEFAULT_MODEL,
        "UI_ORIGIN": environ.get("UI_ORIGIN", "").rstrip("/"),
    }
