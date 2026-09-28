# AI usage log

One row per meaningful interaction. The last column has to be filled in your own words, using the real function and variable names, before this is submitted.

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-09-28 / initial scaffold | Cursor Grok | Organize the Assignment 1 repo for Pitchgate: Flask, no login, SQLite path, ideas and verdicts packages, ADR entry for the framework, and push a public GitHub repo. | Accepted | The scaffold matches the single-process contract. Domain behavior was left unimplemented on purpose. | FILL IN before submission. Explain `load_config`, `create_app`, and `ensure_database` in your own words. |
| 2026-09-28 / ideas domain | Cursor Grok | Build the ideas domain only: display name, problem, audience, and approach. Editing creates a new revision. Older revisions stay stored. SQLite tables and tests on that logic, then push. | Accepted | Validation lives in `clean_field`. Writes live in `create_idea` and `revise_idea`. Routes only call those functions. | FILL IN before submission. Explain `clean_field`, `create_idea`, and `revise_idea` in your own words. |
