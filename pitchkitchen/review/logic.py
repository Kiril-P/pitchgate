SHIP_SCORE = 2.0
KILL_AVERAGE = 1.2
HARSH_SCORE = 1.5
SAFETY_KILL = 0.5
CONFIDENCE_FLOOR = 0.6
ANSWER_CAP = 5

LABELS = ("KILL", "FIX", "SHIP", "PENDING")
DIMENSIONS = ("market_need", "feasibility", "differentiation")


def decide(market_need, feasibility, differentiation, safety_risk, confidence):
    if safety_risk > SAFETY_KILL:
        return "KILL", "safety_veto"
    scores = (market_need, feasibility, differentiation)
    if sum(scores) / len(scores) < KILL_AVERAGE:
        return "KILL", "all_weak"
    if any(score < SHIP_SCORE for score in scores):
        return "FIX", "below_cutoff"
    if confidence < CONFIDENCE_FLOOR:
        return "FIX", "low_confidence"
    return "SHIP", "all_clear"


def focus(verdict):
    if verdict["rule"] == "safety_veto":
        return "safety_risk"
    return min(DIMENSIONS, key=lambda name: verdict[name])


def heat(verdict):
    if verdict["label"] == "KILL":
        return "harsh"
    if all(verdict[name] < HARSH_SCORE for name in DIMENSIONS):
        return "harsh"
    return "normal"


def next_step(labels):
    """labels: the verdict label of every revision on the branch, pitch first."""
    if len(labels) >= 2 and labels[-1] == "KILL" and labels[-2] == "KILL":
        return "binned"
    if len(labels) - 1 >= ANSWER_CAP:
        return "capped"
    return "open"


def over_budget(used, budget):
    """budget is the most Jev calls one idea may make; None means no limit."""
    return budget is not None and used >= budget


def explain(rule):
    text = {
        "safety_veto": "Safety risk is above the cutoff, so the label is KILL no matter how strong the other scores are.",
        "all_weak": "Market need, feasibility, and differentiation average under 1.2 out of 3, so the label is KILL.",
        "below_cutoff": "At least one of market need, feasibility, or differentiation is under 2.0 out of 3.",
        "low_confidence": "Every score clears 2.0, but Jev is less than 60% sure at least one of them is really Solid or better, so this stays FIX.",
        "all_clear": "Every score is at least 2.0 out of 3, safety is at or under 0.5, and Jev is at least 60% sure each score is Solid or better.",
        "missing_key": "No TYPESAFE_API_KEY is set. The revision is saved and the verdict stays pending.",
        "request_failed": "Jev did not return a usable decision. The revision is saved and the verdict stays pending.",
        "over_budget": "This idea has used its whole Jev budget (JEV_BUDGET_PER_IDEA). The revision is saved and the verdict stays pending.",
    }
    return text[rule]


def recommend(dimension):
    text = {
        "market_need": "Show the problem is real: who has it, how often, and what they do about it today.",
        "feasibility": "Show you can build it: what the first version is and who on your team makes it.",
        "differentiation": "Show why you win: name the alternative people use now and what you do that it can't.",
        "safety_risk": "Find a version of this that is legal and doesn't hurt the people it is for.",
    }
    return text[dimension]
