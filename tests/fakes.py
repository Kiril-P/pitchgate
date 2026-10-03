import json


def _score(value, confidence=0.9):
    """confidence becomes the probability of the bucket nearest the score."""
    bucket = min(3, int(value + 0.5))
    probabilities = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0}
    probabilities[str(bucket)] = confidence
    probabilities["0"] += 1 - confidence
    return {"type": "score", "score": value, "confidence": confidence, "probabilities": probabilities}


def jev_scores(market, feasibility, differentiation, safety, confidence=0.9, evidence=2.5, answered=0.9):
    return {
        "answers": {
            "market_need": _score(market, confidence),
            "feasibility": _score(feasibility, confidence),
            "differentiation": _score(differentiation, confidence),
            "evidence": _score(evidence, confidence),
            "safety_risk": {"type": "noul", "noul": safety},
            "answered": {"type": "noul", "noul": answered},
        }
    }


def tasting_scores(evidence_strength, pain_frequency, willingness_to_pay, safety=0.0):
    return {
        "answers": {
            "evidence_strength": _score(evidence_strength),
            "pain_frequency": _score(pain_frequency),
            "willingness_to_pay": _score(willingness_to_pay),
            "safety_risk": {"type": "noul", "noul": safety},
        }
    }


PROVEN = jev_scores(2.5, 2.5, 2.5, 0.0)
PARTIAL = jev_scores(2.5, 1.5, 2.5, 0.0)
UNPROVEN = jev_scores(0.5, 0.5, 0.5, 0.0)
GATE_PASS = tasting_scores(2.5, 2.0, 2.0)
GATE_FAIL = tasting_scores(1.0, 2.0, 2.0)


class FakeJev:
    """Returns the queued payloads in order, then repeats the last one.
    Tasting calls get `tasting` instead, so a round and a gate can share one fake."""

    def __init__(self, *payloads, tasting=GATE_PASS):
        self.payloads = list(payloads)
        self.tasting = tasting
        self.calls = []

    def __call__(self, body, api_key):
        self.calls.append(body)
        if "evidence_strength" in body["questions"]:
            return self.tasting
        if len(self.payloads) > 1:
            return self.payloads.pop(0)
        return self.payloads[0]


class FakeChef:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def __call__(self, body, api_key):
        self.calls.append(body)
        wanted = body["messages"][0]["content"].split("Reply with JSON only:")[-1]
        if self.reply is not None:
            content = self.reply
        elif '"pitch"' in wanted:
            content = {"pitch": "We help students sell textbooks.", "next_steps": ["Run a stall", "Email the union"]}
        elif '"people"' in wanted:
            content = {"people": ["Sellers", "Buyers", "Bookstore staff"], "questions": ["When did you last sell a book?"]}
        elif '"one_liners"' in wanted:
            content = {"one_liners": ["We help A do B by C", "We help D", "We help E"]}
        else:
            content = {"reaction": "Raw.", "question": "Who paid you?"}
        return {"choices": [{"message": {"content": json.dumps(content)}}]}
