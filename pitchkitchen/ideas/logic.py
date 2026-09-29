class IdeaTextError(Exception):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field
        self.message = message


class IdeaNotFound(Exception):
    pass


LABELS = {
    "display_name": "Display name",
    "problem": "Problem",
    "audience": "Who it is for",
    "approach": "How it would work",
}

LIMITS = {
    "display_name": 80,
    "problem": 400,
    "audience": 200,
    "approach": 400,
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


def clean_new_idea(display_name, problem, audience, approach):
    return {
        "display_name": clean_field("display_name", display_name),
        "problem": clean_field("problem", problem),
        "audience": clean_field("audience", audience),
        "approach": clean_field("approach", approach),
    }


def clean_revision(problem, audience, approach):
    return {
        "problem": clean_field("problem", problem),
        "audience": clean_field("audience", audience),
        "approach": clean_field("approach", approach),
    }
