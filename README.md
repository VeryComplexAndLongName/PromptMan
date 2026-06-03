# PromptMan

PromptMan is a FastAPI application with a conversation-first API, RBAC, plugin support, and pluggable runtime caching.

The current product surface is focused on conversation threads and messages.
Legacy prompt/optimize endpoints are removed.

## Key Capabilities

- Conversation thread CRUD with project-scoped access control.
- Message append and message history listing.
- Conversation import from JSON and plain text chain formats.
- Thread-level lightweight analysis (message counts and content stats).
- RBAC (`admin`, `developer`, `viewer`) with project-level access assignment.
- Runtime config management through admin endpoints.
- Pluggable runtime cache backends: `memory`, `redis`, `garnet`, `none`.
- Recursive plugin discovery and plugin modal sessions.
- JWT auth with refresh flow.

## Quick Start

### Requirements

- Python 3.11+
- `uv` (recommended) or `pip`

### Setup (uv)

```powershell
uv sync --extra dev
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

### Setup (pip)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

### Run

```powershell
uvicorn main:app --reload
```

- UI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

## Authentication

On an empty database, bootstrap the first admin:

- `POST /v1/auth/bootstrap-admin`

Then sign in:

- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `GET /v1/auth/status`
- `GET /v1/auth/me`
- `POST /v1/auth/me/password`

## API Surface

### Version

- `GET /v1/version`

### Roles (admin)

- `GET /v1/roles`

### Users (admin)

- `GET /v1/users`
- `POST /v1/users`
- `GET /v1/users/{user_id}`
- `PUT /v1/users/{user_id}`
- `PUT /v1/users/{user_id}/projects`
- `DELETE /v1/users/{user_id}`

### Projects (admin)

- `GET /v1/projects`
- `GET /v1/projects/{project_id}`
- `POST /v1/projects`
- `PUT /v1/projects/{project_id}`
- `DELETE /v1/projects/{project_id}`

### Admin Global Config (admin)

- `GET /v1/admin/config/`
- `GET /v1/admin/config/{key}`
- `PUT /v1/admin/config/{key}` with query param `value`
- `GET /v1/admin/config/meta/providers`
- `GET /v1/admin/config/meta/providers/{provider}/models`
- `POST /v1/admin/config/llm/autoconfigure/preview`
- `POST /v1/admin/config/llm/autoconfigure/apply`

### Conversations

- `POST /v1/conversations/threads`
- `GET /v1/conversations/threads`
- `GET /v1/conversations/threads/{thread_id}`
- `DELETE /v1/conversations/threads/{thread_id}`
- `POST /v1/conversations/threads/{thread_id}/messages`
- `GET /v1/conversations/threads/{thread_id}/messages`
- `POST /v1/conversations/import/json`
- `POST /v1/conversations/import/text`
- `GET /v1/conversations/import/{import_id}`
- `POST /v1/conversations/analyze/{thread_id}`

### Prompt Versions

- `POST /v1/prompt-versions/chains`
- `GET /v1/prompt-versions/chains`
- `GET /v1/prompt-versions/chains/{chain_id}`
- `GET /v1/prompt-versions/chains/{chain_id}/versions`
- `GET /v1/prompt-versions/chains/{chain_id}/versions/{version_no}`
- `POST /v1/prompt-versions/chains/{chain_id}/versions`
- `POST /v1/prompt-versions/chains/{chain_id}/analyze`
- `POST /v1/prompt-versions/chains/{chain_id}/versions/{version_no}/analyze`
- `POST /v1/prompt-versions/chains/{chain_id}/versions/{version_no}/test-runs`
- `GET /v1/prompt-versions/chains/{chain_id}/versions/{version_no}/test-runs`
- `GET /v1/prompt-versions/test-runs`

### Plugins

- `GET /v1/plugins`
- `POST /v1/plugins/_rescan`
- `POST /v1/plugins/{plugin_name}/_load`
- `POST /v1/plugins/{plugin_name}/_reload`
- `DELETE /v1/plugins/{plugin_name}`
- `POST /v1/plugins/{plugin_name}/health`

Modal session endpoints:

- `GET /v1/plugins/{plugin_name}/modals`
- `POST /v1/plugins/{plugin_name}/modals`
- `GET /v1/plugins/{plugin_name}/modals/{session_id}`
- `PATCH /v1/plugins/{plugin_name}/modals/{session_id}/controls/{control_name}`
- `POST /v1/plugins/{plugin_name}/modals/{session_id}/stop`
- `DELETE /v1/plugins/{plugin_name}/modals/{session_id}`

## Environment Variables

### Core

- `DATABASE_URL` (default local SQLite)
- `PROMPTMAN_KEY` (required stable key for persistent deployments)
- `PROMPTMAN_KEY_PREVIOUS` (optional key rotation support)
- `BOOTSTRAP_ADMIN_USERNAME` (optional)
- `BOOTSTRAP_ADMIN_PASSWORD` (optional)
- `LOG_LEVEL` (optional)
- `SHOW_CONSOLE_SOURCE` (optional)

### Runtime Cache / Config Keys

Managed via `app_settings` and admin config API:

- `PROMPTMAN_CACHE_ENABLED`
- `PROMPTMAN_CACHE_MAX_ENTRIES`
- `PROMPTMAN_CACHE_PERSISTENCE_ENABLED`
- `PROMPTMAN_CACHE_PERSISTENCE_LIMIT`
- `PROMPTMAN_RUNTIME_CACHE_BACKEND`
- `PROMPTMAN_RUNTIME_CACHE_URL`
- `PROMPTMAN_RUNTIME_CACHE_NAMESPACE`
- `PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL`
- `PROMPTMAN_PLUGINS_SIGNED_ONLY`

### Simulation Test Keys

Managed via `app_settings` and admin config API:

- `TEST_LLM_PROVIDER`
- `TEST_LLM_MODEL`
- `TEST_LLM_BASE_URL`
- `TEST_LLM_API_TOKEN`
- `TEST_LLM_TIMEOUT_SECONDS`
- `TEST_LLM_USE_OPTIMIZER_FALLBACK`
- `TEST_RAG_ENABLED`
- `TEST_RAG_SOURCE_PATH`
- `TEST_RAG_TOP_K`

Notes:

- `TEST_LLM_*` are used by prompt-version simulation test runs.
- If `TEST_LLM_USE_OPTIMIZER_FALLBACK=true`, missing test LLM fields fall back to `OPTIMIZER_*`.
- RAG chunks are loaded from `TEST_RAG_SOURCE_PATH` and appended to the test prompt when enabled.

## Simulation Testing (Logs + RAG + Security)

PromptMan now includes a simulation runner similar to `PromptOrchestrator` style logs:

- Script: `simulations/conversation_simulation_test.py`
- Log file: `simulations/conversation_simulation_test.log`
- Default RAG knowledge file: `simulations/rag_knowledge.md`

Run one simulation cycle:

```powershell
.\.venv\Scripts\python.exe .\simulations\conversation_simulation_test.py --chain-id 51 --version-no 5 --cycles 1
```

Reset database and seed explicit test data before simulation:

```powershell
.\.venv\Scripts\python.exe .\simulations\conversation_simulation_test.py --seed --reset-db --scale small --chain-id 1 --version-no 1 --cycles 3
```

Direct seed command (without simulation):

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo_data.py --reset-db --scale small
```

More varied demo data for analysis-heavy runs:

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo_data.py --reset-db --scale large
```

The seeded demo set is intentionally mixed:

- threads have different lengths, and most are longer than a simple 2-question / 2-answer exchange
- prompt versions are written to produce different analysis signals, including tokens, reliability, cacheability, and selected security markers

Complex simulation example with seeded data and repeated analysis cycles:

```powershell
.\.venv\Scripts\python.exe .\simulations\conversation_simulation_test.py --seed --reset-db --scale large --chain-id 1 --version-no 1 --cycles 5
```

What is logged per cycle:

- Full prompt
- Prompt with RAG context
- Fixed / semi-fixed / variable prompt parts
- LLM snapshot (provider/model/backend/base_url)
- LLM response and errors
- Token usage
- Security metrics (`injection_risk`, `contradiction_risk`, `ambiguity_risk`, markers)
- Prompt analysis metrics

## Runtime Cache Backends

PromptMan supports four runtime cache backend modes:

- `memory`
	- local in-process cache
- `redis`
	- external Redis via RESP
- `garnet`
	- external Garnet via RESP (same URL format and client path as Redis)
- `none`
	- disables runtime cache reads/writes

Implementation note:

- `redis` and `garnet` use the same RESP backend client (`redis` Python package).
- If external backend initialization fails, runtime cache falls back to `memory`.
- `PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL=true` forces `none` behavior regardless of backend name.

### Quick Config Examples

Set via environment variables before app start.

#### 1. Local in-memory cache (`memory`)

```powershell
$env:PROMPTMAN_RUNTIME_CACHE_BACKEND = "memory"
$env:PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL = "false"
uvicorn main:app --reload
```

#### 2. Redis cache (`redis`)

```powershell
$env:PROMPTMAN_RUNTIME_CACHE_BACKEND = "redis"
$env:PROMPTMAN_RUNTIME_CACHE_URL = "redis://127.0.0.1:6379/0"
$env:PROMPTMAN_RUNTIME_CACHE_NAMESPACE = "promptman"
$env:PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL = "false"
uvicorn main:app --reload
```

#### 3. Garnet cache (`garnet`)

```powershell
$env:PROMPTMAN_RUNTIME_CACHE_BACKEND = "garnet"
$env:PROMPTMAN_RUNTIME_CACHE_URL = "redis://127.0.0.1:6379/0"
$env:PROMPTMAN_RUNTIME_CACHE_NAMESPACE = "promptman"
$env:PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL = "false"
uvicorn main:app --reload
```

Use the same RESP URL scheme as Redis (`redis://host:port/db`).

#### 4. Disable runtime cache (`none`)

```powershell
$env:PROMPTMAN_RUNTIME_CACHE_BACKEND = "none"
$env:PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL = "true"
uvicorn main:app --reload
```

### Change Cache Backend At Runtime (Admin API)

You can switch backend without restart through admin config endpoints.

```text
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_BACKEND?value=redis
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_URL?value=redis://127.0.0.1:6379/0
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_NAMESPACE?value=promptman
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL?value=false
```

Garnet runtime switch example:

```text
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_BACKEND?value=garnet
PUT /v1/admin/config/PROMPTMAN_RUNTIME_CACHE_URL?value=redis://127.0.0.1:6379/0
```

### Docker Compose Examples

Below are practical compose snippets for each runtime cache mode.

#### Redis + PromptMan

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      PROMPTMAN_RUNTIME_CACHE_BACKEND: redis
      PROMPTMAN_RUNTIME_CACHE_URL: redis://redis:6379/0
      PROMPTMAN_RUNTIME_CACHE_NAMESPACE: promptman
      PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL: "false"
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

#### Garnet + PromptMan

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      PROMPTMAN_RUNTIME_CACHE_BACKEND: garnet
      PROMPTMAN_RUNTIME_CACHE_URL: redis://garnet:6379/0
      PROMPTMAN_RUNTIME_CACHE_NAMESPACE: promptman
      PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL: "false"
    depends_on:
      - garnet

  garnet:
    image: ghcr.io/microsoft/garnet:latest
    ports:
      - "6379:6379"
```

#### Local In-Process Cache (Memory)

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      PROMPTMAN_RUNTIME_CACHE_BACKEND: memory
      PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL: "false"
```

#### No Runtime Cache

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      PROMPTMAN_RUNTIME_CACHE_BACKEND: none
      PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL: "true"
```

Quick start for any snippet:

```powershell
docker compose up --build
```

## Database Notes

- Current active domain model includes users, roles, projects, project access, conversations, and imports.
- Legacy prompt/optimizer tables were removed by Alembic migration `20260603_0015`.

## Verification Snapshot (2026-06-03)

Automated tests run from project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Latest result:

- 17 passed, 2 skipped

## Load & Stress Benchmark (PostgreSQL Memory vs Redis)

The benchmark script was run twice on 2026-06-03:

```powershell
.\.venv\Scripts\python.exe scripts\run_db_concurrency_benchmark.py
```

Scenario profile:

- `load_low`: 16 concurrent users, 12s
- `load_high`: 48 concurrent users, 12s
- `stress`: 96 concurrent users, 16s

Run A (generated at UTC 14:18:09):

| Mode | Scenario | Users | RPS | P95 (ms) | Failure % |
|---|---|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 169.67 | 131.67 | 0.0 |
| postgres_memory | load_high | 48 | 164.43 | 387.18 | 0.0 |
| postgres_memory | stress | 96 | 157.30 | 811.67 | 0.0 |
| postgres_redis | load_low | 16 | 174.05 | 129.57 | 0.0 |
| postgres_redis | load_high | 48 | 164.63 | 386.39 | 0.05 |
| postgres_redis | stress | 96 | 40.80 | 10002.16 | 15.79 |

Run B (generated at UTC 14:20:33):

| Mode | Scenario | Users | RPS | P95 (ms) | Failure % |
|---|---|---:|---:|---:|---:|
| postgres_memory | load_low | 16 | 171.40 | 130.87 | 0.0 |
| postgres_memory | load_high | 48 | 165.88 | 386.56 | 0.0 |
| postgres_memory | stress | 96 | 17.90 | 10014.31 | 49.87 |
| postgres_redis | load_low | 16 | 173.07 | 130.18 | 0.0 |
| postgres_redis | load_high | 48 | 164.99 | 383.78 | 0.0 |
| postgres_redis | stress | 96 | 27.30 | 10013.92 | 30.52 |

Conclusions:

- For low/high load scenarios, `memory` and `redis` are nearly identical.
- In `stress`, both modes showed instability across runs (timeouts and higher failure rate), which indicates a broader system bottleneck, not only runtime cache backend behavior.
- Based on current data, switching to Garnet is optional and should be treated as a later optimization after stabilizing stress-path bottlenecks (DB capacity, worker model, and request concurrency profile).

Detailed artifacts:

- Run A report: `loadtests/results/cache_compare/concurrency_20260603_171630/db_concurrency_report.md`
- Run A JSON: `loadtests/results/cache_compare/concurrency_20260603_171630/db_concurrency_results.json`
- Run B report: `loadtests/results/cache_compare/concurrency_20260603_171853/db_concurrency_report.md`
- Run B JSON: `loadtests/results/cache_compare/concurrency_20260603_171853/db_concurrency_results.json`

## Plugins

See `plugins/README.md` for plugin lifecycle, endpoint contracts, signatures, and modal support.

## Development

```powershell
ruff check .
ruff format .
mypy .
```

## License

MIT. See `LICENSE`.
