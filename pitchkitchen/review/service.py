from pitchkitchen.review.coach import ChefUnavailable, write_pitch, write_turn
from pitchkitchen.review.logic import heat, next_step
from pitchkitchen.review.store import chef_for, record_verdict, save_chef, verdicts_for


class NotServable(Exception):
    pass


def run_round(
    connection, revision_ids, founder_text, settings, jev_transport=None, chef_transport=None, idea_id=None
):
    """Scores the newest revision on a branch, then has Chef answer it.

    Safe to call again: a finished verdict or Chef turn is never redone.
    Returns {"verdict", "step", "paused"} where paused is None, "jev", or "chef".
    """
    head = revision_ids[-1]
    verdict = record_verdict(
        connection,
        head,
        founder_text,
        settings["jev_key"],
        transport=jev_transport,
        idea_id=idea_id,
        budget=settings.get("jev_budget"),
    )
    step = step_for(connection, revision_ids)
    if verdict["label"] == "PENDING":
        return {"verdict": verdict, "step": step, "paused": "jev"}
    if "turn" in chef_for(connection, [head]).get(head, {}):
        return {"verdict": verdict, "step": step, "paused": None}

    try:
        turn = write_turn(
            conversation(connection, revision_ids, founder_text),
            verdict,
            verdict["focus"],
            heat(verdict),
            step,
            settings["chef_key"],
            settings["chef_model"],
            settings["chef_url"],
            transport=chef_transport,
        )
    except ChefUnavailable:
        return {"verdict": verdict, "step": step, "paused": "chef"}
    save_chef(connection, head, "turn", turn["roast"], turn["question"])
    return {"verdict": verdict, "step": step, "paused": None}


def serve(connection, revision_ids, founder_text, settings, chef_transport=None):
    head = revision_ids[-1]
    verdict = verdicts_for(connection, [head]).get(head)
    if verdict is None or verdict["label"] != "SHIP":
        raise NotServable()
    pitch = write_pitch(
        conversation(connection, revision_ids, founder_text),
        settings["chef_key"],
        settings["chef_model"],
        settings["chef_url"],
        transport=chef_transport,
    )
    save_chef(connection, head, "polished", pitch)
    return pitch


def step_for(connection, revision_ids):
    found = verdicts_for(connection, revision_ids)
    labels = [found[rid]["label"] if rid in found else "PENDING" for rid in revision_ids]
    return next_step(labels)


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
            messages.append({"role": "chef", "text": (turn["body"] + " " + turn["question"]).strip()})
        messages.append({"role": "founder", "text": answer})
    return messages
