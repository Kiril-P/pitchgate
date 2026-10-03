# Pitch Kitchen

A single-process web app for a student founder club. A member pitches a startup idea in one line, tells the story behind it, and then answers for it. Every step is scored KILL, FIX, or SHIP.

This repository is the Assignment 1 app. It runs as one process and stores data in SQLite. Ideas and review are separate packages so they can be split later.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

The process binds to `0.0.0.0`. Configure it with environment variables. For local runs, copy `.env.example` to `.env` and fill in the keys; the file is git-ignored and optional. Variables set in the shell override it.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Port the process listens on |
| `DATA_DIR` | `data` | Directory for the SQLite file |
| `TYPESAFE_API_KEY` | empty | Key for the Jev API. Without it, text saves and the verdict stays PENDING |
| `JEV_BUDGET_PER_IDEA` | `10` | Most Jev calls one idea may make, failed calls included. After that, verdicts stay PENDING |
| `COACH_API_KEY` | empty | Key for Chef's model. Without it, the verdict shows and Chef's reply waits for a retry |
| `COACH_URL` | Gemini's OpenAI-compatible endpoint | Any OpenAI-compatible chat completions URL |
| `COACH_MODEL` | `gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-3.5-flash-lite` | Model Chef uses. A comma-separated list is tried in order when a model is busy |

The database file is `DATA_DIR/pitchkitchen.sqlite`. Startup creates the file and the `ideas`, `revisions`, `verdicts`, `chef_messages`, and `jev_calls` tables if they are missing. `jev_calls` logs every Jev request per idea so `JEV_BUDGET_PER_IDEA` can be enforced. No login is required.

An idea starts with a pitch: a one-liner ("We help [who] [do what] by [how]") and a longer story. Each answer is stored as a new revision whose parent is the revision before it. After every save, Jev scores everything the founder has written on that branch, and Chef replies with a roast and one Mom Test question about the weakest score.

Jev returns market need, feasibility, and differentiation on a 0–3 scale, plus a safety-risk probability. The label is decided in `pitchkitchen/review/logic.py`, in this order:

1. Safety risk above 0.5 is KILL.
2. The three scores averaging under 1.2 is KILL.
3. Any score under 2.0 is FIX.
4. Jev less than 60% sure that every score is 2 or 3 is FIX.
5. Anything else is SHIP.

A finished label is not replaced. Two KILLs in a row bin the idea, and after 5 answers the last verdict stands. A SHIP can be saved as final, and Chef writes the polished pitch. If Jev or Chef is unavailable, the answer is kept and the page offers a retry.

## Tests

```bash
pytest --cov=pitchkitchen --cov-report=term-missing
```

The target is at least 70% on the core business logic. The last run was 63 tests passing at 94% total coverage. Tests never call the network: Jev and Chef are replaced by fakes in `tests/fakes.py`.

- `tests/test_ideas.py`: field checks, branch walking, and idea storage.
- `tests/test_review.py`: verdict rules, focus, heat, round cap, and verdict storage.
- `tests/test_chef.py`: Chef's request, reply parsing, and model fallback.
- `tests/test_service.py`: one full round and saving a SHIP as final.
- `tests/test_loop.py`: whole interviews through the pages, including every ending.
- `tests/test_app.py`: routes and form errors.
- `tests/test_config.py`: environment variables and the optional `.env` file.

## Layout

- `app.py` starts the process.
- `pitchkitchen/config.py` reads environment variables. `pitchkitchen/db.py` opens SQLite and creates the tables.
- `pitchkitchen/ideas/` owns everything the founder wrote. `logic.py` checks the fields and walks a branch from the newest revision back to the pitch. `store.py` writes the ideas and revisions.
- `pitchkitchen/review/` owns everything the app says back. `logic.py` applies the cutoffs and round rules. `jev.py` calls the scoring model. `coach.py` calls Chef's model. `service.py` runs one round: Jev, then the rules, then Chef. `store.py` writes verdicts, Chef's messages, and the Jev call log.
- `pitchkitchen/pages.py` is the only place the two domains are called together.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.
