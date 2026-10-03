import os
from pathlib import Path

from pitchkitchen.review.coach import DEFAULT_MODEL, DEFAULT_URL

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_JEV_BUDGET = 10


def read_env_file(path, environ):
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        environ.setdefault(key, value.strip().strip("\"'"))


def load_config(environ=None, env_file=ENV_FILE):
    environ = os.environ if environ is None else environ
    read_env_file(env_file, environ)
    data_dir = Path(environ.get("DATA_DIR", "data")).expanduser()
    return {
        "DATA_DIR": data_dir,
        "DATABASE": data_dir / "pitchkitchen.sqlite",
        "PORT": int(environ.get("PORT", "5000")),
        "TYPESAFE_API_KEY": environ.get("TYPESAFE_API_KEY", ""),
        "JEV_BUDGET_PER_IDEA": int(environ.get("JEV_BUDGET_PER_IDEA", "") or DEFAULT_JEV_BUDGET),
        "COACH_API_KEY": environ.get("COACH_API_KEY", ""),
        "COACH_URL": environ.get("COACH_URL", "") or DEFAULT_URL,
        "COACH_MODEL": environ.get("COACH_MODEL", "") or DEFAULT_MODEL,
        "ORGANIZER_KEY": environ.get("ORGANIZER_KEY", ""),
    }
