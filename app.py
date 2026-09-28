from pitchgate import create_app
from pitchgate.config import load_config

config = load_config()
app = create_app(config)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config["PORT"])
