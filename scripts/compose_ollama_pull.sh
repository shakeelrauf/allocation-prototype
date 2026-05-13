#!/bin/sh
# Run inside ollama/ollama image as a one-shot service: wait for server, then pull model.
set -e
MODEL="${NEWTON3_LLM_MODEL:-llama3.2}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"

echo "compose_ollama_pull: waiting for Ollama at ${OLLAMA_HOST} ..."
i=0
while [ "$i" -lt 180 ]; do
  if ollama list >/dev/null 2>&1; then
    echo "compose_ollama_pull: Ollama is ready."
    break
  fi
  i=$((i + 1))
  sleep 1
done
if ! ollama list >/dev/null 2>&1; then
  echo "compose_ollama_pull: Ollama did not become ready in time." >&2
  exit 1
fi

echo "compose_ollama_pull: pulling model '${MODEL}' (idempotent; first run may take several minutes)..."
ollama pull "${MODEL}"
echo "compose_ollama_pull: done."
