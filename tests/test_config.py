from pathlib import Path

from pitchkitchen.config import load_config, read_env_file


def test_defaults_without_env_file(tmp_path):
    config = load_config({}, env_file=tmp_path / ".env")

    assert config["PORT"] == 5000
    assert config["DATABASE"] == Path("data") / "pitchkitchen.sqlite"
    assert config["TYPESAFE_API_KEY"] == ""


def test_env_file_fills_in_missing_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# keys\n"
        "\n"
        "TYPESAFE_API_KEY=jev-123\n"
        "export PORT=6000\n"
        "COACH_API_KEY=\"sk-abc\"\n"
        "not a setting\n"
    )
    environ = {}

    config = load_config(environ, env_file=env_file)

    assert config["TYPESAFE_API_KEY"] == "jev-123"
    assert config["PORT"] == 6000
    assert environ["COACH_API_KEY"] == "sk-abc"
    assert "not a setting" not in environ


def test_real_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=6000\n")
    environ = {"PORT": "7000"}

    read_env_file(env_file, environ)

    assert environ["PORT"] == "7000"
