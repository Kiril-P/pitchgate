# Pitchgate

A single-process web app for a student founder club. A member writes a short startup idea, submits it, and gets a verdict: KILL, FIX, or SHIP. Editing the idea creates a new revision with its own verdict.

This repository is the Assignment 1 app. It runs as one process and stores data in SQLite. Ideas and verdicts are separate packages so they can be split later. Neither domain is implemented yet.

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

The database file is `DATA_DIR/pitchgate.sqlite`. Startup creates the file if it is missing. No login is required. Each idea will carry a display name.

## Tests

```bash
pytest --cov=pitchgate --cov-report=term-missing
```

Coverage of the two domains is still ahead. The target is at least 70% on the core business logic once those domains exist.

## Layout

- `app.py` starts the process.
- `pitchgate/ideas/` will own idea text and revisions.
- `pitchgate/verdicts/` will own rubric scores and the KILL / FIX / SHIP rule.
- `ADR.md` records design decisions.
- `AI_USAGE.md` records meaningful AI help.
