from datetime import date


class IdeaTextError(Exception):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


class IdeaNotFound(Exception):
    pass


class IdeaClosed(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.status = status


STATUSES = ("cooking", "parked", "served", "binned")
CLOSED = ("served", "binned")
TONES = ("supportive", "tough", "ramsay")
DEFAULT_TONE = "tough"
EVIDENCE_PER_SESSION = 10

STATIONS = (
    {"key": "prep", "name": "Prep", "job": "Pitch"},
    {"key": "grill", "name": "Grill", "job": "Interview"},
    {"key": "tasting", "name": "Tasting", "job": "Real conversations"},
    {"key": "takeaway", "name": "Served", "job": "Pitch + next steps"},
)
STATION_KEYS = tuple(station["key"] for station in STATIONS)
AFTER_PITCH = "grill"


LABELS = {
    "display_name": "Display name",
    "one_liner": "One-liner",
    "story": "The story",
    "answer": "Answer",
    "who": "Who you talked to",
    "role": "Their role",
    "today_they": "What they do today",
    "paid": "What they pay today",
    "quote": "What they said",
    "spoken_on": "Date",
    "consent": "Consent",
    "tone": "Chef's tone",
}

LIMITS = {
    "display_name": 80,
    "one_liner": 200,
    "story": 2000,
    "answer": 1000,
    "who": 80,
    "role": 80,
    "today_they": 500,
    "paid": 200,
    "quote": 1000,
}


def clean_field(field, value, required=True):
    text = "" if value is None else str(value).strip()
    if text == "" and required:
        raise IdeaTextError(field, LABELS[field] + " is required.")
    if len(text) > LIMITS[field]:
        raise IdeaTextError(
            field,
            LABELS[field] + " must be " + str(LIMITS[field]) + " characters or fewer.",
        )
    return text


def clean_pitch(display_name, one_liner, story):
    return {
        "display_name": clean_field("display_name", display_name),
        "one_liner": clean_field("one_liner", one_liner),
        "story": clean_field("story", story),
    }


def clean_answer(answer):
    return clean_field("answer", answer)


def clean_tone(tone):
    if not tone:
        return DEFAULT_TONE
    if tone not in TONES:
        raise IdeaTextError("tone", "Pick one of Chef's tones.")
    return tone


def clean_consent(consent):
    if not consent:
        raise IdeaTextError("consent", "Tick the box to agree that Chef's AI providers and the organizers can read your idea.")


def clean_evidence(fields, today=None):
    """One logged customer conversation. The date can't be in the future."""
    today = today or date.today()
    raw_date = (fields.get("spoken_on") or "").strip()
    try:
        spoken_on = date.fromisoformat(raw_date)
    except ValueError:
        raise IdeaTextError("spoken_on", "Date must be a real date (YYYY-MM-DD).")
    if spoken_on > today:
        raise IdeaTextError("spoken_on", "Log conversations that already happened, not planned ones.")
    return {
        "who": clean_field("who", fields.get("who")),
        "role": clean_field("role", fields.get("role"), required=False),
        "spoken_on": spoken_on.isoformat(),
        "today_they": clean_field("today_they", fields.get("today_they"), required=False),
        "paid": clean_field("paid", fields.get("paid"), required=False),
        "quote": clean_field("quote", fields.get("quote")),
    }


def current_head(revisions):
    if not revisions:
        return None
    return max(revision["id"] for revision in revisions)


def walk_branch(revisions, head_id):
    by_id = {revision["id"]: revision for revision in revisions}
    branch = []
    current = by_id.get(head_id)
    while current is not None:
        branch.append(current)
        current = by_id.get(current["parent_id"])
    branch.reverse()
    return branch


def other_versions(revisions, branch):
    """For each revision on the branch, how many siblings (earlier edits) it has."""
    counts = {}
    for revision in revisions:
        if revision["parent_id"] is not None:
            counts[revision["parent_id"]] = counts.get(revision["parent_id"], 0) + 1
    return {revision["id"]: counts.get(revision["parent_id"], 1) - 1 for revision in branch if revision["parent_id"]}


def rail(current):
    """Every station in order, marked done, current, or upcoming relative to `current`."""
    position = STATION_KEYS.index(current)
    stations = []
    for index, station in enumerate(STATIONS):
        if index < position:
            state = "done"
        elif index == position:
            state = "current"
        else:
            state = "upcoming"
        stations.append(dict(station, state=state))
    return stations


def station_name(key):
    return STATIONS[STATION_KEYS.index(key)]["name"]


def founder_text(branch, evidence=None):
    pitch = branch[0]
    return {
        "one_liner": pitch["one_liner"],
        "story": pitch["story"],
        "answers": [revision["answer"] for revision in branch[1:]],
        "evidence": list(evidence or []),
    }
