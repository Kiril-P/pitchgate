"""The README is how a grader or a new developer runs the system, so it must keep up with system.yaml."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text()
SYSTEM = yaml.safe_load((ROOT / "system.yaml").read_text())


def test_the_readme_gives_the_live_url():
    assert SYSTEM["public_url"] in README


@pytest.mark.parametrize("service", sorted(SYSTEM["services"]))
def test_the_readme_documents_every_variable_a_service_reads(service):
    missing = [name for name in SYSTEM["services"][service]["env"] if "`" + name + "`" not in README]
    assert not missing, "README does not document " + ", ".join(missing) + " for " + service


@pytest.mark.parametrize(
    "command",
    [
        "docker compose up --build",
        "docker compose stop review",
        "flask --app wsgi run",
        "TEST_SQL_URL",
        "--cov-fail-under=70",
        "az containerapp",
    ],
)
def test_the_readme_shows_how_to_run_test_and_deploy(command):
    assert command in README
