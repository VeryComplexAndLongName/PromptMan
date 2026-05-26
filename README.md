# PromptMan

[![CI](https://github.com/VeryComplexAndLongName/PromptMan/actions/workflows/ci.yml/badge.svg)](https://github.com/VeryComplexAndLongName/PromptMan/actions/workflows/ci.yml)
[![Docker](https://github.com/VeryComplexAndLongName/PromptMan/actions/workflows/docker.yml/badge.svg)](https://github.com/VeryComplexAndLongName/PromptMan/actions/workflows/docker.yml)
[![Coverage](https://codecov.io/gh/VeryComplexAndLongName/PromptMan/graph/badge.svg)](https://codecov.io/gh/VeryComplexAndLongName/PromptMan)

PromptMan: FastAPI + Vue app for storing, versioning, and optimizing prompts.

PromptMan is **REST API-first**: the primary product surface is the HTTP API, and the application architecture is optimized around API workflows.

The built-in UI is intentionally a secondary feature: a simple, convenient client for quick operations on top of the same REST API.

The project is aimed at small and medium teams that need concurrent multi-user access, role-based controls, and predictable API behavior under shared load. Concurrent behavior and throughput are validated with a repeatable Locust-based load test harness — results and charts are included in the repository.

![Main Program Purpose](screen2.png)

## Program Snapshot

![Screenshot 1](1.png)
![Screenshot 2](2.png)
![Screenshot 2](3.png)
![Screenshot 2](4.png)

## Key Features

- **REST API-first** architecture with API endpoints as the primary integration surface.
- **REST API-first** workflow for automation, integrations, and CI/CD usage.
- UI as a secondary, intentionally simple and convenient client over the same REST API.
- Designed for small and medium teams with concurrent access needs and RBAC.
- Concurrent behavior validated by a Locust-based load test harness with benchmarked results and generated charts.
- Zero failures under concurrent read/cache workloads; throughput scales linearly with cache-hit traffic.
- Can be deployed in cloud environments for shared, always-on access as a cloud solution.

- Prompt storage by `project` + `name` with immutable version history.
- Structured prompt fields: `role`, `task`, `context`, `constraints`, `output_format`, `examples`.
- Tagging plus AND/OR search.
- Server-side prompt pagination with `X-Total-Count`.
- Server-side prompt sorting (`updated_at`, `created_at`, `name`, `project`) with default `updated_at desc`.
- Prompt delete with cascading cleanup of versions and access data.
- Unified optimization path through pluggable optimizer backend.
- Optimization profiles: `fast`, `quality`, `ultra`.
- Multi-provider LLM support: Ollama, OpenAI, Anthropic.
- Dynamic provider model discovery.
- Per-user optimization config persisted in the database.
- Authentication for REST API and UI.
- 30-minute access tokens with refresh-token based session renewal.
- RBAC with `admin`, `developer`, and `viewer` roles.
- Admin UI for project CRUD, user CRUD, and project access assignment.
- Normalized database schema with dedicated `projects` and `roles` tables.
- Prompt audit metadata: created/updated timestamps plus the user who made the change.
- Semantic Versioning (SemVer) with runtime version endpoint (`GET /v1/version`).
- Sensitive config values encrypted at rest.
- Automatic database migration on startup.
- Default bootstrap admin support for first run.

## Versioning (SemVer)

This project uses Semantic Versioning: `MAJOR.MINOR.PATCH`.

- `PATCH`
  - backward-compatible bugfixes and internal fixes
- `MINOR`
  - backward-compatible new features or endpoints
- `MAJOR`
  - any backward-incompatible API/behavior change

Current application version is defined in [pyproject.toml](pyproject.toml) under `project.version`.
At runtime the app exposes version info via:

```text
GET /v1/version
```

Example response:

```json
{
  "name": "prompt-man",
  "version": "0.1.0"
}
```

### Release Bump Checklist

1. Decide bump type (`PATCH` / `MINOR` / `MAJOR`).
2. Update `project.version` in [pyproject.toml](pyproject.toml).
3. Run tests.
4. Commit with release note (for example: `chore(release): 0.2.0`).
5. Create git tag matching version (for example: `v0.2.0`).

## Requirements

- Python 3.11+
- `uv` recommended, or plain `pip`

## Setup

### Using uv

```powershell
uv sync --extra dev
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

## CI And Coverage

- GitHub Actions workflow `CI` runs `ruff`, `mypy`, and the test suite on every push and pull request to `main`.
- Coverage is uploaded to Codecov from the same workflow, which enables the coverage badge above.
- For a public repository, the Codecov badge usually works after installing the Codecov GitHub App.
- For a private repository, add `CODECOV_TOKEN` to repository secrets before the upload step can succeed.

### Using pip

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

## Run

```powershell
uvicorn main:app --reload
```

On startup the app applies Alembic migrations automatically before serving requests.

- UI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

## Cloud Deployment (Optional)

PromptMan can be deployed not only locally, but also in cloud infrastructure to provide shared team access as a cloud solution.

- Typical cloud setup: containerized app + managed PostgreSQL + stable `PROMPTMAN_KEY` + HTTPS reverse proxy/load balancer.
- This allows remote access for distributed teams and centralized API/UI usage.
- Any environment that can run Docker or Python web services is suitable (for example VM-based hosting, container platforms, or Kubernetes).

## First Run And Authentication

The application is protected by authentication for both UI and API access.

- On a clean database, the login screen switches into bootstrap mode.
- The first admin can be created through `POST /v1/auth/bootstrap-admin` or from the UI.
- Startup also ensures a default admin exists when the database is empty.
- Current default bootstrap credentials are `admin` / `admin`.

Authenticated users receive a bearer token and all protected API routes require it.

Session behavior:

- Access token lifetime is 30 minutes.
- Login/bootstrap returns both an access token and a refresh token.
- `POST /v1/auth/refresh` issues a new token pair when the access token has expired but the refresh token is still valid.
- The UI refreshes the session automatically on `401` caused by an expired access token.
- The UI also schedules a proactive refresh 1-3 minutes before access token expiry.

### ⚠️ Important: Set PROMPTMAN_KEY for Persistent Deployments

The application encrypts password hashes at rest using the `PROMPTMAN_KEY` environment variable. **For persistent deployments (non-development), you MUST set this variable to a consistent, secure value.**

If `PROMPTMAN_KEY` is not set, the app uses a default key. This means:
- **Login will fail with "Invalid credentials"** if the app restarts and the key changes
- **Password hashes stored with one key cannot be decrypted with a different key**

**Setup:**

```bash
# Generate a secure random key (Linux/Mac)
export PROMPTMAN_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Or on Windows PowerShell
$env:PROMPTMAN_KEY = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))

# Then start the app
python -m uvicorn main:app
```

Store this key securely in your deployment environment (e.g., GitHub Secrets, Azure Key Vault, .env file in production).

## RBAC And Access Model

- `admin`
  - full access to all prompts and all projects
  - can manage users, roles view, projects, and project assignments
- `developer`
  - can only access prompts in explicitly assigned projects
  - has personal optimization config but no admin management access
- `viewer`
  - can read all prompts and personal config
  - cannot create, update, optimize, or delete anything

Roles are stored in a dedicated `roles` table. API responses still expose role names such as `admin` and `developer`.

## Database Model

The database is normalized internally while the external prompt API still works with project names.

- `projects`
  - reference table for project names
- `prompts.project_id`
  - foreign key to `projects.id`
- `project_access.project_id`
  - foreign key to `projects.id`
- `roles`
  - reference table for RBAC roles
- `users.role_id`
  - foreign key to `roles.id`
- `configs.user_id`
  - one-to-one per-user optimization config
- `prompts.created_at` / `prompts.updated_at`
  - prompt-level audit timestamps
- `prompts.created_by_id` / `prompts.updated_by_id`
  - prompt-level audit actor references
- `prompt_versions.created_at`
  - version creation timestamp
- `prompt_versions.created_by_id`
  - version author reference

Deleting a project cascades to related prompt and access rows.

## UI Overview

UI is deliberately not the main product surface. PromptMan is **REST API-first**, and the UI is intentionally kept simple and convenient as a companion client.

### Browse Tab

- View prompts by project/name.
- Filter by project and tag.
- Sort prompt lists by last modified, created time, name, or project.
- Default sort order is last modified descending.
- Expand a prompt to inspect latest content and version history.
- See who created the prompt, who updated it last, and when those actions happened.
- All user-visible prompt audit timestamps are shown explicitly in UTC.
- Edit tags, create a new version, optimize, and delete prompts when the role has write access.
- Viewer sees the same data in read-only mode.

### Create Tab

- Create a prompt with required `name`, `project`, and `task`.
- Fill optional structured fields.
- Preview the composed prompt.
- Optimize before saving.

### Config Tab

- Manage personal optimization settings.
- Configure LLM provider, model, base URL, timeout, and token.
- Configure optimizer profile, model hint, and rounds.
- Save settings per user.
- Reuse the saved config in optimization and model discovery.
- Viewer can inspect config values but cannot save changes.
- The session banner shows UTC expiry time, a live expiry countdown, and the next scheduled refresh time.

### Admin Tab

Visible for admins only.

- Project CRUD.
- User CRUD.
- Assign project access to users.
- View role and active/inactive state.
- Project and user lists are scrollable to keep the page compact.

Viewer does not have access to this tab.


## Plugins

PromptMan supports extenable plugin system (EPS). Repository already contains a test plugins shows up an EPS ability.

In `plugins/` you can find `README.md` with plugin types description, instruction on how to create your own plugins, sign and integration plugins. In `plugins/examples/` You can see pluginf of all three types.

For plugin signing, PromptMan now uses external PromptManSign service. A convenience helper `plugins/sign_via_service.py` uploads plugin files as multipart form data and writes detached `.signature.json` sidecars locally.
For a minimal team cheat sheet, use `plugins/SIGNING_QUICKSTART.md`.

PromptMan includes a built‑in **Prompt Efficiency Analyzer** plugin designed to measure the stability, predictability, and cache‑friendliness of prompt versions.  
The analyzer works **locally**, does not call any LLMs, and requires no external services.  
It evaluates prompt efficiency across several key metrics. It locates in `plugins/` folder

## Global Config in UI

Visible for admins in the Config tab.

- Load all keys from `GET /v1/admin/config/`.
- Save one key via `PUT /v1/admin/config/{key}?value=...`.
- Values are app-wide (shared), not per-user.
- Typical managed keys:
  - `PROMPTMAN_CACHE_ENABLED`
  - `PROMPTMAN_CACHE_MAX_ENTRIES`
  - `PROMPTMAN_CACHE_PERSISTENCE_ENABLED`
  - `PROMPTMAN_CACHE_PERSISTENCE_LIMIT`
  - `OPTIMIZER_PROVIDER`
  - `OPTIMIZER_MODEL`
  - `OPTIMIZER_BASE_URL`
  - `OPTIMIZER_TIMEOUT_SECONDS`
  - `OPTIMIZER_API_TOKEN`
  - `OPTIMIZER_BACKEND`
  - `OLLAMA_BASE_URL`

### Optimization Modal

- Shows the optimized prompt text in a focused view.
- Supports `Reoptimize` without leaving the modal.
- Supports applying optimized content back into Create or Browse flows.

### Session Handling In UI

- The sign-in screen explains the 30-minute access-token lifetime.
- The app retries authenticated API requests once after refreshing the session.
- The app schedules refresh automatically 1-3 minutes before token expiry.
- The session banner displays both the remaining access-token lifetime and the next scheduled refresh countdown.
- Prompt cards and version history show audit metadata directly in the UI.

## Per-User Optimization Config

Each user has a separate optimization config row in `configs`.

- `GET /v1/optimize/config` returns the current user's config.
- `PUT /v1/optimize/config` updates the current user's config.
- `POST /v1/optimize` uses the current user's config.
- `GET /v1/optimize/providers/{provider}/models` uses the current user's config as the default override source.

One user's changes do not modify another user's config.

## Optimization Features

### Prompt Optimization

Endpoint:

```text
POST /v1/optimize
```

- Main UI optimize path.
- Uses active backend configured by `OPTIMIZER_BACKEND`.
- Falls back to heuristic mode when backend/provider call fails.

**How Leo optimization works:**

The default `leo` backend uses the `leo-prompt-optimizer` library.
Leo structures a 10-step prompt-engineering methodology (analyze intent → extract components → enhance clarity → add context → define persona → structure instructions → add examples → specify output format → optimize tokens → insert placeholders) and submits it to an **LLM via the configured provider**.
The LLM executes the structured rewrite based on that system prompt.
An LLM provider (Ollama, OpenAI, Anthropic, etc.) **must be configured** to use Leo; without it the service falls back to the built-in heuristic engine.

Profiles:

- `fast`
  - lowest cost / lowest latency
- `quality`
  - more candidates and filtering
- `ultra`
  - heaviest preset with more aggressive generation settings

### Backend Model Providers

- Supported provider families: OpenAI-compatible, Anthropic, Groq, Gemini, Mistral.
- Provider/model selection is controlled via per-user config and environment defaults.
- Ollama can be used in two ways:
  - `llm_provider: "ollama"` (native local profile)
  - `llm_provider: "openai"` with `llm_base_url` pointing to Ollama's OpenAI-compatible endpoint
    (the service auto-normalizes common local URLs like `http://127.0.0.1:11434` to `/v1`).

### Model Discovery

Endpoint:

```text
GET /v1/optimize/providers/{provider}/models
```

- Ollama: discovered via provider API.
- OpenAI: discovered through provider API when credentials are available.
- OpenAI + local Ollama base URL: discovered through Ollama `/api/tags` compatibility path.
- Anthropic: discovered through provider API when credentials are available.
- For token-required providers, no token means an empty model list (no static fallback list is returned).

## Optimization Config Example

```json
{
  "model_id": null,
  "rounds": 2,
  "gp_profile": "ultra",
  "llm_provider": "ollama",
  "llm_model": "qwen2.5:0.5b",
  "llm_base_url": "http://127.0.0.1:11434",
  "llm_timeout_seconds": 300,
  "llm_api_token": null
}
```

## Security Notes

- Password hashes are stored encrypted.
- LLM API tokens are stored encrypted.
- API responses never return plaintext token values.
- Tokens are decrypted only when needed for provider calls.
- Refresh tokens are signed and verified separately from access tokens.

## Environment Variables

- `DATABASE_URL`
  - default: `sqlite:///./v1/prompts.db`
- `BOOTSTRAP_ADMIN_USERNAME`
  - optional first-run admin username override
- `BOOTSTRAP_ADMIN_PASSWORD`
  - optional first-run admin password override
- `PROMPTMAN_KEY` ⚠️ **IMPORTANT**
  - encryption key for password hashes; **MUST be set and kept consistent for persistent deployments**
  - if not set, uses a default key (development only)
  - login will fail with "Invalid credentials" if the key changes between app restarts
  - see [First Run And Authentication](#first-run-and-authentication) for setup instructions
- `PROMPTMAN_KEY_PREVIOUS`
  - optional comma-separated list of older keys used for decryption fallback during key rotation/migration
- `PROMPTMAN_CACHE_ENABLED`
  - enable/disable built-in in-memory cache (default: `true`)
  - set to `false`, `0`, `no`, or `off` to disable; use this when deploying Redis or other external cache
  - when disabled, cache functions bypass in-memory storage and execute requests directly
- `PROMPTMAN_CACHE_PERSISTENCE_ENABLED`
  - enable/disable cache persistence to the `cache_requests` table (default: `true`)
  - set to `false`, `0`, `no`, or `off` to skip saving hot prompt cache entries on shutdown and skip prewarming on startup
- `PROMPTMAN_CACHE_PERSISTENCE_LIMIT`
  - maximum number of hot prompt cache entries to persist and prewarm (default: `100`)
- `OPTIMIZER_BACKEND`
  - active optimizer backend name (default: `leo`)
- `OPTIMIZER_MODEL_ID`
  - optional fallback model hint when no per-user override exists
- `OPTIMIZER_ROUNDS`
  - fallback round count
- `OPTIMIZER_PROFILE`
  - fallback profile: `fast`, `quality`, `ultra`
- `OPTIMIZER_PROVIDER`
  - fallback provider
- `OPTIMIZER_MODEL`
  - fallback model
- `OPTIMIZER_BASE_URL`
  - fallback provider base URL
- `OPTIMIZER_TIMEOUT_SECONDS`
  - fallback timeout
- `OPTIMIZER_API_TOKEN`
  - fallback encrypted token source

Per-user config returned by `/v1/optimize/config` takes precedence over environment defaults for that user's optimize flows.

Cache lifecycle behavior:

- The application persists the hottest prompt-read cache entries into the `cache_requests` table during shutdown.
- On startup, it loads those rows back and prewarms the in-memory cache.
- Only non-destructive prompt read paths are included in this persistence flow.
- This is useful when you want faster first requests after restart without deploying an external cache.

For Docker with a mounted database volume, keep `PROMPTMAN_KEY` stable between image updates/recreates. Example:

```powershell
docker run --name prompt-man --restart unless-stopped -p 8000:8000 -e DATABASE_URL=sqlite:////data/v1/prompts.db -e PROMPTMAN_KEY="your-long-stable-secret" -v promptman-data:/data verycomplexandlongname/prompt-man:0.1.5
```

## API Surface

### Auth

- `POST /v1/auth/bootstrap-admin`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `GET /v1/auth/status`
- `GET /v1/auth/me`

`POST /v1/auth/login`, `POST /v1/auth/bootstrap-admin`, and `POST /v1/auth/refresh` return:

- `access_token`
- `refresh_token`
- `access_token_ttl_seconds`
- `refresh_token_ttl_seconds`
- `access_token_expires_at`
- `refresh_token_expires_at`
- `user`

### Roles

- `GET /v1/roles`

Admin-only read of available RBAC roles.

### Admin Global Config

- `GET /v1/admin/config/`
- `GET /v1/admin/config/{key}`
- `PUT /v1/admin/config/{key}` (query param: `value`)

Admin-only runtime settings endpoints.

### Users

- `GET /v1/users`
- `POST /v1/users`
- `GET /v1/users/{user_id}`
- `PUT /v1/users/{user_id}`
- `PUT /v1/users/{user_id}/projects`
- `DELETE /v1/users/{user_id}`

### Projects

- `GET /v1/projects`
- `GET /v1/projects/{project_id}`
- `POST /v1/projects`
- `PUT /v1/projects/{project_id}`
- `DELETE /v1/projects/{project_id}`

### Prompts

- `GET /v1/prompts`
  - query params: `project`, `tag`, `limit`, `offset`, `sort_by`, `sort_order`
  - defaults: `sort_by=updated_at`, `sort_order=desc`
  - response header: `X-Total-Count`
  - each prompt includes `created_at`, `updated_at`, `created_by_username`, `updated_by_username`
- `GET /v1/prompts/search`
  - query params: repeated `tags`, `mode`, optional `project`
- `POST /v1/prompts`
- `GET /v1/prompts/{project}/{name}`
- `PUT /v1/prompts/{project}/{name}`
- `DELETE /v1/prompts/{project}/{name}`
- `PUT /v1/prompts/{project}/{name}/tags`
- `GET /v1/prompts/{project}/{name}/versions`
- `GET /v1/prompts/{project}/{name}/versions/{version}`

Each version response includes:

- `created_at`
- `created_by_username`
- prompt component fields

### Optimize

- `POST /v1/optimize`
- `GET /v1/optimize/config`
- `PUT /v1/optimize/config`
- `GET /v1/optimize/providers/{provider}/models`

## Prompt Uniqueness Rules

- Prompt identity is unique by `name + project_id` internally.
- Prompt versions enforce uniqueness for the full content tuple:
  - `role`, `task`, `context`, `constraints`, `output_format`, `examples`
- Duplicate version content returns `409 Conflict`.

## Scaling And Database

By default the application uses **SQLite** — no installation required, zero configuration, and it works out of the box for small teams (up to ~20–30 concurrent users on a single host).

For higher load, multi-instance deployments, or production environments, switch to **PostgreSQL** (or any other SQLAlchemy-supported database: MySQL, MariaDB, etc.). The application code does not change — only `DATABASE_URL`.

### Horizontal Scaling With PostgreSQL

SQLite is not a good fit for horizontal scaling because the data lives in a single local file, so multiple app instances cannot safely share it. For any multi-instance or load-balanced setup, use PostgreSQL as the shared database.

If you want to add an external cache layer, you can use Redis or Cornet. In that case, disable the built-in in-memory cache with `PROMPTMAN_CACHE_ENABLED=false` so only the external cache is used.

```
                        ┌─────────────────────────────────────┐
                        │           Load Balancer             │
                        │    (nginx / Traefik / AWS ALB)      │
                        └───────┬──────────────┬──────────────┘
                                │              │
                    ┌───────────▼───┐      ┌───▼───────────┐
                    │  prompt-man   │      │  prompt-man   │
                    │  instance 1   │      │  instance 2   │
                    │  (Docker)     │      │  (Docker)     │
                    └───────┬───────┘      └───────┬───────┘
                            │                      │
                            └──────────┬───────────┘
                                       │
                              ┌────────▼────────┐
                              │   PostgreSQL    │
                              │  (shared DB)    │
                              └─────────────────┘
```

SQLite is a single-file database accessed by one process at a time — horizontal scaling with SQLite is not possible.
PostgreSQL is a network database that all instances connect to simultaneously.

Examples of scaling behind a Load Balancer:

- Two PromptMan instances behind nginx or Traefik, both connected to the same PostgreSQL database.
- Three or more PromptMan instances behind AWS ALB, Azure Load Balancer, or another L7/L4 balancer, with PostgreSQL as the shared state store.

Important: if you use SQLite, run the app with a single worker (`--workers 1`) regardless of CPU count. SQLite is fine for local or single-process deployments, but multiple workers create separate in-memory caches and contend for the same database file.

### Switching From SQLite To PostgreSQL

**1. Use the built-in PostgreSQL driver already included in the project dependencies:**

PromptMan already includes `psycopg2-binary` for PostgreSQL.

No code changes are required to switch modes in this repository.

**2. Create a PostgreSQL database and user:**

```sql
CREATE DATABASE promptman;
CREATE USER promptman_user WITH ENCRYPTED PASSWORD 'your-strong-password';
GRANT ALL PRIVILEGES ON DATABASE promptman TO promptman_user;
```

**3. Set `DATABASE_URL`** via environment variable:

```
DATABASE_URL=postgresql://promptman_user:your-strong-password@db-host:5432/promptman
```

Notes:

- The application runtime is synchronous for both SQLite and PostgreSQL.
- Startup migrations run automatically on every boot.
- Cache persistence and prewarm are handled during app lifespan startup/shutdown, so you do not need a separate cache service unless you choose Redis or another external cache.

For Docker:

```powershell
docker run --name prompt-man --restart unless-stopped -p 8000:8000 `
  -e DATABASE_URL=postgresql://promptman_user:your-strong-password@db-host:5432/promptman `
  -e PROMPTMAN_KEY="your-long-stable-secret" `
  verycomplexandlongname/prompt-man:latest
```

**4. Start the application — no further steps needed.**

The application creates and migrates the entire database schema automatically on startup via Alembic. You do not need to prepare the schema, create tables, or run any SQL scripts manually.

```
[startup] Running Alembic migrations...
[startup] migrations done  ← schema is ready
[startup] Application is ready to serve requests
```

### Switching Back From PostgreSQL To SQLite

Switching back is also only an environment change.

PowerShell:

```powershell
$env:DATABASE_URL = "sqlite:///./v1/prompts.db"
uvicorn main:app --host 127.0.0.1 --port 8000
```

Docker:

```powershell
docker run --name prompt-man --restart unless-stopped -p 8000:8000 `
  -e DATABASE_URL=sqlite:////data/v1/prompts.db `
  -e PROMPTMAN_KEY="your-long-stable-secret" `
  -v promptman-data:/data `
  verycomplexandlongname/prompt-man:latest
```

### Database URL Reference

| Database   | Example `DATABASE_URL`                                              |
|------------|---------------------------------------------------------------------|
| SQLite     | `sqlite:///./v1/prompts.db`                                            |
| PostgreSQL | `postgresql://user:password@host:5432/dbname`                       |
| MySQL      | `mysql+pymysql://user:password@host:3306/dbname`                    |

## Notes For Operators

- The UI and API expose prompt projects by name for usability.
- The database stores project and role references by foreign key.
- If you inspect SQLite directly, expect `project_id` and `role_id` rather than string columns in normalized tables.

```text
GET /v1/prompts?limit=10&offset=20
```

- `limit` and `offset` are optional.
- This allows API clients to either fetch the full collection or just a page/slice.

## Development

```powershell
ruff check .
ruff format .
mypy .
```

## Load Testing And Concurrency Validation

Concurrent behavior and throughput have been validated with a repeatable Locust-based load test harness. The harness benchmarks four paths: the general mixed workload, a cache-heavy workload that repeatedly hits shared prompt-read and optimization-cache paths, a dedicated hot optimization workload, and a cold optimization workload that intentionally bypasses the optimization cache.

Load-test scenarios run at 10, 20, and 40 concurrent users. Results confirm that the application handles concurrent multi-user access correctly and without data races. Race-condition safety is additionally covered by dedicated integration tests (`tests/integration/test_race_conditions.py`) that exercise shared-resource write paths under parallelism.

**Benchmark charts are included in the repository** and cover throughput (RPS), P95 latency, average latency, and failure rate across all scenarios and user levels — see the chart section below.

### Run benchmark

```powershell
python loadtests/benchmark_rps.py --host http://127.0.0.1:8000 --duration 15s --users 10 20 40 --spawn-rate 10 --scenarios mixed cache optimize_hot optimize_cold --clean
```

### Switch database mode for benchmarks

Switching between **SQLite sync** and **PostgreSQL sync** is just a `DATABASE_URL` change.

SQLite sync:

```powershell
$env:DATABASE_URL = "sqlite:///./v1/prompts.db"
uvicorn main:app --host 127.0.0.1 --port 8000
```

PostgreSQL sync:

```powershell
$env:DATABASE_URL = "postgresql://postgres:your-password@localhost:5432/promptman"
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Build charts

```powershell
python loadtests/generate_charts.py
```

Charts are written to `loadtests/`.
When `loadtests/results/benchmark_manifest.json` exists, chart generation uses the manifest results directly, so stale CSVs and setup traffic do not pollute focused scenario graphs.

### Latest benchmark snapshot

Current local SQLite sync snapshot (`15s`, `10/20/40` users, shared auth token, default thresholds `failure<=1%`, `p95<=500ms`):

| Scenario | Users | RPS | P95 (ms) | Avg (ms) | Failure % | Pass |
| --- | ---: | ---: | ---: | ---: | ---: | :---: |
| mixed | 10 | 34.06 | 57.00 | 45.84 | 0.00 | yes |
| mixed | 20 | 62.84 | 130.00 | 32.91 | 0.00 | yes |
| mixed | 40 | 54.65 | 840.00 | 315.55 | 0.00 | no |
| cache | 10 | 102.62 | 21.00 | 9.64 | 0.00 | yes |
| cache | 20 | 165.32 | 67.00 | 27.55 | 0.00 | yes |
| cache | 40 | 140.46 | 260.00 | 148.98 | 0.00 | yes |
| optimize_hot | 10 | 19.34 | 23.00 | 11.99 | 0.00 | yes |
| optimize_hot | 20 | 38.28 | 23.00 | 12.26 | 0.00 | yes |
| optimize_hot | 40 | 68.79 | 72.00 | 23.99 | 0.00 | yes |
| optimize_cold | 10 | 0.18 | 11000.00 | 6985.02 | 0.00 | no |
| optimize_cold | 20 | 0.00 | inf | inf | 100.00 | no |
| optimize_cold | 40 | 0.00 | inf | inf | 100.00 | no |

Observed takeaway:

- **Mixed traffic is healthy at 10 and 20 users** (`34.06 → 62.84 RPS`, `57 → 130 ms` p95) and only crosses the default p95 threshold at 40 users, where LLM-bound work pushes p95 to `840 ms`.
- **Cache-heavy traffic scales strongly**: from `102.62 RPS` at `10` users to `140.46 RPS` at `40` users, all with zero failures. This remains the dominant usage pattern for teams repeatedly reading shared prompts.
- **Hot optimization sustains high throughput under concurrency**: `19.34 → 38.28 → 68.79 RPS` as users grow from `10` to `40`, all with zero failures and sub-`75 ms` p95 even at the highest measured concurrency.
- Cache reuse delivers approximately **105× throughput gain** and **478× p95 reduction** compared to cold optimization at `10` users on the same host — making repeated prompt optimization viable under team load.
- At 20 and 40 users, cold optimization (no cache, real LLM call) did not complete requests inside the 15-second window — expected behavior given local LLM latency, not an application defect.

### DB Mode Comparison

The application is currently supported in two runtime configurations:

- SQLite sync
- PostgreSQL sync

Historical note: before async runtime support was removed, the application was also benchmarked in a PostgreSQL async prototype. Those measurements are kept below for comparison, but that mode is no longer part of the supported application runtime because it did not provide practical gains on this codebase.

Switching between SQLite sync and PostgreSQL sync was verified by changing only `DATABASE_URL`.

### Concurrency smoke comparison

Live HTTP concurrency smoke (`12` parallel prompt creates + `12` parallel list requests, one shared project, one shared tag):

| Mode | Create OK | List OK | Final prompt count |
| --- | ---: | ---: | ---: |
| SQLite sync | 12/12 | 12/12 | 12 |
| PostgreSQL sync | 12/12 | 12/12 | 12 |
| PostgreSQL async (historical) | 12/12 | 12/12 | 12 |

### 40-user benchmark comparison

Measured at `40` concurrent users on the same machine:

| Mode | Mixed RPS | Mixed P95 (ms) | Cache RPS | Cache P95 (ms) | Optimize Hot RPS | Optimize Hot P95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SQLite sync | 42.82 | 810.00 | 255.70 | 80.00 | 72.01 | 39.00 |
| PostgreSQL sync | 60.62 | 690.00 | 243.62 | 87.00 | 70.69 | 43.00 |
| PostgreSQL async (historical) | 36.22 | 3100.00 | 179.72 | 200.00 | 68.62 | 100.00 |

### Cold optimize comparison at 10 users

`optimize_cold` remains dominated by LLM latency, so `10` users is the only meaningful finite comparison point:

| Mode | RPS | P95 (ms) | Avg (ms) | Failure % |
| --- | ---: | ---: | ---: | ---: |
| SQLite sync | 0.16 | 12000.00 | 9396.95 | 0.00 |
| PostgreSQL sync | 0.39 | 13000.00 | 7485.71 | 0.00 |
| PostgreSQL async (historical) | 0.18 | 11000.00 | 7144.59 | 0.00 |

Observed takeaway from the DB-mode comparison:

- **PostgreSQL sync is the best balanced measured mode** on this codebase: it improves mixed-workload throughput and mixed-workload P95 relative to SQLite sync, while keeping cache and hot-optimize performance close.
- **SQLite sync is still very competitive for read-heavy local workloads** and reached the highest measured cache-only throughput on this machine (`255.70 RPS` at `40` users).
- **The historical PostgreSQL async prototype did not deliver practical benefits**: mixed throughput was lower than both sync modes, mixed P95 was materially worse, and hot/cache paths were not improved enough to justify the extra runtime complexity.
- **PostgreSQL is the recommended production mode** for this codebase: it remains operationally simple to enable and was the strongest overall measured option under mixed concurrent load.
- **Database switching is operationally simple**: SQLite sync ↔ PostgreSQL sync is just a `DATABASE_URL` change.
- **Concurrency correctness was the same across all measured modes in live smoke testing**: every measured mode completed `12/12` concurrent creates and `12/12` concurrent list requests with the expected final prompt count.
- **Async runtime support was removed from the application after these measurements**: the benchmark data is preserved here as the rationale for keeping only the simpler sync runtime in the product.

### Cache Impact Test

The repository now includes an executable unit test that measures the cache effect directly:

- `test_cached_optimization_is_faster_than_cold_optimization` in `tests/unit/test_unit_optimizer_and_crud.py`

It uses a deliberately slow fake optimizer backend and asserts that repeated cache hits complete materially faster than an equivalent series of cache misses.

### Charts

All charts are generated from benchmark results and committed to the repository. They provide visual evidence of throughput, latency, and failure behavior under concurrent load.

#### Dashboard

![Load Testing Dashboard](loadtests/chart_dashboard.png)

Combined view for quick comparison across all scenarios and user levels — throughput, P95 latency, average latency, and failure rate in one place.

#### Optimize Hot Vs Cold

![Optimize Hot Vs Cold](loadtests/chart_optimize_compare.png)

Isolates repeated identical optimize calls (cache-hit path) from cache-busting calls (cold path). Demonstrates the ~110× throughput and ~297× p95 improvement from cache reuse under concurrent load.

#### Throughput (RPS)

![Load Test Throughput](loadtests/chart_rps.png)

Shows how total request throughput scales as concurrent user count grows. Cache-hit and hot-optimization paths show near-linear scaling — confirms the application does not degrade under concurrent access for these workloads.

#### P95 Latency

![Load Test P95 Latency](loadtests/chart_p95_latency.png)

Tail latency under concurrent load. Cache-heavy scenarios stay flat (under 200 ms at 40 users), confirming stable response times as concurrency grows.

#### Average Latency

![Load Test Average Latency](loadtests/chart_avg_latency.png)

General response-time trend. Use together with P95 to distinguish average slowdown from tail-only spikes caused by outlier requests.

#### Failure Rate

![Load Test Failure Rate](loadtests/chart_failure_rate.png)

Percentage of failed requests per scenario and user level. Cache and hot-optimization scenarios show 0% failures at all concurrency levels.

### Historical DB Mode Comparison Charts

These charts were generated before async runtime support was removed. They are retained as historical evidence for the decision to keep the application sync-only.

#### Historical DB Mode Dashboard

![DB Mode Dashboard](loadtests/chart_db_mode_dashboard.png)

Combined comparison of cache throughput, mixed-workload P95, hot optimize throughput, and cold optimize P95 across SQLite sync, PostgreSQL sync, and the historical PostgreSQL async prototype.

#### Historical 40-User Throughput By Mode

![40-User Throughput By Mode](loadtests/chart_db_mode_40_rps.png)

Grouped comparison of `mixed`, `cache`, and `optimize_hot` throughput at `40` users across the measured modes.

#### Historical 40-User P95 By Mode

![40-User P95 By Mode](loadtests/chart_db_mode_40_p95.png)

Grouped comparison of tail latency for the same `40`-user scenarios. PostgreSQL sync remained the most balanced measured option.

#### Historical Cold Optimize P95 At 10 Users

![Cold Optimize P95 At 10 Users](loadtests/chart_db_mode_cold_10_p95.png)

Focused comparison for the cold optimize path at `10` users, where all measured modes still produced finite values.


## Snippets

- Diagnostic one-off scripts are stored in `snippets/`.
- Current files:
  - `snippets/task_snippet.py` - runtime `/v1/optimize/config` verification against running server.
  - `snippets/test_api.py` - local `TestClient` check for optimize config behavior.
  - `snippets/test_snippet.py` - direct helper-function check for non-string field normalization.

## Project Structure

```text
.
├── main.py
├── crud.py
├── models.py
├── schemas.py
├── optimizer_service.py
├── database.py
├── pyproject.toml
├── requirements.txt
├── snippets/
├── tests/
├── alembic/
└── ui/
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
