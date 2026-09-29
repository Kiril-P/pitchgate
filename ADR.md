# Architecture Decision Record

## 1. Backend language and framework
Date: 2026-09-28
Status: Decided
Context: The app is one process that serves pages and will later read and write SQLite. It has to stay small enough to explain on paper, with no notes, at the comprehension check.
Decision: Python with Flask. Flask serves the HTML and the routes in the same process, and SQLite stays in the standard library.
Alternatives considered: FastAPI. It is a strong fit for a JSON API, and it was rejected because this app is a small server-rendered site. The extra API machinery would be surface area to explain without buying a feature the club needs. Django was rejected because the app does not need its admin, auth, or ORM.
Consequences: Routing and templates stay thin. Domain rules will live in `pitchgate/ideas/` and `pitchgate/verdicts/`, which keeps the framework choice from spreading into the business logic. A later service split can keep those two packages and drop the Flask layer on one of them.

## 2. Ideas and verdicts meet only at a revision id
Date: 2026-09-28
Status: Decided
Context: The app needs two domains that can be split later. A verdict is about one wording of an idea, and the idea package should not own the cutoff rules.
Decision: `pitchgate/ideas/` stores display name and revision text. `pitchgate/verdicts/` stores scores and the label. The only shared key is `revision_id`. Flask routes in `pitchgate/pages.py` save the revision first, then ask the verdict domain to score it.
Alternatives considered: Keep the label columns on `revisions`. That needs one less join, and it was rejected because a verdict change would sit in the idea table and the two domains could not be split without cutting that table apart.
Consequences: An idea can be saved when Jev is down. The verdict row is still written, with label PENDING. A later service split can move `pitchgate/verdicts/` out and leave the routes calling it with a revision id and the text snapshot.

## 3. Idea text lives on revisions
Date: 2026-09-28
Status: Decided
Context: A member can edit an idea, and the earlier wording has to remain. A later verdict must be attachable to the exact text that was judged, not to whatever the idea says after the next edit.
Decision: `ideas` stores the id, display name, and created time. `revisions` stores problem, audience, approach, and `idea_id`. An edit inserts a row. It does not update the previous one.
Alternatives considered: One table, with the text columns overwritten on edit. That is fewer rows, and it was rejected because the old wording would be gone before a verdict could point at it.
Consequences: The current text is the revision with the highest id. The `verdicts` table references `revision_id`. Listing ideas joins each idea to that latest revision.
