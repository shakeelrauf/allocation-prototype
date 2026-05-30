# Newton 3 — project structure

The repo root holds **entrypoints, docs, and infra** only. Application code lives in the **`newton3/` Python package**.

## Repository root

| Path | Purpose |
|------|---------|
| [CLAUDE.md](../CLAUDE.md) | Hackathon context for AI assistants |
| [README.md](../README.md) | Quick start |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Phase 1 + AWS mapping |
| [run_local.py](../run_local.py) | Local FastAPI + SQLite (`uvicorn`) |
| [cli.py](../cli.py) | CLI shim → `newton3.cli` |
| [pyproject.toml](../pyproject.toml) | Package metadata + pytest path |
| [requirements-dev.txt](../requirements-dev.txt) | Local dev deps |
| [requirements-aws.txt](../requirements-aws.txt) | Lambda build (SAM) |
| [requirements-docker.txt](../requirements-docker.txt) | Docker image |
| [Dockerfile](../Dockerfile) | App + built UI |
| [docker-compose.yml](../docker-compose.yml) | Ollama + Newton |
| `data/` | Local SQLite (gitignored) |
| `fixtures/` | Migration + cohort sample data |
| `scripts/` | Migration, cohort import |
| `tests/` | Pytest |
| `ui/` | React (Vite) operator console |
| `aws/handlers/` | Lambda handlers (thin) |
| `infra/sam/` | AWS SAM template |

## Python package: `newton3/`

### `newton3/domain/` — core rules (hackathon engine)

| Module | Responsibility |
|--------|----------------|
| `models.py` | `UserProfile`, `BehaviorEvent`, tiers, score state |
| `scoring_engine.py` | Penalties, rewards, decay, caps |
| `allocation_engine.py` | Rank, allocate, explain |
| `event_processor.py` | Route events → scoring |
| `shadow_engine.py` | Legacy vs Newton compare |
| `tenant_weights.py` | Per-group penalty/reward overrides |
| `fairness.py` | Complaint cohort analysis |
| `insights.py` | Anomaly / risk heuristics |

### `newton3/persistence/` — storage adapters

| Module | Responsibility |
|--------|----------------|
| `store.py` | `ScoreStore` protocol, `InMemoryStore` |
| `sqlite_store.py` | Local / Docker SQLite |
| `dynamodb_store.py` | AWS DynamoDB (5 tables) |
| `store_factory.py` | `NEWTON3_STORE=sqlite\|dynamodb` |

### `newton3/services/` — application layer

| Module | Responsibility |
|--------|----------------|
| `events_queue.py` | SQS enqueue + batch worker parsing |
| `cohort_import.py` | Metabase CSV → store |
| `llm_explain.py` | Template + Ollama (local) + **Bedrock Converse** (AWS) |

### `newton3/api/`

| Module | Responsibility |
|--------|----------------|
| `app.py` | FastAPI routes, static UI mount |

### Other package modules

| Module | Responsibility |
|--------|----------------|
| `paths.py` | `REPO_ROOT` for fixtures / `ui/dist` |
| `observability.py` | Structured logging hooks |
| `cli.py` | `demo`, `event`, `stream`, `local-llm` commands |

## AWS (serverless)

See [DEPLOY_AWS.md](./DEPLOY_AWS.md) and [AWS_SERVERLESS_ARCHITECTURE.md](./AWS_SERVERLESS_ARCHITECTURE.md).

- **Console Lambda** — Mangum → `newton3.api.app:create_app()`
- **Scoring Lambda** — SQS → `events_queue` + `event_processor`
- **Read / Allocation Lambdas** — hot paths
- **EventBridge → SQS** — external producers

## Local development

```bash
pip install -r requirements-dev.txt
python run_local.py --reload --db ./data/newton3.db
cd ui && npm run dev
pytest
```

## Import convention

Always use package imports:

```python
from newton3.domain.event_processor import process_event
from newton3.persistence.store_factory import make_store
from newton3.api.app import create_app
```

Do not add new top-level `.py` modules on the repo root.
