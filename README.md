# Pitch Kitchen

A single-process web app for a university venture lab. A student founder pitches an idea, or starts with none, Chef interviews them about what has already happened, and between sessions they find facts online and talk to real people. Every idea can export a starter pack: one Markdown file with the problem, the evidence and its sources, what to build first, and a CLAUDE.md and first prompt for Claude Code. The pack is a draft until the idea is served, which happens when real conversations back it, not when the pitch sounds good. Organizers see the whole cohort on one page: who is moving, who is stuck, and who has talked to real customers.

This repository is the Assignment 1 app. It runs as one process and stores data in SQLite. Ideas, review, and cohort are separate packages so they can be split later.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000. On macOS, AirPlay Receiver often holds port 5000; run `PORT=5050 python app.py` instead.

The process binds to `0.0.0.0`. Configure it with environment variables. For local runs, copy `.env.example` to `.env` and fill in the keys; the file is git-ignored and optional. Variables set in the shell override it.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Port the process listens on |
| `DATA_DIR` | `data` | Directory for the SQLite file |
| `TYPESAFE_API_KEY` | empty | Key for the Jev API. Without it, text saves and verdicts stay PENDING |
| `JEV_BUDGET_PER_IDEA` | `15` | Most successful Jev calls one idea may make: two full sessions (pitch, 10 answers, a gate) plus a retry. Failed calls don't count; one text is tried at most 3 times |
| `COACH_API_KEY` | empty | Key for Chef's model. Without it, the verdict shows and Chef's reply waits for a retry. Web fact search uses the same key with Gemini's own API and Google Search, so it only works with a Gemini key that has search quota (the free tier often has none); without it, Chef suggests what to look up instead |
| `COACH_URL` | Gemini's OpenAI-compatible endpoint | Any OpenAI-compatible chat completions URL |
| `COACH_MODEL` | `gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite` | Model Chef uses. A comma-separated list is tried in order when a model is busy (15 s timeout each) |
| `ORGANIZER_KEY` | empty | Opens `/organizer?key=...`. Empty turns the organizer page off |

The database file is `DATA_DIR/pitchkitchen.sqlite`. Startup creates the file and every table if missing, and migrates an older database in place (old KILL/FIX/SHIP labels become UNPROVEN/PARTIAL/PROVEN).

## How it works

1. **Prep.** The founder picks where they are starting: no idea yet, an idea, or already talked to customers. With no idea, they tell Chef about their week and Chef sparks three small problems from it, each with a story and a first fact to check. The founder writes a story and a one-liner ("We help [who] [do what] by [how]"). Chef can suggest three one-liners from the story. They pick Chef's tone (supportive, tough, or full Ramsay; only Ramsay swears), whether to share the idea on the cohort board, and consent to the text being sent to Gemini and Typesafe and read by organizers.
2. **Grill.** Each answer is a new revision. Jev scores it, `pitchkitchen/review/logic.py` decides the label, and Chef asks the next Mom Test question first, then reacts in a sentence or two. Chef coaches beginners in plain words and turns "I don't know" into a small mission for the week; with founders who say they talked to customers, he expects names, dates, and numbers. A session is 5 answers. Any answer can be edited; the edit is saved as a sibling revision and re-scored.
3. **Tasting.** After a session Chef writes homework: three kinds of people to talk to and three questions about their past behaviour. The founder logs each conversation (who, date, what they do and pay today, what they said) and can log facts: Chef searches the web with Google Search through Gemini, and only sentences Google ties to a source link are shown; the founder ticks the ones to keep, or adds a fact with its link by hand. If search is unavailable, Chef suggests four things to look up and the page turns each into a Google search link; the model gives no facts or links in that case. With 3 or more logs this session, one batched Jev call scores them at the gate. Passing opens the next 5-answer session.
4. **Served.** A PROVEN verdict plus at least 3 logged conversations (facts don't count) can be served. Chef writes a pitch from the founder's own facts and three next steps.
5. **Starter pack.** At any point Chef can write the plan part of a starter pack: problem, first customer, assumptions to test, 3 to 5 version-one features, user stories, screens, data model, stack, first tasks, and a first prompt for Claude Code. `pitchkitchen/pack.py` copies the evidence section straight from the logs, so a pack never cites a conversation that was not logged, and adds a CLAUDE.md. It downloads from `/i/<token>/starter-pack.md`, is marked Draft until the idea is served and Verified after, and the page says when it is out of date.

Jev returns market need, feasibility, differentiation, and evidence (how much of the latest message is past fact) on a 0–3 scale, a safety-risk probability, and for answers whether the founder answered Chef's question. Market need judges the problem itself; how well the founder backs it up is the evidence score. The page shows bands (None, Weak, Solid, Strong), not decimals. The label is decided in this order:

1. Safety risk above 0.5 is UNPROVEN.
2. Answered probability under 0.5 is PARTIAL (dodged), and Chef asks again. A dodge never counts toward the bin, and an honest none, zero, or never counts as an answer.
3. The three scores averaging under 1.2 is UNPROVEN.
4. Any of the three scores under 2.0 is PARTIAL; the page names which ones and what to show next.
5. Evidence under 2.0 is PARTIAL (mostly claims).
6. Jev less than 60% sure every score is 2 or 3 is PARTIAL.
7. Anything else is PROVEN.

The tasting gate passes when evidence strength is at least 2.0 and the average of evidence strength, pain frequency, and willingness to pay is at least 1.5. It is sent back on safety risk above 0.5. A sent-back gate needs a new log before the next try. A beginner's first gate (no idea yet, or an idea without customers) is a starter gate: any three facts or conversations pass it unless they look unsafe, and Jev's bars still show how strong they were.

Two UNPROVEN answers in a row inside a session bin the idea, but only after a passed tasting gate. In the first session nobody has talked to customers yet, so a weak idea finishes its five answers and goes to homework. A binned idea can be pivoted: the pitch form opens prefilled, and the new idea links back to the old one.

**Privacy.** Every idea lives at `/i/<token>`, a random link. The home page lists only ideas created in this browser (their tokens are in a cookie) plus ideas their founders chose to share. There is no login; anyone holding a link can act on that idea.

**Organizers.** `/organizer?key=ORGANIZER_KEY` shows ideas, founders, active this week, answers per idea, the share who talked to real people, the share of founders who came back on another day, a funnel from pitch to served, and a table with stuck ideas (7+ days idle) first.

## Tests

```bash
pytest --cov=pitchkitchen --cov-report=term-missing
```

The target is at least 70% on the core business logic. The last run was 137 tests passing at 97% total coverage. Tests never call the network: Jev, Chef, and the web search are replaced by fakes in `tests/fakes.py`.

- `tests/test_ideas.py`: field and evidence checks, branch walking, sibling edits, tokens, pivots, storage and migration.
- `tests/test_review.py`: verdict and gate rules, bands, Jev parsing, budget and retry cap, verdict and gate storage, label migration.
- `tests/test_chef.py`: Chef's prompts per tone and level, sessions, homework, one-liner and spark suggestions, sourced web facts, the starter pack plan, served pitch, model fallback.
- `tests/test_service.py`: one full round, homework, the tasting and starter gates, serving on conversations only, and storing a starter pack.
- `tests/test_pack.py`: the starter pack Markdown, draft and verified.
- `tests/test_loop.py`: whole journeys through the pages, including every ending, a beginner keeping web facts, and downloading a starter pack.
- `tests/test_app.py`: routes, private links and the home page cookie, form errors, Prep suggestions.
- `tests/test_cohort.py`: cohort metrics, stuck ideas, and the organizer key.
- `tests/test_config.py`: environment variables and the optional `.env` file.

## Layout

- `app.py` starts the process.
- `pitchkitchen/config.py` reads environment variables. `pitchkitchen/db.py` opens SQLite and creates the tables.
- `pitchkitchen/ideas/` owns everything the founder wrote: ideas, revisions, and evidence logs. `logic.py` checks fields and walks a branch. `store.py` writes them.
- `pitchkitchen/review/` owns everything the app says back. `logic.py` holds the label, gate, and session rules. `jev.py` calls the scoring model. `coach.py` calls Chef's model. `service.py` runs a round, a gate, and serving. `store.py` writes verdicts, gates, Chef's messages, and the Jev call log.
- `pitchkitchen/cohort/` is pure: it turns plain dicts into organizer rows and metrics. It has no tables.
- `pitchkitchen/pack.py` is pure too: it turns an idea's logs and Chef's plan into the starter pack Markdown.
- `pitchkitchen/pages.py` (founder pages) and `pitchkitchen/organizer.py` (organizer page) are the only places the domains are called together.
- `pitchkitchen/templates/` and `pitchkitchen/static/` are the frontend. `chat.js` locks a form while Chef works and shows the answer before the reply arrives. `kitchen.js` runs the small interactions: local times, counters, saved drafts, copy buttons, the delete dialog, keyboard shortcuts, and sorting the organizer table. htmx and the Bricolage Grotesque font (SIL Open Font License) are vendored, so the pages load nothing from the internet.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.

### Tables

| Domain | Table | Columns |
|---|---|---|
| ideas | `ideas` | id, display_name, status, station, token, tone, level (new, idea, tested), pivot_of, shared, consent_at, created_at |
| ideas | `revisions` | id, idea_id, parent_id, kind, one_liner, story, answer, created_at |
| ideas | `evidence` | id, idea_id, session, kind (conversation, fact), who, role, spoken_on, today_they, paid, quote, source, created_at |
| review | `verdicts` | id, revision_id, market_need, feasibility, differentiation, safety_risk, confidence, evidence, answered, label, rule, created_at |
| review | `gates` | id, idea_id, session, last_evidence_id, evidence_strength, pain_frequency, willingness_to_pay, safety_risk, label, rule, created_at |
| review | `chef_messages` | id, revision_id, kind (turn, polished, homework, next_steps, starter_pack), body, question, created_at |
| review | `jev_calls` | id, idea_id, revision_id, purpose (verdict, gate), ok, created_at |
