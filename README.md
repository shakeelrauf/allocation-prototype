# Newton 3.0
Demo URL https://www.loom.com/share/fe1813ab3d1940a1890a9c8107c91d29
Behaviour scoring and space-allocation prototype: FastAPI backend, React UI, SQLite persistence, optional LLM explanations (Ollama-compatible).

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
python run_local.py --reload
```

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

## Layout

| Path | Role |
|------|------|
| `api.py` | FastAPI app and routes |
| `ui/` | React (Vite) frontend |
| `docker-compose.yml` | App + Ollama + model pull |
| `DOCKER.md` | Docker-only reference |
