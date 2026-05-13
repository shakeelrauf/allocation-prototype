# Docker: full stack with one command

One Compose file runs:

- **Frontend** — production React build served by FastAPI from the same origin (port **8765**)
- **Backend** — FastAPI + SQLite on a named volume
- **LLM** — Ollama, with an automatic **wait + model pull** before Newton starts

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose **v2.20+** (`docker compose`). The stack uses `depends_on` **conditions** (`service_healthy`, `service_completed_successfully`).

## Start everything

From the `newton3` directory:

```bash
docker compose up --build
```

**First run:** after Ollama becomes healthy, the `ollama-pull` step downloads `NEWTON3_LLM_MODEL` (default **`llama3.2`**) into the `ollama_models` volume. That can take several minutes depending on bandwidth; Newton starts on **8765** only after the pull finishes. Later runs are quick because the pull is idempotent.

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)**.

Examples on the same host:

- UI + API: `http://127.0.0.1:8765`
- Fairness report JSON: `http://127.0.0.1:8765/api/reports/fairness?window_days=30&format=json`
- Ollama (optional host access): `http://127.0.0.1:11434`

Detached:

```bash
docker compose up --build -d
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## Change the LLM model

Set **`NEWTON3_LLM_MODEL`** for **both** the pull step and the app (Compose wires the same default):

```bash
export NEWTON3_LLM_MODEL=phi3
docker compose up --build
```

Or add a `.env` file next to `docker-compose.yml`:

```env
NEWTON3_LLM_MODEL=phi3
```

## Why `explain-llm` is slower in Docker than on the host

- **No GPU in the container path** — On macOS, Ollama outside Docker can use **Metal**. Ollama *inside* Docker Desktop or Colima usually runs on **CPU only**, so each reply is much slower. The browser stays on “sending” until the model finishes (Newton waits for Ollama with `NEWTON3_LLM_TIMEOUT`, default 120s).
- **Large prompts** — The API sends a **store snapshot** (events + allocation). Fewer lines = faster inference. Compose sets smaller defaults (`NEWTON3_LLM_SNAPSHOT_*`); override or raise them if you need more context.
- **Cold-loaded models** — First request after idle can load weights into memory. `NEWTON3_LLM_KEEP_ALIVE` (set in Compose) asks Ollama to keep the model resident between chats.

**Faster options:** use a smaller model (`NEWTON3_LLM_MODEL=tinyllama`), run **Ollama on the host** and point Newton at `http://host.docker.internal:11434/...`, or accept longer waits for big models on CPU.

### Ollama log lines you might see

| Log | Meaning |
|-----|--------|
| `load: printing all EOG tokens` / `<|eot_id|>` etc. | Normal **special-token** registration for the chat template (end-of-text / end-of-message). |
| `special tokens cache size = 256` and `print_info: max token length = 256` | **llama.cpp** internal sizing for special-token / piece caches. **Not** “only 256 tokens of context” — your run also shows `n_ctx_train = 131072` for this checkpoint. Reply length is still governed by **`NEWTON3_LLM_MAX_TOKENS`**. |
| `print_info: model type = 3B` / `general.name = Llama 3.2 3B Instruct` | Which **GGUF** is loaded (here the **3B** instruct variant, ~2 GB on CPU in Docker). |
| `load_tensors` / `CPU model buffer size ≈ … MiB` | Weights are being **mapped or copied into RAM** on CPU. First load after pull can take **minutes**. |
| `waiting for server … "llm server loading model"` | The **inference runner** is starting after load; normal before the first completion. |
| `127.0.0.1` `HEAD "/"` / `GET "/api/tags"` | **Docker healthchecks** (and similar probes) hitting the API inside the Ollama container. |

## Data persistence

| Volume          | Purpose |
|-----------------|--------|
| `newton_data`   | SQLite at `/data/newton3.db` in the `newton` container |
| `ollama_models` | Ollama weights under `/root/.ollama` |

Remove data (DB + models):

```bash
docker compose down -v
```

## Environment variables (`newton` service)

| Variable            | Default in compose | Meaning |
|---------------------|--------------------|---------|
| `NEWTON3_DB_PATH`   | `/data/newton3.db` | SQLite path |
| `NEWTON3_LLM_URL`   | `http://ollama:11434/v1/chat/completions` | OpenAI-compatible chat URL |
| `NEWTON3_LLM_MODEL` | `llama3.2` (overridable via host `.env`) | Model name for URL + pull script |
| `NEWTON3_LLM_SNAPSHOT_EVENTS_LOOKBACK` | `72` in compose | How many recent events the LLM snapshot may scan (smaller = faster) |
| `NEWTON3_LLM_SNAPSHOT_MAX_EVENT_LINES` | `35` in compose | Max event lines included in the snapshot |
| `NEWTON3_LLM_KEEP_ALIVE` | `15m` in compose | Ollama `keep_alive` so the model is not unloaded immediately after each reply |
| `NEWTON3_LLM_MAX_TOKENS` | `320` in compose | Cap on generated tokens (`64`–`4096` clamped in code) |
| `NEWTON3_LLM_TIMEOUT` | `120` (seconds) | Max wait for Ollama per request |
| `NEWTON3_LLM_NUM_CTX` | *(unset)* | Optional Ollama `options.num_ctx` (e.g. `2048`) to cap context work if prompts fit |
| `NEWTON3_UI_DIST`   | *(unset)*          | Override UI static directory (must contain `index.html`) |

## Ollama only (legacy)

**`docker-compose.llm.yml`** still runs Ollama alone for native Python workflows. Prefer **`docker-compose.yml`** for the full stack.

## API-only image (no Compose)

If Ollama runs elsewhere:

```bash
docker build -t newton3 .
docker run --rm -p 8765:8765 \
  -e NEWTON3_DB_PATH=/data/newton3.db \
  -e NEWTON3_LLM_URL=http://host.docker.internal:11434/v1/chat/completions \
  -e NEWTON3_LLM_MODEL=llama3.2 \
  -v newton3_data:/data \
  newton3
```

On Linux you may need `--add-host=host.docker.internal:host-gateway`.

## Rebuild after code changes

```bash
docker compose build --no-cache newton && docker compose up -d
```
