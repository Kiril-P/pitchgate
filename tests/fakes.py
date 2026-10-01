import json


def jev_scores(market, feasibility, differentiation, safety, confidence=0.9):
    """confidence becomes the probability of the bucket nearest the score."""

    def score(value):
        bucket = min(3, int(value + 0.5))
        probabilities = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0}
        probabilities[str(bucket)] = confidence
        probabilities["0"] += 1 - confidence
        return {"type": "score", "score": value, "confidence": confidence, "probabilities": probabilities}

    return {
        "answers": {
            "market_need": score(market),
            "feasibility": score(feasibility),
            "differentiation": score(differentiation),
            "safety_risk": {"type": "noul", "noul": safety},
        }
    }


SHIP = jev_scores(2.5, 2.5, 2.5, 0.0)
FIX = jev_scores(2.5, 1.5, 2.5, 0.0)
KILL = jev_scores(0.5, 0.5, 0.5, 0.0)


class FakeJev:
    """Returns the queued payloads in order, then repeats the last one."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, body, api_key):
        self.calls.append(body)
        if len(self.payloads) > 1:
            return self.payloads.pop(0)
        return self.payloads[0]


class FakeChef:
    def __init__(self, reply=None):
        self.reply = reply
        self.calls = []

    def __call__(self, body, api_key):
        self.calls.append(body)
        if self.reply is not None:
            content = self.reply
        elif "pitch" in body["messages"][0]["content"].split("Reply with JSON only:")[-1]:
            content = {"pitch": "We help students sell textbooks."}
        else:
            content = {"roast": "Raw.", "question": "Who paid you?"}
        return {"choices": [{"message": {"content": json.dumps(content)}}]}
