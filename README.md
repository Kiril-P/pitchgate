# Pitch Kitchen

A web app for a university venture lab. A student founder pitches an idea, or starts with none, Chef interviews them about what has already happened, and between sessions they find facts online and talk to real people. Jev scores every answer; the idea is served only when real conversations back it. Every idea can export a starter pack for Claude Code, and organizers see the whole cohort on one page.

**Live:** https://kpetrovskiieu2024ui.z28.web.core.windows.net (the first request after a quiet hour can take up to a minute while the services and their databases wake up; the page says so).

Assignment 2 split the Assignment 1 monolith along its ADR-2 seam into two services, each with its own container and its own SQL Server database, deployed to Azure by GitHub Actions:

```text
browser ── static UI (ui/, Azure Storage static website)
   │  HTTPS + CORS
   ├──► ideas   (services/ideas)   what the founder writes   ──► ideas database
   │       │ HTTP, 5 s / 30 s timeouts
   │       ▼
   └──► review  (services/review)  what the app says back    ──► review database
                      └──► Jev (Typesafe) and Chef (Gemini)
```

- **ideas** owns ideas, the revision tree of pitch and answers, logged conversations and facts, the starter pack Markdown, and the organizer view. The UI calls it for everything about an idea, and it calls review for every judgement (`ideas/flows.py`).
- **review** owns Jev's verdicts and tasting gates, Chef's messages, the Jev call budget and Chef's prep suggestions. It stores the idea and revision ids ideas sends; no foreign key crosses the seam (ADR 7).
- When review is down, ideas still saves a pitch and serves every idea page with the founder's own text and a notice; answers, logs and deletes are refused with a 503 and save nothing.

The system is described for machines in `system.yaml` (schema: `system.schema.json`) and `services/*/openapi.yaml`. Decisions are in `ADR.md`; AI help is in `AI_USAGE.md`.

## Run the whole system locally

Needs Docker Desktop (on Apple Silicon, turn on "Use Rosetta for x86_64/amd64 emulation" for the SQL Server image).

```bash
cp .env.example .env        # fill in the three passwords; the API keys are optional
docker compose up --build
```

- UI: http://localhost:8080 · ideas: http://localhost:8001 · review: http://localhost:8002 (`/health` on both)
- `sql` runs SQL Server 2022; the one-off `db-init` runs `db/init.sql`, which creates the `ideas` and `review` databases and one login per service that can open only its own database. It is idempotent and runs on every `up`.
- Without `TYPESAFE_API_KEY` verdicts stay PENDING; without `COACH_API_KEY` Chef pauses. Everything else works.
- See partial failure: `docker compose stop review`, reload an idea page (founder's text plus "can't be loaded right now"), try to answer (503, nothing saved), then `docker compose start review`.

## Run one service on its own

Each service is a plain Flask app with its own `requirements.txt`. It needs a SQL Server database it may create tables in; `docker compose up -d sql db-init` gives you one.

```bash
cd services/review
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL="mssql://review_app:<REVIEW_DB_PASSWORD>@localhost:1433/review"
flask --app wsgi run --port 8002
```

For ideas, use `services/ideas`, its own login and database, and `REVIEW_URL=http://localhost:8002`. The compose file does not publish SQL Server's port; add `ports: ["1433:1433"]` to `sql` while you need it. Migrations run at startup either way.

## Configuration

Every variable each service reads, as in `system.yaml`. Secrets have no default; on Azure they come from GitHub Actions secrets and are stored as Container Apps secrets.

**ideas**

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port the service listens on |
| `DATABASE_URL` | secret | `mssql://user:password@host:1433/database`, plus `?encrypt=require` on Azure |
| `VERSION` | `dev` | Commit SHA reported by `/health`; set at image build time |
| `DB_CONNECT_ATTEMPTS` | `8` | Connection attempts at startup while a paused database resumes (backoff 2 to 20 s) |
| `REVIEW_URL` | `http://review:8000` | Base URL of the review service |
| `REVIEW_TIMEOUT_S` | `5` | Timeout for calls to review that do not wait on Jev or Chef |
| `REVIEW_SLOW_TIMEOUT_S` | `30` | Timeout for calls that wait on Jev or Chef (the schema's limit) |
| `ORGANIZER_KEY` | secret | Key for the organizer view; unset turns it off |
| `UI_ORIGIN` | empty | The only browser origin allowed by CORS |

**review**

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port the service listens on |
| `DATABASE_URL` | secret | Connection string of the review database |
| `VERSION` | `dev` | Commit SHA reported by `/health` |
| `DB_CONNECT_ATTEMPTS` | `8` | Connection attempts at startup |
| `TYPESAFE_API_KEY` | secret | Jev; without it verdicts and gates stay PENDING |
| `JEV_BUDGET_PER_IDEA` | `15` | Most successful Jev calls one idea may make |
| `COACH_API_KEY` | secret | Chef's model (Gemini); without it Chef pauses |
| `COACH_URL` | Gemini's OpenAI-compatible endpoint | Any OpenAI-compatible chat completions URL |
| `COACH_MODEL` | `gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite` | Tried in order while the step's 16 s budget allows |
| `UI_ORIGIN` | empty | The only browser origin allowed by CORS |

## Tests and coverage

Tests run against a real SQL Server, never the network: Jev, Chef and web search are fakes. Point `TEST_SQL_URL` at a login that may create databases; the tests create and drop their own.

```bash
docker run -d --name pk-sql --platform linux/amd64 -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=<password>" -p 1433:1433 mcr.microsoft.com/mssql/server:2022-latest
export TEST_SQL_URL="mssql://sa:<password>@localhost:1433/master"

cd services/ideas  && pytest --cov=ideas  --cov-fail-under=70     # 71 tests, 98%
cd services/review && pytest --cov=review --cov-fail-under=70     # 87 tests, 96%
pytest                                                            # from the root: cross-seam journeys and system description checks
ruff check services tests
```

- `services/*/tests/`: each service's rules, store, migrations, API, health and request logs, and a check that every Flask route is in its OpenAPI document. Ideas' API tests replace review with `StubReview`, which can also time out, refuse or be down.
- `tests/integration/test_journeys.py`: the Assignment 1 founder journeys with the real review app served on a local port and the real ideas app calling it over HTTP, each with its own database, plus one with review stopped.
- `tests/integration/test_system_description.py` and `test_readme.py`: `system.yaml` lists exactly what the code reads, with the same defaults and timeouts; every call ideas makes is in review's OpenAPI document; this README keeps up with both.

## Migrations

Each service's schema is the numbered SQL files in `services/<name>/migrations/`, applied in name order at startup and recorded in `schema_migrations`; a second start applies nothing. Each file runs in one transaction with its record, so a failing file changes nothing. To change the schema, add the next file (`003_…sql`); never edit one that has been applied. A line holding only `GO` splits a file into batches. `002_add_updated_at.sql` is the example of changing a table that already holds data: it adds `ideas.updated_at` and backfills it for every existing idea.

## How deployment works

Every change reaches `main` through a pull request; `main` requires the seven CI checks. On every push and pull request, `.github/workflows/ci.yml` runs ruff, each service's tests against a throwaway SQL Server (failing under 70% coverage), the cross-seam suite, `system.yaml` and OpenAPI validation, and both image builds. On a push to `main`, `.github/workflows/deploy.yml`:

1. calls `ci.yml`, so nothing deploys unless CI passed on that commit;
2. pushes `ghcr.io/kiril-p/pitchgate-ideas:<sha>` and `pitchgate-review:<sha>` (public packages, `provenance: false`);
3. signs in to Azure as the managed identity `kpetrovski-ieu2024-github` over OpenID Connect (no password exists);
4. sets each Container App's secrets from GitHub secrets and points it at the new image (`az containerapp secret set`, `az containerapp update`);
5. waits until both `/health` endpoints report the new commit, then prints each new revision's startup log (migration lines) into the run;
6. writes `ui/config.js` with both service URLs and uploads `ui/` to the storage account's `$web` container.

GitHub secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `IDEAS_DB_PASSWORD`, `REVIEW_DB_PASSWORD`, `ORGANIZER_KEY`, `TYPESAFE_API_KEY`, `COACH_API_KEY`. Variables: `PREFIX`, `RESOURCE_GROUP`, `UI_STORAGE`.

## Azure initial setup (done once; reproduce in bash)

Everything is in `rg-kpetrovski-ieu2024` in `francecentral`; after this, only the pipeline changes anything. Passwords are generated locally and never written in the repository.

```bash
PREFIX=kpetrovski-ieu2024; RG=rg-$PREFIX; LOCATION=francecentral
STORAGE=kpetrovskiieu2024ui; SQL_SERVER=$PREFIX-sql; ENVIRONMENT=$PREFIX-env; GH_REPO=Kiril-P/pitchgate

# 1. Region (from the "Allowed resource deployment regions" policy) and providers
az policy assignment list --query "[?displayName=='Allowed resource deployment regions'].parameters.listOfAllowedLocations.value"
for p in Microsoft.App Microsoft.OperationalInsights Microsoft.Sql Microsoft.Storage Microsoft.ManagedIdentity; do az provider register -n $p; done
az group create -n $RG -l $LOCATION

# 2. The UI: a storage static website
az storage account create -n $STORAGE -g $RG -l $LOCATION --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 --allow-blob-public-access false
az storage blob service-properties update --account-name $STORAGE --static-website --index-document index.html --auth-mode key

# 3. SQL server and one free serverless database per service
az sql server create -n $SQL_SERVER -g $RG -l $LOCATION --admin-user pkadmin --admin-password "$SQL_ADMIN_PASSWORD" --minimal-tls-version 1.2
az sql server firewall-rule create -g $RG -s $SQL_SERVER -n AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
for svc in ideas review; do
  az sql db create -g $RG -s $SQL_SERVER -n $PREFIX-$svc-db --edition GeneralPurpose --family Gen5 --capacity 1 --min-capacity 0.5 \
    --compute-model Serverless --backup-storage-redundancy Local --use-free-limit true --free-limit-exhaustion-behavior AutoPause
done
# One contained user per database, with the firewall open to my IP only while doing it. As pkadmin, in <svc>-db:
#   CREATE USER [<svc>_app] WITH PASSWORD = '<password>';
#   ALTER ROLE db_ddladmin ADD MEMBER [<svc>_app]; ALTER ROLE db_datareader ADD MEMBER [<svc>_app]; ALTER ROLE db_datawriter ADD MEMBER [<svc>_app];
az sql server firewall-rule create -g $RG -s $SQL_SERVER -n Setup --start-ip-address "$MYIP" --end-ip-address "$MYIP"
az sql server firewall-rule delete -g $RG -s $SQL_SERVER -n Setup

# 4. Container Apps (Consumption, 0 to 1 replicas, no Log Analytics workspace; CORS is in the code, not the ingress)
az containerapp env create -n $ENVIRONMENT -g $RG -l $LOCATION --logs-destination none
for svc in review ideas; do
  az containerapp create -n $PREFIX-$svc -g $RG --environment $ENVIRONMENT --image mcr.microsoft.com/k8se/quickstart:latest \
    --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.25 --memory 0.5Gi \
    --env-vars UI_ORIGIN=https://kpetrovskiieu2024ui.z28.web.core.windows.net
done

# 5. The pipeline's identity: Contributor on this resource group only, trusted for main of this repository
az identity create -n $PREFIX-github -g $RG
az role assignment create --assignee-object-id "$(az identity show -n $PREFIX-github -g $RG --query principalId -o tsv)" \
  --assignee-principal-type ServicePrincipal --role Contributor --scope "$(az group show -n $RG --query id -o tsv)"
az identity federated-credential create --identity-name $PREFIX-github -g $RG -n github-main \
  --issuer https://token.actions.githubusercontent.com --subject "repo:${GH_REPO}:ref:refs/heads/main" --audiences api://AzureADTokenExchange
az identity federated-credential create --identity-name $PREFIX-github -g $RG -n github-main-ids \
  --issuer https://token.actions.githubusercontent.com --subject "repo:Kiril-P@194789402/pitchgate@1392491780:ref:refs/heads/main" --audiences api://AzureADTokenExchange

# 6. GitHub secrets and variables (values from the steps above; never committed)
for s in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID IDEAS_DB_PASSWORD REVIEW_DB_PASSWORD ORGANIZER_KEY TYPESAFE_API_KEY COACH_API_KEY; do gh secret set $s; done
gh variable set PREFIX --body $PREFIX; gh variable set RESOURCE_GROUP --body $RG; gh variable set UI_STORAGE --body $STORAGE

# 7. Read access for grading
for p in amartini@faculty.ie.edu bserra@faculty.ie.edu; do az role assignment create --assignee $p --role Reader --scope "$(az group show -n $RG --query id -o tsv)"; done
```

Logs: `az containerapp logs show -n kpetrovski-ieu2024-ideas -g rg-kpetrovski-ieu2024 --type console --follow`.

## How the product works

1. **Prep.** The founder picks where they start: no idea yet, an idea, or already talked to customers. With no idea, Chef sparks three small problems from their week. They write a story and a one-liner ("We help [who] [do what] by [how]"), pick Chef's tone (supportive, tough, or full Ramsay), and consent to the text going to Gemini and Typesafe and to organizers.
2. **Grill.** Each answer is a new revision. Jev scores it, review's `logic.py` decides the label, and Chef asks the next Mom Test question. A session is 5 answers. Any answer can be edited; the edit is a sibling revision and is re-scored.
3. **Tasting.** After a session Chef writes homework. The founder logs conversations and facts (web search through Gemini, only sentences Google ties to a source). With 3 or more logs this session, one Jev call scores them at the gate; passing opens the next session. A beginner's first gate passes on any three facts or conversations unless they look unsafe.
4. **Served.** A PROVEN verdict plus at least 3 logged conversations (facts don't count) can be served; Chef writes a pitch from the founder's facts and three next steps.
5. **Starter pack.** Chef plans the build; ideas copies the evidence section straight from the logs, so a pack never cites something that was not logged. It is a Draft until the idea is served.

Labels, in order: safety risk above 0.5 is UNPROVEN; a dodged question is PARTIAL and asked again; the three scores averaging under 1.2 is UNPROVEN; any score under 2.0, evidence under 2.0, or Jev less than 60% sure is PARTIAL; anything else is PROVEN. Two UNPROVEN answers in a row inside a session bin the idea, but only after a passed gate; a binned idea can be pivoted. Every idea lives at a private token; the home page lists only tokens this browser keeps plus ideas shared on the cohort board. There is no login (ADR 5).

## Layout

- `services/ideas/ideas/`: `api.py` (routes), `flows.py` (everything done together with review), `review_client.py` (HTTP with timeouts), `logic.py` and `store.py` (the domain), `view.py` (the page JSON), `pack.py` and `cohort.py` (pure), `db.py`, `migrations.py`, `observe.py` (health, logs), `cors.py`.
- `services/review/review/`: `api.py`, `service.py` (rounds, gates, serving), `logic.py` (label, gate and session rules), `jev.py`, `coach.py` (Chef, with time budgets), `store.py`, `db.py`, `migrations.py`, `observe.py`, `cors.py`.
- `services/*/Dockerfile`, `requirements.in` (direct dependencies) and `requirements.txt` (locked), `openapi.yaml`, `migrations/`, `tests/`.
- `ui/`: static HTML, CSS and JavaScript; `ui/config.js` holds the service URLs (overwritten at deploy).
- `db/init.sql`, `docker-compose.yml`, `.github/workflows/`, `system.yaml`, `system.schema.json`, `ADR.md`, `AI_USAGE.md`.

### Tables

| Service | Table | Columns |
|---|---|---|
| ideas | `ideas` | id, display_name, status, station, token, tone, level, pivot_of, shared, consent_at, created_at, updated_at |
| ideas | `revisions` | id, idea_id, parent_id, kind, one_liner, story, answer, created_at |
| ideas | `evidence` | id, idea_id, session, kind (conversation, fact), who, role, spoken_on, today_they, paid, quote, source, created_at |
| review | `verdicts` | id, revision_id, market_need, feasibility, differentiation, safety_risk, confidence, evidence, answered, label, rule, created_at |
| review | `gates` | id, idea_id, session, last_evidence_id, evidence_strength, pain_frequency, willingness_to_pay, safety_risk, label, rule, created_at |
| review | `chef_messages` | id, revision_id, kind, body, question, created_at |
| review | `jev_calls` | id, idea_id, revision_id, purpose (verdict, gate), ok, created_at |

Both databases also have `schema_migrations` (version, applied_at). `idea_id` and `revision_id` in review are plain integers that ideas hands over.

## Secret incidents

None. No credential has been committed to this repository or its history. If one ever is, it is revoked or rotated within 24 hours, the GitHub secret is updated, and the incident is recorded here (what leaked, when, what was done).
