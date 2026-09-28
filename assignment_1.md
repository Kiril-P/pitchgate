## Individual Assignment 1
**Topic:** Build a Simple Application to Serve as the Basis for DevOps Work

**Deadline:** 2026-10-04 23:59

**Written Comprehension Check:** in class, at/after the deadline session (date announced separately)

### Assignment Philosophy
AI use is allowed and expected. That changes what counts as evidence of effort: a working app no longer proves you made real design decisions, since AI makes "working" cheap. Grading weights the things AI can't do for you: the decisions you made along the way, and your ability to explain your own code cold, on paper, with no notes.

Keep it real, not academic. Build something you could plausibly ship to a real user. You can invent stakeholders, users, or scale requirements to justify design choices (e.g., "10,000 daily users, so..."). Stakeholders are people or organizations, not tools like Git, Azure, or Blackboard.

### Objective
Design and build a **minimal, monolithic application** that will later be split into services, Dockerized, and deployed to Azure in Assignment 2. It must run as a single process in a single container. A standard deployment script will be provided separately; your job is to satisfy the contract in §7 so that script works unmodified.

### 1. Scope & Architecture Constraints
This assignment caps *how many processes/containers it runs in*, not what technology you use. Some constraints below are hard requirements, needed so the shared deployment script works on everyone's app. Everything else is your choice, as long as you can justify it.

**1a. Hard requirements (deployment homogeneity, not a complexity judgment):**
- Single process, single container. No microservices, multiple repos, or separately deployed services.
- **Storage: SQLite**, at one documented path. Mandatory: every app needs the same storage shape for the deployment script and for Assignment 2.
- One dependency manifest at the repo root (`requirements.txt`, `package.json` + lockfile, etc). No per-folder manifests.
- No Dockerfile, `docker-compose.yml`, or CI workflow (`.github/workflows/`) that you write yourself. Deployment tooling is provided separately; Docker/CI come later in the course.
- No Terraform/Bicep/ARM or other IaC you author.
- No real public deployment (custom domain, Render/Heroku, etc). Run locally and satisfy §7; real deployment is Assignment 2.
- No external managed database or cache. Everything lives inside your one container.

**1b. Free choices, justify each in `ADR.md`:**
- **Backend language/framework**: explain why you chose it and what it buys you. Example: using Django when nothing needs it over Flask/FastAPI is graded down as poor judgment, not banned.
- Whether to add authentication/login.
- Any pattern beyond the basics (GraphQL, WebSockets, in-process background task, heavier ORM), as long as it fits the single-process constraint.
- Frontend approach: plain HTML/CSS/JS, templates, or heavier, served by the same process.
- Dependency count: soft cap ~12 third-party packages.
- File count: rough guidance ~15-50 files (excluding lockfiles/venvs/node_modules).

**1c. Out of scope, regardless of justification:** message brokers (Redis/RabbitMQ), background job runners (Celery, cron containers), or an actual multi-service split. These assume more than one deployed process, which §7's single-container contract doesn't support. If your use case wants them, treat that as a signal: design your two feature domains (§3) to be *logically* separable now (that's the second required `ADR.md` entry, §5), and leave physically separating them to a later assignment.

**1d. Use a stack you're already comfortable in.** For most students that's Python. Anything works if you can write and explain the code yourself, cold, at the comprehension check (§6). Picking an unfamiliar language because AI can generate it too is the fastest way to fail that check.

New ideas for the app can be proposed to the professor, but still need to comply with this section.

### 2. Application Scope
Propose your own use case and get it pre-approved before you start building. It needs enough substance for two genuinely distinct backend feature domains (§3) plus SQLite persistence; a single-entity CRUD toy ("add and remove a task, nothing else") is probably too thin. Most ideas need a second feature domain with real purpose: tasks + tags, posts + comments, links + click analytics, weather dashboard + saved locations/alerts. Bring your specific plan to the professor before writing code.

### 3. Required Features
- **SQLite persistence** (required): underlies both domains. Neither domain counts as "working" unless it reads/writes through SQLite.
- **At least 2 distinct backend feature domains** (required): each with its own responsibility and data, coupled as little as possible. Each should be something that could become its own microservice later (you're not building that split now, §1c), and you should be able to point to where the seam would go.
- A third domain, or extra polish on the two above, is optional and worth a small amount folded into Code Quality. Don't spend hours here instead of on §4/§5.

### 4. Testing
Automated unit tests (pytest/unittest, Jest/Mocha, or your language's equivalent) covering the **core business logic** of your two domains, not framework glue or routing, at **≥70% coverage**, measured with a standard tool (pytest-cov, coverage.py, nyc, jest --coverage). Report the coverage command and result in your README.

### 5. Process Deliverables
The core of the assignment: artifacts that make your design thinking visible over time, not just a snapshot at the deadline.

**`ADR.md`**, a lightweight Architecture Decision Record log at the repo root. Exactly 5 entries, this format:
```
## [N]. <Title>
Date: YYYY-MM-DD
Status: Decided
Context: 1-3 sentences, what forced this decision
Decision: 1-2 sentences, what you chose
Alternatives considered: at least one real alternative, and why you rejected it
Consequences: 1-2 sentences, what this costs or enables later
```
One entry required for each:
1. **Backend language/framework choice**: the justification from §1b (what it buys you, what you rejected).
2. **How you scoped your two feature domains to be independently modularizable**.
3. **A data-model/schema decision in SQLite**: e.g. how the two domains' data relates. Should visually match the database diagram in §8.
4. **Your testing approach**: what you prioritized toward the 70% bar, what you left thinner, and why.
5. **One thing you deliberately chose not to build**, and why.

Add entries as you make the decisions, not all at once. Your 5 entries must span at least **3 distinct commit dates**; landing them all in one commit defeats the point of the log.

**`AI_USAGE.md`**, a structured AI usage log. One row per meaningful interaction:

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|

The last column matters most: explain, using your own function/variable names, how the accepted code actually works. Vague explanations are exactly what §6 is designed to catch. Disclosure is grade-neutral: you're graded on accuracy and specificity, never on the fact that you used AI.

**Commit history**: at least **12 commits** across at least **6 distinct calendar days**, no single day over 40% of total commits. Push to a remote (GitHub); we check push timestamps, not local dates. "Initial commit", "WIP", "update", "fix" don't count as meaningful messages; describe what changed and why. Fabricated or backdated history is an academic integrity violation.

### 6. Written Comprehension Check (a multiplier, not a normal rubric line)
In class, at or after the deadline, you'll answer 6 short-answer questions about your own project: on paper, closed-book, no notes/device/AI. Answers are graded against your actual repo, report, ADR log, and AI usage log.

**How it affects your grade:** §3-§5 and §7-§9 are scored normally and summed to a subtotal out of 100. The check is scored separately, out of 100, and **multiplies** the subtotal (it isn't added). Example: subtotal 88/100, check 60% gives a final grade of 88 × 0.60 = **52.8/100**. A great subtotal can't buy out of a bad check, and a great check can't inflate a thin submission.

Easy to ace if you know your project. If your ADR log, AI usage log, and commits reflect real work and understanding, this should be straightforward. You're graded on accuracy and specificity, not handwriting or prose.

### 7. Azure Container Deployment Contract
Assignment 2 Dockerizes and deploys this app using a script provided unmodified to everyone. Your app must:
1. Run as a single process, started by one documented command (`python app.py`, `npm start`).
2. Bind to `0.0.0.0`, not `localhost`/`127.0.0.1`.
3. Read its port from one environment variable (e.g. `PORT`), with a sane default.
4. Need no interactive setup at startup (no `input()`, wizard, manual migration). Run cleanly after clone + install + start.
5. Write its SQLite file to one documented path, ideally under a configurable directory (e.g. `DATA_DIR`).
6. Have no required external runtime dependency beyond a public API your use case genuinely needs. No external managed DB/cache/queue.
7. Expose exactly one dependency manifest at the repo root.
8. Not depend on a Dockerfile, `docker-compose.yml`, or CI workflow to run. (You shouldn't have one anyway, per §1a; if you do, it's ignored, but your app must not need it.)
9. Be configurable entirely via environment variables. No editing source to reconfigure, no hard dependency on a `.env` file existing.
10. Start and be ready within a few seconds, no manual warm-up.

### 8. Documentation
A short report (4-5 pages):
- SDLC model chosen and justification (SMART goals; how you did or didn't follow it in practice)
- **Architecture overview diagram**, must match what you actually built
- **Database model/schema diagram** (tables, columns, relationships), must match ADR-3 and your actual schema
- README with setup instructions clear enough for someone else to run the project, including the coverage command from §4
- The AI-disclosure statement required by the course syllabus: "I acknowledge the use of [AI system] to [how you used it]. The prompts used include [...]. The output of these prompts was used to [...]." This is a report-level summary; the detailed log lives in `AI_USAGE.md`.

### 9. Version Control
- Individual Git repository.
- Commit requirements per §5 (12+ commits, 6+ distinct days, pushed to a remote).

### Deliverables
- Git repository with code, `ADR.md`, and `AI_USAGE.md` at the root
- Report (4-5 pages) per §8
- Attendance at the written comprehension check (§6)

### Grading Criteria
Each category below is scored normally and summed to a subtotal out of 100. The written comprehension check (§6) isn't one of these categories: it's scored separately, out of 100, and multiplies the subtotal (example in §6).

| Category | Weight | Breakdown |
|---|---|---|
| Working Features | 20% | Feature domain 1: 10% · Feature domain 2: 10% (both must use SQLite to count) |
| Testing | 15% | ≥70% coverage on core logic (§4); sliding scale below threshold, 0 if tests absent |
| Code Quality & Version Control | 20% | 10% code quality (justified tech choices per §1b, modularity between domains) · 10% commit cadence & hygiene (§5) |
| Documentation & Report | 15% | 5% SDLC explanation · 5% diagrams (must match repo) · 5% README/setup |
| Process Evidence | 30% | 15% `ADR.md` · 15% `AI_USAGE.md` |
| **Subtotal** | **100%** | |
| **× Written Comprehension Check (§6)** | **0-100%** | Multiplies the subtotal (worked example in §6) |

Process Evidence carries the largest share of the subtotal: it's the record of decisions made over time, not a snapshot at the deadline. Working features and code quality still matter (you need a genuinely working, well-built app), but AI makes "working" cheap and says little on its own about whether you understand what you shipped. None of this matters if you can't explain your project cold: the comprehension check sits outside the rubric, as a multiplier, because it's the one part that's closed-book, in person, and checked directly against your code.
