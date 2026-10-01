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
| `COACH_API_KEY` | empty | Key for Chef's model. Without it, the verdict shows and Chef's reply waits for a retry |
| `COACH_URL` | Gemini's OpenAI-compatible endpoint | Any OpenAI-compatible chat completions URL |
| `COACH_MODEL` | `gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite,gemini-3.5-flash-lite` | Model Chef uses. A comma-separated list is tried in order when a model is busy |

The database file is `DATA_DIR/pitchkitchen.sqlite`. Startup creates the file and the `ideas`, `revisions`, and `verdicts` tables if they are missing. No login is required.

An idea starts with a pitch: a one-liner ("We help [who] [do what] by [how]") and a longer story. Each answer is stored as a new revision whose parent is the revision before it. After every save, Jev scores everything the founder has written on that branch.

Jev returns market need, feasibility, and differentiation on a 0–3 scale, plus a safety-risk probability. The label is decided in `pitchkitchen/review/logic.py`: safety above 0.5 forces KILL, any score under 2.0 is FIX, confidence under 0.6 blocks SHIP, and a clean result is SHIP. A finished label is not replaced.

## Tests

```bash
pytest --cov=pitchkitchen --cov-report=term-missing
```

The target is at least 70% on the core business logic. Idea checks and branch walking are in `tests/test_ideas.py`. Verdict rules are in `tests/test_review.py`. Routes are in `tests/test_app.py`.

## Layout

- `app.py` starts the process.
- `pitchkitchen/ideas/` owns everything the founder wrote. `logic.py` checks the fields and walks a branch from the newest revision back to the pitch. `store.py` writes SQLite.
- `pitchkitchen/review/` owns everything the app says back. `logic.py` applies the cutoffs. `jev.py` calls the scoring model. `store.py` writes SQLite.
- `pitchkitchen/pages.py` is the only place the two domains are called together.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.
