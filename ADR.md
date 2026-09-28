# Architecture Decision Record

## 1. Backend language and framework
Date: 2026-09-28
Status: Decided
Context: The app is one process that serves pages and will later read and write SQLite. It has to stay small enough to explain on paper, with no notes, at the comprehension check.
Decision: Python with Flask. Flask serves the HTML and the routes in the same process, and SQLite stays in the standard library.
Alternatives considered: FastAPI. It is a strong fit for a JSON API, and it was rejected because this app is a small server-rendered site. The extra API machinery would be surface area to explain without buying a feature the club needs. Django was rejected because the app does not need its admin, auth, or ORM.
Consequences: Routing and templates stay thin. Domain rules will live in `pitchgate/ideas/` and `pitchgate/verdicts/`, which keeps the framework choice from spreading into the business logic. A later service split can keep those two packages and drop the Flask layer on one of them.
