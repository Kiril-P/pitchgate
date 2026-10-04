PROVEN_SCORE = 2.0
UNPROVEN_AVERAGE = 1.2
HARSH_SCORE = 1.5
SAFETY_VETO = 0.5
CONFIDENCE_FLOOR = 0.6
ANSWERED_FLOOR = 0.5
EVIDENCE_FLOOR = 2.0
SESSION_ANSWERS = 5
RETRY_CAP = 3

GATE_MIN_LOGS = 3
GATE_WINDOW = 5
GATE_EVIDENCE = 2.0
GATE_AVERAGE = 1.5
SERVE_MIN_LOGS = 3

LABELS = ("UNPROVEN", "PARTIAL", "PROVEN", "PENDING")
GATE_LABELS = ("PASSED", "SENT_BACK", "PENDING")
DIMENSIONS = ("market_need", "feasibility", "differentiation")
OLD_LABELS = {"KILL": "UNPROVEN", "FIX": "PARTIAL", "SHIP": "PROVEN"}


def decide(market_need, feasibility, differentiation, safety_risk, confidence, evidence=None, answered=None):
    """answered is None for the pitch, where Chef has not asked anything yet.
    A dodge is checked before the scores: a non-answer is asked again, it never counts toward the bin."""
    if safety_risk > SAFETY_VETO:
        return "UNPROVEN", "safety_veto"
    if answered is not None and answered < ANSWERED_FLOOR:
        return "PARTIAL", "dodged"
    scores = (market_need, feasibility, differentiation)
    if sum(scores) / len(scores) < UNPROVEN_AVERAGE:
        return "UNPROVEN", "all_weak"
    if any(score < PROVEN_SCORE for score in scores):
        return "PARTIAL", "below_cutoff"
    if evidence is not None and evidence < EVIDENCE_FLOOR:
        return "PARTIAL", "mostly_claims"
    if confidence < CONFIDENCE_FLOOR:
        return "PARTIAL", "low_confidence"
    return "PROVEN", "all_clear"


def decide_tasting(evidence_strength, pain_frequency, willingness_to_pay, safety_risk):
    if safety_risk > SAFETY_VETO:
        return "SENT_BACK", "gate_safety"
    if evidence_strength < GATE_EVIDENCE:
        return "SENT_BACK", "gate_weak_evidence"
    if (evidence_strength + pain_frequency + willingness_to_pay) / 3 < GATE_AVERAGE:
        return "SENT_BACK", "gate_weak_signal"
    return "PASSED", "gate_clear"


def gate_ready(session_logs, logs_since_last_gate):
    """A gate needs enough logs this session and something new since the last try."""
    return session_logs >= GATE_MIN_LOGS and logs_since_last_gate > 0


def band(score):
    if score is None:
        return ""
    if score < 0.5:
        return "None"
    if score < 1.5:
        return "Weak"
    if score < 2.5:
        return "Solid"
    return "Strong"


def focus(verdict):
    if verdict["rule"] == "safety_veto":
        return "safety_risk"
    if verdict["rule"] == "dodged":
        return "answered"
    if verdict["rule"] == "mostly_claims":
        return "evidence"
    return min(DIMENSIONS, key=lambda name: verdict[name])


def heat(verdict):
    if verdict["label"] == "UNPROVEN":
        return "harsh"
    if all(verdict[name] < HARSH_SCORE for name in DIMENSIONS):
        return "harsh"
    return "normal"


def next_step(labels, sessions=1):
    """labels: the verdict label of every revision on the branch, pitch first.
    sessions: how many grill sessions are unlocked (passed tasting gates + 1).
    Only two UNPROVEN answers in a row inside a session after a passed gate bin the idea;
    before the founder has talked to anyone, a weak session ends in homework."""
    answers = len(labels) - 1
    this_session = answers - SESSION_ANSWERS * (sessions - 1)
    if sessions > 1 and this_session >= 2 and labels[-1] == "UNPROVEN" and labels[-2] == "UNPROVEN":
        return "binned"
    if answers >= SESSION_ANSWERS * sessions:
        return "homework"
    return "open"


def answers_left(answer_count, sessions):
    return max(0, SESSION_ANSWERS * sessions - answer_count)


def over_budget(used, budget):
    """budget is the most successful Jev calls one idea may make; None means no limit."""
    return budget is not None and used >= budget


def can_serve(label, log_count):
    return label == "PROVEN" and log_count >= SERVE_MIN_LOGS


def explain(rule):
    text = {
        "safety_veto": "This looks illegal or harmful to the people it is for, so it stays UNPROVEN however strong the rest is.",
        "all_weak": "Market need, feasibility, and differentiation are all weak, so this is UNPROVEN.",
        "dodged": "The last answer did not answer Chef's question with a specific fact, so Chef asks again.",
        "below_cutoff": "At least one of market need, feasibility, or differentiation is below Solid.",
        "mostly_claims": "The scores are Solid, but the latest answer is mostly opinion or plans, not things that already happened.",
        "low_confidence": "The scores are Solid, but Jev is unsure they really are. Add specifics.",
        "all_clear": "Market need, feasibility, and differentiation are all Solid or better, backed by things that already happened.",
        "missing_key": "No TYPESAFE_API_KEY is set. The text is saved and the verdict stays pending.",
        "request_failed": "Jev did not return a usable score. The text is saved; try again.",
        "retry_cap": "Jev failed three times on this text. The text is saved; edit it or try later.",
        "over_budget": "This idea has used its whole Jev budget (JEV_BUDGET_PER_IDEA). The text is saved and the verdict stays pending.",
        "gate_safety": "The conversations point at something illegal or harmful. Sent back.",
        "gate_weak_evidence": "The conversations are mostly opinions or compliments, not what people actually did or paid. Sent back.",
        "gate_weak_signal": "The evidence is real, but the pain is rare or nobody spends anything on it today. Sent back.",
        "gate_clear": "Real conversations show a real, frequent problem people already spend on. A new grill session is open.",
    }
    return text[rule]


def recommend(dimension):
    text = {
        "market_need": "Show the problem is real: who has it, how often, and what they do about it today.",
        "feasibility": "Show you can build it: what the first version is and who on your team makes it.",
        "differentiation": "Show why you win: name the alternative people use now and what you do that it can't.",
        "safety_risk": "Find a version of this that is legal and doesn't hurt the people it is for.",
        "answered": "Answer the question Chef asked, with one thing that already happened.",
        "evidence": "Swap plans and opinions for facts: who, when, how many, how much.",
    }
    return text[dimension]
