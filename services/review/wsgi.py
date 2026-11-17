from review import create_app
from review.config import load_config

app = create_app(load_config())
