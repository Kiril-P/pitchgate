import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

QUESTIONS = {
    "market_need": {
        "type": "score",
        "instructions": "How real is the market need in this startup idea?",
        "criteria": ["None", "Weak", "Solid", "Strong"],
    },
    "feasibility": {
        "type": "score",
        "instructions": "How feasible is this startup idea for a small student team?",
        "criteria": ["None", "Weak", "Solid", "Strong"],
    },
    "differentiation": {
        "type": "score",
        "instructions": "How different is this startup idea from what already exists?",
        "criteria": ["None", "Weak", "Solid", "Strong"],
    },
    "safety_risk": {
        "type": "noul",
        "instructions": "Does this idea depend on something illegal or dangerous to the people it is for?",
        "criteria": {
            "true": "Illegal or likely to harm people",
            "false": "Ordinary business risk only",
        },
    },
}


class JevUnavailable(Exception):
    pass


def judge(state, api_key, transport=None):
    if not api_key:
        raise JevUnavailable()
    body = {
        "model": "jev-latest",
        "state": state,
        "questions": QUESTIONS,
    }
    if transport is None:
        payload = _post(body, api_key)
    else:
        payload = transport(body, api_key)
    return parse_answers(payload)


def parse_answers(payload):
    try:
        answers = payload["answers"]
        market_need = float(answers["market_need"]["score"])
        feasibility = float(answers["feasibility"]["score"])
        differentiation = float(answers["differentiation"]["score"])
        safety_risk = float(answers["safety_risk"]["noul"])
        confidence = min(
            _solid_or_better(answers["market_need"]),
            _solid_or_better(answers["feasibility"]),
            _solid_or_better(answers["differentiation"]),
        )
    except (KeyError, TypeError, ValueError):
        raise JevUnavailable()
    return {
        "market_need": market_need,
        "feasibility": feasibility,
        "differentiation": differentiation,
        "safety_risk": safety_risk,
        "confidence": confidence,
    }


def _solid_or_better(answer):
    """Jev's probability that the score is 2 (Solid) or 3 (Strong)."""
    probabilities = answer["probabilities"]
    return float(probabilities["2"]) + float(probabilities["3"])


def _post(body, api_key):
    request = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log.warning("Jev request failed: HTTP %s %s", error.code, error.read()[:300])
        raise JevUnavailable()
    except (OSError, ValueError) as error:
        log.warning("Jev request failed: %r", error)
        raise JevUnavailable()
