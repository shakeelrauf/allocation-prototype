# syntax=docker/dockerfile:1
# Build React UI, then run FastAPI + static SPA on one port.

FROM node:22-alpine AS ui-build
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY allocation_engine.py api.py cli.py event_processor.py insights.py \
    llm_explain.py models.py observability.py run_local.py scoring_engine.py \
    shadow_engine.py sqlite_store.py store.py tenant_weights.py ./

COPY --from=ui-build /ui/dist ./ui/dist

RUN mkdir -p /data
ENV NEWTON3_DB_PATH=/data/newton3.db

EXPOSE 8765
CMD ["sh", "-c", "mkdir -p /data && exec uvicorn api:app --host 0.0.0.0 --port 8765"]
