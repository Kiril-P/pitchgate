import os
from pathlib import Path


def load_config():
    data_dir = Path(os.environ.get("DATA_DIR", "data")).expanduser()
    return {
        "DATA_DIR": data_dir,
        "DATABASE": data_dir / "pitchgate.sqlite",
        "PORT": int(os.environ.get("PORT", "5000")),
    }
