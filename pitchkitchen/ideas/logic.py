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

STATIONS = (
    {"key": "prep", "name": "Prep", "job": "Spark", "built": True},
    {"key": "grill", "name": "Grill", "job": "Interview", "built": True},
    {"key": "tasting", "name": "Tasting", "job": "Evidence", "built": False},
    {"key": "plating", "name": "Plating", "job": "Shape", "built": False},
    {"key": "recipe", "name": "Recipe", "job": "PRD", "built": False},
    {"key": "mise", "name": "Mise en place", "job": "Tech plan", "built": False},
    {"key": "takeaway", "name": "Takeaway", "job": "Handoff", "built": False},
)
STATION_KEYS = tuple(station["key"] for station in STATIONS)
AFTER_PITCH = "grill"


LABELS = {
    "display_name": "Display name",
    "one_liner": "One-liner",
    "story": "The story",
    "answer": "Answer",
}

LIMITS = {
    "display_name": 80,
    "one_liner": 200,
    "story": 2000,
    "answer": 1000,
}


def clean_field(field, value):
    text = "" if value is None else str(value).strip()
    if text == "":
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


def founder_text(branch):
    pitch = branch[0]
    return {
        "one_liner": pitch["one_liner"],
        "story": pitch["story"],
        "answers": [revision["answer"] for revision in branch[1:]],
    }
