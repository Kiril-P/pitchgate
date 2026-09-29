SHIP_SCORE = 2.0
SAFETY_KILL = 0.5
CONFIDENCE_FLOOR = 0.6

LABELS = ("KILL", "FIX", "SHIP", "PENDING")


def decide(market_need, feasibility, differentiation, safety_risk, confidence):
    if safety_risk > SAFETY_KILL:
        return "KILL", "safety_veto"
    scores = (market_need, feasibility, differentiation)
    if any(score < SHIP_SCORE for score in scores):
        return "FIX", "below_cutoff"
    if confidence < CONFIDENCE_FLOOR:
        return "FIX", "low_confidence"
    return "SHIP", "all_clear"


def explain(rule):
    text = {
        "safety_veto": "Safety risk is above the cutoff, so the label is KILL no matter how strong the other scores are.",
        "below_cutoff": "At least one of market need, feasibility, or differentiation is under 2.0 out of 3.",
        "low_confidence": "Every score would clear the cutoff, but confidence is under 0.6, so this stays FIX.",
        "all_clear": "Every score is at least 2.0 out of 3, safety is at or under 0.5, and confidence is at least 0.6.",
        "missing_key": "No TYPESAFE_API_KEY is set. The revision is saved and the verdict stays pending.",
        "request_failed": "Jev did not return a usable decision. The revision is saved and the verdict stays pending.",
    }
    return text[rule]
