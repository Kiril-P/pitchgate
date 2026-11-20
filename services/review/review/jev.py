import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT = 15
LEVELS = ["None", "Weak", "Solid", "Strong"]

QUESTIONS = {
    "market_need": {
        "type": "score",
        "instructions": (
            "How real and painful is the problem this idea solves for the people it targets? "
            "Judge the problem itself, from what is generally known and what the founder reports, including "
            "what those people already do or pay about it today. Do not lower the score because the founder's "
            "wording is vague, casual, or lacks proof; that is scored separately as evidence."
        ),
        "criteria": LEVELS,
    },
    "feasibility": {
        "type": "score",
        "instructions": "How feasible is this startup idea for a small student team?",
        "criteria": LEVELS,
    },
    "differentiation": {
        "type": "score",
        "instructions": "How different is this startup idea from what already exists?",
        "criteria": LEVELS,
    },
    "evidence": {
        "type": "score",
        "instructions": (
            "In the founder's latest message only, how much is past behaviour with specifics "
            "(who, when, how many, how much, what they paid) rather than opinions, compliments, "
            "hypotheticals, or plans?"
        ),
        "criteria": LEVELS,
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

ANSWERED = {
    "type": "noul",
    "instructions": (
        "Does the founder's latest answer directly answer latest_question with at least one specific fact? "
        "An honest none, zero, or never (for example 'nobody has paid yet') is a specific fact and counts as an answer."
    ),
    "criteria": {
        "true": "Answers the question with a specific fact, including an honest none, zero, or never",
        "false": "Dodges, changes the subject, or answers with opinions, hopes, or plans",
    },
}

TASTING_QUESTIONS = {
    "evidence_strength": {
        "type": "score",
        "instructions": (
            "Across these logged customer conversations, how strong is the evidence that the problem is real: "
            "past behaviour, named people, and specifics, rather than opinions or compliments? "
            "A friend saying they would use it is an opinion, not evidence."
        ),
        "criteria": LEVELS,
    },
    "pain_frequency": {
        "type": "score",
        "instructions": "How often and how badly do the people in these conversations have this problem?",
        "criteria": LEVELS,
    },
    "willingness_to_pay": {
        "type": "score",
        "instructions": "How much evidence is there that these people already spend money or real time solving this problem today?",
        "criteria": LEVELS,
    },
    "safety_risk": QUESTIONS["safety_risk"],
}


class JevUnavailable(Exception):
    pass


def judge(state, api_key, transport=None):
    """Scores the founder's text. Asks `answered` only when Chef asked a question."""
    questions = dict(QUESTIONS)
    if state.get("latest_question"):
        questions["answered"] = ANSWERED
    payload = _call(state, questions, api_key, transport)
    return parse_answers(payload, "answered" in questions)


def judge_tasting(state, api_key, transport=None):
    payload = _call(state, TASTING_QUESTIONS, api_key, transport)
    return parse_tasting(payload)


def _call(state, questions, api_key, transport):
    if not api_key:
        raise JevUnavailable()
    body = {"model": "jev-latest", "state": state, "questions": questions}
    if transport is None:
        return _post(body, api_key)
    return transport(body, api_key)


def parse_answers(payload, with_answered=False):
    try:
        answers = payload["answers"]
        measured = {
            "market_need": float(answers["market_need"]["score"]),
            "feasibility": float(answers["feasibility"]["score"]),
            "differentiation": float(answers["differentiation"]["score"]),
            "safety_risk": float(answers["safety_risk"]["noul"]),
            "confidence": min(
                _solid_or_better(answers["market_need"]),
                _solid_or_better(answers["feasibility"]),
                _solid_or_better(answers["differentiation"]),
            ),
            "evidence": float(answers["evidence"]["score"]) if "evidence" in answers else None,
            "answered": float(answers["answered"]["noul"]) if with_answered else None,
        }
    except (KeyError, TypeError, ValueError):
        raise JevUnavailable()
    return measured


def parse_tasting(payload):
    try:
        answers = payload["answers"]
        return {
            "evidence_strength": float(answers["evidence_strength"]["score"]),
            "pain_frequency": float(answers["pain_frequency"]["score"]),
            "willingness_to_pay": float(answers["willingness_to_pay"]["score"]),
            "safety_risk": float(answers["safety_risk"]["noul"]),
        }
    except (KeyError, TypeError, ValueError):
        raise JevUnavailable()


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
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log.warning("Jev request failed: HTTP %s %s", error.code, error.read()[:300])
        raise JevUnavailable()
    except (OSError, ValueError) as error:
        log.warning("Jev request failed: %r", error)
        raise JevUnavailable()
