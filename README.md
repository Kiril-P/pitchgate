# Pitchgate

A single-process web app for a student founder club. A member writes a short startup idea, submits it, and gets a verdict: KILL, FIX, or SHIP. Editing the idea creates a new revision with its own verdict.

This repository is the Assignment 1 app. It runs as one process and stores data in SQLite. Ideas and verdicts are separate packages so they can be split later.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

The process binds to `0.0.0.0`. Configure it with environment variables. A `.env` file is not required.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5000` | Port the process listens on |
| `DATA_DIR` | `data` | Directory for the SQLite file |
| `TYPESAFE_API_KEY` | empty | Key for the Jev API. Without it, revisions save and the verdict stays PENDING |

The database file is `DATA_DIR/pitchgate.sqlite`. Startup creates the file and the `ideas`, `revisions`, and `verdicts` tables if they are missing. No login is required. Each idea stores a display name. Problem, audience, and approach are stored on revisions. Saving an edit inserts a new revision and scores that revision.

Jev returns market need, feasibility, and differentiation on a 0–3 scale, plus a safety-risk probability. The label is decided in `pitchgate/verdicts/logic.py`: safety above 0.5 forces KILL, any score under 2.0 is FIX, confidence under 0.6 blocks SHIP, and a clean result is SHIP. A finished label is not replaced.

## Tests

```bash
pytest --cov=pitchgate --cov-report=term-missing
```

The target is at least 70% on the core business logic. Idea checks are in `tests/test_ideas.py`. Verdict rules are in `tests/test_verdicts.py`.

## Layout

- `app.py` starts the process.
- `pitchgate/ideas/` owns idea text and revisions. `logic.py` checks the fields. `store.py` writes SQLite.
- `pitchgate/verdicts/` owns rubric scores and the KILL / FIX / SHIP rule. `logic.py` applies the cutoffs. `jev.py` calls the model. `store.py` writes SQLite.
- `pitchgate/pages.py` is the only place the two domains are called together.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.
