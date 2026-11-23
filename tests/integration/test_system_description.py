"""system.yaml and the OpenAPI documents must match the code: every variable each service reads, its default,
every call across the seam, and the timeouts it uses."""

from pathlib import Path

import pytest
import yaml

from ideas.config import load_config as ideas_config
from review.config import load_config as review_config

ROOT = Path(__file__).resolve().parents[2]
SYSTEM = yaml.safe_load((ROOT / "system.yaml").read_text())
CONFIGS = {"ideas": ideas_config({}), "review": review_config({})}


def openapi_operations(service):
    paths = yaml.safe_load((ROOT / SYSTEM["services"][service]["openapi"]).read_text())["paths"]
    return {method.upper() + " " + path for path, item in paths.items() for method in item if method != "parameters"}


@pytest.mark.parametrize("service", ["ideas", "review"])
def test_every_variable_a_service_reads_is_listed_with_its_real_default(service):
    listed = SYSTEM["services"][service]["env"]
    config = CONFIGS[service]

    assert set(listed) == set(config)
    for name, entry in listed.items():
        if entry.get("secret"):
            assert config[name] == "", name + " is a secret, so the code must have no default for it"
        elif isinstance(config[name], (int, float)):
            assert float(entry["default"]) == float(config[name]), name
        else:
            assert str(entry["default"]) == str(config[name]), name


def test_every_call_across_the_seam_exists_in_the_called_services_openapi_document():
    for service, description in SYSTEM["services"].items():
        for call in description.get("calls", []):
            missing = set(call["endpoints"]) - openapi_operations(call["service"])
            assert not missing, service + " calls endpoints review does not document: " + ", ".join(sorted(missing))


def test_the_timeouts_in_system_yaml_are_the_ones_ideas_uses():
    timeouts = sorted(call["timeout_s"] for call in SYSTEM["services"]["ideas"]["calls"])
    assert timeouts == sorted([CONFIGS["ideas"]["REVIEW_TIMEOUT_S"], CONFIGS["ideas"]["REVIEW_SLOW_TIMEOUT_S"]])


def test_ideas_sends_its_calls_to_the_variable_system_yaml_names():
    assert {call["url_env"] for call in SYSTEM["services"]["ideas"]["calls"]} == {"REVIEW_URL"}
    assert "REVIEW_URL" in CONFIGS["ideas"]
