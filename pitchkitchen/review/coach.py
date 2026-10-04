import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT = 15
DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_MODEL = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"

TONES = ("supportive", "tough", "ramsay")
DEFAULT_TONE = "tough"

PERSONAS = {
    "supportive": (
        "You are Chef, a warm but honest startup mentor at Pitch Kitchen, a student venture lab tool. "
        "You encourage the founder, point out what is genuinely good, and are honest about gaps. No swearing, no insults."
    ),
    "tough": (
        "You are Chef, head of Pitch Kitchen, a student venture lab tool. You are direct, impatient with vague talk, "
        "and dry. You challenge the idea hard but stay professional: no swearing, no insults, never about the person."
    ),
    "ramsay": (
        "You are Chef, head of Pitch Kitchen: a startup idea kitchen run like Gordon Ramsay runs a restaurant. "
        "You are loud, impatient, funny, and you may swear when it lands. "
        "You roast the idea and the answers, never the person's identity. Use the founder's own words against them."
    ),
}

GROUND_RULES = (
    "You only care about facts: what people did, paid, said, and how often. You never accept hypotheticals. "
    "Never mention Jev, scores, numbers out of 3, labels, rules, or that anything was scored: speak as if you judged it yourself. "
    "Never assume the founder interviewed, tested, or sold anything they have not said they did. "
    "If the founder states numbers or customers that do not appear in their logged conversations, ask for the specifics behind them: who, when, how many. "
    "Founders log conversations after a grill session, so never scold them for having none yet. "
    "Judge what is proven, not whether the idea is good: an idea without evidence is not proven yet, never dead or hopeless."
)

TURN_RULES = {
    "open": "Ask exactly one question with one thing to answer: one number, one name, or one event. It must be about {focus_name}. Ask about past behaviour and facts (Mom Test): what happened, who, how many, how much, when. No hypotheticals, and never join two questions with 'and' or 'or'.",
    "homework": "This was the founder's last answer this session. Do not ask a question; set \"question\" to \"\". Tell them the next step is to go and talk to real people before the next session.",
    "binned": "This idea was UNPROVEN twice in a row, even after a tasting session with real conversations. It is binned. Do not ask a question; set \"question\" to \"\". Say plainly what it still did not prove, and that a pivot, a different customer or problem, is welcome.",
}

HEAT_RULES = {
    "normal": "The idea has something. If it is strong, admit it and push them to sharpen it.",
    "harsh": "Nothing important is proven yet and the idea looks weak. Your question must push for one hard fact, or a pivot to a customer, problem, or approach they have evidence for.",
}

FOCUS_NAMES = {
    "market_need": "market need (is the problem real and painful)",
    "feasibility": "feasibility (can this team actually build it)",
    "differentiation": "differentiation (why this beats what people use now)",
    "safety_risk": "safety (the idea looks illegal or harmful to the people it is for)",
    "answered": "the question you asked last time, which the founder dodged; ask it again, sharper",
    "evidence": "evidence (they gave opinions or plans; ask what already happened)",
}


class ChefUnavailable(Exception):
    pass


def persona(tone):
    return PERSONAS.get(tone, PERSONAS[DEFAULT_TONE]) + "\n" + GROUND_RULES


def evidence_text(logs):
    if not logs:
        return "The founder has not logged any customer conversations yet."
    lines = ["Customer conversations the founder logged:"]
    for entry in logs:
        lines.append(
            "- {who} ({role}), {spoken_on}: does today: {today_they}; paid: {paid}; said: \"{quote}\"".format(
                **{key: entry.get(key) or "n/a" for key in ("who", "role", "spoken_on", "today_they", "paid", "quote")}
            )
        )
    return "\n".join(lines)


def write_turn(
    conversation, verdict, focus, heat, step, api_key,
    model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, tone=DEFAULT_TONE, evidence=None,
):
    instructions = "\n".join(
        [
            persona(tone),
            "",
            "Private notes, never repeat them: the latest version is " + verdict["label"] + ".",
            "Market need {}, feasibility {}, differentiation {}.".format(
                verdict.get("market_need_band") or "unknown",
                verdict.get("feasibility_band") or "unknown",
                verdict.get("differentiation_band") or "unknown",
            ),
            "Focus on " + FOCUS_NAMES[focus] + ".",
            evidence_text(evidence),
            HEAT_RULES[heat],
            TURN_RULES[step].format(focus_name=FOCUS_NAMES[focus]),
            "",
            'Reply with JSON only: {"question": "one question", "reaction": "1 to 2 short sentences reacting to their latest message"}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    reaction = reply.get("reaction")
    question = reply.get("question", "")
    if not isinstance(reaction, str) or not reaction.strip() or not isinstance(question, str):
        raise ChefUnavailable()
    return {"reaction": reaction.strip(), "question": question.strip() if step == "open" else ""}


def write_homework(
    conversation, focus, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, tone=DEFAULT_TONE, evidence=None,
):
    instructions = "\n".join(
        [
            persona(tone),
            "",
            "The founder's grill session is over. Give them homework before the next one.",
            "The weakest area is " + FOCUS_NAMES[focus] + ".",
            evidence_text(evidence),
            "Name exactly 3 kinds of people to talk to this week (specific enough to find: role and where), "
            "and exactly 3 Mom Test questions about their past behaviour, not about the idea.",
            'Reply with JSON only: {"people": ["...", "...", "..."], "questions": ["...", "...", "..."]}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    people = _strings(reply.get("people"))
    questions = _strings(reply.get("questions"))
    if not people or not questions:
        raise ChefUnavailable()
    return {"people": people[:3], "questions": questions[:3]}


def suggest_one_liners(rough_idea, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None):
    instructions = "\n".join(
        [
            "You help student founders write a one-line pitch.",
            'Write exactly 3 different one-liners in the form "We help [who] [do what] by [how]", each under 150 characters.',
            "Use only what the founder wrote. Be specific about who.",
            'Reply with JSON only: {"one_liners": ["...", "...", "..."]}',
        ]
    )
    conversation = [{"role": "founder", "text": rough_idea}]
    one_liners = _strings(_complete(instructions, conversation, api_key, model, url, transport).get("one_liners"))
    if not one_liners:
        raise ChefUnavailable()
    return one_liners[:3]


def write_pitch(conversation, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, evidence=None):
    instructions = "\n".join(
        [
            "You are Chef from Pitch Kitchen. This idea is backed by evidence. Drop the act and write the founder's final pitch.",
            "One paragraph, 80 to 120 words, first person plural (\"We help...\").",
            "Use only facts the founder stated or logged. Prefer facts from the logged conversations. Do not invent numbers, customers, or traction.",
            evidence_text(evidence),
            "Then list 3 concrete next steps for the coming two weeks.",
            'Reply with JSON only: {"pitch": "...", "next_steps": ["...", "...", "..."]}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    pitch = reply.get("pitch")
    if not isinstance(pitch, str) or not pitch.strip():
        raise ChefUnavailable()
    return {"pitch": pitch.strip(), "next_steps": _strings(reply.get("next_steps"))[:3]}


def transcript(conversation):
    lines = []
    for message in conversation:
        speaker = "Founder" if message["role"] == "founder" else "Chef"
        lines.append(speaker + ": " + message["text"])
    return "\n\n".join(lines)


def _strings(value):
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


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
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log.warning("Chef request failed: HTTP %s %s", error.code, error.read()[:300])
        raise ChefUnavailable()
    except (OSError, ValueError) as error:
        log.warning("Chef request failed: %r", error)
        raise ChefUnavailable()
