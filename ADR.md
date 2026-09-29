# Architecture Decision Record

## 1. Backend language and framework
Date: 2026-09-28
Status: Decided
Context: The app is one process that serves pages, reads and writes SQLite, and calls external model APIs. It has to stay small enough to explain on paper, with no notes, at the comprehension check.
Decision: Python with Flask. Flask serves the HTML and the routes in the same process, and SQLite stays in the standard library. External APIs are called with the standard library's `urllib`, not vendor SDKs.
Alternatives considered: FastAPI. It is a strong fit for a JSON API, and it was rejected because this app is a small server-rendered site. The extra API machinery would be surface area to explain without buying a feature the club needs. Django was rejected because the app does not need its admin, auth, or ORM. For HTTP, `requests` and vendor SDKs were rejected because each API is one POST with a JSON body, and every extra package counts toward the dependency cap.
Consequences: Routing and templates stay thin. Domain rules live in `pitchkitchen/ideas/` and `pitchkitchen/review/`, which keeps the framework choice from spreading into the business logic. A later service split can keep those two packages and drop the Flask layer on one of them. Timeouts and error handling for each API are written by hand in one file per API.

## 2. Ideas and review meet only at a revision id
Date: 2026-09-29
Status: Decided
Context: The app needs two domains that can be split later. A verdict is about one exact version of what the founder wrote, and the ideas package should not own the cutoff rules or know which models are called.
Decision: `pitchkitchen/ideas/` stores everything the founder wrote. `pitchkitchen/review/` stores everything the app says back: Jev's scores, the label, and later Chef's questions. The only shared key is `revision_id`. Routes in `pitchkitchen/pages.py` save the revision first, then pass review the revision id and a snapshot of the founder's text.
Alternatives considered: Keep the label columns on `revisions`. That needs one less join, and it was rejected because a verdict change would sit in the idea table and the two domains could not be split without cutting that table apart. Putting Chef in its own third package was also rejected, because Chef's question depends directly on Jev's scores and the two would always be called together.
Consequences: An idea can be saved when Jev is down. The verdict row is still written, with label PENDING. A later service split can move `pitchkitchen/review/` out as one service that takes a revision id and text and returns a verdict.

## 3. The conversation is a tree of revisions
Date: 2026-09-29
Status: Decided
Context: The founder pitches once and then answers questions. Each answer is scored together with everything before it, and editing an earlier answer later must not erase text that was already scored.
Decision: `revisions` holds both kinds of founder text. A pitch row has the one-liner and story and no parent. An answer row has the answer and a `parent_id` pointing at the revision before it. A CHECK constraint enforces which columns each kind fills. The current conversation is the newest revision and its chain of parents.
Alternatives considered: A separate `answers` table with a position number under one pitch row. It is simpler to list, and it was rejected because editing answer 2 would either overwrite scored text or need a version column on every answer. With `parent_id`, an edit is a new sibling and old verdicts still point at the exact text they judged.
Consequences: Each `verdicts` row references one revision, which fixes the exact branch that was judged. Rebuilding a conversation walks parents in Python (`walk_branch`), which is fine at club scale but would need a recursive query for very large trees.
