from pitchkitchen.review.coach import ChefUnavailable, write_homework, write_pitch, write_starter_pack, write_turn
from pitchkitchen.review.logic import GATE_WINDOW, can_serve, gate_ready, heat, next_step
from pitchkitchen.review.store import (
    chef_for,
    gates_for,
    gates_passed,
    record_gate,
    record_verdict,
    save_chef,
    save_chef_json,
    verdicts_for,
)


class NotServable(Exception):
    pass


class GateNotReady(Exception):
    pass


def run_round(
    connection, revision_ids, founder_text, settings, jev_transport=None, chef_transport=None, idea_id=None, tone="tough",
    level="idea",
):
    """Scores the newest revision on a branch, then has Chef answer it.

    founder_text is the ideas snapshot: one_liner, story, answers, and evidence logs.
    Safe to call again: a finished verdict, Chef turn, or homework is never redone.
    Returns {"verdict", "step", "paused"} where paused is None, "jev", or "chef".
    """
    head = revision_ids[-1]
    sessions = sessions_for(connection, idea_id)
    state = dict(
        founder_text,
        evidence=[_log_state(entry) for entry in founder_text.get("evidence") or []],
        latest_question=_latest_question(connection, revision_ids),
    )
    verdict = record_verdict(
        connection,
        head,
        state,
        settings["jev_key"],
        transport=jev_transport,
        idea_id=idea_id,
        budget=settings.get("jev_budget"),
    )
    step = step_for(connection, revision_ids, sessions)
    if verdict["label"] == "PENDING":
        return {"verdict": verdict, "step": step, "paused": "jev"}

    chef = dict(
        api_key=settings["chef_key"],
        model=settings["chef_model"],
        url=settings["chef_url"],
        transport=chef_transport,
        tone=tone,
        evidence=founder_text.get("evidence"),
    )
    talk = conversation(connection, revision_ids, founder_text)
    stored = chef_for(connection, [head]).get(head, {})
    try:
        if "turn" not in stored:
            turn = write_turn(talk, verdict, verdict["focus"], heat(verdict), step, level=level, **chef)
            save_chef(connection, head, "turn", turn["reaction"], turn["question"])
        if step == "homework" and "homework" not in stored:
            save_chef_json(connection, head, "homework", write_homework(talk, verdict["focus"], level=level, **chef))
    except ChefUnavailable:
        return {"verdict": verdict, "step": step, "paused": "chef"}
    return {"verdict": verdict, "step": step, "paused": None}


def conversations(logs):
    """Only real conversations count toward serving; facts found online don't."""
    return [entry for entry in logs or [] if entry.get("kind", "conversation") == "conversation"]


def serve(connection, revision_ids, founder_text, settings, chef_transport=None):
    head = revision_ids[-1]
    verdict = verdicts_for(connection, [head]).get(head)
    logs = founder_text.get("evidence") or []
    if verdict is None or not can_serve(verdict["label"], len(conversations(logs))):
        raise NotServable()
    served = write_pitch(
        conversation(connection, revision_ids, founder_text),
        settings["chef_key"],
        settings["chef_model"],
        settings["chef_url"],
        transport=chef_transport,
        evidence=logs,
    )
    save_chef(connection, head, "polished", served["pitch"])
    save_chef_json(connection, head, "next_steps", served["next_steps"])
    return served


def write_pack(connection, revision_ids, founder_text, settings, verified, chef_transport=None):
    """Has Chef plan the starter pack and stores it on the newest revision, with how many logs
    it saw and whether the idea was served, so the page can tell when it is out of date."""
    head = revision_ids[-1]
    logs = founder_text.get("evidence") or []
    plan = write_starter_pack(
        conversation(connection, revision_ids, founder_text),
        settings["chef_key"],
        settings["chef_model"],
        settings["chef_url"],
        transport=chef_transport,
        evidence=logs,
        verified=verified,
    )
    stored = dict(plan, verified=verified, logs=len(logs))
    save_chef_json(connection, head, "starter_pack", stored)
    return stored


def gate_status(connection, idea_id, evidence):
    """Where this session's tasting stands. A failed (PENDING) gate doesn't count
    as an attempt, so the founder can retry it without logging something new."""
    session = sessions_for(connection, idea_id)
    logs = [entry for entry in evidence if entry["session"] == session]
    gates = gates_for(connection, idea_id)
    tried = [gate for gate in gates if gate["session"] == session and gate["label"] != "PENDING"]
    last_seen = tried[-1]["last_evidence_id"] if tried else 0
    fresh = [entry for entry in logs if entry["id"] > last_seen]
    return {
        "session": session,
        "logs": logs,
        "ready": gate_ready(len(logs), len(fresh)),
        "latest": gates[-1] if gates else None,
    }


def run_gate(connection, idea_id, head_id, founder_text, settings, jev_transport=None, starter=False):
    """Scores this session's tasting logs. Raises GateNotReady when there are too
    few logs or nothing new since the last attempt."""
    status = gate_status(connection, idea_id, founder_text.get("evidence") or [])
    if not status["ready"]:
        raise GateNotReady()
    logs = status["logs"][-GATE_WINDOW:]
    state = {
        "one_liner": founder_text["one_liner"],
        "story": founder_text["story"],
        "conversations": [_log_state(entry) for entry in logs],
    }
    return record_gate(
        connection,
        idea_id,
        head_id,
        status["session"],
        max(entry["id"] for entry in logs),
        state,
        settings["jev_key"],
        budget=settings.get("jev_budget"),
        transport=jev_transport,
        starter=starter,
    )


def sessions_for(connection, idea_id):
    if idea_id is None:
        return 1
    return gates_passed(connection, idea_id) + 1


def step_for(connection, revision_ids, sessions=1):
    found = verdicts_for(connection, revision_ids)
    labels = [found[rid]["label"] if rid in found else "PENDING" for rid in revision_ids]
    return next_step(labels, sessions)


def conversation(connection, revision_ids, founder_text):
    chef = chef_for(connection, revision_ids)
    messages = [
        {
            "role": "founder",
            "text": "One-liner: " + founder_text["one_liner"] + "\n\nStory: " + founder_text["story"],
        }
    ]
    for revision_id, answer in zip(revision_ids, founder_text["answers"]):
        turn = chef.get(revision_id, {}).get("turn")
        if turn:
            messages.append({"role": "chef", "text": (turn["question"] + " " + turn["body"]).strip()})
        messages.append({"role": "founder", "text": answer})
    return messages


def _latest_question(connection, revision_ids):
    if len(revision_ids) < 2:
        return ""
    previous = revision_ids[-2]
    turn = chef_for(connection, [previous]).get(previous, {}).get("turn")
    return turn["question"] if turn else ""


def _log_state(entry):
    found = {key: entry[key] for key in ("who", "role", "spoken_on", "today_they", "paid", "quote")}
    found["kind"] = entry.get("kind", "conversation")
    if found["kind"] == "fact":
        found["source"] = entry.get("source", "")
    return found
