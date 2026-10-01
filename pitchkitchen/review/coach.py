import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-3.5-flash-lite"

PERSONA = """You are Chef, head of Pitch Kitchen: a startup idea kitchen run like Gordon Ramsay runs a restaurant.
Student founders pitch ideas and you grill them. You are loud, impatient, funny, and you swear when it lands.
You roast the idea and the answers, never the person's identity. Use the founder's own words against them.
You only care about facts: what people did, paid, said, and how often. You never accept hypotheticals."""

TURN_RULES = {
    "open": "Ask exactly one question. It must be about {focus_name}. Ask about past behaviour and facts (Mom Test): what happened, who, how many, how much, when. No hypotheticals, no multi-part questions.",
    "capped": "This was the founder's last answer. Do not ask a question; set \"question\" to \"\". Tell them the verdict stands and what the one thing to fix would have been.",
    "binned": "This idea got KILL twice in a row. It is binned. Do not ask a question; set \"question\" to \"\". Send it to the bin in style and tell them to come back with a new idea.",
}

HEAT_RULES = {
    "normal": "Tone: tough but fair. If the label is SHIP, admit it grudgingly and push them to sharpen it.",
    "harsh": "Tone: brutal. The idea is close to dead. Your question must push a pivot: a different customer, problem, or approach they have evidence for.",
}

FOCUS_NAMES = {
    "market_need": "market need (is the problem real and painful)",
    "feasibility": "feasibility (can this team actually build it)",
    "differentiation": "differentiation (why this beats what people use now)",
    "safety_risk": "safety (the idea looks illegal or harmful to the people it is for)",
}


class ChefUnavailable(Exception):
    pass


def write_turn(conversation, verdict, focus, heat, step, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None):
    instructions = "\n".join(
        [
            PERSONA,
            "",
            "Jev, the scoring model, labelled the founder's latest version " + verdict["label"] + ".",
            "Scores out of 3: market need {market_need:.1f}, feasibility {feasibility:.1f}, differentiation {differentiation:.1f}. Safety risk {safety_risk:.0%}.".format(**verdict),
            "The weakest area is " + FOCUS_NAMES[focus] + ".",
            HEAT_RULES[heat],
            TURN_RULES[step].format(focus_name=FOCUS_NAMES[focus]),
            "",
            'Reply with JSON only: {"roast": "2 to 3 sentences reacting to their latest message", "question": "one question"}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    roast = reply.get("roast")
    question = reply.get("question", "")
    if not isinstance(roast, str) or not roast.strip() or not isinstance(question, str):
        raise ChefUnavailable()
    return {"roast": roast.strip(), "question": question.strip() if step == "open" else ""}


def write_pitch(conversation, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None):
    instructions = "\n".join(
        [
            "You are Chef from Pitch Kitchen. This idea passed. Drop the act and write the founder's final pitch.",
            "One paragraph, 80 to 120 words, first person plural (\"We help...\").",
            "Use only facts the founder stated. Do not invent numbers, customers, or traction.",
            'Reply with JSON only: {"pitch": "..."}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    pitch = reply.get("pitch")
    if not isinstance(pitch, str) or not pitch.strip():
        raise ChefUnavailable()
    return pitch.strip()


def transcript(conversation):
    lines = []
    for message in conversation:
        speaker = "Founder" if message["role"] == "founder" else "Chef"
        lines.append(speaker + ": " + message["text"])
    return "\n\n".join(lines)


def _complete(instructions, conversation, api_key, model, url, transport):
    if not api_key:
        raise ChefUnavailable()
    models = [name.strip() for name in model.split(",") if name.strip()]
    for index, name in enumerate(models):
        body = {
            "model": name,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": transcript(conversation)},
            ],
        }
        try:
            if transport is None:
                payload = _post(url, body, api_key)
            else:
                payload = transport(body, api_key)
            break
        except ChefUnavailable:
            if index == len(models) - 1:
                raise
    try:
        reply = json.loads(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise ChefUnavailable()
    if not isinstance(reply, dict):
        raise ChefUnavailable()
    return reply


def _post(url, body, api_key):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log.warning("Chef request failed: HTTP %s %s", error.code, error.read()[:300])
        raise ChefUnavailable()
    except (OSError, ValueError) as error:
        log.warning("Chef request failed: %r", error)
        raise ChefUnavailable()
