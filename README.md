# Pitch Kitchen

A single-process web app for a university venture lab. A student founder pitches an idea, Chef interviews them about what has already happened, and between sessions they go talk to real people and log what those people said. An idea is served when the evidence backs it, not when the pitch sounds good. Organizers see the whole cohort on one page: who is moving, who is stuck, and who has talked to real customers.

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
| `JEV_BUDGET_PER_IDEA` | `10` | Most successful Jev calls one idea may make. Failed calls don't count; one text is tried at most 3 times |
| `COACH_API_KEY` | empty | Key for Chef's model. Without it, the verdict shows and Chef's reply waits for a retry |
| `COACH_URL` | Gemini's OpenAI-compatible endpoint | Any OpenAI-compatible chat completions URL |
| `COACH_MODEL` | `gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite` | Model Chef uses. A comma-separated list is tried in order when a model is busy (15 s timeout each) |
| `ORGANIZER_KEY` | empty | Opens `/organizer?key=...`. Empty turns the organizer page off |

The database file is `DATA_DIR/pitchkitchen.sqlite`. Startup creates the file and every table if missing, and migrates an older database in place (old KILL/FIX/SHIP labels become UNPROVEN/PARTIAL/PROVEN).

## How it works

1. **Prep.** The founder writes a story and a one-liner ("We help [who] [do what] by [how]"). Chef can suggest three one-liners from the story. They pick Chef's tone (supportive, tough, or full Ramsay; only Ramsay swears), whether to share the idea on the cohort board, and consent to the text being sent to Gemini and Typesafe and read by organizers.
2. **Grill.** Each answer is a new revision. Jev scores it, `pitchkitchen/review/logic.py` decides the label, and Chef asks the next Mom Test question first, then reacts in a sentence or two. A session is 5 answers. Any answer can be edited; the edit is saved as a sibling revision and re-scored.
3. **Tasting.** After a session Chef writes homework: three kinds of people to talk to and three questions about their past behaviour. The founder logs each conversation (who, date, what they do and pay today, what they said). With 3 or more logs this session, one batched Jev call scores them at the gate. Passing opens the next 5-answer session.
4. **Served.** A PROVEN verdict plus at least 3 logged conversations can be served. Chef writes a pitch from the founder's own facts and three next steps.

Jev returns market need, feasibility, differentiation, and evidence (how much of the latest message is past fact) on a 0–3 scale, a safety-risk probability, and for answers whether the founder answered Chef's question. The page shows bands (None, Weak, Solid, Strong), not decimals. The label is decided in this order:

1. Safety risk above 0.5 is UNPROVEN.
2. The three scores averaging under 1.2 is UNPROVEN.
3. Answered probability under 0.5 is PARTIAL (dodged), and Chef asks again.
4. Any of the three scores under 2.0 is PARTIAL.
5. Evidence under 2.0 is PARTIAL (mostly claims).
6. Jev less than 60% sure every score is 2 or 3 is PARTIAL.
7. Anything else is PROVEN.

The tasting gate passes when evidence strength is at least 2.0 and the average of evidence strength, pain frequency, and willingness to pay is at least 1.5. It is sent back on safety risk above 0.5. A sent-back gate needs a new log before the next try.

Two UNPROVEN in a row bin the idea. A binned idea can be pivoted: the pitch form opens prefilled, and the new idea links back to the old one.

**Privacy.** Every idea lives at `/i/<token>`, a random link. The home page lists only ideas created in this browser (their tokens are in a cookie) plus ideas their founders chose to share. There is no login; anyone holding a link can act on that idea.

**Organizers.** `/organizer?key=ORGANIZER_KEY` shows ideas, founders, active this week, answers per idea, the share who talked to real people, the share of founders who came back on another day, a funnel from pitch to served, and a table with stuck ideas (7+ days idle) first.

## Tests

```bash
pytest --cov=pitchkitchen --cov-report=term-missing
```

The target is at least 70% on the core business logic. The last run was 111 tests passing at 97% total coverage. Tests never call the network: Jev and Chef are replaced by fakes in `tests/fakes.py`.

- `tests/test_ideas.py`: field and evidence checks, branch walking, sibling edits, tokens, pivots, storage and migration.
- `tests/test_review.py`: verdict and gate rules, bands, Jev parsing, budget and retry cap, verdict and gate storage, label migration.
- `tests/test_chef.py`: Chef's prompts per tone, sessions, homework, one-liner suggestions, served pitch, model fallback.
- `tests/test_service.py`: one full round, homework, the tasting gate, and serving.
- `tests/test_loop.py`: whole journeys through the pages, including every ending.
- `tests/test_app.py`: routes, private links and the home page cookie, form errors, Prep suggestions.
- `tests/test_cohort.py`: cohort metrics, stuck ideas, and the organizer key.
- `tests/test_config.py`: environment variables and the optional `.env` file.

## Layout

- `app.py` starts the process.
- `pitchkitchen/config.py` reads environment variables. `pitchkitchen/db.py` opens SQLite and creates the tables.
- `pitchkitchen/ideas/` owns everything the founder wrote: ideas, revisions, and evidence logs. `logic.py` checks fields and walks a branch. `store.py` writes them.
- `pitchkitchen/review/` owns everything the app says back. `logic.py` holds the label, gate, and session rules. `jev.py` calls the scoring model. `coach.py` calls Chef's model. `service.py` runs a round, a gate, and serving. `store.py` writes verdicts, gates, Chef's messages, and the Jev call log.
- `pitchkitchen/cohort/` is pure: it turns plain dicts into organizer rows and metrics. It has no tables.
- `pitchkitchen/pages.py` (founder pages) and `pitchkitchen/organizer.py` (organizer page) are the only places the domains are called together.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.

### Tables

| Domain | Table | Columns |
|---|---|---|
| ideas | `ideas` | id, display_name, status, station, token, tone, pivot_of, shared, consent_at, created_at |
| ideas | `revisions` | id, idea_id, parent_id, kind, one_liner, story, answer, created_at |
| ideas | `evidence` | id, idea_id, session, who, role, spoken_on, today_they, paid, quote, created_at |
| review | `verdicts` | id, revision_id, market_need, feasibility, differentiation, safety_risk, confidence, evidence, answered, label, rule, created_at |
| review | `gates` | id, idea_id, session, last_evidence_id, evidence_strength, pain_frequency, willingness_to_pay, safety_risk, label, rule, created_at |
| review | `chef_messages` | id, revision_id, kind (turn, polished, homework, next_steps), body, question, created_at |
| review | `jev_calls` | id, idea_id, revision_id, purpose (verdict, gate), ok, created_at |
