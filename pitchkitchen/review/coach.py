import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT = 15
SEARCH_TIMEOUT = 40
DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
SEARCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"

TONES = ("supportive", "tough", "ramsay")
DEFAULT_TONE = "tough"
DEFAULT_LEVEL = "idea"

LEVEL_RULES = {
    "new": (
        "This founder is a beginner who started with no idea. Use plain words and no jargon. "
        "Say in one short sentence why you ask. If they don't know, turn your question into one small mission "
        "for this week, like finding one competitor and its price or asking one friend when they last had the problem."
    ),
    "idea": (
        "This founder has an idea but little evidence yet. Be concrete. If they don't know, give them one small "
        "mission to find out this week: a fact they can look up, or one person they can ask."
    ),
    "tested": (
        "This founder says they have already talked to customers. Expect names, dates, and numbers, and hold them to it."
    ),
}

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
        "You roast the idea and the founder's claims, never the person's identity or their customers. Use the founder's own words against them."
    ),
}

GROUND_RULES = (
    "You only care about facts: what people did, paid, said, and how often. You never accept hypotheticals. "
    "Never mention Jev, scores, numbers out of 3, labels, rules, or that anything was scored: speak as if you judged it yourself. "
    "Never assume the founder interviewed, tested, or sold anything they have not said they did. "
    "If the founder states numbers or customers that do not appear in their logged conversations, ask for the specifics behind them: who, when, how many. "
    "Founders log conversations after a grill session, so never scold them for having none yet. "
    "Judge what is proven, not whether the idea is good: an idea without evidence is not proven yet, never dead or hopeless. "
    "Never say something is proven unless the private notes say the latest version is PROVEN. "
    "Quote the founder's answers and logs exactly, and never ask for a fact they already gave. "
    "If the founder asks what is missing, say in plain words which area is still weak and what would show it, without numbers."
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


def persona(tone, level=DEFAULT_LEVEL):
    return "\n".join([PERSONAS.get(tone, PERSONAS[DEFAULT_TONE]), GROUND_RULES, LEVEL_RULES.get(level, LEVEL_RULES[DEFAULT_LEVEL])])


def evidence_text(logs):
    talks = [entry for entry in logs or [] if entry.get("kind", "conversation") == "conversation"]
    facts = [entry for entry in logs or [] if entry.get("kind") == "fact"]
    lines = []
    if talks:
        lines.append("Customer conversations the founder logged:")
        for entry in talks:
            lines.append(
                "- {who} ({role}), {spoken_on}: does today: {today_they}; paid: {paid}; said: \"{quote}\"".format(
                    **{key: entry.get(key) or "n/a" for key in ("who", "role", "spoken_on", "today_they", "paid", "quote")}
                )
            )
    else:
        lines.append("The founder has not logged any customer conversations yet.")
    if facts:
        lines.append("Facts the founder found online (they show the market, not that these customers have the problem):")
        for entry in facts:
            lines.append("- {quote} (source: {who}, {source})".format(**entry))
    return "\n".join(lines)


def write_turn(
    conversation, verdict, focus, heat, step, api_key,
    model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, tone=DEFAULT_TONE, evidence=None, level=DEFAULT_LEVEL,
):
    instructions = "\n".join(
        [
            persona(tone, level),
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
    level=DEFAULT_LEVEL,
):
    reach = (
        "people they can actually reach this week: friends, classmates, people in their group chats"
        if level in ("new", "idea")
        else "specific enough to find: role and where"
    )
    instructions = "\n".join(
        [
            persona(tone, level),
            "",
            "The founder's grill session is over. Give them homework before the next one.",
            "The weakest area is " + FOCUS_NAMES[focus] + ".",
            evidence_text(evidence),
            "Name exactly 3 kinds of people to talk to this week (" + reach + "), "
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


def suggest_sparks(about, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None):
    """For a founder with no idea yet: three small problems from their own life to start testing."""
    instructions = "\n".join(
        [
            "You help a student who has no startup idea yet find a first problem worth testing.",
            "From what they wrote about their life, suggest exactly 3 small, real problems that they or people around them run into often.",
            'For each: a one-liner in the form "We help [who] [do what] by [how]" under 150 characters; '
            "a story of 2 to 3 sentences in the student's own first-person voice, using only what they wrote; "
            "and the first fact they could check this week.",
            'Reply with JSON only: {"sparks": [{"one_liner": "...", "story": "...", "first_fact": "..."}]}',
        ]
    )
    reply = _complete(instructions, [{"role": "founder", "text": about}], api_key, model, url, transport)
    sparks = []
    items = reply.get("sparks")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and _text(item.get("one_liner")):
            sparks.append(
                {
                    "one_liner": _text(item.get("one_liner")),
                    "story": _text(item.get("story")),
                    "first_fact": _text(item.get("first_fact")),
                }
            )
    if not sparks:
        raise ChefUnavailable()
    return sparks[:3]


def find_facts(one_liner, story, api_key, model=DEFAULT_MODEL, transport=None):
    """Searches the web with Gemini's Google Search tool. Only sentences that Google ties to a
    source link come back, so every fact the founder sees can be checked."""
    if not api_key:
        raise ChefUnavailable()
    prompt = (
        "Search the web for facts about the problem behind this startup idea. Give 5 short, specific facts, "
        "one sentence each, with numbers or names where possible: competitors and what they charge, how often "
        "the problem happens, what people pay or do about it today, and public complaints.\n"
        "Idea: " + one_liner + "\nStory: " + story
    )
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    models = [name.strip() for name in model.split(",") if name.strip()]
    for index, name in enumerate(models):
        try:
            if transport is None:
                payload = _send(SEARCH_URL.format(model=name), body, {"x-goog-api-key": api_key}, SEARCH_TIMEOUT)
            else:
                payload = transport(dict(body, model=name), api_key)
            break
        except ChefUnavailable:
            if index == len(models) - 1:
                raise
    facts = parse_facts(payload)
    if not facts:
        raise ChefUnavailable()
    return facts


def suggest_searches(one_liner, story, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None):
    """When web search is unavailable: what the founder can look up themselves. The model
    gives no facts and no links; the page turns each query into a plain search link."""
    instructions = "\n".join(
        [
            "You help a student founder find facts about the problem behind their idea. You cannot browse the web.",
            "Do not state any facts, numbers, or links. Suggest exactly 4 things to look up: competitors and what they "
            "charge, how often the problem happens, what people pay or do about it today, and public complaints.",
            "For each: what to find, in one short sentence, and a web search query that would find it.",
            'Reply with JSON only: {"searches": [{"find": "...", "query": "..."}]}',
        ]
    )
    conversation = [{"role": "founder", "text": "Idea: " + one_liner + "\nStory: " + story}]
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    searches = [item for item in _pairs(reply.get("searches"), "find", "query") if item["query"]]
    if not searches:
        raise ChefUnavailable()
    return searches[:4]


def parse_facts(payload):
    try:
        meta = payload["candidates"][0].get("groundingMetadata") or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ChefUnavailable()
    sources = [chunk.get("web") or {} for chunk in meta.get("groundingChunks") or []]
    facts = []
    for support in meta.get("groundingSupports") or []:
        text = _text((support.get("segment") or {}).get("text")).lstrip("*-• ").strip()
        linked = [sources[i] for i in support.get("groundingChunkIndices") or [] if i < len(sources) and sources[i].get("uri")]
        if len(text) < 25 or not linked or any(fact["fact"] == text for fact in facts):
            continue
        facts.append({"fact": text[:1000], "source": linked[0]["uri"], "site": _text(linked[0].get("title"))[:80]})
    return facts[:5]


def write_starter_pack(
    conversation, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, evidence=None, verified=False
):
    """The plan part of a starter pack. The evidence part is copied from the logs by pitchkitchen/pack.py."""
    instructions = "\n".join(
        [
            "You are Chef from Pitch Kitchen. Turn this founder's idea into a starter pack for building a first version "
            "with Claude Code, an AI coding assistant.",
            "Use only facts the founder stated or logged. Anything the evidence does not show goes in assumptions, "
            "each worded as something to test.",
            "The idea is served: the evidence backs it, so plan the smallest product that serves the people in the logs."
            if verified
            else "The idea is not proven yet: plan the smallest product that helps the founder learn whether the problem is real.",
            evidence_text(evidence),
            "Keep version one to 3 to 5 features a beginner can build in a weekend, each tied to a fact or an assumption. "
            "Prefer a simple stack: one process and SQLite unless the facts need more.",
            "user_stories use the form 'As a ..., I want ..., so that ...'. data_model lists tables and their fields. "
            "tasks are 8 to 10 small build steps in order, the first runnable within an hour. claude_prompt is the "
            "first message to paste into Claude Code, under 200 words: what to build first, the stack, the version-one "
            "features, and to ask before adding anything else.",
            'Reply with JSON only: {"problem": "...", "first_customer": "...", "assumptions": ["..."], '
            '"mvp": [{"feature": "...", "why": "..."}], "not_yet": ["..."], "user_stories": ["..."], '
            '"screens": ["..."], "data_model": [{"table": "...", "fields": "..."}], "stack": "...", '
            '"tasks": ["..."], "claude_prompt": "..."}',
        ]
    )
    reply = _complete(instructions, conversation, api_key, model, url, transport)
    pack = {
        "problem": _text(reply.get("problem")),
        "first_customer": _text(reply.get("first_customer")),
        "assumptions": _strings(reply.get("assumptions")),
        "mvp": _pairs(reply.get("mvp"), "feature", "why"),
        "not_yet": _strings(reply.get("not_yet")),
        "user_stories": _strings(reply.get("user_stories")),
        "screens": _strings(reply.get("screens")),
        "data_model": _pairs(reply.get("data_model"), "table", "fields"),
        "stack": _text(reply.get("stack")),
        "tasks": _strings(reply.get("tasks")),
        "claude_prompt": _text(reply.get("claude_prompt")),
    }
    if not (pack["problem"] and pack["mvp"] and pack["tasks"] and pack["claude_prompt"]):
        raise ChefUnavailable()
    return pack


def write_pitch(conversation, api_key, model=DEFAULT_MODEL, url=DEFAULT_URL, transport=None, evidence=None):
    instructions = "\n".join(
        [
            "You are Chef from Pitch Kitchen. This idea is backed by evidence. Drop the act and write the founder's final pitch.",
            "One paragraph, 80 to 120 words, first person plural (\"We help...\").",
            "Use only facts the founder stated or logged. Prefer facts from the logged conversations. Do not invent numbers, customers, or traction.",
            "Keep each number's scope exactly as the founder gave it: one clinic's result stays one clinic's result.",
            evidence_text(evidence),
            "Then list 3 concrete next steps for the coming two weeks that test what is still not proven.",
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


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _strings(value):
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _pairs(value, first, second):
    if not isinstance(value, list):
        return []
    return [
        {first: _text(item.get(first)), second: _text(item.get(second))}
        for item in value
        if isinstance(item, dict) and _text(item.get(first))
    ]


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
    return _send(url, body, {"Authorization": "Bearer " + api_key}, TIMEOUT)


def _send(url, body, headers, timeout):
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=dict(headers, **{"Content-Type": "application/json"}),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log.warning("Chef request failed: HTTP %s %s", error.code, error.read()[:300])
        raise ChefUnavailable()
    except (OSError, ValueError) as error:
        log.warning("Chef request failed: %r", error)
        raise ChefUnavailable()
