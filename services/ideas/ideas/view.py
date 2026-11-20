from ideas.logic import CLOSED, LIMITS, other_versions, rail, station_name

REVIEW_DOWN = "Scores and Chef's questions can't be loaded right now. Your idea and logs are safe; try again in a minute."


def public(idea):
    return {key: value for key, value in idea.items() if key not in ("revisions", "branch", "branch_ids", "activity")}


def idea_view(idea, evidence, state, pivot_from=None):
    """The idea page as JSON: what ideas stores, merged with what review says about it.
    With state None, because review could not be reached, the founder's own text still comes back."""
    versions = other_versions(idea["revisions"], idea["branch"])
    verdicts = state["verdicts"] if state else {}
    chef = state["chef"] if state else {}
    branch = [
        dict(
            revision,
            verdict=verdicts.get(str(revision["id"])),
            chef=chef.get(str(revision["id"]), {}).get("turn"),
            versions=versions.get(revision["id"], 0),
        )
        for revision in idea["branch"]
    ]
    talks = sum(1 for entry in evidence if entry["kind"] == "conversation")
    found = {
        "idea": dict(public(idea), station_name=station_name(idea["station"])),
        "stations": rail(idea["station"]),
        "branch": branch,
        "closed": idea["status"] in CLOSED,
        "evidence": evidence,
        "talks": talks,
        "facts": len(evidence) - talks,
        "pivot_from": {"token": pivot_from["token"], "one_liner": pivot_from["branch"][0]["one_liner"]} if pivot_from else None,
        "limits": LIMITS,
        "review": None,
        "notice": None,
    }
    if state is None:
        found["notice"] = REVIEW_DOWN
        return found

    head = branch[-1]
    head_chef = chef.get(str(head["id"]), {})
    paused = None
    if head["verdict"] is None or head["verdict"]["label"] == "PENDING":
        paused = "jev"
    elif head["chef"] is None or (state["step"] == "homework" and "homework" not in head_chef):
        paused = "chef"
    verified = idea["status"] == "served"
    pack = state["pack"]
    found["review"] = {
        "step": state["step"],
        "paused": paused,
        "sessions": state["sessions"],
        "answers_left": state["answers_left"],
        "session_answers": state["session_answers"],
        "homework": state["homework"],
        "polished": head_chef.get("polished"),
        "next_steps": head_chef.get("next_steps"),
        "gate": state["gate"],
        "servable": state["servable"],
        "serve_min_logs": state["serve_min_logs"],
        "starter": state["starter"],
        "starter_gate": state["starter_gate"],
        "jev_used": state["jev_used"],
        "jev_budget": state["jev_budget"],
        "pack": pack["body"] if pack else None,
        "pack_stale": pack is not None
        and (pack["revision_id"] != head["id"] or pack["body"]["logs"] != len(evidence) or pack["body"]["verified"] != verified),
    }
    return found


def summary(listed, label):
    """One idea on a board, from list_ideas, with its newest verdict label (None when review is unreachable)."""
    return dict(public(listed), station_name=station_name(listed["station"]), label=label)
