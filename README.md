# Newton 3.0

**Hackathon submission:** behaviour-driven allocation for Wayleadr 2.0 (AWS-native Phase 1 + working demo).

| Resource | Link |
|----------|------|
| AI / hackathon context | [CLAUDE.md](./CLAUDE.md) |
| Demo video | [Loom — CSV import & full UI walkthrough](https://www.loom.com/share/d7478cd7208a498cba2b2272b6b4a42c) |
| Internal repo | https://github.com/wayleadr-internal/shakeel-allocation-prototype |
| Architecture | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| AWS serverless review | [docs/AWS_SERVERLESS_ARCHITECTURE.md](./docs/AWS_SERVERLESS_ARCHITECTURE.md) |
| Reviewer pack | [docs/SUBMISSION.md](./docs/SUBMISSION.md) |
| **AWS deploy** | [docs/DEPLOY_AWS.md](./docs/DEPLOY_AWS.md) |

Behaviour scoring and space-allocation: **shared Python engines**, **FastAPI + React demo** (SQLite), **AWS SAM stack** (Lambda + DynamoDB + EventBridge), optional LLM explanations (Ollama locally, Amazon Bedrock on AWS).

## Project structure

The repo has **two layers**: a Python package with all product logic, and thin AWS adapters. They are not duplicates — local and cloud both call the same `newton3` code.

```text
office_projects/newton3/          ← repo root (entrypoints, docs, infra only)
├── newton3/                      ← Python package — scoring, API, stores (the “app”)
│   ├── domain/                   ← rules: scoring, allocation, events, fairness
│   ├── persistence/              ← SQLite (local) + DynamoDB (AWS)
│   ├── services/                 ← LLM explain, SQS events, cohort import
│   ├── api/app.py                ← FastAPI routes (React UI talks here)
│   ├── cli.py                    ← demo / stream / local-llm commands
│   └── local_ollama.py           ← auto-start Ollama for run_local.py
├── aws/handlers/                 ← Lambda entrypoints only (no business logic)
│   ├── console.py                ← full API via Mangum + DynamoDB
│   ├── scoring.py                ← SQS worker for behaviour events
│   ├── allocation.py             ← rank / allocate / shadow / explain
│   └── api.py                    ← fast WayID behaviour-score reads
├── run_local.py                  ← local server: Uvicorn + SQLite + Ollama
├── cli.py                        ← shim → python -m newton3.cli
├── ui/                           ← React operator console (Vite)
├── infra/sam/                    ← CloudFormation / SAM deploy
├── tests/                        ← pytest
└── scripts/                      ← migration, cohort import
```

| Layer | What it is | Runs as |
|-------|------------|---------|
| **`newton3/`** | Behaviour engine, persistence, HTTP API, LLM service | Imported everywhere |
| **`aws/handlers/`** | Translates Lambda/API Gateway/SQS events into `newton3` calls | AWS Lambda only |
| **Repo root** | `run_local.py`, Docker, docs, fixtures — not application modules | Your machine / CI |

**Local:** `run_local.py` → `newton3.api.app` → **SQLite** → optional **Ollama** for Explain & AI.

**AWS:** API Gateway → Lambdas in `aws/handlers/` → same `newton3` modules → **DynamoDB** + **Bedrock** (Console Lambda) + **SQS** (scoring).

Put new features under `newton3/domain/` or `newton3/services/` — keep `aws/handlers/*.py` thin (env + one function call). Full detail: [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md).

**Demo:** [Loom recording](https://www.loom.com/share/d7478cd7208a498cba2b2272b6b4a42c) — upload Metabase CSV in the UI, then events, parking allocation, explain & AI, insights, and fairness tabs.

**Imports:**

```python
from newton3.domain.event_processor import process_event
from newton3.persistence.store_factory import make_store
from newton3.api.app import create_app
```

## Run everything (recommended)

Requires [Docker Compose](https://docs.docker.com/compose/) v2.20+.

From this directory:

```bash
docker compose up --build
```

Then open **http://127.0.0.1:8765** (API and built UI on one port). The stack starts Ollama, pulls the default LLM (`llama3.2` unless you set `NEWTON3_LLM_MODEL`), then starts the app. The first model download can take a while.

More detail (changing models, volumes, troubleshooting): **[DOCKER.md](./DOCKER.md)**.

## Run locally (development)

**Python 3.11+**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
# or: pip install -e ".[api]"
python run_local.py --reload   # starts Ollama automatically if installed
```

First time with LLM: `python run_local.py --reload --ollama-pull` (downloads `llama3.2`), or install Ollama from https://ollama.com/download.

**UI** (Vite dev server; proxies `/api` to the backend, default port 8765):

```bash
cd ui && npm install && npm run dev
```

Optional LLM without Docker: see `scripts/setup_local_llm.sh` and `docker-compose.llm.yml`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## AWS (hybrid serverless)

```bash
cd infra/sam && sam build && sam deploy --guided
# Console (Mangum) + read/allocation Lambdas + SQS scoring — see docs/DEPLOY_AWS.md
```

Local stays SQLite: `python run_local.py --reload --db ./data/newton3.db`

## Metabase import (one step, no CSV in repo)

Upload **Algorithm User Complaints - Metabase.csv** from your machine:

- **UI:** Dashboard or Reports → **Select CSV file** (import runs automatically)
- **CLI (optional, same single step):**

```bash
python scripts/import_fairness_cohort_sheet.py \
  --input "/path/to/Algorithm User Complaints - Metabase.csv" \
  --db ./data/newton3.db
```

Details: [docs/FAIRNESS_COMPLAINT_COHORT.md](./docs/FAIRNESS_COMPLAINT_COHORT.md)

## Migration (your own Rails CSV export)

Place `groups.csv`, `users.csv`, `events.csv` under `fixtures/migration/` (see README there), then:

```bash
python scripts/migrate_from_rails_export.py --dir fixtures/migration --dry-run
python scripts/migrate_from_rails_export.py --backend dynamodb --stage dev --dir fixtures/migration
```

## Key docs

| Doc | Contents |
|-----|----------|
| [CLAUDE.md](./CLAUDE.md) | Hackathon goals, scoring rules, event model |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Phase 1 design, dual runtime, DynamoDB |
| [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) | Every package folder explained |
| [docs/DEPLOY_AWS.md](docs/DEPLOY_AWS.md) | SAM deploy, Bedrock, smoke tests |
| [docs/SUBMISSION.md](docs/SUBMISSION.md) | Reviewer checklist |
| [docs/SLIDES_FOR_PPT.md](docs/SLIDES_FOR_PPT.md) | Full slide deck source (give to Claude for PPT) |
