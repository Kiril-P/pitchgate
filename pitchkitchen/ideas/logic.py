class IdeaTextError(Exception):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


class IdeaNotFound(Exception):
    pass


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


def founder_text(branch):
    pitch = branch[0]
    return {
        "one_liner": pitch["one_liner"],
        "story": pitch["story"],
        "answers": [revision["answer"] for revision in branch[1:]],
    }
