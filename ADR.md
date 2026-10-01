# Architecture Decision Record

## 1. Backend language and framework
Date: 2026-09-28
Status: Decided
Context: The app is one process that serves pages, reads and writes SQLite, and calls external model APIs. It has to stay small enough to explain on paper, with no notes, at the comprehension check.
Decision: Python with Flask. Flask serves the HTML and the routes in the same process, and SQLite stays in the standard library. External APIs are called with the standard library's `urllib`, not vendor SDKs.
Alternatives considered: FastAPI. It is a strong fit for a JSON API, and it was rejected because this app is a small server-rendered site. The extra API machinery would be surface area to explain without buying a feature the club needs. Django was rejected because the app does not need its admin, auth, or ORM. For HTTP, `requests` and vendor SDKs were rejected because each API is one POST with a JSON body, and every extra package counts toward the dependency cap.
Consequences: Routing and templates stay thin. Domain rules live in `pitchkitchen/ideas/` and `pitchkitchen/review/`, which keeps the framework choice from spreading into the business logic. A later service split can keep those two packages and drop the Flask layer on one of them. Timeouts and error handling for each API are written by hand in one file per API.
Update 2026-10-01: Chef was planned on OpenAI, but the account had no API credits. Because `review/coach.py` posts plain OpenAI-style chat JSON with `urllib`, moving Chef to Google Gemini's OpenAI-compatible endpoint only needed a configurable `COACH_URL`. No SDK had to be swapped. The free tier is often overloaded, so `COACH_MODEL` takes a comma-separated list and Chef tries the next model when one is busy.

## 2. Ideas and review meet only at a revision id
Date: 2026-09-29
Status: Decided
Context: The app needs two domains that can be split later. A verdict is about one exact version of what the founder wrote, and the ideas package should not own the cutoff rules or know which models are called.
Decision: `pitchkitchen/ideas/` stores everything the founder wrote. `pitchkitchen/review/` stores everything the app says back: Jev's scores, the label, and later Chef's questions. The only shared key is `revision_id`. Routes in `pitchkitchen/pages.py` save the revision first, then pass review the revision id and a snapshot of the founder's text.
Alternatives considered: Keep the label columns on `revisions`. That needs one less join, and it was rejected because a verdict change would sit in the idea table and the two domains could not be split without cutting that table apart. Putting Chef in its own third package was also rejected, because Chef's question depends directly on Jev's scores and the two would always be called together.
Consequences: An idea can be saved when Jev is down. The verdict row is still written, with label PENDING. A later service split can move `pitchkitchen/review/` out as one service that takes a revision id and text and returns a verdict.
Update 2026-10-01: Chef is built inside review. `review/service.py` runs one round (Jev, then the rules in `review/logic.py`, then Chef in `review/coach.py`) and stores Chef's reply in `chef_messages`, keyed by `revision_id` like `verdicts`. The idea's status (cooking, parked, served, binned) stays in ideas, and `pages.py` sets it from what review returns. Deleting an idea is also done in `pages.py`: review forgets its rows first, then ideas deletes the revisions, so neither package reaches into the other's tables.

## 3. The conversation is a tree of revisions
Date: 2026-09-29
Status: Decided
Context: The founder pitches once and then answers questions. Each answer is scored together with everything before it, and editing an earlier answer later must not erase text that was already scored.
Decision: `revisions` holds both kinds of founder text. A pitch row has the one-liner and story and no parent. An answer row has the answer and a `parent_id` pointing at the revision before it. A CHECK constraint enforces which columns each kind fills. The current conversation is the newest revision and its chain of parents.
Alternatives considered: A separate `answers` table with a position number under one pitch row. It is simpler to list, and it was rejected because editing answer 2 would either overwrite scored text or need a version column on every answer. With `parent_id`, an edit is a new sibling and old verdicts still point at the exact text they judged.
Consequences: Each `verdicts` row references one revision, which fixes the exact branch that was judged. Rebuilding a conversation walks parents in Python (`walk_branch`), which is fine at club scale but would need a recursive query for very large trees.

## 4. Tests use fake Jev and Chef, never the network
Date: 2026-10-01
Status: Decided
Context: Every round calls two external APIs. Jev costs credits per call. The free Gemini tier used for Chef returns "high demand" errors several times an hour. The brief needs at least 70% coverage, and the tests have to pass on a fresh clone with no keys.
Decision: `jev.judge` and the functions in `review/coach.py` take an optional `transport` argument: a function that receives the request body and key and returns the parsed JSON. Tests pass small fakes from `tests/fakes.py` (`FakeJev`, `FakeChef`) that return payloads shaped like the real replies, and `create_app` accepts `JEV_TRANSPORT` and `CHEF_TRANSPORT` so the page tests in `tests/test_loop.py` can drive a whole interview through the Flask test client. The database is an in-memory SQLite connection for store and service tests and a `tmp_path` file for page tests.
Alternatives considered: Patching `urllib.request.urlopen` with `unittest.mock`. It needs no change to the code, and it was rejected because each test would have to fake HTTP responses and byte bodies instead of the JSON the code actually reasons about, so tests would break whenever the request plumbing changes. Recording real responses with a library like `vcrpy` was rejected because it adds a dependency and stores API replies in the repo. Calling the real APIs in tests was rejected because it costs credits, needs keys, and fails whenever Gemini is overloaded.
Consequences: The suite runs in under a second with no keys and no network. Rules, branch walking, the round service, and every ending (cap, two KILLs, serve, park, delete, Chef failing and retrying) are covered. The two `_post` functions are the only untested code; they were checked by hand against the live APIs on 2026-10-01, and the fake Jev payload was updated then to include the `probabilities` field that `parse_answers` now reads.
