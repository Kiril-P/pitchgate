from ideas import create_app
from ideas.config import load_config

app = create_app(load_config())
